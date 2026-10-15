#include "i2s_microphone.h"
#include <string.h>
#include "esp_log.h"
#include "esp_check.h"
#include "esp_attr.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"

static const char *TAG = "i2s_microphone";

#define I2S_MIC_MIN_SAMPLE_RATE     (8000)
#define I2S_MIC_MAX_SAMPLE_RATE     (50000)

static i2s_chan_handle_t s_rx_handle = NULL;
static i2s_chan_handle_t s_third_handle = NULL;
static bool s_is_initialized = false;
static volatile uint32_t s_dma_completed_blocks = 0;
static volatile uint32_t s_dma_completed_frames = 0;
static volatile uint32_t s_dma_overflow_events = 0;
static volatile uint32_t s_dma_overflow_frames = 0;
static volatile uint32_t s_third_blocks = 0;
static volatile uint32_t s_third_frames = 0;
static volatile uint32_t s_third_overflows = 0;
static volatile uint32_t s_third_lost_frames = 0;
static portMUX_TYPE s_dma_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile bool s_latch_requested = false;
static volatile uint32_t s_latch_generation = 0;
static volatile uint32_t s_latch_first_block = 0;
static int32_t s_previous_left = 0;
static int32_t s_previous_right = 0;

static bool IRAM_ATTR i2s_mic_on_recv(i2s_chan_handle_t handle,
                                      i2s_event_data_t *event, void *user_ctx)
{
    (void)handle;
    portENTER_CRITICAL_ISR(&s_dma_lock);
    if (user_ctx != NULL) {
        s_third_blocks++;
        s_third_frames += (uint32_t)(event->size / (2 * sizeof(int32_t)));
        portEXIT_CRITICAL_ISR(&s_dma_lock);
        return false;
    }
    s_dma_completed_blocks++;
    s_dma_completed_frames += (uint32_t)(event->size / (2 * sizeof(int32_t)));
    if (s_latch_requested) {
        // The completed block has ended; frame zero of the next block is the
        // first frame eligible for the requested processing transition.
        s_latch_first_block = s_dma_completed_blocks + 1;
        s_latch_generation++;
        s_latch_requested = false;
    }
    portEXIT_CRITICAL_ISR(&s_dma_lock);
    return false;
}

static bool IRAM_ATTR i2s_mic_on_overflow(i2s_chan_handle_t handle,
                                          i2s_event_data_t *event, void *user_ctx)
{
    (void)handle;
    portENTER_CRITICAL_ISR(&s_dma_lock);
    if (user_ctx != NULL) {
        s_third_overflows++;
        s_third_lost_frames += (uint32_t)(event->size / (2 * sizeof(int32_t)));
        portEXIT_CRITICAL_ISR(&s_dma_lock);
        return false;
    }
    s_dma_overflow_events++;
    s_dma_overflow_frames += (uint32_t)(event->size / (2 * sizeof(int32_t)));
    portEXIT_CRITICAL_ISR(&s_dma_lock);
    return false;
}

esp_err_t i2s_mic_init(const i2s_mic_config_t *config)
{
    // Apply defaults if no config provided or fields unset
    i2s_mic_config_t cfg;
    if (config == NULL) {
        cfg.sample_rate = I2S_MIC_DEFAULT_SAMPLE_RATE;
        cfg.sck_pin     = I2S_MIC_DEFAULT_SCK_PIN;
        cfg.ws_pin      = I2S_MIC_DEFAULT_WS_PIN;
        cfg.sd_pin      = I2S_MIC_DEFAULT_SD_PIN;
        cfg.i2s_port    = I2S_NUM_0;
    } else {
        cfg = *config;
        if (cfg.sample_rate == 0) {
            cfg.sample_rate = I2S_MIC_DEFAULT_SAMPLE_RATE;
        }
    }

    // Validate parameters against INMP441 hardware specifications
    if (cfg.sample_rate < I2S_MIC_MIN_SAMPLE_RATE || cfg.sample_rate > I2S_MIC_MAX_SAMPLE_RATE) {
        ESP_LOGE(TAG, "Sample rate %lu Hz out of range [%d, %d] Hz",
                 (unsigned long)cfg.sample_rate, I2S_MIC_MIN_SAMPLE_RATE, I2S_MIC_MAX_SAMPLE_RATE);
        return ESP_ERR_INVALID_ARG;
    }

    if (!GPIO_IS_VALID_OUTPUT_GPIO(cfg.sck_pin) ||
        !GPIO_IS_VALID_OUTPUT_GPIO(cfg.ws_pin) ||
        !GPIO_IS_VALID_GPIO(cfg.sd_pin) ||
        cfg.sck_pin == cfg.ws_pin || cfg.sck_pin == cfg.sd_pin || cfg.ws_pin == cfg.sd_pin ||
        (cfg.i2s_port != I2S_NUM_0 && cfg.i2s_port != I2S_NUM_1)) {
        ESP_LOGE(TAG, "Invalid I2S pins or port: SCK=%d, WS=%d, SD=%d, port=%d",
                 cfg.sck_pin, cfg.ws_pin, cfg.sd_pin, (int)cfg.i2s_port);
        return ESP_ERR_INVALID_ARG;
    }

    // If previously initialized, deinitialize first to prevent resource leak
    if (s_is_initialized || s_rx_handle != NULL || s_third_handle != NULL) {
        ESP_LOGW(TAG, "Driver already initialized; re-initializing...");
        i2s_mic_deinit();
    }
    portENTER_CRITICAL(&s_dma_lock);
    s_dma_completed_blocks = 0;
    s_dma_completed_frames = 0;
    s_dma_overflow_events = 0;
    s_dma_overflow_frames = 0;
    s_third_blocks = s_third_frames = 0;
    s_third_overflows = s_third_lost_frames = 0;
    s_latch_requested = false;
    s_latch_generation = 0;
    s_latch_first_block = 0;
    portEXIT_CRITICAL(&s_dma_lock);
    s_previous_left = s_previous_right = 0;

    ESP_LOGI(TAG, "Initializing INMP441 I2S: rate=%lu Hz, SCK=%d, WS=%d, SD=%d, port=%d",
             (unsigned long)cfg.sample_rate, cfg.sck_pin, cfg.ws_pin, cfg.sd_pin, (int)cfg.i2s_port);

    // 1. Channel allocation with I2S_MIC_DMA_DESC_NUM x 240 DMA frames
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(cfg.i2s_port, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = I2S_MIC_DMA_DESC_NUM;
    chan_cfg.dma_frame_num = I2S_MIC_DMA_FRAME_NUM;
    chan_cfg.auto_clear_after_cb = false;
    chan_cfg.auto_clear_before_cb = false;
    chan_cfg.allow_pd = false;
    chan_cfg.intr_priority = 0;
    chan_cfg.tx_destination = I2S_DESTINATION_DMA;
    chan_cfg.rx_destination = I2S_DESTINATION_DMA;

    esp_err_t ret = i2s_new_channel(&chan_cfg, NULL, &s_rx_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to allocate I2S channel: %s", esp_err_to_name(ret));
        return ret;
    }

    // 2. Capture 32-bit stereo DMA words. INMP441's 24 data bits occupy bits [31:8].
    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(cfg.sample_rate),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = (gpio_num_t)cfg.sck_pin,
            .ws   = (gpio_num_t)cfg.ws_pin,
            .dout = I2S_GPIO_UNUSED,
            .din  = (gpio_num_t)cfg.sd_pin,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv   = false,
            },
        },
    };

    // Explicit hardware timing overrides for INMP441
    std_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
    std_cfg.slot_cfg.slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT; // 32 BCLK ticks/slot (64 per frame)
    std_cfg.slot_cfg.ws_width = 32;                             // 32-cycle WS pulse
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_BOTH;             // Both Left (Mic 1) and Right (Mic 2) slots enabled
    std_cfg.slot_cfg.ws_pol = false;                            // Philips standard: WS is LOW for Left, HIGH for Right
    std_cfg.slot_cfg.bit_shift = true;                          // 1 BCLK delay after WS transition
    std_cfg.slot_cfg.msb_right = false;                         // Required for >16-bit words on classic ESP32

    // Configure the slave GPIO inputs first. The master's GPIO setup must
    // happen last so the shared BCLK/WS pins remain driven by I2S0.
    i2s_chan_config_t third_chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_1, I2S_ROLE_SLAVE);
    third_chan_cfg.dma_desc_num = I2S_MIC_DMA_DESC_NUM;
    third_chan_cfg.dma_frame_num = I2S_MIC_DMA_FRAME_NUM;
    ret = i2s_new_channel(&third_chan_cfg, NULL, &s_third_handle);
    if (ret != ESP_OK) goto third_failed;
    i2s_std_config_t third_cfg = std_cfg;
    third_cfg.gpio_cfg.din = (gpio_num_t)I2S_MIC_THIRD_SD_PIN;
    ret = i2s_channel_init_std_mode(s_third_handle, &third_cfg);
    if (ret != ESP_OK) goto third_failed;
    ret = gpio_set_pull_mode((gpio_num_t)I2S_MIC_THIRD_SD_PIN, GPIO_PULLDOWN_ONLY);
    if (ret != ESP_OK) goto third_failed;

    ret = i2s_channel_init_std_mode(s_rx_handle, &std_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init I2S standard mode: %s", esp_err_to_name(ret));
        goto third_failed;
    }

    // Enable internal pull-down on SD pin to prevent bus floating during High-Z cycles
    ret = gpio_set_pull_mode((gpio_num_t)cfg.sd_pin, GPIO_PULLDOWN_ONLY);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure SD pull-down: %s", esp_err_to_name(ret));
        goto third_failed;
    }

    const i2s_event_callbacks_t callbacks = {
        .on_recv = i2s_mic_on_recv,
        .on_recv_q_ovf = i2s_mic_on_overflow,
    };
    ret = i2s_channel_register_event_callback(s_rx_handle, &callbacks, NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register DMA callbacks: %s", esp_err_to_name(ret));
        goto third_failed;
    }

    // I2S1 is a slave on the SAME BCLK/WS wires. Enable it before I2S0
    // starts the clocks so both DMA receivers see the first WS edge.
    ret = i2s_channel_register_event_callback(s_third_handle, &callbacks, s_third_handle);
    if (ret != ESP_OK) goto third_failed;
    ret = i2s_channel_enable(s_third_handle);
    if (ret != ESP_OK) goto third_failed;

    // 3. Enable channel (starts BCLK and WS generation and DMA reception)
    ret = i2s_channel_enable(s_rx_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enable I2S channel: %s", esp_err_to_name(ret));
        goto third_failed;
    }

    s_is_initialized = true;
    ESP_LOGI(TAG, "INMP441 I2S standard driver successfully initialized and running");
    return ESP_OK;
third_failed:
    ESP_LOGE(TAG, "I2S1/dual receiver setup failed: %s", esp_err_to_name(ret));
    i2s_mic_deinit();
    return ret;
}

void i2s_mic_get_dma_stats(i2s_mic_dma_stats_t *stats)
{
    if (stats == NULL) {
        return;
    }
    portENTER_CRITICAL(&s_dma_lock);
    stats->completed_blocks = s_dma_completed_blocks;
    stats->completed_frames = s_dma_completed_frames;
    stats->overflow_events = s_dma_overflow_events;
    stats->overflow_frames = s_dma_overflow_frames;
    portEXIT_CRITICAL(&s_dma_lock);
}

void i2s_mic_get_third_dma_stats(i2s_mic_dma_stats_t *stats)
{
    if (stats == NULL) return;
    portENTER_CRITICAL(&s_dma_lock);
    stats->completed_blocks = s_third_blocks;
    stats->completed_frames = s_third_frames;
    stats->overflow_events = s_third_overflows;
    stats->overflow_frames = s_third_lost_frames;
    portEXIT_CRITICAL(&s_dma_lock);
}

esp_err_t i2s_mic_read_third_samples(int32_t *third, size_t num_frames,
                                     size_t *frames_read, uint32_t timeout_ms)
{
    if (third == NULL || num_frames == 0 || num_frames > I2S_MIC_DMA_FRAME_NUM)
        return ESP_ERR_INVALID_ARG;
    if (!s_is_initialized || s_third_handle == NULL) return ESP_ERR_INVALID_STATE;
    static int32_t interleaved[I2S_MIC_DMA_FRAME_NUM * 2];
    size_t bytes_read = 0;
    esp_err_t ret = i2s_channel_read(s_third_handle, interleaved,
                        num_frames * 2 * sizeof(int32_t), &bytes_read, timeout_ms);
    size_t count = bytes_read / (2 * sizeof(int32_t));
    for (size_t i = 0; i < count; ++i)
        third[i] = i2s_mic_convert_sample(interleaved[2 * i]);
    if (frames_read != NULL) *frames_read = count;
    return ret;
}

uint32_t i2s_mic_request_frame_latch(void)
{
    if (!s_is_initialized) return 0;
    portENTER_CRITICAL(&s_dma_lock);
    s_latch_requested = true;
    uint32_t requested_generation = s_latch_generation + 1;
    portEXIT_CRITICAL(&s_dma_lock);
    return requested_generation;
}

void i2s_mic_get_frame_latch(i2s_mic_frame_latch_t *latch)
{
    if (latch == NULL) return;
    portENTER_CRITICAL(&s_dma_lock);
    latch->generation = s_latch_generation;
    latch->first_block = s_latch_first_block;
    portEXIT_CRITICAL(&s_dma_lock);
}

esp_err_t i2s_mic_read_raw(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms)
{
    if (dest == NULL || num_samples == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!s_is_initialized || s_rx_handle == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    size_t bytes_to_read = num_samples * sizeof(int32_t);
    size_t bytes_read = 0;

    esp_err_t ret = i2s_channel_read(s_rx_handle, dest, bytes_to_read, &bytes_read, timeout_ms);

    if (samples_read != NULL) {
        *samples_read = bytes_read / sizeof(int32_t);
    }

    return ret;
}

esp_err_t i2s_mic_read_samples(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms)
{
    size_t local_read = 0;
    esp_err_t ret = i2s_mic_read_raw(dest, num_samples, &local_read, timeout_ms);

    if (ret == ESP_OK || (ret == ESP_ERR_TIMEOUT && local_read > 0)) {
        for (size_t i = 0; i < local_read; i++) {
            dest[i] = i2s_mic_convert_sample(dest[i]);
        }
    }

    if (samples_read != NULL) {
        *samples_read = local_read;
    }

    return ret;
}

esp_err_t i2s_mic_read_stereo_samples(int32_t *left, int32_t *right, size_t num_frames, size_t *frames_read, uint32_t timeout_ms)
{
    if (left == NULL || right == NULL || num_frames == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!s_is_initialized || s_rx_handle == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    // Static buffer for interleaved DMA samples [L0, R0, L1, R1, ...]
    static int32_t s_interleaved[1024];
    size_t total_frames = 0;
    esp_err_t ret = ESP_OK;
    while (total_frames < num_frames) {
        size_t remaining = num_frames - total_frames;
        size_t chunk_frames = (remaining <= 512) ? remaining : 512;
        size_t bytes_read = 0;
        ret = i2s_channel_read(s_rx_handle, s_interleaved,
                               chunk_frames * 2 * sizeof(int32_t), &bytes_read, timeout_ms);
        size_t chunk_obtained = bytes_read / (2 * sizeof(int32_t));

        for (size_t i = 0; i < chunk_obtained; i++) {
            // One DMA stereo frame always contains both microphone slots.
            int32_t current_left = i2s_mic_convert_sample(s_interleaved[2 * i]);
            int32_t current_right = i2s_mic_convert_sample(s_interleaved[2 * i + 1]);
#if I2S_MIC_SKEW_FRAMES == 1
            left[total_frames + i] = s_previous_left;
            right[total_frames + i] = current_right;
#elif I2S_MIC_SKEW_FRAMES == -1
            left[total_frames + i] = current_left;
            right[total_frames + i] = s_previous_right;
#else
            left[total_frames + i] = current_left;
            right[total_frames + i] = current_right;
#endif
            s_previous_left = current_left;
            s_previous_right = current_right;
        }
        total_frames += chunk_obtained;
        if (ret != ESP_OK || chunk_obtained < chunk_frames) {
            break;
        }
    }

    if (frames_read != NULL) {
        *frames_read = total_frames;
    }

    return ret;
}

esp_err_t i2s_mic_deinit(void)
{
    if (!s_is_initialized && s_rx_handle == NULL && s_third_handle == NULL) {
        return ESP_OK; // Idempotent
    }

    ESP_LOGI(TAG, "Deinitializing I2S microphone driver...");

    esp_err_t ret = ESP_OK;
    if (s_third_handle != NULL) {
        i2s_channel_disable(s_third_handle);
        esp_err_t third_ret = i2s_del_channel(s_third_handle);
        if (third_ret != ESP_OK) ret = third_ret;
        s_third_handle = NULL;
    }
    if (s_rx_handle != NULL) {
        esp_err_t ret_disable = i2s_channel_disable(s_rx_handle);
        if (ret_disable != ESP_OK && ret_disable != ESP_ERR_INVALID_STATE) {
            ESP_LOGW(TAG, "i2s_channel_disable returned: %s", esp_err_to_name(ret_disable));
            ret = ret_disable;
        }

        esp_err_t ret_del = i2s_del_channel(s_rx_handle);
        if (ret_del != ESP_OK) {
            ESP_LOGE(TAG, "i2s_del_channel returned: %s", esp_err_to_name(ret_del));
            ret = ret_del;
        }
    }

    s_rx_handle = NULL;
    s_is_initialized = false;

    return ret;
}

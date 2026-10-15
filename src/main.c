#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "esp_timer.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "driver/uart_vfs.h"
#include "i2s_microphone.h"
#include "fft_tdoa.h"
#include "telemetry.h"

static const char *TAG = "main";
#define CAPTURE_FRAMES I2S_MIC_DMA_FRAME_NUM
#define WARMUP_BLOCKS 12
#define CALIBRATION_WINDOWS 20
#define CALIBRATION_MIN_R 0.95f
#define PHASE_MIN_CONFIDENCE 0.5f
#define PHASE_BINS (FFT_TDOA_SIZE / 2)

typedef enum { STATE_WARMUP, STATE_CALIBRATING, STATE_RUNNING } pipeline_state_t;
typedef enum { COMMAND_START, COMMAND_CAL, COMMAND_CLEAR } control_command_t;

static QueueHandle_t s_control_queue;
static bool s_cal_ready[PHASE_BINS];
static float s_cal_bias[3][PHASE_BINS];

#if I2S_MIC_DEFAULT_SAMPLE_RATE != FFT_TDOA_SAMPLE_RATE
#error "I2S sample rate and phase FFT sample rate must match"
#endif

// Keep DMA buffers off the FreeRTOS task stack.
static int32_t s_left_buf[CAPTURE_FRAMES];
static int32_t s_right_buf[CAPTURE_FRAMES];
static int32_t s_third_buf[CAPTURE_FRAMES];
static int32_t s_fft_left[FFT_TDOA_SIZE];
static int32_t s_fft_right[FFT_TDOA_SIZE];
static int32_t s_fft_third[FFT_TDOA_SIZE];

static float wrap_phase(float phase)
{
    const float pi = 3.14159265358979323846f;
    while (phase > pi) phase -= 2.0f * pi;
    while (phase < -pi) phase += 2.0f * pi;
    return phase;
}

typedef struct {
    float ux, uy, uz, r, azimuth_deg, elevation_deg;
} direction_t;

static direction_t phase_direction(const float phi[3], float frequency_hz)
{
    const float pi = 3.14159265358979323846f;
    float scale = FFT_TDOA_SPEED_OF_SOUND /
                  (2.0f * pi * frequency_hz * FFT_TDOA_MIC_DISTANCE);
    float ux = scale * (2.0f * phi[0] + phi[1] - phi[2]) / 3.0f;
    float uy = scale * (phi[1] + phi[2]) / sqrtf(3.0f);
    direction_t out = {.r = hypotf(ux, uy)};
    if (out.r > 1.0f) {
        ux /= out.r;
        uy /= out.r;
        out.uz = 0.0f;
    } else {
        out.uz = sqrtf(1.0f - ux * ux - uy * uy);
    }
    out.ux = ux;
    out.uy = uy;
    float azimuth = atan2f(uy, ux) * 180.0f / pi;
    out.azimuth_deg = azimuth < 0.0f ? azimuth + 360.0f : azimuth;
    out.elevation_deg = atan2f(out.uz, hypotf(ux, uy)) * 180.0f / pi;
    return out;
}

static void serial_control_task(void *pvParameters)
{
    (void)pvParameters;
    char line[32];
    while (1) {
        if (fgets(line, sizeof(line), stdin) == NULL) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }
        control_command_t command;
        if (strncmp(line, "START", 5) == 0) command = COMMAND_START;
        else if (strncmp(line, "CAL", 3) == 0) command = COMMAND_CAL;
        else if (strncmp(line, "CLEAR", 5) == 0) command = COMMAND_CLEAR;
        else {
            ESP_LOGW(TAG, "Unknown command; use START, CAL, or CLEAR");
            continue;
        }
        if (xQueueSend(s_control_queue, &command, pdMS_TO_TICKS(100)) != pdPASS) {
            ESP_LOGW(TAG, "Control command queue full");
        }
    }
}


static void phase_fft_3ch_self_test(void)
{
    const float pi = 3.14159265358979323846f;
    const float f = 187.5f; // Exact 48 kHz / 2048 FFT bin.
    const float ux = 0.3f, uy = 0.4f;
    const float phi21 = 2.0f * pi * f * FFT_TDOA_MIC_DISTANCE * ux /
                        FFT_TDOA_SPEED_OF_SOUND;
    const float phi31 = 2.0f * pi * f * FFT_TDOA_MIC_DISTANCE *
                        (ux / 2.0f + sqrtf(3.0f) * uy / 2.0f) /
                        FFT_TDOA_SPEED_OF_SOUND;
    for (int i = 0; i < FFT_TDOA_SIZE; ++i) {
        float t = 2.0f * pi * f * i / FFT_TDOA_SAMPLE_RATE;
        s_fft_left[i] = (int32_t)(100000.0f * sinf(t));
        s_fft_right[i] = (int32_t)(100000.0f * sinf(t + phi21));
        s_fft_third[i] = (int32_t)(100000.0f * sinf(t + phi31));
    }
    fft_phase_doa_result_3ch_t result;
    fft_phase_doa_process_3ch(s_fft_left, s_fft_right, s_fft_third, &result);
    const float uz = sqrtf(1.0f - ux * ux - uy * uy);
    const float expected_az = atan2f(uy, ux) * 180.0f / pi;
    const float expected_el = atan2f(uz, hypotf(ux, uy)) * 180.0f / pi;
    if (result.signal_active && fabsf(result.dominant_freq_hz - f) < 0.1f &&
        fabsf(result.azimuth_deg - expected_az) < 1.0f &&
        fabsf(result.elevation_deg - expected_el) < 1.0f) {
        ESP_LOGI(TAG, "Three-channel FFT phase self-test PASS: az=%.2f el=%.2f",
                 result.azimuth_deg, result.elevation_deg);
    } else {
        ESP_LOGE(TAG, "Three-channel FFT phase self-test FAIL: f=%.2f az=%.2f el=%.2f",
                 result.dominant_freq_hz, result.azimuth_deg, result.elevation_deg);
    }
}

static void audio_capture_task(void *pvParameters)
{
    (void)pvParameters;
    // Every read is one entire 240-frame DMA block. The ISR records the
    // sequence of the NEXT block; processing starts at that block's frame 0.
    pipeline_state_t state = STATE_WARMUP;
    pipeline_state_t pending_target = STATE_RUNNING;
    bool calibrate_after_warmup = false;
    uint32_t warmup_remaining = WARMUP_BLOCKS;
    uint32_t pending_latch_generation = 0;
    uint32_t read_blocks = 0;
    uint32_t dma_restarts = 0;
    uint32_t cumulative_dma_blocks = 0;
    uint32_t cumulative_overflows = 0;
    uint32_t cumulative_lost_frames = 0;
    uint32_t calibration_windows = 0;
    int calibration_bin = -1;
    int active_bin = -1;
    float calibration_cos_sum = 0.0f;
    float calibration_sin_sum = 0.0f;
    float calibration_cos3[2] = {0}, calibration_sin3[2] = {0};
    int64_t sum_left = 0;
    int64_t sum_right = 0;
    int64_t sum_third = 0;
    unsigned samples_in_point = 0;
    uint32_t read_timeouts = 0;
    uint32_t short_reads = 0;
    uint32_t read_errors = 0;
    uint32_t fft_windows = 0;
    uint32_t phase_windows = 0;
    uint32_t max_read_gap_us = 0;
    uint32_t max_fft_us = 0;
    uint64_t total_frames = 0;
    uint64_t frames_since_init = 0;
    uint64_t previous_total_frames = 0;
    size_t fft_fill = 0;
    int phase_bin = -1;
    float phase_cos_sum = 0.0f;
    float phase_sin_sum = 0.0f;
    float phase_cos3[2] = {0}, phase_sin3[2] = {0};
    float magnitude_left_sum = 0.0f;
    float magnitude_right_sum = 0.0f;
    float magnitude_third_sum = 0.0f;
    int64_t previous_read_us = 0;
    int64_t previous_report_us = esp_timer_get_time();
    uint32_t last_overflow_events = 0;
    uint32_t last_third_overflow_events = 0;
    uint32_t cumulative_third_blocks = 0;
    uint32_t cumulative_third_overflows = 0;
    uint32_t cumulative_third_lost = 0;
    uint64_t third_frames_since_init = 0;

    while (1) {
        control_command_t command;
        while (xQueueReceive(s_control_queue, &command, 0) == pdTRUE) {
            if (command == COMMAND_CLEAR) {
                memset(s_cal_ready, 0, sizeof(s_cal_ready));
                memset(s_cal_bias, 0, sizeof(s_cal_bias));
                ESP_LOGI(TAG, "All RAM phase baselines cleared");
            } else if (command == COMMAND_START) {
                state = STATE_WARMUP;
                warmup_remaining = WARMUP_BLOCKS;
                calibrate_after_warmup = false;
                pending_latch_generation = 0;
                calibration_windows = 0;
                fft_fill = 0;
                sum_left = sum_right = sum_third = 0;
                samples_in_point = 0;
                fft_windows = phase_windows = 0;
                phase_bin = -1;
                phase_cos_sum = phase_sin_sum = 0.0f;
                memset(phase_cos3, 0, sizeof(phase_cos3));
                memset(phase_sin3, 0, sizeof(phase_sin3));
                magnitude_left_sum = magnitude_right_sum = 0.0f;
                magnitude_third_sum = 0.0f;
                ESP_LOGI(TAG, "START: discarding %u complete DMA blocks", WARMUP_BLOCKS);
            } else if (state == STATE_WARMUP) {
                calibrate_after_warmup = true;
                ESP_LOGI(TAG, "CAL: will latch calibration after warmup");
            } else if (pending_latch_generation == 0) {
                pending_target = STATE_CALIBRATING;
                pending_latch_generation = i2s_mic_request_frame_latch();
                ESP_LOGI(TAG, "CAL: requested ISR latch generation %lu",
                         (unsigned long)pending_latch_generation);
            }
        }
        int64_t read_start_us = esp_timer_get_time();
        if (previous_read_us != 0 && read_start_us > previous_read_us) {
            uint32_t gap_us = (uint32_t)(read_start_us - previous_read_us);
            if (gap_us > max_read_gap_us) max_read_gap_us = gap_us;
        }
        previous_read_us = read_start_us;
        size_t frames_read = 0;
        esp_err_t err = i2s_mic_read_stereo_samples(s_left_buf, s_right_buf,
                                                    CAPTURE_FRAMES, &frames_read, 100);
        size_t third_frames_read = 0;
        esp_err_t third_err = i2s_mic_read_third_samples(s_third_buf,
                                      CAPTURE_FRAMES, &third_frames_read, 100);
        i2s_mic_dma_stats_t current_dma;
        i2s_mic_dma_stats_t third_dma;
        i2s_mic_get_dma_stats(&current_dma);
        i2s_mic_get_third_dma_stats(&third_dma);
        total_frames += frames_read;
        frames_since_init += frames_read;
        third_frames_since_init += third_frames_read;
        if (err != ESP_OK || frames_read != CAPTURE_FRAMES ||
            third_err != ESP_OK || third_frames_read != CAPTURE_FRAMES) {
            if (err == ESP_ERR_TIMEOUT) read_timeouts++;
            if (third_err == ESP_ERR_TIMEOUT) read_timeouts++;
            if (frames_read != CAPTURE_FRAMES || third_frames_read != CAPTURE_FRAMES) short_reads++;
            if ((err != ESP_OK && err != ESP_ERR_TIMEOUT) ||
                (third_err != ESP_OK && third_err != ESP_ERR_TIMEOUT)) read_errors++;
            // A partial read changes the driver's private DMA offset. Restart
            // the receiver instead of treating the next read as frame zero.
            ESP_LOGW(TAG, "Partial I2S blocks (%u/%u, %u/%u); restarting both DMA receivers",
                     (unsigned)frames_read, CAPTURE_FRAMES,
                     (unsigned)third_frames_read, CAPTURE_FRAMES);
            cumulative_dma_blocks += current_dma.completed_blocks;
            cumulative_overflows += current_dma.overflow_events;
            cumulative_lost_frames += current_dma.overflow_frames;
            cumulative_third_blocks += third_dma.completed_blocks;
            cumulative_third_overflows += third_dma.overflow_events;
            cumulative_third_lost += third_dma.overflow_frames;
            dma_restarts++;
            // A fresh DMA start can change inter-controller sample alignment.
            memset(s_cal_ready, 0, sizeof(s_cal_ready));
            i2s_mic_deinit();
            i2s_mic_config_t config = I2S_MIC_DEFAULT_CONFIG();
            while (i2s_mic_init(&config) != ESP_OK) {
                ESP_LOGE(TAG, "I2S restart failed; retrying");
                vTaskDelay(pdMS_TO_TICKS(500));
            }
            state = STATE_WARMUP;
            warmup_remaining = WARMUP_BLOCKS;
            pending_latch_generation = 0;
            calibrate_after_warmup = false;
            read_blocks = last_overflow_events = last_third_overflow_events = 0;
            frames_since_init = 0;
            third_frames_since_init = 0;
            fft_fill = 0;
            sum_left = sum_right = sum_third = 0;
            samples_in_point = 0;
            fft_windows = phase_windows = 0;
            phase_bin = -1;
            phase_cos_sum = phase_sin_sum = 0.0f;
            memset(phase_cos3, 0, sizeof(phase_cos3));
            memset(phase_sin3, 0, sizeof(phase_sin3));
            magnitude_left_sum = magnitude_right_sum = 0.0f;
            magnitude_third_sum = 0.0f;
            previous_total_frames = total_frames;
            previous_report_us = esp_timer_get_time();
            continue;
        }

        read_blocks++;
        bool discard_current = false;
        if (current_dma.overflow_events != last_overflow_events ||
            third_dma.overflow_events != last_third_overflow_events) {
            // A dropped block can shift the two independent DMA streams by
            // 240 frames. Restart both receivers, never pair their next reads.
            cumulative_dma_blocks += current_dma.completed_blocks;
            cumulative_overflows += current_dma.overflow_events;
            cumulative_lost_frames += current_dma.overflow_frames;
            cumulative_third_blocks += third_dma.completed_blocks;
            cumulative_third_overflows += third_dma.overflow_events;
            cumulative_third_lost += third_dma.overflow_frames;
            dma_restarts++;
            memset(s_cal_ready, 0, sizeof(s_cal_ready));
            i2s_mic_deinit();
            i2s_mic_config_t config = I2S_MIC_DEFAULT_CONFIG();
            while (i2s_mic_init(&config) != ESP_OK) {
                ESP_LOGE(TAG, "I2S overflow restart failed; retrying");
                vTaskDelay(pdMS_TO_TICKS(500));
            }
            state = STATE_WARMUP;
            warmup_remaining = WARMUP_BLOCKS;
            pending_latch_generation = 0;
            calibrate_after_warmup = false;
            read_blocks = last_overflow_events = last_third_overflow_events = 0;
            frames_since_init = third_frames_since_init = 0;
            fft_fill = 0;
            sum_left = sum_right = sum_third = 0;
            samples_in_point = 0;
            fft_windows = phase_windows = 0;
            phase_bin = -1;
            phase_cos_sum = phase_sin_sum = 0.0f;
            memset(phase_cos3, 0, sizeof(phase_cos3));
            memset(phase_sin3, 0, sizeof(phase_sin3));
            magnitude_left_sum = magnitude_right_sum = 0.0f;
            magnitude_third_sum = 0.0f;
            previous_total_frames = total_frames;
            previous_report_us = esp_timer_get_time();
            ESP_LOGW(TAG, "DMA queue overflow: restarted both receivers and cleared calibration");
            continue;
        } else if (pending_latch_generation != 0) {
            i2s_mic_frame_latch_t latch;
            i2s_mic_get_frame_latch(&latch);
            if (latch.generation >= pending_latch_generation) {
                uint32_t block_sequence = read_blocks + current_dma.overflow_events;
                if (block_sequence == latch.first_block) {
                    state = pending_target;
                    pending_latch_generation = 0;
                    fft_fill = 0;
                    sum_left = sum_right = sum_third = 0;
                    samples_in_point = 0;
                    calibration_windows = 0;
                    calibration_bin = -1;
                    calibration_cos_sum = calibration_sin_sum = 0.0f;
                    memset(calibration_cos3, 0, sizeof(calibration_cos3));
                    memset(calibration_sin3, 0, sizeof(calibration_sin3));
                    fft_windows = phase_windows = 0;
                    phase_bin = -1;
                    phase_cos_sum = phase_sin_sum = 0.0f;
                    memset(phase_cos3, 0, sizeof(phase_cos3));
                    memset(phase_sin3, 0, sizeof(phase_sin3));
                    magnitude_left_sum = magnitude_right_sum = 0.0f;
                    magnitude_third_sum = 0.0f;
                    ESP_LOGI(TAG, "ISR-latched %s at block %lu, frame 0",
                             state == STATE_CALIBRATING ? "CAL" : "START",
                             (unsigned long)block_sequence);
                } else if (block_sequence > latch.first_block) {
                    state = STATE_WARMUP;
                    warmup_remaining = WARMUP_BLOCKS;
                    pending_latch_generation = 0;
                    fft_fill = 0;
                    discard_current = true;
                    ESP_LOGW(TAG, "Missed latched block; restarting warmup");
                }
            }
        }

        if (state == STATE_WARMUP) {
            if (!discard_current && warmup_remaining > 0 && --warmup_remaining == 0) {
                pending_target = calibrate_after_warmup ? STATE_CALIBRATING : STATE_RUNNING;
                pending_latch_generation = i2s_mic_request_frame_latch();
                ESP_LOGI(TAG, "Warmup complete; ISR latch generation %lu requested",
                         (unsigned long)pending_latch_generation);
            }
        } else if (!discard_current) {
            for (size_t i = 0; i < frames_read; ++i) {
                // Corresponding left and right values came from the same I2S frame.
                sum_left += s_left_buf[i];
                sum_right += s_right_buf[i];
                sum_third += s_third_buf[i];
                s_fft_left[fft_fill] = s_left_buf[i];
                s_fft_right[fft_fill] = s_right_buf[i];
                s_fft_third[fft_fill] = s_third_buf[i];
                fft_fill++;
                if (++samples_in_point == TELEMETRY_PLOT_DECIMATION) {
                    stereo_telemetry_packet_t packet = {
                        .mic1 = (int32_t)(sum_left / TELEMETRY_PLOT_DECIMATION),
                        .mic2 = (int32_t)(sum_right / TELEMETRY_PLOT_DECIMATION),
                        .mic3 = (int32_t)(sum_third / TELEMETRY_PLOT_DECIMATION),
                    };
                    // Keep reading I2S even if the serial plotter falls behind.
                    telemetry_send_stereo_packet(&packet);
                    sum_left = sum_right = sum_third = 0;
                    samples_in_point = 0;
                }
                if (fft_fill == FFT_TDOA_SIZE) {
                    fft_phase_doa_result_3ch_t result;
                    int64_t fft_start_us = esp_timer_get_time();
                    fft_phase_doa_process_3ch(s_fft_left, s_fft_right, s_fft_third, &result);
                    uint32_t fft_us = (uint32_t)(esp_timer_get_time() - fft_start_us);
                    if (fft_us > max_fft_us) max_fft_us = fft_us;
                    fft_windows++;
                    fft_fill = 0;

                    bool valid = result.signal_active &&
                                 result.confidence >= PHASE_MIN_CONFIDENCE;
                    int bin = valid ? (int)lroundf(result.dominant_freq_hz * FFT_TDOA_SIZE /
                                                   FFT_TDOA_SAMPLE_RATE) : -1;
                    valid = valid && bin > 0 && bin < PHASE_BINS;
                    if (valid) {
                        active_bin = bin;
                        if (phase_bin < 0) phase_bin = bin;
                        if (bin == phase_bin) {
                            phase_cos_sum += cosf(result.pair_21.phi_rad);
                            phase_sin_sum += sinf(result.pair_21.phi_rad);
                            phase_cos3[0] += cosf(result.pair_31.phi_rad);
                            phase_sin3[0] += sinf(result.pair_31.phi_rad);
                            phase_cos3[1] += cosf(result.pair_32.phi_rad);
                            phase_sin3[1] += sinf(result.pair_32.phi_rad);
                            magnitude_left_sum += result.rms_m1;
                            magnitude_right_sum += result.rms_m2;
                            magnitude_third_sum += result.rms_m3;
                            phase_windows++;
                        }
                    }
                    if (state == STATE_CALIBRATING) {
                        if (!valid || (calibration_bin >= 0 && bin != calibration_bin)) {
                            calibration_bin = -1;
                            calibration_windows = 0;
                            calibration_cos_sum = calibration_sin_sum = 0.0f;
                            memset(calibration_cos3, 0, sizeof(calibration_cos3));
                            memset(calibration_sin3, 0, sizeof(calibration_sin3));
                        } else {
                            if (calibration_bin < 0) calibration_bin = bin;
                            calibration_cos_sum += cosf(result.pair_21.phi_rad);
                            calibration_sin_sum += sinf(result.pair_21.phi_rad);
                            calibration_cos3[0] += cosf(result.pair_31.phi_rad);
                            calibration_sin3[0] += sinf(result.pair_31.phi_rad);
                            calibration_cos3[1] += cosf(result.pair_32.phi_rad);
                            calibration_sin3[1] += sinf(result.pair_32.phi_rad);
                            calibration_windows++;
                            if (calibration_windows >= CALIBRATION_WINDOWS) {
                                float R = hypotf(calibration_cos_sum, calibration_sin_sum) /
                                          calibration_windows;
                                float R31 = hypotf(calibration_cos3[0], calibration_sin3[0]) / calibration_windows;
                                float R32 = hypotf(calibration_cos3[1], calibration_sin3[1]) / calibration_windows;
                                if (R >= CALIBRATION_MIN_R && R31 >= CALIBRATION_MIN_R &&
                                    R32 >= CALIBRATION_MIN_R) {
                                    float bias = atan2f(calibration_sin_sum,
                                                        calibration_cos_sum);
                                    s_cal_bias[0][calibration_bin] = bias;
                                    for (int p = 0; p < 2; ++p)
                                        s_cal_bias[p + 1][calibration_bin] =
                                            atan2f(calibration_sin3[p], calibration_cos3[p]);
                                    s_cal_ready[calibration_bin] = true;
                                    state = STATE_RUNNING;
                                    ESP_LOGI(TAG, "CAL ready: %.2f Hz bias=%.3f deg R=%.4f",
                                             (float)calibration_bin * FFT_TDOA_SAMPLE_RATE /
                                             FFT_TDOA_SIZE,
                                             bias * 180.0f / 3.14159265358979323846f, R);
                                    // Do not mix uncalibrated and calibrated
                                    // windows in one one-second report.
                                    fft_windows = phase_windows = 0;
                                    phase_bin = -1;
                                    phase_cos_sum = phase_sin_sum = 0.0f;
                                    memset(phase_cos3, 0, sizeof(phase_cos3));
                                    memset(phase_sin3, 0, sizeof(phase_sin3));
                                    magnitude_left_sum = magnitude_right_sum = 0.0f;
                                    magnitude_third_sum = 0.0f;
                                }
                                calibration_windows = 0;
                                calibration_cos_sum = calibration_sin_sum = 0.0f;
                                memset(calibration_cos3, 0, sizeof(calibration_cos3));
                                memset(calibration_sin3, 0, sizeof(calibration_sin3));
                            }
                        }
                    }
                }
            }
        }

        int64_t report_us = esp_timer_get_time();
        if (report_us - previous_report_us >= 1000000) {
            i2s_mic_dma_stats_t dma;
            i2s_mic_dma_stats_t dma3;
            i2s_mic_get_dma_stats(&dma);
            i2s_mic_get_third_dma_stats(&dma3);
            sync_telemetry_packet_t sync = {
                .frames_per_second = (uint32_t)((total_frames - previous_total_frames) * 1000000ULL /
                                                (uint64_t)(report_us - previous_report_us)),
                .dma_blocks = cumulative_dma_blocks + dma.completed_blocks,
                .dma_backlog_frames = dma.completed_frames > dma.overflow_frames + frames_since_init ?
                                      (uint32_t)(dma.completed_frames - dma.overflow_frames - frames_since_init) : 0,
                .dma_overflow_events = cumulative_overflows + dma.overflow_events,
                .dma_overflow_frames = cumulative_lost_frames + dma.overflow_frames,
                .third_dma_blocks = cumulative_third_blocks + dma3.completed_blocks,
                .third_overflow_events = cumulative_third_overflows + dma3.overflow_events,
                .third_overflow_frames = cumulative_third_lost + dma3.overflow_frames,
                .third_backlog_frames = dma3.completed_frames > dma3.overflow_frames + third_frames_since_init ?
                    (uint32_t)(dma3.completed_frames - dma3.overflow_frames - third_frames_since_init) : 0,
                .read_timeouts = read_timeouts,
                .short_reads = short_reads,
                .read_errors = read_errors,
                .fft_windows = fft_windows,
                .phase_windows = phase_windows,
                .max_read_gap_us = max_read_gap_us,
                .max_fft_us = max_fft_us,
                .plot_drops = telemetry_get_overflow_drops(),
                .pipeline_state = state,
                .calibration_windows = calibration_windows,
                .dma_restarts = dma_restarts,
                .skew_frames = I2S_MIC_SKEW_FRAMES,
            };
            int report_bin = phase_bin > 0 ? phase_bin : active_bin;
            if (report_bin > 0 && report_bin < PHASE_BINS) {
                sync.cal_ready = s_cal_ready[report_bin];
                sync.calibration_frequency_hz = (float)report_bin *
                    FFT_TDOA_SAMPLE_RATE / FFT_TDOA_SIZE;
                if (sync.cal_ready) {
                    sync.phase_bias_deg = s_cal_bias[0][report_bin] *
                        180.0f / 3.14159265358979323846f;
                }
            }
            if (phase_windows > 0 && phase_bin > 0) {
                const float pi = 3.14159265358979323846f;
                sync.frequency_hz = (float)phase_bin * FFT_TDOA_SAMPLE_RATE / FFT_TDOA_SIZE;
                float raw[3] = {
                    atan2f(phase_sin_sum, phase_cos_sum),
                    atan2f(phase_sin3[0], phase_cos3[0]),
                    atan2f(phase_sin3[1], phase_cos3[1])
                };
                float phi[3];
                for (int p = 0; p < 3; ++p)
                    phi[p] = sync.cal_ready ? wrap_phase(raw[p] - s_cal_bias[p][phase_bin]) : raw[p];
                sync.phase_raw_deg = raw[0] * 180.0f / pi;
                sync.raw_phase31_deg = raw[1] * 180.0f / pi;
                sync.raw_phase32_deg = raw[2] * 180.0f / pi;
                sync.phase_deg = phi[0] * 180.0f / pi;
                sync.phase31_deg = phi[1] * 180.0f / pi;
                sync.phase32_deg = phi[2] * 180.0f / pi;
                float r21 = hypotf(phase_cos_sum, phase_sin_sum) / phase_windows;
                float r31 = hypotf(phase_cos3[0], phase_sin3[0]) / phase_windows;
                float r32 = hypotf(phase_cos3[1], phase_sin3[1]) / phase_windows;
                sync.phase_resultant = fminf(r21, fminf(r31, r32));
                sync.magnitude_left = magnitude_left_sum / phase_windows;
                sync.magnitude_right = magnitude_right_sum / phase_windows;
                sync.magnitude_third = magnitude_third_sum / phase_windows;
                sync.phase_consistency_deg = fabsf(wrap_phase(phi[1] - phi[0] - phi[2])) * 180.0f / pi;
                // Keep both raw and baseline-corrected solutions for display modes.
                direction_t raw_direction = phase_direction(raw, sync.frequency_hz);
                direction_t direction = phase_direction(phi, sync.frequency_hz);
                sync.raw_azimuth_deg = raw_direction.azimuth_deg;
                sync.raw_elevation_deg = raw_direction.elevation_deg;
                sync.raw_direction_r = raw_direction.r;
                sync.raw_ux = raw_direction.ux;
                sync.raw_uy = raw_direction.uy;
                sync.raw_uz = raw_direction.uz;
                sync.azimuth_deg = direction.azimuth_deg;
                sync.elevation_deg = direction.elevation_deg;
                sync.direction_r = direction.r;
                sync.ux = direction.ux;
                sync.uy = direction.uy;
                sync.uz = direction.uz;
                sync.direction_valid = sync.cal_ready && state == STATE_RUNNING &&
                    sync.phase_resultant >= CALIBRATION_MIN_R &&
                    sync.phase_consistency_deg < 5.0f &&
                    sync.direction_r <= 1.05f;
            }
            telemetry_send_sync_packet(&sync);
            previous_total_frames = total_frames;
            previous_report_us = report_us;
            fft_windows = phase_windows = 0;
            max_read_gap_us = max_fft_us = 0;
            phase_bin = -1;
            phase_cos_sum = phase_sin_sum = 0.0f;
            memset(phase_cos3, 0, sizeof(phase_cos3));
            memset(phase_sin3, 0, sizeof(phase_sin3));
            magnitude_left_sum = magnitude_right_sum = 0.0f;
            magnitude_third_sum = 0.0f;
        }
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "Three microphone phase FFT: >mic1/2/3, SYNC3, START/CAL/CLEAR");
    ESP_LOGI(TAG, "I2S: %d Hz, GPIO SCK=%d WS=%d SD=%d, skew=%d frame(s)",
             I2S_MIC_DEFAULT_SAMPLE_RATE, I2S_MIC_DEFAULT_SCK_PIN,
             I2S_MIC_DEFAULT_WS_PIN, I2S_MIC_DEFAULT_SD_PIN, I2S_MIC_SKEW_FRAMES);
    ESP_LOGI(TAG, "Mic3: I2S1 slave SD=%d, shared BCLK/WS", I2S_MIC_THIRD_SD_PIN);
    ESP_LOGI(TAG, "Plot: %d three-channel points/s at %d baud",
             I2S_MIC_DEFAULT_SAMPLE_RATE / TELEMETRY_PLOT_DECIMATION,
             TELEMETRY_BAUD_RATE);

    esp_err_t ret = telemetry_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Telemetry initialization failed: %s", esp_err_to_name(ret));
        return;
    }

    s_control_queue = xQueueCreate(8, sizeof(control_command_t));
    if (s_control_queue == NULL) {
        ESP_LOGE(TAG, "Could not allocate control queue");
        telemetry_deinit();
        return;
    }

    fft_tdoa_init();
    phase_fft_3ch_self_test();

    // Serial calibration requires an explicit command after the reference
    // source is positioned. Ambient sound is never used automatically.
    esp_err_t uart_err = uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0);
    if (uart_err == ESP_OK || uart_err == ESP_ERR_INVALID_STATE) {
        uart_vfs_dev_use_driver(UART_NUM_0);
    } else {
        ESP_LOGE(TAG, "Console RX setup failed: %s", esp_err_to_name(uart_err));
    }

    i2s_mic_config_t mic_cfg = I2S_MIC_DEFAULT_CONFIG();
    ret = i2s_mic_init(&mic_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "I2S initialization failed: %s", esp_err_to_name(ret));
        vQueueDelete(s_control_queue);
        telemetry_deinit();
        return;
    }

    TaskHandle_t telemetry_handle = NULL;
    if (xTaskCreatePinnedToCore(telemetry_task_run, "telemetry", 4096,
                                NULL, 2, &telemetry_handle, 0) != pdPASS) {
        ESP_LOGE(TAG, "Could not start telemetry task");
        i2s_mic_deinit();
        vQueueDelete(s_control_queue);
        telemetry_deinit();
        return;
    }

    if (xTaskCreatePinnedToCore(audio_capture_task, "audio_capture", 6144,
                                NULL, 10, NULL, 1) != pdPASS) {
        ESP_LOGE(TAG, "Could not start capture task");
        vTaskDelete(telemetry_handle);
        i2s_mic_deinit();
        vQueueDelete(s_control_queue);
        telemetry_deinit();
        return;
    }

    if (uart_err == ESP_OK || uart_err == ESP_ERR_INVALID_STATE) {
        if (xTaskCreatePinnedToCore(serial_control_task, "serial_control", 3072,
                                    NULL, 3, NULL, 0) != pdPASS) {
            ESP_LOGE(TAG, "Could not start serial control task");
        }
    }

    vTaskDelete(NULL);
}

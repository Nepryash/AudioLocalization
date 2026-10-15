#include "telemetry.h"
#include <stdio.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

static const char *TAG = "telemetry";
static QueueHandle_t s_telemetry_queue = NULL;
static QueueHandle_t s_sync_queue = NULL;
static volatile uint32_t s_overflow_drops = 0;

esp_err_t telemetry_init(void)
{
    if (s_telemetry_queue != NULL) {
        return ESP_OK;
    }

    s_telemetry_queue = xQueueCreate(TELEMETRY_QUEUE_DEPTH, sizeof(stereo_telemetry_packet_t));
    if (s_telemetry_queue == NULL) {
        ESP_LOGE(TAG, "Failed to allocate stereo telemetry queue");
        return ESP_ERR_NO_MEM;
    }
    s_sync_queue = xQueueCreate(1, sizeof(sync_telemetry_packet_t));
    if (s_sync_queue == NULL) {
        vQueueDelete(s_telemetry_queue);
        s_telemetry_queue = NULL;
        return ESP_ERR_NO_MEM;
    }
    s_overflow_drops = 0;
    return ESP_OK;
}

esp_err_t telemetry_send_sync_packet(const sync_telemetry_packet_t *packet)
{
    if (packet == NULL || s_sync_queue == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    return xQueueOverwrite(s_sync_queue, packet) == pdPASS ? ESP_OK : ESP_FAIL;
}

esp_err_t telemetry_send_stereo_packet(const stereo_telemetry_packet_t *packet)
{
    if (packet == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_telemetry_queue == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    if (xQueueSend(s_telemetry_queue, packet, 0) != pdPASS) {
        s_overflow_drops++;
        return ESP_ERR_TIMEOUT;
    }
    return ESP_OK;
}

void telemetry_task_run(void *pvParameters)
{
    (void)pvParameters;
    stereo_telemetry_packet_t packet;
    sync_telemetry_packet_t sync;
    char line_buf[96];
    char sync_buf[512];
    char angle_buf[768];

    while (1) {
        QueueHandle_t q = s_telemetry_queue;
        if (q == NULL) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        if (xQueueReceive(q, &packet, pdMS_TO_TICKS(100)) == pdTRUE) {
            // Third sample comes from the I2S1 slave on the same clocks.
            int len = snprintf(line_buf, sizeof(line_buf),
                               ">mic1:%ld\n>mic2:%ld\n>mic3:%ld\n",
                               (long)packet.mic1, (long)packet.mic2,
                               (long)packet.mic3);
            if (len > 0 && len < (int)sizeof(line_buf)) {
                fputs(line_buf, stdout);
                fflush(stdout);
            }
        }
        if (s_sync_queue != NULL && xQueueReceive(s_sync_queue, &sync, 0) == pdTRUE) {
            // Plain text stays in Teleplot's console instead of creating extra charts.
            int len = snprintf(sync_buf, sizeof(sync_buf),
                "SYNC fps=%lu dma=%lu backlog=%lu ovf=%lu lost=%lu timeout=%lu short=%lu err=%lu "
                "fft=%lu phase_n=%lu f=%.2f phi=%.3f phi_raw=%.3f "
                "phi_bias=%.3f R=%.3f cal_ready=%lu cal_f=%.2f "
                "state=%lu cal_n=%lu restart=%lu skew=%ld "
                "mag1=%.0f mag2=%.0f gap_us=%lu fft_us=%lu plot_drop=%lu\n",
                (unsigned long)sync.frames_per_second,
                (unsigned long)sync.dma_blocks,
                (unsigned long)sync.dma_backlog_frames,
                (unsigned long)sync.dma_overflow_events,
                (unsigned long)sync.dma_overflow_frames,
                (unsigned long)sync.read_timeouts,
                (unsigned long)sync.short_reads,
                (unsigned long)sync.read_errors,
                (unsigned long)sync.fft_windows,
                (unsigned long)sync.phase_windows,
                sync.frequency_hz, sync.phase_deg, sync.phase_raw_deg,
                sync.phase_bias_deg, sync.phase_resultant,
                (unsigned long)sync.cal_ready, sync.calibration_frequency_hz,
                (unsigned long)sync.pipeline_state,
                (unsigned long)sync.calibration_windows,
                (unsigned long)sync.dma_restarts, (long)sync.skew_frames,
                sync.magnitude_left, sync.magnitude_right,
                (unsigned long)sync.max_read_gap_us,
                (unsigned long)sync.max_fft_us,
                (unsigned long)sync.plot_drops);
            if (len > 0 && len < (int)sizeof(sync_buf)) {
                fputs(sync_buf, stdout);
            }
            len = snprintf(angle_buf, sizeof(angle_buf),
                "SYNC3 f=%.2f az=%.2f el=%.2f ux=%.4f uy=%.4f uz=%.4f "
                "valid=%lu r=%.3f coh=%.3f "
                "raw_az=%.2f raw_el=%.2f raw_ux=%.4f raw_uy=%.4f raw_uz=%.4f raw_r=%.3f "
                "phi21=%.3f phi31=%.3f phi32=%.3f "
                "raw21=%.3f raw31=%.3f raw32=%.3f "
                "closure=%.3f cal=%lu state=%lu cal_n=%lu "
                "mag1=%.0f mag2=%.0f mag3=%.0f "
                "dma0=%lu dma1=%lu ovf0=%lu ovf1=%lu lost0=%lu lost1=%lu "
                "backlog0=%lu backlog1=%lu fft=%lu phase_n=%lu\n",
                sync.frequency_hz, sync.azimuth_deg, sync.elevation_deg,
                sync.ux, sync.uy, sync.uz,
                (unsigned long)sync.direction_valid, sync.direction_r,
                sync.phase_resultant,
                sync.raw_azimuth_deg, sync.raw_elevation_deg,
                sync.raw_ux, sync.raw_uy, sync.raw_uz, sync.raw_direction_r,
                sync.phase_deg, sync.phase31_deg, sync.phase32_deg,
                sync.phase_raw_deg, sync.raw_phase31_deg, sync.raw_phase32_deg,
                sync.phase_consistency_deg, (unsigned long)sync.cal_ready,
                (unsigned long)sync.pipeline_state,
                (unsigned long)sync.calibration_windows,
                sync.magnitude_left, sync.magnitude_right, sync.magnitude_third,
                (unsigned long)sync.dma_blocks, (unsigned long)sync.third_dma_blocks,
                (unsigned long)sync.dma_overflow_events,
                (unsigned long)sync.third_overflow_events,
                (unsigned long)sync.dma_overflow_frames,
                (unsigned long)sync.third_overflow_frames,
                (unsigned long)sync.dma_backlog_frames,
                (unsigned long)sync.third_backlog_frames,
                (unsigned long)sync.fft_windows, (unsigned long)sync.phase_windows);
            if (len > 0 && len < (int)sizeof(angle_buf)) fputs(angle_buf, stdout);
            fflush(stdout);
        }
    }
}

esp_err_t telemetry_deinit(void)
{
    if (s_telemetry_queue == NULL) {
        return ESP_OK;
    }
    QueueHandle_t q = s_telemetry_queue;
    s_telemetry_queue = NULL;
    vQueueDelete(q);
    if (s_sync_queue != NULL) {
        vQueueDelete(s_sync_queue);
        s_sync_queue = NULL;
    }
    return ESP_OK;
}

uint32_t telemetry_get_overflow_drops(void)
{
    return s_overflow_drops;
}

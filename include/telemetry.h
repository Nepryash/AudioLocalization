#pragma once

#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

// 500 three-channel points/second leaves UART room for diagnostics.
#define TELEMETRY_PLOT_DECIMATION  (96)
#define TELEMETRY_QUEUE_DEPTH      (64)
#define TELEMETRY_BAUD_RATE        (460800)

typedef struct {
    int32_t mic1;  // Left I2S slot, L/R pin tied to GND
    int32_t mic2;  // Right I2S slot, L/R pin tied to 3.3 V
    int32_t mic3;  // I2S1 left slot, L/R pin tied to GND
} stereo_telemetry_packet_t;

typedef struct {
    uint32_t frames_per_second;
    uint32_t dma_blocks;
    uint32_t dma_backlog_frames;
    uint32_t dma_overflow_events;
    uint32_t dma_overflow_frames;
    uint32_t read_timeouts;
    uint32_t short_reads;
    uint32_t read_errors;
    uint32_t fft_windows;
    uint32_t phase_windows;
    uint32_t max_read_gap_us;
    uint32_t max_fft_us;
    uint32_t plot_drops;
    uint32_t pipeline_state;       // 0 warmup, 1 calibrating, 2 running
    uint32_t cal_ready;            // Baseline available for the reported FFT bin
    uint32_t calibration_windows;
    uint32_t dma_restarts;
    int32_t skew_frames;
    float frequency_hz;
    float phase_deg;
    float phase_raw_deg;
    float phase_bias_deg;
    float calibration_frequency_hz;
    float phase_resultant;
    float magnitude_left;
    float magnitude_right;
    float magnitude_third;
    float phase31_deg;
    float phase32_deg;
    float azimuth_deg;
    float elevation_deg;
    float ux;
    float uy;
    float uz;
    float direction_r;
    float raw_azimuth_deg;
    float raw_elevation_deg;
    float raw_ux;
    float raw_uy;
    float raw_uz;
    float raw_direction_r;
    float raw_phase31_deg;
    float raw_phase32_deg;
    float phase_consistency_deg;
    uint32_t direction_valid;
    uint32_t third_dma_blocks;
    uint32_t third_overflow_events;
    uint32_t third_overflow_frames;
    uint32_t third_backlog_frames;
} sync_telemetry_packet_t;

esp_err_t telemetry_init(void);
esp_err_t telemetry_send_stereo_packet(const stereo_telemetry_packet_t *packet);
esp_err_t telemetry_send_sync_packet(const sync_telemetry_packet_t *packet);
void telemetry_task_run(void *pvParameters);
esp_err_t telemetry_deinit(void);
uint32_t telemetry_get_overflow_drops(void);

#ifdef __cplusplus
}
#endif

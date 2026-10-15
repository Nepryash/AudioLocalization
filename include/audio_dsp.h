#pragma once

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Window decimation factor (128 samples at 16 kHz yields 125 Hz stream rate)
 */
#define AUDIO_DSP_DECIMATION_FACTOR   (128)

/**
 * @brief 24-bit full-scale constants
 */
#define AUDIO_DSP_FULL_SCALE          (8388607.0f) // 2^23 - 1
#define AUDIO_DSP_MIN_SCALE           (-8388608.0f) // -2^23
#define AUDIO_DSP_FULL_SCALE_INT      (8388607)
#define AUDIO_DSP_MIN_SCALE_INT       (-8388608)

/**
 * @brief Telemetry packet holding acoustic metrics for a single decimation window
 */
typedef struct {
    int32_t decimated_sample; /*!< Downsampled acoustic sample */
    int32_t rms_level;        /*!< Full-window RMS energy in 24-bit range [0, 8388607] */
    int32_t peak_level;       /*!< Full-window peak absolute amplitude [0, 8388607] */
} audio_telemetry_packet_t;

/**
 * @brief Process a window of signed 24-bit audio samples and compute RMS energy and peak amplitude.
 *
 * Calculations performed:
 * - decimated_sample: samples[0] instantaneous representative sample.
 * - peak_level: max(|sample[i]|) clamped to [0, 8388607].
 * - rms_level: normalized single-precision FPU RMS sqrtf(sum(x_i^2) / N) * 8388607.0f clamped to [0, 8388607].
 *
 * Safe handling:
 * - If out_packet is NULL, function returns immediately.
 * - If samples is NULL or num_samples == 0, zeroes out all packet fields.
 *
 * @param samples Pointer to array of signed 24-bit audio samples.
 * @param num_samples Number of samples in the window (typically AUDIO_DSP_DECIMATION_FACTOR).
 * @param out_packet Pointer to output telemetry packet.
 */
void audio_dsp_process_window(const int32_t *samples, size_t num_samples, audio_telemetry_packet_t *out_packet);

#ifdef __cplusplus
}
#endif

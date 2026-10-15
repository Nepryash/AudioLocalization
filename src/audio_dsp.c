#include "audio_dsp.h"
#include <math.h>

void audio_dsp_process_window(const int32_t *samples, size_t num_samples, audio_telemetry_packet_t *out_packet)
{
    if (out_packet == NULL) {
        return;
    }

    if (samples == NULL || num_samples == 0) {
        out_packet->decimated_sample = 0;
        out_packet->rms_level = 0;
        out_packet->peak_level = 0;
        return;
    }

    // 1. Instantaneous downsampled sample (first sample in decimation window)
    out_packet->decimated_sample = samples[0];

    // 2. Peak amplitude tracking and single-precision FPU sum-of-squares accumulation
    int32_t peak = 0;
    float sum_sq = 0.0f;

    for (size_t i = 0; i < num_samples; i++) {
        int32_t s = samples[i];

        // Track absolute amplitude within 24-bit dynamic range [0, 8388607]
        int32_t abs_s;
        if (s <= AUDIO_DSP_MIN_SCALE_INT) {
            abs_s = AUDIO_DSP_FULL_SCALE_INT;
        } else if (s < 0) {
            abs_s = -s;
        } else {
            abs_s = s;
        }

        if (abs_s > AUDIO_DSP_FULL_SCALE_INT) {
            abs_s = AUDIO_DSP_FULL_SCALE_INT;
        }

        if (abs_s > peak) {
            peak = abs_s;
        }

        // Normalize sample to float [-1.0f, +1.0f] and accumulate square on Xtensa FPU
        const float inv_full_scale = 1.0f / AUDIO_DSP_FULL_SCALE;
        float x = (float)s * inv_full_scale;
        sum_sq += x * x;
    }

    out_packet->peak_level = peak;

    // 3. RMS computation: sqrtf(mean square), then scale back to 24-bit integer
    float mean_sq = sum_sq / (float)num_samples;
    float rms_norm = sqrtf(mean_sq);
    int32_t rms = (int32_t)lroundf(rms_norm * AUDIO_DSP_FULL_SCALE);

    if (rms > AUDIO_DSP_FULL_SCALE_INT) {
        rms = AUDIO_DSP_FULL_SCALE_INT;
    } else if (rms < 0) {
        rms = 0;
    }

    out_packet->rms_level = rms;
}

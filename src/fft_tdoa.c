#include "fft_tdoa.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// Precomputed tables
static float s_hanning[FFT_TDOA_SIZE];
static uint16_t s_bit_rev[FFT_TDOA_SIZE];
static float s_twiddle_cos[FFT_TDOA_SIZE / 2];
static float s_twiddle_sin[FFT_TDOA_SIZE / 2];
static bool s_initialized = false;

// Static scratch buffers for forward FFTs (pinned to BSS to protect FreeRTOS stack)
static float s_x1_r[FFT_TDOA_SIZE];
static float s_x1_i[FFT_TDOA_SIZE];
static float s_x2_r[FFT_TDOA_SIZE];
static float s_x2_i[FFT_TDOA_SIZE];
static float s_x3_r[FFT_TDOA_SIZE];
static float s_x3_i[FFT_TDOA_SIZE];

static uint16_t reverse_bits(uint16_t x, int bits)
{
    uint16_t result = 0;
    for (int i = 0; i < bits; i++) {
        result = (result << 1) | (x & 1);
        x >>= 1;
    }
    return result;
}

void fft_tdoa_init(void)
{
    if (s_initialized) {
        return;
    }

    const int n = FFT_TDOA_SIZE;
    int bits = 0;
    while ((1 << bits) < n) {
        bits++;
    }

    // 1. Precompute Hanning window
    for (int i = 0; i < n; i++) {
        s_hanning[i] = 0.5f * (1.0f - cosf((float)(2.0 * M_PI * i) / (float)(n - 1)));
    }

    // 2. Precompute bit-reversal lookup
    for (int i = 0; i < n; i++) {
        s_bit_rev[i] = reverse_bits((uint16_t)i, bits);
    }

    // 3. Precompute forward FFT twiddle factors (-2*pi*k/N)
    for (int i = 0; i < n / 2; i++) {
        double angle = -2.0 * M_PI * i / n;
        s_twiddle_cos[i] = (float)cos(angle);
        s_twiddle_sin[i] = (float)sin(angle);
    }

    s_initialized = true;
}

/**
 * @brief Forward Radix-2 Cooley-Tukey FFT.
 *
 * NOTE: Only forward FFT is implemented. IFFT is strictly banned.
 */
static void fft_radix2_forward(float *real, float *imag, int n)
{
    // 1. Bit-reversal permutation
    for (int i = 0; i < n; i++) {
        int j = s_bit_rev[i];
        if (i < j) {
            float tr = real[i];
            float ti = imag[i];
            real[i] = real[j];
            imag[i] = imag[j];
            real[j] = tr;
            imag[j] = ti;
        }
    }

    // 2. Cooley-Tukey butterfly stages
    for (int len = 2; len <= n; len <<= 1) {
        int half_len = len >> 1;
        int step = n / len;

        for (int i = 0; i < n; i += len) {
            for (int j = 0; j < half_len; j++) {
                int k = j * step;
                float wr = s_twiddle_cos[k];
                float wi = s_twiddle_sin[k];

                int u = i + j;
                int v = i + j + half_len;

                float tr = wr * real[v] - wi * imag[v];
                float ti = wr * imag[v] + wi * real[v];

                real[v] = real[u] - tr;
                imag[v] = imag[u] - ti;
                real[u] = real[u] + tr;
                imag[u] = imag[u] + ti;
            }
        }
    }
}

void fft_phase_calc_pair(float x_j_r, float x_j_i,
                         float x_i_r, float x_i_i,
                         phase_pair_result_t *result)
{
    if (result == NULL) {
        return;
    }

    // 1. Multiply X_j by complex conjugate of X_i:
    //    P_ji = X_j * conj(X_i) = (x_j_r + j*x_j_i) * (x_i_r - j*x_i_i)
    float prod_r = x_j_r * x_i_r + x_j_i * x_i_i;
    float prod_i = x_j_i * x_i_r - x_j_r * x_i_i;

    // 2. Extract pure angle (argument) in radians: phi_ji = arg(P_ji)
    float phi = atan2f(prod_i, prod_r);
    result->phi_rad = phi;

}


void fft_phase_doa_process_3ch(const int32_t *mic1,
                              const int32_t *mic2,
                              const int32_t *mic3,
                              fft_phase_doa_result_3ch_t *result)
{
    if (!s_initialized) {
        fft_tdoa_init();
    }

    if (result == NULL || mic1 == NULL || mic2 == NULL || mic3 == NULL) {
        return;
    }

    const int n = FFT_TDOA_SIZE;
    memset(result, 0, sizeof(*result));

    // 1. RMS Levels
    double sq1 = 0.0, sq2 = 0.0, sq3 = 0.0;
    double sum1 = 0.0, sum2 = 0.0, sum3 = 0.0;
    for (int i = 0; i < n; i++) {
        double s1 = (double)mic1[i];
        double s2 = (double)mic2[i];
        double s3 = (double)mic3[i];
        sq1 += s1 * s1;
        sq2 += s2 * s2;
        sq3 += s3 * s3;
        sum1 += s1;
        sum2 += s2;
        sum3 += s3;
    }

    result->rms_m1 = (int32_t)sqrt(sq1 / n);
    result->rms_m2 = (int32_t)sqrt(sq2 / n);
    result->rms_m3 = (int32_t)sqrt(sq3 / n);

    result->signal_active = (result->rms_m1 >= FFT_TDOA_SILENCE_THRESHOLD &&
                                result->rms_m2 >= FFT_TDOA_SILENCE_THRESHOLD &&
                                result->rms_m3 >= FFT_TDOA_SILENCE_THRESHOLD);
    if (!result->signal_active) {
        return;
    }

    // 2. Window time-domain samples
    const float mean1 = (float)(sum1 / n);
    const float mean2 = (float)(sum2 / n);
    const float mean3 = (float)(sum3 / n);
    for (int i = 0; i < n; i++) {
        s_x1_r[i] = ((float)mic1[i] - mean1) * s_hanning[i];
        s_x1_i[i] = 0.0f;
        s_x2_r[i] = ((float)mic2[i] - mean2) * s_hanning[i];
        s_x2_i[i] = 0.0f;
        s_x3_r[i] = ((float)mic3[i] - mean3) * s_hanning[i];
        s_x3_i[i] = 0.0f;
    }

    // 3. Forward FFT on all 3 channels
    fft_radix2_forward(s_x1_r, s_x1_i, n);
    fft_radix2_forward(s_x2_r, s_x2_i, n);
    fft_radix2_forward(s_x3_r, s_x3_i, n);

    // 4. Find dominant frequency bin in 80 - 200 Hz band
    const float bin_res = (float)FFT_TDOA_SAMPLE_RATE / (float)n;
    int k_min = (int)ceilf(FFT_TDOA_BAND_MIN_HZ / bin_res);
    int k_max = (int)floorf(FFT_TDOA_BAND_MAX_HZ / bin_res);

    if (k_min < 1) k_min = 1;
    if (k_max >= n / 2) k_max = n / 2 - 1;

    int best_bin = k_min;
    float max_power = -1.0f;
    float total_band_power = 0.0f;

    for (int k = k_min; k <= k_max; k++) {
        float p1 = s_x1_r[k] * s_x1_r[k] + s_x1_i[k] * s_x1_i[k];
        float p2 = s_x2_r[k] * s_x2_r[k] + s_x2_i[k] * s_x2_i[k];
        float p3 = s_x3_r[k] * s_x3_r[k] + s_x3_i[k] * s_x3_i[k];
        float combined_power = p1 + p2 + p3;
        total_band_power += combined_power;

        if (combined_power > max_power) {
            max_power = combined_power;
            best_bin = k;
        }
    }

    float dominant_freq = (float)best_bin * bin_res;
    result->dominant_freq_hz = dominant_freq;
    result->dominant_bin = best_bin;
    result->dominant_power = max_power;

    if (total_band_power > 1e-6f) {
        result->confidence = fminf(fmaxf(max_power / total_band_power, 0.0f), 1.0f);
    } else {
        result->signal_active = false;
        result->dominant_freq_hz = 0.0f;
        result->dominant_bin = 0;
        result->dominant_power = 0.0f;
        return;
    }

    // 5. Extract complex FFT values at dominant bin
    float x1_r = s_x1_r[best_bin], x1_i = s_x1_i[best_bin];
    float x2_r = s_x2_r[best_bin], x2_i = s_x2_i[best_bin];
    float x3_r = s_x3_r[best_bin], x3_i = s_x3_i[best_bin];

    // 6. Calculate phase differences for all 3 pairs:
    //    phi_21 = arg(X2 * conj(X1))
    //    phi_31 = arg(X3 * conj(X1))
    //    phi_32 = arg(X3 * conj(X2))
    fft_phase_calc_pair(x2_r, x2_i, x1_r, x1_i, &result->pair_21);
    fft_phase_calc_pair(x3_r, x3_i, x1_r, x1_i, &result->pair_31);
    fft_phase_calc_pair(x3_r, x3_i, x2_r, x2_i, &result->pair_32);

    // 7. Closed-form direction vector calculation from project sensitivity analysis:
    //    u_x = c * (2*phi21 + phi31 - phi32) / (6 * pi * f * d)
    //    u_y = c * (phi31 + phi32) / (2 * sqrt(3) * pi * f * d)
    const float c = FFT_TDOA_SPEED_OF_SOUND;
    const float d = FFT_TDOA_MIC_DISTANCE;
    const float f = dominant_freq;
    const float pi = (float)M_PI;

    float phi21 = result->pair_21.phi_rad;
    float phi31 = result->pair_31.phi_rad;
    float phi32 = result->pair_32.phi_rad;

    float ux = (c * (2.0f * phi21 + phi31 - phi32)) / (6.0f * pi * f * d);
    float uy = (c * (phi31 + phi32)) / (2.0f * sqrtf(3.0f) * pi * f * d);

    // Project noisy out-of-range estimates to the unit front hemisphere.
    float r_xy_sq = ux * ux + uy * uy;
    result->projection_r = sqrtf(r_xy_sq);
    float uz = 0.0f;
    if (r_xy_sq > 1.0f) {
        float scale = 1.0f / sqrtf(r_xy_sq);
        ux *= scale;
        uy *= scale;
        uz = 0.0f;
    } else {
        uz = sqrtf(1.0f - r_xy_sq);
    }

    result->u_x = ux;
    result->u_y = uy;
    result->u_z = uz;

    float azimuth = atan2f(uy, ux) * (180.0f / pi);
    result->azimuth_deg = azimuth < 0.0f ? azimuth + 360.0f : azimuth;
    result->elevation_deg = atan2f(uz, hypotf(ux, uy)) * (180.0f / pi);
}

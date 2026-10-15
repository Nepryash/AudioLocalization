#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Acoustic array physical and FFT parameters
 *
 * Implements the Direct Narrowband FFT Cross-Spectrum Phase-Difference
 * DOA estimation algorithm from the project design documents
 * (Vladyslav Nepriakhin & Aleksey Kapustjonoks).
 *
 * STRICTLY BANNED:
 *   - NO GCC-PHAT
 *   - NO time-domain cross-correlation
 *   - NO IFFT
 *   - NO search for correlation peaks
 */
#define FFT_TDOA_SIZE               (2048)      /*!< 42.67 ms at 48 kHz; 23.4375 Hz/bin */
#define FFT_TDOA_SAMPLE_RATE        (48000)     /*!< Audio sampling rate in Hz */
#define FFT_TDOA_SPEED_OF_SOUND     (343.0f)    /*!< Speed of sound in m/s (20 deg C air) */
#define FFT_TDOA_MIC_DISTANCE       (0.20f)     /*!< Inter-microphone distance d = 20 cm */
#define FFT_TDOA_BAND_MIN_HZ        (80.0f)     /*!< Target band minimum (80 Hz) */
#define FFT_TDOA_BAND_MAX_HZ        (200.0f)    /*!< Target band maximum (200 Hz) */
#define FFT_TDOA_SILENCE_THRESHOLD  (2500)      /*!< RMS threshold below which signals are considered silence */

/**
 * @brief Complex single-precision float representation
 */
typedef struct {
    float r;    /*!< Real component */
    float i;    /*!< Imaginary component */
} complex_f32_t;

/**
 * @brief Cross-spectrum phase for a single microphone pair (j, i)
 */
typedef struct {
    float phi_rad;          /*!< Exact phase difference in radians: phi_ji = arg(X_j * conj(X_i)) */
} phase_pair_result_t;

/**
 * @brief Full 3-Microphone Array Narrowband Phase-Difference DOA result
 *
 * Array Geometry (Equilateral triangle, centroid at origin):
 *   m1 = (-d/2, -sqrt(3)*d/6, 0)   [Bottom-Left]
 *   m2 = (+d/2, -sqrt(3)*d/6, 0)   [Bottom-Right]
 *   m3 = (0,    +sqrt(3)*d/3, 0)   [Top]
 */
typedef struct {
    float dominant_freq_hz; /*!< Extracted dominant frequency bin in the 80-200 Hz band */
    int dominant_bin;       /*!< FFT bin index corresponding to dominant frequency */
    float dominant_power;   /*!< Combined spectral power of dominant frequency */
    float confidence;       /*!< Spectral purity (dominant power / band power) [0.0, 1.0] */

    // Three pairwise cross-spectrum phases at the same selected bin.
    phase_pair_result_t pair_21; /*!< Pair M2 vs M1: phi_21 = arg(X2 * conj(X1)) */
    phase_pair_result_t pair_31; /*!< Pair M3 vs M1: phi_31 = arg(X3 * conj(X1)) */
    phase_pair_result_t pair_32; /*!< Pair M3 vs M2: phi_32 = arg(X3 * conj(X2)) */

    // Unit Direction Vector (closed-form conversion from Sensitivity Analysis docx)
    float u_x;              /*!< In-plane X direction: c * (2*phi21 + phi31 - phi32) / (6 * pi * f * d) */
    float u_y;              /*!< In-plane Y direction: c * (phi31 + phi32) / (2 * sqrt(3) * pi * f * d) */
    float u_z;              /*!< Out-of-plane Z direction: sqrt(max(0, 1 - u_x^2 - u_y^2)) */

    // Conventional spherical angles with azimuth in XY and elevation above XY.
    float azimuth_deg;      /*!< atan2(u_y, u_x) in [0, 360) degrees */
    float elevation_deg;    /*!< atan2(u_z, hypot(u_x,u_y)) in [0, 90] degrees */
    float projection_r;     /*!< Unclamped sqrt(u_x^2 + u_y^2) for plausibility gating */

    // Signal Levels
    int32_t rms_m1;         /*!< RMS level of Mic 1 */
    int32_t rms_m2;         /*!< RMS level of Mic 2 */
    int32_t rms_m3;         /*!< RMS level of Mic 3 */
    bool signal_active;     /*!< True if all three microphone RMS levels exceed threshold */
} fft_phase_doa_result_3ch_t;

/**
 * @brief Initialize precomputed Hanning window, twiddle factors, and bit-reversal table.
 */
void fft_tdoa_init(void);

/**
 * @brief Calculate cross-spectrum phase for an arbitrary microphone pair.
 *
 * Implements:
 *   1. X_j(f) and X_i(f) complex values at dominant frequency f
 *   2. phi_ji = arg(X_j(f) * conj(X_i(f)))
 *
 * @param x_j_r Real part of channel j FFT at frequency f
 * @param x_j_i Imag part of channel j FFT at frequency f
 * @param x_i_r Real part of channel i FFT at frequency f
 * @param x_i_i Imag part of channel i FFT at frequency f
 * @param result Pointer to output pair result
 */
void fft_phase_calc_pair(float x_j_r, float x_j_i,
                         float x_i_r, float x_i_i,
                         phase_pair_result_t *result);

/**
 * @brief Process 3-microphone audio frames using Direct Narrowband FFT Phase-Difference
 * to calculate the projected front-hemisphere vector, azimuth, and elevation.
 *
 * @param mic1 Pointer to Mic 1 (Bottom-Left) samples (length FFT_TDOA_SIZE).
 * @param mic2 Pointer to Mic 2 (Bottom-Right) samples (length FFT_TDOA_SIZE).
 * @param mic3 Pointer to Mic 3 (Top) samples (length FFT_TDOA_SIZE).
 * @param result Pointer to 3-channel DOA output result.
 */
void fft_phase_doa_process_3ch(const int32_t *mic1,
                              const int32_t *mic2,
                              const int32_t *mic3,
                              fft_phase_doa_result_3ch_t *result);

#ifdef __cplusplus
}
#endif

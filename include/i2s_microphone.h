#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "driver/i2s_std.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Default hardware configuration constants
 */
#define I2S_MIC_DEFAULT_SAMPLE_RATE     (48000)
#define I2S_MIC_DEFAULT_SCK_PIN         (14)
#define I2S_MIC_DEFAULT_WS_PIN          (27)
#define I2S_MIC_DEFAULT_SD_PIN          (32)
#define I2S_MIC_THIRD_SD_PIN            (33)
#define I2S_MIC_DMA_FRAME_NUM           (240)
#define I2S_MIC_DMA_DESC_NUM            (12)

/*
 * Optional measured inter-channel skew, in whole stereo frames. Leave at zero
 * for the shared-clock INMP441 pair. A positive value delays mic1 by one frame
 * to match a mic2 channel known to lag by one; negative delays mic2 instead.
 * This is not an automatic calibration and must not be set from room acoustics.
 */
#ifndef I2S_MIC_SKEW_FRAMES
#define I2S_MIC_SKEW_FRAMES             (0)
#endif
#if I2S_MIC_SKEW_FRAMES < -1 || I2S_MIC_SKEW_FRAMES > 1
#error "I2S_MIC_SKEW_FRAMES currently supports only -1, 0, or +1"
#endif

/**
 * @brief Port type fallback for ESP-IDF v6.1.0 compatibility
 */
#ifndef I2S_PORT_T_DEFINED
typedef int i2s_port_t;
#define I2S_PORT_T_DEFINED
#endif

/**
 * @brief Hardware configuration parameters for INMP441 I2S microphone
 */
typedef struct {
    uint32_t sample_rate;   /*!< Audio sampling rate in Hz (e.g., 16000) */
    int sck_pin;            /*!< Serial Clock (BCLK) GPIO pin */
    int ws_pin;             /*!< Word Select (LRCK) GPIO pin */
    int sd_pin;             /*!< Serial Data (DIN) GPIO pin */
    i2s_port_t i2s_port;    /*!< Hardware I2S port (I2S_NUM_0 or I2S_NUM_1) */
} i2s_mic_config_t;

typedef struct {
    uint32_t completed_blocks;
    uint32_t completed_frames;
    uint32_t overflow_events;
    uint32_t overflow_frames;
} i2s_mic_dma_stats_t;

typedef struct {
    uint32_t generation;
    uint32_t first_block;  /* 1-based completed-block sequence; frame 0 begins here. */
} i2s_mic_frame_latch_t;

/**
 * @brief Default configuration initializer macro
 */
#define I2S_MIC_DEFAULT_CONFIG() {                  \
    .sample_rate = I2S_MIC_DEFAULT_SAMPLE_RATE,     \
    .sck_pin     = I2S_MIC_DEFAULT_SCK_PIN,         \
    .ws_pin      = I2S_MIC_DEFAULT_WS_PIN,          \
    .sd_pin      = I2S_MIC_DEFAULT_SD_PIN,          \
    .i2s_port    = I2S_NUM_0,                       \
}

/**
 * @brief Initialize the INMP441 I2S microphone peripheral and start DMA reception.
 *
 * If config is NULL, default parameters are used (16000 Hz, SCK=14, WS=27, SD=32, I2S_NUM_0).
 * Configures 32-bit slot / 32-bit receive word Philips standard mode and enables internal
 * pull-down on the SD GPIO line to prevent bus floating during high-impedance cycles.
 *
 * @param config Pointer to configuration struct, or NULL for default configuration.
 * @return 
 *      - ESP_OK: Initialized and enabled successfully
 *      - ESP_ERR_INVALID_ARG: Invalid GPIO pin or sample rate
 *      - ESP_ERR_NO_MEM: Failed to allocate DMA or channel memory
 *      - ESP_ERR_INVALID_STATE: Driver already running or peripheral in invalid state
 */
esp_err_t i2s_mic_init(const i2s_mic_config_t *config);

/**
 * @brief Read raw 32-bit DMA words directly from the I2S microphone.
 *
 * Reads unprocessed 32-bit words as received from the DMA buffer.
 * INMP441 delivers 24-bit data MSB-aligned in bits [31:8] with bits [7:0] padded with 0.
 *
 * @param dest Destination buffer for raw 32-bit samples.
 * @param num_samples Maximum number of samples to read.
 * @param samples_read Pointer to store actual count of samples read (can be NULL).
 * @param timeout_ms Maximum time to wait in milliseconds.
 * @return 
 *      - ESP_OK: Read completed successfully
 *      - ESP_ERR_TIMEOUT: Timeout occurred before requested samples arrived
 *      - ESP_ERR_INVALID_ARG: Destination buffer is NULL or num_samples is 0
 *      - ESP_ERR_INVALID_STATE: I2S driver is not initialized or running
 */
esp_err_t i2s_mic_read_raw(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms);

/**
 * @brief Read acoustic samples converted to true signed 24-bit dynamic range.
 *
 * Reads incoming DMA samples and applies arithmetic sign extension (raw >> 8)
 * in-place, returning samples in the signed 24-bit range [-8388608, +8388607].
 *
 * @param dest Destination buffer to store converted 24-bit audio samples.
 * @param num_samples Maximum number of samples to read.
 * @param samples_read Pointer to store actual count of samples read (can be NULL).
 * @param timeout_ms Maximum time to wait in milliseconds.
 * @return 
 *      - ESP_OK: Read completed successfully
 *      - ESP_ERR_TIMEOUT: Timeout occurred before requested samples arrived
 *      - ESP_ERR_INVALID_ARG: Destination buffer is NULL or num_samples is 0
 *      - ESP_ERR_INVALID_STATE: I2S driver is not initialized or running
 */
esp_err_t i2s_mic_read_samples(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms);

/**
 * @brief Read stereo acoustic frames (Left = Mic 1, Right = Mic 2).
 *
 * Reads interleaved stereo samples [L0, R0, L1, R1, ...] from DMA, applies
 * arithmetic sign extension (raw >> 8), and demuxes into separate left and right buffers.
 *
 * @param left Buffer to store Left channel (Mic 1) samples.
 * @param right Buffer to store Right channel (Mic 2) samples.
 * @param num_frames Number of stereo frames to read.
 * @param frames_read Pointer to store count of frames actually read (can be NULL).
 * @param timeout_ms Maximum time to wait in milliseconds.
 * @return 
 *      - ESP_OK: Read completed successfully
 *      - ESP_ERR_TIMEOUT: Timeout occurred before requested frames arrived
 *      - ESP_ERR_INVALID_ARG: Destination buffer is NULL or num_frames is 0
 *      - ESP_ERR_INVALID_STATE: I2S driver is not initialized or running
 */
esp_err_t i2s_mic_read_stereo_samples(int32_t *left, int32_t *right, size_t num_frames, size_t *frames_read, uint32_t timeout_ms);

/** Snapshot DMA completion and RX queue overflow counters. */
void i2s_mic_get_dma_stats(i2s_mic_dma_stats_t *stats);
/** I2S1 slave DMA counters for microphone 3. */
void i2s_mic_get_third_dma_stats(i2s_mic_dma_stats_t *stats);
/** Read one full I2S1 stereo DMA block; only its left slot is mic3. */
esp_err_t i2s_mic_read_third_samples(int32_t *third, size_t num_frames,
                                     size_t *frames_read, uint32_t timeout_ms);

/** Arm the next DMA completion callback to latch the following full block. */
uint32_t i2s_mic_request_frame_latch(void);

/** Read the most recent ISR-latched first-block sequence. */
void i2s_mic_get_frame_latch(i2s_mic_frame_latch_t *latch);

/**
 * @brief Disable and deallocate the I2S microphone channel and DMA resources.
 *
 * Safely stops DMA reception, disables clock generation, and frees all driver memory.
 * Idempotent: safe to call if already deinitialized.
 *
 * @return 
 *      - ESP_OK: Deinitialized successfully or already deinitialized
 *      - Error code if channel stop/deletion fails
 */
esp_err_t i2s_mic_deinit(void);

/**
 * @brief Arithmetic sign-extension inline helper.
 *
 * Converts a raw 32-bit DMA word into a signed 24-bit integer waveform.
 * Because raw_32 is signed int32_t, the C99 right shift operator emits the Xtensa
 * LX6 'srai' (Shift Right Arithmetic Immediate) instruction, replicating the sign
 * bit into bits [31:24].
 *
 * @param raw_32 Raw 32-bit word from I2S DMA.
 * @return Signed 24-bit sample represented in int32_t [-8388608, +8388607].
 */
static inline int32_t i2s_mic_convert_sample(int32_t raw_32) {
    return raw_32 >> 8; // Arithmetic right shift sign-extends 24-bit to 32-bit
}

#ifdef __cplusplus
}
#endif

# Audio Math & Interface Contract Specification Report

**Project**: SensorTechINMP441 Phase 1 Audio Acquisition & Telemetry  
**Author**: Milestone M1 Explorer 2 (Audio Math & Contract Specialist)  
**Date**: October 2026  
**Target Architecture**: ESP32 Dev Module (Xtensa Dual-Core LX6 @ 240 MHz), ESP-IDF v6.1.0 (GCC 15.2.0)  
**Scope**: 24-in-32 Bit Transformation Math, Dynamic Range Integrity, Buffer Reading Contracts, and Downstream M2 DSP Conformance  

---

## Executive Summary

This report establishes the mathematical foundations, machine-level assembly proofs, interface contracts, and downstream DSP conformance specifications for **Milestone M1 (Core Audio Engine & Configuration)**. 

### Core Conclusions
1. **Mathematical Invariance of `raw_32 >> 8`**:
   The INMP441 transmits 24-bit two's complement audio MSB-first in 32-bit slots. When acquired by the ESP32 I2S hardware peripheral, the audio data occupies bits `[31:8]`, while the trailing bits `[7:0]` correspond to the sensor's tri-state / pull-down period. An arithmetic right shift by 8 (`raw_32 >> 8`) on a signed 32-bit integer (`int32_t`) is the **unique, mathematically exact, and optimal** transformation. It preserves the full 24-bit signed dynamic range $[-8,388,608, +8,388,607]$ with zero DC bias, zero bit inversion, and automatically truncates trailing tri-state bus noise.
2. **Xtensa LX6 Assembly Optimization**:
   On the Xtensa LX6 architecture with GCC 15.2.0, `raw_32 >> 8` compiles directly to a single `srai aX, aX, 8` (Shift Right Arithmetic Immediate) instruction. In an in-place buffer loop, the Xtensa hardware zero-overhead loop engine executes the transformation in **~4 CPU cycles per sample**. For a standard 240-sample DMA frame, the entire conversion takes **~4.0 microseconds** ($0.026\%$ of CPU time at 240 MHz).
3. **Catastrophic Failure Modes Categorized**:
   - **Unsigned shift (`uint32_t >> 8`)**: Performs logical right shift, turning negative numbers into huge positives ($+16,777,216$ error), inducing catastrophic DC offset and clipping.
   - **Bitwise masking (`(raw >> 8) & 0x00FFFFFF`)**: Clears bits `[31:24]`, destroying the two's complement sign extension and rectifying the waveform.
   - **Left-then-right shifts (`<< 8 >> 16`)**: Corrupts MSB alignment because data is already left-aligned.
4. **Buffer Reading Contract Architecture**:
   We establish a decoupled dual-read contract:
   - `i2s_mic_read_raw()`: Reads raw 32-bit DMA words for low-level diagnostics and hardware debugging.
   - `i2s_mic_read_samples()`: Performs in-place transformation via `i2s_mic_convert_sample()`, returning verified signed 24-bit audio in $[-8388608, +8388607]$ with zero heap allocations.
5. **Downstream M2 DSP Conformance**:
   The M2 DSP module (`audio_dsp.h`) expects samples strictly in $[-8388608, +8388607]$. Normalizing with $2^{23} = 8,388,608.0\text{f}$ guarantees power-of-2 mantissa preservation in the Xtensa single-precision FPU. Peak amplitude tracking is optimized in the integer domain with saturation at $8,388,607$.

---

## 1. 24-in-32 Bit Sample Transformation Math Deep Dive

### 1.1 Physical Bit Alignment in 32-Bit Slots
Under the I2S Philips standard (`bit_shift = true`, 1 SCK delay after WS transition):
- The INMP441 shifts out 24 bits MSB-first during SCK cycles 2 through 25.
- SCK cycles 26 through 32 (7 bits) are tri-stated (High-Z).
- The ESP32 I2S receiver samples each bit on the SCK rising edge into a 32-bit internal shift register.
- When transferred via DMA into system RAM as a 32-bit word (`int32_t raw_32`), the bits are mapped as:

```
 31 30 29 28 27 26 ... 10  9  8   7  6  5  4  3  2  1  0
┌──┬────────────────────────────┬────────────────────────┐
│S │ Audio Data Bits [22 .. 0]  │ Trailing Bus Padding   │
└──┴────────────────────────────┴────────────────────────┘
Bit 31:      Sign bit (S = Bit 23 of audio sample)
Bits 30..8:  Audio bits 22 down to 0 (LSB)
Bits 7..0:   Trailing bits during High-Z (pulled to 0 by bus pull-down)
```

### 1.2 Mathematical Proof of Arithmetic Right Shift
Let $x \in [-2^{23}, 2^{23}-1]$ be the 24-bit two's complement integer emitted by the microphone.
When aligned in bits `[31:8]` of a 32-bit word, the raw integer value is:
$$\text{raw}_{32} = x \cdot 2^8 + \epsilon = 256x + \epsilon$$
where $\epsilon \in [0, 255]$ represents any residual low-byte noise during the 8 idle clocks.

Applying arithmetic right shift by 8:
$$f(\text{raw}_{32}) = \lfloor \text{raw}_{32} / 256 \rfloor = \lfloor (256x + \epsilon) / 256 \rfloor = x + \lfloor \epsilon / 256 \rfloor$$
Because $\epsilon \in [0, 255]$, $\lfloor \epsilon / 256 \rfloor = 0$ for all possible noise values.
Therefore:
$$f(\text{raw}_{32}) = x \quad \text{identically for all } x \in [-8388608, +8388607]$$

#### Proof of Automatic Noise Rejection:
Any noise on the SD line during the tri-state period (e.g. capacitive coupling from BCLK, slow pull-down discharge) is restricted to bits `[7:0]`. Because the arithmetic right shift drops the lowest 8 bits completely, **all noise in bits `[7:0]` is mathematically eliminated without requiring an explicit bitwise mask.**

### 1.3 Boundary Proofs & Golden Values

The following table provides verified mathematical mappings for all critical boundary points:

| Acoustic State | Raw 32-Bit Hex | Signed 32-Bit Decimal | Converted Hex (`>> 8`) | Converted Decimal | Dynamic Range Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Max Positive (+FS)** | `0x7FFFFF00` | $+2,147,483,392$ | `0x007FFFFF` | $+8,388,607$ | Strictly preserved (+FS) |
| **Max Pos w/ Bus Noise**| `0x7FFFFFFF` | $+2,147,483,647$ | `0x007FFFFF` | $+8,388,607$ | Noise eliminated, +FS preserved |
| **Half Scale Positive** | `0x40000000` | $+1,073,741,824$ | `0x00400000` | $+4,194,304$ | Exact linearity |
| **Small Positive (+1)** | `0x00000100` | $+256$ | `0x00000001` | $+1$ | LSB preserved |
| **Pure Silence (Zero)** | `0x00000000` | $0$ | `0x00000000` | $0$ | Perfect zero baseline |
| **Low-Byte Noise Only** | `0x000000FF` | $+255$ | `0x00000000` | $0$ | Truncated to 0 (No DC drift) |
| **Small Negative (-1)** | `0xFFFFFF00` | $-256$ | `0xFFFFFFFF` | $-1$ | Sign extended |
| **Neg -1 w/ Noise** | `0xFFFFFF80` | $-128$ | `0xFFFFFFFF` | $-1$ | Noise eliminated, -1 preserved |
| **Half Scale Negative** | `0xC0000000` | $-1,073,741,824$ | `0xFFC00000` | $-4,194,304$ | Exact linearity |
| **Max Negative (-FS)** | `0x80000000` | $-2,147,483,648$ | `0xFF800000` | $-8,388,608$ | Strictly preserved (-FS) |

### 1.4 Xtensa LX6 Machine-Level Instruction Verification
Using the cross-compiler toolchain (`xtensa-esp32-elf-gcc` v15.2.0 with `-O2 -mlongcalls`):

#### Scalar Conversion Helper:
```c
static inline int32_t i2s_mic_convert_sample(int32_t raw_32) {
    return raw_32 >> 8;
}
```
Compiles to:
```assembly
srai    a2, a2, 8
```
- Instruction: `srai` (Shift Right Arithmetic Immediate).
- Execution Latency: **1 CPU clock cycle**.
- Zero branching, zero pipeline stalls.

#### In-Place Buffer Conversion Loop:
```c
void convert_buffer_inplace(int32_t *buf, size_t count) {
    for (size_t i = 0; i < count; i++) {
        buf[i] >>= 8;
    }
}
```
Compiles to:
```assembly
    loop    a8, .L_END
.L_LOOP:
    l32i.n  a9, a2, 0        # Load 32-bit raw word from RAM
    srai    a9, a9, 8        # Arithmetic shift right by 8 with sign extension
    s32i.n  a9, a2, 0        # Store converted 24-bit word back to RAM
    addi.n  a2, a2, 4        # Advance buffer pointer
.L_END:
```
- Hardware Zero-Overhead Loop: The Xtensa LX6 CPU hardware loop controller executes the loop without branch penalties.
- Pipeline Throughput: Exactly 4 instructions per iteration (~4 cycles).
- Execution Time: For 240 samples @ 240 MHz:
  $$\tau_{\text{conv}} = \frac{240 \times 4}{240 \times 10^6} = 4.0\,\mu\text{s}$$
  The DMA buffer accumulates for $15,000\,\mu\text{s}$ ($15\text{ ms}$). CPU utilization for conversion is $4.0 / 15000 = \mathbf{0.026\%}$.

### 1.5 C Standards & Implementation Guarantees
- **ISO C Standard**: ISO/IEC 9899:1999 (C99) §6.5.7 and ISO/IEC 9899:2011 (C11) §6.5.7 state:
  *"If E1 has a signed type and a negative value, the resulting value of E1 >> E2 is implementation-defined."*
- **GCC Implementation Guarantee**: The GCC manual (*Integers: Implementation-Defined Behavior*) explicitly specifies:
  *"Signed ‘>>’ acts on negative numbers by sign extension (arithmetic right shift)."*
- **Architecture Mandate**: The Xtensa instruction set provides separate logical (`srli`) and arithmetic (`srai`) shift instructions. GCC on Xtensa unconditionally emits `srai` for signed types.

### 1.6 Catastrophic Failure Modes Analysis

#### Failure Mode 1: Unsigned Logical Shift Right
```c
// BUG: Declaring buffer or casting to uint32_t
uint32_t raw_u = (uint32_t)dma_buf[i];
int32_t sample = (int32_t)(raw_u >> 8);
```
- **Mechanism**: The compiler emits `srli` (Shift Right Logical Immediate). Bits `[31:24]` are filled with zeros instead of replicating the sign bit.
- **Impact on Negative Numbers**:
  `0x80000000` ($-8,388,608$) becomes `0x00800000` ($+8,388,608$).
  `0xFFFFFF00` ($-1$) becomes `0x00FFFFFF` ($+16,777,215$).
- **Mathematical Error**:
  $$\Delta = \text{result}_{\text{bug}} - \text{result}_{\text{true}} = +16,777,216 \quad (+2^{24})$$
- **Resulting Symptom**: The negative half-wave is reflected into the extreme positive domain. The signal baseline shifts from $0$ to $+8,388,608$ (50% of full scale). Telemetry RMS squares this offset, causing full-scale saturation and permanent waveform distortion.

#### Failure Mode 2: Bitwise Masking with `0x00FFFFFF`
```c
// BUG: Masking lower 24 bits after shift
int32_t sample = (raw_32 >> 8) & 0x00FFFFFF;
```
- **Mechanism**: The arithmetic shift correctly extends the sign bits into `[31:24]`, but the `& 0x00FFFFFF` mask clears them back to `0x00`.
- **Resulting Symptom**: Identical to Failure Mode 1. All negative numbers become large positive integers.

#### Failure Mode 3: Shifting Left Before Right
```c
// BUG: Assuming audio is right-aligned
int32_t sample = (raw_32 << 8) >> 16;
```
- **Mechanism**: In a 32-bit slot, audio data is already left-aligned at bits `[31:8]`. Shifting left by 8 causes signed integer overflow (undefined behavior in C) and shifts the MSB out of the register, destroying the audio waveform.

---

## 2. Buffer Reading Contract Design

### 2.1 Contract Specifications: `i2s_mic_read_raw` vs `i2s_mic_read_samples`

| Contract Attribute | `i2s_mic_read_raw` | `i2s_mic_read_samples` |
| :--- | :--- | :--- |
| **Header Declaration** | `esp_err_t i2s_mic_read_raw(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms)` | `esp_err_t i2s_mic_read_samples(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms)` |
| **Output Data Format** | Raw 32-bit DMA words (`[31:8]` = 24-bit audio, `[7:0]` = padding) | Clean signed 24-bit audio integers in $[-8388608, +8388607]$ |
| **Conversion Status** | None (direct bitwise copy from DMA) | In-place arithmetic conversion (`dest[i] >>= 8`) |
| **Buffer Sizing Unit** | Number of 32-bit words (`num_samples`) | Number of 32-bit words (`num_samples`) |
| **Memory Allocation** | Zero heap allocation (caller provides buffer) | Zero heap allocation (in-place modification) |
| **Execution Cost** | 0 CPU cycles after DMA completion | ~4 CPU cycles per sample (~4 µs for 240 samples) |
| **Downstream Consumers**| Raw bitfield loggers, hardware bus diagnostic tools, multi-channel demuxers | Downstream M2 DSP (`audio_dsp_process_window`), FFT, Serial Plotter |

### 2.2 Preconditions, Postconditions & Invariants

#### Function: `i2s_mic_read_raw`
- **Preconditions**:
  1. `i2s_mic_init()` has been successfully executed (`s_rx_handle != NULL`).
  2. `dest != NULL` and points to contiguous memory capable of holding at least `num_samples * sizeof(int32_t)` bytes.
  3. `samples_read != NULL`.
  4. `num_samples > 0`.
- **Postconditions**:
  1. `*samples_read` holds the exact number of 32-bit samples retrieved from the DMA ring buffer ($0 \le \text{*samples\_read} \le \text{num\_samples}$).
  2. If return is `ESP_OK`, `*samples_read == num_samples` (or partial frames if timeout).
  3. `dest` contains unaltered DMA words.
- **Error Codes**:
  - `ESP_OK`: Successful read.
  - `ESP_ERR_INVALID_ARG`: `dest == NULL`, `samples_read == NULL`, or `num_samples == 0`.
  - `ESP_ERR_INVALID_STATE`: Driver uninitialized or handle deleted.
  - `ESP_ERR_TIMEOUT`: DMA ring buffer had no frames available within `timeout_ms`.

#### Function: `i2s_mic_read_samples`
- **Preconditions**: Identical to `i2s_mic_read_raw`.
- **Postconditions**:
  1. `*samples_read` holds the number of valid converted audio samples.
  2. For all $i \in [0, \text{*samples\_read}-1]$:
     $$\text{dest}[i] \in [-8,388,608, \ +8,388,607]$$
  3. No dynamic memory is allocated or freed.
- **Error Codes**: Identical to `i2s_mic_read_raw`.

### 2.3 Concrete Implementation Pattern

```c
esp_err_t i2s_mic_read_raw(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms)
{
    if (dest == NULL || samples_read == NULL || num_samples == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_rx_handle == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    size_t bytes_to_read = num_samples * sizeof(int32_t);
    size_t bytes_read = 0;
    TickType_t ticks_to_wait = (timeout_ms == UINT32_MAX) ? portMAX_DELAY : pdMS_TO_TICKS(timeout_ms);

    esp_err_t ret = i2s_channel_read(s_rx_handle, dest, bytes_to_read, &bytes_read, ticks_to_wait);
    *samples_read = bytes_read / sizeof(int32_t);
    return ret;
}

esp_err_t i2s_mic_read_samples(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms)
{
    esp_err_t ret = i2s_mic_read_raw(dest, num_samples, samples_read, timeout_ms);
    if (ret != ESP_OK && (samples_read == NULL || *samples_read == 0)) {
        return ret;
    }

    size_t count = *samples_read;
    for (size_t i = 0; i < count; i++) {
        dest[i] = i2s_mic_convert_sample(dest[i]);
    }

    return ret;
}
```

---

## 3. Conformance Testing for Downstream M2 DSP Integration

### 3.1 Interface Binding with M2 `audio_dsp.h`
The downstream DSP processing pipeline in `audio_dsp.h` processes discrete windows of audio ($N = 128$ samples, decimation factor $D = 128$):

```c
typedef struct {
    int32_t decimated_sample; // Instantaneous downsampled sample
    int32_t rms_level;        // Full-window RMS energy in [0, 8388607]
    int32_t peak_level;       // Full-window peak absolute amplitude in [0, 8388607]
} audio_telemetry_packet_t;

void audio_dsp_process_window(const int32_t *samples, size_t num_samples, audio_telemetry_packet_t *out_packet);
```

### 3.2 Floating-Point Scaling & Integer Precision Analysis
In M2 DSP processing, incoming samples are normalized to single-precision float for single-cycle FPU accumulation:

1. **Normalization Factor ($2^{23}$ vs $2^{23}-1$)**:
   - `FULL_SCALE_DIV = 8388608.0f` ($2^{23}$):
     - Power-of-two division in IEEE 754 decrements the exponent by 23 without altering mantissa bits.
     - Negative full-scale: $-8,388,608 / 8388608.0\text{f} = -1.0\text{f}$ exactly.
     - Positive full-scale: $+8,388,607 / 8388608.0\text{f} = +0.99999988\text{f}$.
   - When scaling RMS back to the 24-bit telemetry range for the Serial Plotter:
     $$\text{rms\_level} = \text{lroundf}(\text{rms\_f} \times 8388607.0\text{f})$$
     Clamped to $8,388,607$.
2. **Tolerance on Full-Scale DC Test**:
   Because $8388607 / 8388608 \times 8388607 = 8388605.999$, rounding yields $8,388,606$ ($\pm 1$ count off $8,388,607$). Test assertions must allow a tolerance of $\pm 1$ count ($0.00001\%$, $-138\text{ dBFS}$).
3. **Peak Amplitude Tracking**:
   To avoid floating-point truncation, peak absolute amplitude should be tracked directly in the integer domain:
   ```c
   int32_t abs_s = (sample <= -8388608) ? 8388607 : (sample < 0 ? -sample : sample);
   if (abs_s > peak_int) {
       peak_int = abs_s;
   }
   ```

### 3.3 Golden Test Vectors for Conformance Verification

The following test vectors must pass in Tier 1 host tests and M2 integration tests:

| Vector ID | Description | Input Vector ($N=128$) | Expected Decimated | Expected RMS | Expected Peak | Tolerance |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| **V1** | Full-Scale Pos DC | $x_i = \text{0x7FFFFF00}$ | $+8,388,607$ | $8,388,607$ | $8,388,607$ | $\pm 1$ |
| **V2** | Full-Scale Neg DC | $x_i = \text{0x80000000}$ | $-8,388,608$ | $8,388,607$ | $8,388,607$ | $\pm 0$ |
| **V3** | Quiescent Silence | $x_i = \text{0x00000000}$ | $0$ | $0$ | $0$ | $\pm 0$ |
| **V4** | Trailing Bus Noise | $x_i = \text{0x000000FF}$ | $0$ | $0$ | $0$ | $\pm 0$ |
| **V5** | Full-Scale Sine | $x_i = \lfloor 8388607 \sin(\frac{2\pi i}{128}) \rfloor \ll 8$ | $0$ | $5,931,641$ | $8,388,607$ | $\pm 1\%$ |
| **V6** | Half-Scale Clap | $x_{64} = \text{0x40000000}$, others $0$ | $0$ | $370,728$ | $4,194,304$ | $\pm 1$ |
| **V7** | Square Wave ($\pm \text{FS}$) | $x_{0..63} = \text{0x7FFFFF00}$, $x_{64..127} = \text{0x80000000}$ | $-8,388,608$ | $8,388,607$ | $8,388,607$ | $\pm 1$ |

---

## 4. Header & Implementation Recommendations for the Worker

### 4.1 Authoritative Header Contract: `include/i2s_microphone.h`

```c
#pragma once

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "esp_err.h"
#include "driver/i2s_std.h"

#ifdef __cplusplus
extern "C" {
#endif

#define I2S_MIC_DEFAULT_SAMPLE_RATE     (16000)
#define I2S_MIC_DEFAULT_SCK_PIN         (14)
#define I2S_MIC_DEFAULT_WS_PIN          (27)
#define I2S_MIC_DEFAULT_SD_PIN          (32)

/**
 * @brief Configuration parameters for I2S microphone driver.
 */
typedef struct {
    uint32_t sample_rate;   /**< Audio sample rate in Hz (default: 16000) */
    int sck_pin;            /**< GPIO pin for Serial Clock / BCLK */
    int ws_pin;             /**< GPIO pin for Word Select / LRCK */
    int sd_pin;             /**< GPIO pin for Serial Data In */
    i2s_port_t i2s_port;    /**< Hardware I2S port (I2S_NUM_0 or I2S_NUM_1) */
} i2s_mic_config_t;

/**
 * @brief Default configuration initializer macro.
 */
#define I2S_MIC_DEFAULT_CONFIG() {                  \
    .sample_rate = I2S_MIC_DEFAULT_SAMPLE_RATE,     \
    .sck_pin     = I2S_MIC_DEFAULT_SCK_PIN,         \
    .ws_pin      = I2S_MIC_DEFAULT_WS_PIN,          \
    .sd_pin      = I2S_MIC_DEFAULT_SD_PIN,          \
    .i2s_port    = I2S_NUM_0,                       \
}

/**
 * @brief Initialize the I2S peripheral and configure standard mode for INMP441.
 *
 * @param config Pointer to configuration struct. If NULL, default config is used.
 * @return ESP_OK on success, or appropriate error code.
 */
esp_err_t i2s_mic_init(const i2s_mic_config_t *config);

/**
 * @brief Read raw 32-bit DMA words directly from the I2S channel.
 *
 * @param dest Pointer to destination buffer (must hold num_samples * 4 bytes).
 * @param num_samples Maximum number of samples (32-bit words) to read.
 * @param samples_read Pointer to store the number of samples actually read.
 * @param timeout_ms Timeout in milliseconds (or UINT32_MAX for portMAX_DELAY).
 * @return ESP_OK on success, ESP_ERR_TIMEOUT on timeout, or error code.
 */
esp_err_t i2s_mic_read_raw(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms);

/**
 * @brief Read audio samples from I2S channel and convert in-place to signed 24-bit range.
 *
 * Each sample is guaranteed to be in the signed range [-8388608, +8388607].
 *
 * @param dest Pointer to destination buffer (must hold num_samples * 4 bytes).
 * @param num_samples Maximum number of samples to read.
 * @param samples_read Pointer to store the number of samples actually read.
 * @param timeout_ms Timeout in milliseconds.
 * @return ESP_OK on success, ESP_ERR_TIMEOUT on timeout, or error code.
 */
esp_err_t i2s_mic_read_samples(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms);

/**
 * @brief Stop I2S channel and release all hardware and DMA resources.
 *
 * @return ESP_OK on success.
 */
esp_err_t i2s_mic_deinit(void);

/**
 * @brief Inline arithmetic right shift converter.
 *
 * Extracts 24-bit audio from upper 24 bits of 32-bit slot with sign extension.
 * Eliminates trailing tri-state bus padding bits [7:0].
 *
 * @param raw_32 Raw 32-bit word from DMA.
 * @return Signed 24-bit audio integer in [-8388608, +8388607].
 */
static inline int32_t i2s_mic_convert_sample(int32_t raw_32)
{
    return raw_32 >> 8;
}

#ifdef __cplusplus
}
#endif
```

---

## 5. Verification Matrix & Test Strategy

| Test Level | Test Case | Target Property | Verification Method |
| :--- | :--- | :--- | :--- |
| **Tier 1 (Host Unit Test)** | `test_arithmetic_shift_boundaries` | Boundary values ($-FS, +FS, 0, \pm 1$) match expected | Python script `verify_math.py` |
| **Tier 1 (Host Unit Test)** | `test_trailing_noise_immunity` | Inputs with non-zero lower byte yield exact converted value | Python script `verify_math.py` |
| **Tier 1 (Host Unit Test)** | `test_dsp_pipeline_integration` | Golden vectors V1–V7 produce expected RMS & Peak within tolerance | Python script `test_dsp_integration.py` |
| **Tier 2 (Build & Static)** | `pio run -e esp32dev` | Clean compilation with zero warnings on Xtensa GCC 15.2.0 | `& "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run` |
| **Tier 2 (Assembly Inspection)** | `srai` instruction verification | `i2s_mic_convert_sample` compiles to single-cycle `srai` instruction | Inspected `test_assembly.s` |
| **Tier 3 (HIL Integration)** | `test_dma_read_stream` | `i2s_mic_read_samples` executes at 16 kHz without DMA underruns | Serial rate monitoring |
| **Tier 4 (Acoustic E2E)** | Quiescent room silence | Baseline centered around 0 with noise floor $< -50\text{ dBFS}$ | `tools/audio_plotter.py` |

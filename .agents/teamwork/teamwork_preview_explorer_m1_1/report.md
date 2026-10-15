# Technical Implementation Report: Milestone M1 (Core Audio Engine & Configuration)

**Role**: Milestone M1 Explorer 1 (Hardware & Driver Specialist)  
**Author**: Explorer M1-1  
**Target Environment**: ESP-IDF v6.1.0 (`framework-espidf @ 4.60100.0`, GCC 15.2.0) on ESP32 (`esp32dev`)  
**Target Hardware**: InvenSense / TDK INMP441 Omnidirectional Digital I2S MEMS Microphone  
**Date**: 2026-10-06  

---

## 1. Executive Summary

Milestone M1 establishes the hardware and driver foundation for Phase 1 of the acoustic array system. The system acquires high-fidelity 24-bit digital audio from an INMP441 MEMS microphone using ESP-IDF v6.1.0's modern standard I2S driver (`driver/i2s_std.h`), buffers data via DMA ring descriptors, and provides clean sample extraction for downstream DSP processing and UART telemetry.

This report provides complete, drop-in technical specifications for the Worker agent covering:
1. **`platformio.ini`**: Setting `monitor_speed = 115200` to support real-time serial telemetry.
2. **`src/CMakeLists.txt`**: Declaring required component dependencies (`esp_driver_i2s`, `esp_driver_gpio`, `driver`) and include directories (`"." "../include"`).
3. **`include/i2s_microphone.h`**: Defining the interface contract conforming strictly to `PROJECT.md`, including a critical backward-compatibility typedef for `i2s_port_t` required by ESP-IDF v6.1.0.
4. **`src/i2s_microphone.c`**: Implementing the complete hardware driver with modern ESP-IDF v6 APIs, 6 $\times$ 240 DMA frame ring buffers, 32-bit slot width / 24-bit data Philips format, GPIO pin assignments (SCK 14, WS 27, SD 32), internal pull-down on SD, and robust error checking.
5. **Build Verification**: Step-by-step verification methodology using PlatformIO CLI.

---

## 2. Configuration & Build System Updates

### 2.1 `platformio.ini` Specification

#### Issue Analysis
The current `platformio.ini` lacks `monitor_speed`, causing PlatformIO serial monitor to default to 9600 baud. Requirement R2 specifies UART telemetry at 115200 baud. Additionally, PlatformIO generates a flash memory size warning during compilation because the `esp32dev` default profile expects 4MB while `sdkconfig.esp32dev` defaults to 2MB.

#### Proposed `platformio.ini`
```ini
; PlatformIO Project Configuration File
; SensorTechINMP441 - Phase 1 Acoustic Acquisition & Telemetry

[env:esp32dev]
platform = espressif32
board = esp32dev
framework = espidf
monitor_speed = 115200
```

*Notes for Worker*:
- `monitor_speed = 115200` ensures that `pio device monitor` immediately connects at the correct baud rate for Serial Plotter telemetry.

---

### 2.2 `src/CMakeLists.txt` Specification

#### Issue Analysis
In ESP-IDF v6.1.0, hardware drivers have been modularized out of common components into discrete components (`esp_driver_i2s`, `esp_driver_gpio`). Without explicit `REQUIRES` directives in `src/CMakeLists.txt`, includes such as `#include "driver/i2s_std.h"` or `#include "driver/gpio.h"` will cause header not found or undefined symbol linker errors. Furthermore, the `include/` directory at the project root must be registered so `main.c` and other source files can locate `i2s_microphone.h`.

#### Current `src/CMakeLists.txt`
```cmake
FILE(GLOB_RECURSE app_sources ${CMAKE_SOURCE_DIR}/src/*.*)
idf_component_register(SRCS ${app_sources})
```

#### Proposed `src/CMakeLists.txt`
```cmake
FILE(GLOB_RECURSE app_sources ${CMAKE_SOURCE_DIR}/src/*.*)

idf_component_register(SRCS ${app_sources}
                       INCLUDE_DIRS "." "../include"
                       REQUIRES esp_driver_i2s esp_driver_gpio driver)
```

*Verification*:
- `esp_driver_i2s`: Contains `driver/i2s_std.h`, `driver/i2s_common.h`, and `driver/i2s_types.h`.
- `esp_driver_gpio`: Contains `driver/gpio.h`.
- `driver`: Common driver legacy symbols and peripheral mappings.
- `INCLUDE_DIRS "." "../include"`: Allows referencing headers directly via `#include "i2s_microphone.h"`.

---

## 3. Interface Contract: `include/i2s_microphone.h`

### 3.1 Critical Discovery: `i2s_port_t` in ESP-IDF v6.1.0
In legacy ESP-IDF (v4/early v5), the I2S port was an enum named `i2s_port_t`. In ESP-IDF v6.1.0, the driver was completely rewritten:
- The channel configuration struct (`i2s_chan_config_t` in `driver/i2s_common.h:65`) defines `int id;` for the port ID.
- The port macros are `#define I2S_NUM_0 0`, `#define I2S_NUM_1 1`, `#define I2S_NUM_AUTO -1`.
- The typedef `i2s_port_t` **no longer exists** anywhere in ESP-IDF v6.1.0 headers.

To ensure `include/i2s_microphone.h` adheres strictly to the contract in `PROJECT.md` (`i2s_port_t i2s_port;`) while compiling cleanly on ESP-IDF v6.1.0, `i2s_microphone.h` must include a standard fallback definition:
```c
#ifndef I2S_PORT_T_DEFINED
typedef int i2s_port_t;
#define I2S_PORT_T_DEFINED
#endif
```

### 3.2 Full Drop-In Header Code (`include/i2s_microphone.h`)

```c
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
#define I2S_MIC_DEFAULT_SAMPLE_RATE     (16000)
#define I2S_MIC_DEFAULT_SCK_PIN         (14)
#define I2S_MIC_DEFAULT_WS_PIN          (27)
#define I2S_MIC_DEFAULT_SD_PIN          (32)

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

/**
 * @brief Initialize the INMP441 I2S microphone peripheral and start DMA reception.
 *
 * If config is NULL, default parameters are used (16000 Hz, SCK=14, WS=27, SD=32, I2S_NUM_0).
 * Configures 32-bit slot / 24-bit data Philips standard mode and enables internal
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
```

---

## 4. Hardware Driver Implementation: `src/i2s_microphone.c`

### 4.1 Detailed Design Principles

1. **DMA Buffer Sizing & Latency Balance**:
   - `dma_desc_num = 6`: 6 circular DMA descriptors.
   - `dma_frame_num = 240`: 240 frames per DMA buffer.
   - At $16\text{ kHz}$: Buffer duration $= 240 / 16000 = 15\text{ ms}$. Total ring buffer capacity $= 6 \times 15\text{ ms} = 90\text{ ms}$.
   - Memory footprint: $6 \times 240 \times 4\text{ bytes} = 5,760\text{ bytes}$ (under 6 KB DMA RAM).
   - This 90 ms buffer pool guarantees zero DMA underruns even if FreeRTOS preempts the capture task during minor bursts or flash writes.

2. **INMP441 Hardware Compatibility Settings**:
   - `slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT`: The INMP441 datasheet specifies that the microphone requires exactly 64 BCLK clock pulses per stereo frame ($32\text{ pulses per slot}$).
   - `data_bit_width = I2S_DATA_BIT_WIDTH_24BIT`: 24 valid audio bits transmitted MSB-first.
   - `ws_width = 32`: 32 BCLK cycles per half-frame.
   - `ws_pol = false`: Philips standard where WS is LOW for the Left channel.
   - `bit_shift = true`: 1-bit BCLK delay between WS transition and first data bit.
   - `msb_right = false`: Required on classic ESP32 silicon for word sizes $> 16\text{ bits}$.
   - `mclk_multiple = I2S_MCLK_MULTIPLE_256`: With 64-bit frames ($32 \times 2$), $256 / 64 = 4$, an exact integer divider producing zero jitter.

3. **Internal Pull-Down on SD (GPIO 32)**:
   - When the microphone is not driving the data line (the 7 trailing cycles of each slot, plus the entire 32 cycles of the Right slot when $L/R = \text{GND}$), the SD line floats in high impedance (High-Z).
   - Capacitive coupling from adjacent high-speed clock lines (SCK/WS) injects noise into a floating pin, causing false non-zero bits and DC drift.
   - Calling `gpio_set_pull_mode((gpio_num_t)cfg.sd_pin, GPIO_PULLDOWN_ONLY)` pulls the High-Z bus to logic 0, yielding an ultra-clean zero baseline.
   - GPIO 32 is an input/output GPIO with full internal pull-down support (unlike input-only GPIOs 34–39).

4. **In-Place Transformation for `i2s_mic_read_samples`**:
   - `i2s_mic_read_samples` reads raw words directly into the destination buffer and applies `i2s_mic_convert_sample()` in-place.
   - Zero heap allocations, zero copying, cache-efficient.

### 4.2 Full Drop-In Source Code (`src/i2s_microphone.c`)

```c
#include "i2s_microphone.h"
#include <string.h>
#include "esp_log.h"
#include "esp_check.h"
#include "driver/gpio.h"

static const char *TAG = "i2s_microphone";

#define I2S_MIC_DMA_DESC_NUM        (6)
#define I2S_MIC_DMA_FRAME_NUM       (240)
#define I2S_MIC_MIN_SAMPLE_RATE     (8000)
#define I2S_MIC_MAX_SAMPLE_RATE     (50000)

static i2s_chan_handle_t s_rx_handle = NULL;
static bool s_is_initialized = false;

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
        if (cfg.sck_pin <= 0) {
            cfg.sck_pin = I2S_MIC_DEFAULT_SCK_PIN;
        }
        if (cfg.ws_pin <= 0) {
            cfg.ws_pin = I2S_MIC_DEFAULT_WS_PIN;
        }
        if (cfg.sd_pin <= 0) {
            cfg.sd_pin = I2S_MIC_DEFAULT_SD_PIN;
        }
    }

    // Validate parameters against INMP441 hardware specifications
    if (cfg.sample_rate < I2S_MIC_MIN_SAMPLE_RATE || cfg.sample_rate > I2S_MIC_MAX_SAMPLE_RATE) {
        ESP_LOGE(TAG, "Sample rate %lu Hz out of range [%d, %d] Hz",
                 (unsigned long)cfg.sample_rate, I2S_MIC_MIN_SAMPLE_RATE, I2S_MIC_MAX_SAMPLE_RATE);
        return ESP_ERR_INVALID_ARG;
    }

    if (!GPIO_IS_VALID_GPIO(cfg.sck_pin) || !GPIO_IS_VALID_GPIO(cfg.ws_pin) || !GPIO_IS_VALID_GPIO(cfg.sd_pin)) {
        ESP_LOGE(TAG, "Invalid GPIO pin assigned: SCK=%d, WS=%d, SD=%d", cfg.sck_pin, cfg.ws_pin, cfg.sd_pin);
        return ESP_ERR_INVALID_ARG;
    }

    // If previously initialized, deinitialize first to prevent resource leak
    if (s_is_initialized && s_rx_handle != NULL) {
        ESP_LOGW(TAG, "Driver already initialized; re-initializing...");
        i2s_mic_deinit();
    }

    ESP_LOGI(TAG, "Initializing INMP441 I2S: rate=%lu Hz, SCK=%d, WS=%d, SD=%d, port=%d",
             (unsigned long)cfg.sample_rate, cfg.sck_pin, cfg.ws_pin, cfg.sd_pin, cfg.i2s_port);

    // 1. Channel allocation with 6 x 240 DMA frames
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

    // 2. Configure standard mode with INMP441 32-bit slot / 24-bit data Philips format
    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(cfg.sample_rate),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_24BIT, I2S_SLOT_MODE_MONO),
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
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;             // Left slot (INMP441 L/R tied to GND)
    std_cfg.slot_cfg.ws_pol = false;                            // Philips standard: WS is LOW for Left
    std_cfg.slot_cfg.bit_shift = true;                          // 1 BCLK delay after WS transition
    std_cfg.slot_cfg.msb_right = false;                         // Required for >16-bit words on classic ESP32

    // Enable internal pull-down on SD pin to prevent bus floating during High-Z cycles
    gpio_set_pull_mode((gpio_num_t)cfg.sd_pin, GPIO_PULLDOWN_ONLY);

    ret = i2s_channel_init_std_mode(s_rx_handle, &std_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init I2S standard mode: %s", esp_err_to_name(ret));
        i2s_del_channel(s_rx_handle);
        s_rx_handle = NULL;
        return ret;
    }

    // 3. Enable channel (starts BCLK and WS generation and DMA reception)
    ret = i2s_channel_enable(s_rx_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enable I2S channel: %s", esp_err_to_name(ret));
        i2s_del_channel(s_rx_handle);
        s_rx_handle = NULL;
        return ret;
    }

    s_is_initialized = true;
    ESP_LOGI(TAG, "INMP441 I2S standard driver successfully initialized and running");
    return ESP_OK;
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

esp_err_t i2s_mic_deinit(void)
{
    if (!s_is_initialized || s_rx_handle == NULL) {
        return ESP_OK; // Idempotent
    }

    ESP_LOGI(TAG, "Deinitializing I2S microphone driver...");

    esp_err_t ret_disable = i2s_channel_disable(s_rx_handle);
    if (ret_disable != ESP_OK) {
        ESP_LOGW(TAG, "i2s_channel_disable returned: %s", esp_err_to_name(ret_disable));
    }

    esp_err_t ret_del = i2s_del_channel(s_rx_handle);
    if (ret_del != ESP_OK) {
        ESP_LOGE(TAG, "i2s_del_channel returned: %s", esp_err_to_name(ret_del));
    }

    s_rx_handle = NULL;
    s_is_initialized = false;

    return (ret_disable != ESP_OK) ? ret_disable : ret_del;
}
```

---

## 5. Hardware Timing & Pinout Analysis

### 5.1 GPIO Pin Assignment Validation
| Signal | INMP441 Pin | ESP32 GPIO | Direction | Characteristics & Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **BCLK** | `SCK` | **GPIO 14** | Output | High-speed clock out. Avoids strapping pin GPIO 12 (MTDI flash voltage hazard) and GPIO 15 (boot ROM log). |
| **WS** | `WS` | **GPIO 27** | Output | Clean GPIO matrix output, non-strapping, stable high-frequency clock generation. |
| **DIN** | `SD` | **GPIO 32** | Input | RTC/matrix GPIO input. Integrated pull-down resistor enabled to prevent floating bus noise. |
| **L/R** | `L/R` | **GND** | Hardwired | Hardwired to ground. Configures microphone to transmit during Left slot ($WS = \text{LOW}$). |
| **VDD** | `VDD` | **3.3V** | Power | Regulated 3.3V rail (INMP441 rating is 1.62V to 3.63V). Never connect to 5V. |
| **GND** | `GND` | **GND** | Ground | Common system ground. |

### 5.2 INMP441 Timing Diagram & Slot Alignment
From InvenSense datasheet DS-INMP441:
1. When WS falls LOW, Left slot starts.
2. Bit 1: 1 BCLK delay (High-Z).
3. Bits 2 to 25: INMP441 drives 24-bit two's complement audio MSB-first ($S, \text{Bit } 22 \dots \text{Bit } 0$).
4. Bits 26 to 32: INMP441 immediately tri-states SD. Internal pull-down holds line at logic 0.
5. In DMA memory, the 32-bit word receives:
   - Bits [31:8]: 24-bit audio data.
   - Bits [7:0]: Logic 0 (pull-down).
6. Arithmetic shift `raw >> 8` sign-extends bit 31 into bits [31:24], resulting in clean $[-8388608, +8388607]$ audio.

### 5.3 3-Microphone Array Forward Compatibility
Per `MEMORY_ACOUSTIC_ARRAY.md` Section 5:
- **Phase 1**: Single mic on `I2S0_L` (SCK=14, WS=27, SD=32, L/R=GND).
- **Phase 2**: Solder Mic 2 to the same SCK=14, WS=27, SD=32 with `L/R` tied to `VDD` (`I2S0_R`).
- **Phase 3**: Add Mic 3 with SD to GPIO 33 (`I2S1_L`), sharing SCK=14 and WS=27.
The Phase 1 architecture requires zero PCB or pin redesign for Phases 2 and 3.

---

## 6. Build Verification & Quality Assurance Method

### 6.1 Verification Commands
To verify the implementation independently:
1. Update `platformio.ini` and `src/CMakeLists.txt`.
2. Add `include/i2s_microphone.h` and `src/i2s_microphone.c`.
3. In `src/main.c`, add an initialization test call:
   ```c
   #include "i2s_microphone.h"
   void app_main(void) {
       ESP_ERROR_CHECK(i2s_mic_init(NULL));
   }
   ```
4. Run the PlatformIO build command:
   ```powershell
   & "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run
   ```

### 6.2 Acceptance Thresholds
- **Exit Code**: 0 (Zero compile or link warnings/errors).
- **RAM Overhead**: $< 7\text{ KB}$ (DMA buffers occupy 5,760 bytes).
- **Flash Footprint**: $< 160\text{ KB}$.
- **Warning Check**: Zero warnings regarding undefined `i2s_port_t`, missing components, or type signedness issues.

---

## 7. Summary Checklist for Worker Agent

| Task | Target File | Action |
| :--- | :--- | :--- |
| 1 | `platformio.ini` | Append `monitor_speed = 115200` |
| 2 | `src/CMakeLists.txt` | Update to require `esp_driver_i2s`, `esp_driver_gpio`, `driver`, and include `"../include"` |
| 3 | `include/i2s_microphone.h` | Create header with `i2s_port_t` typedef fallback and `i2s_mic_convert_sample` inline helper |
| 4 | `src/i2s_microphone.c` | Implement modern I2S standard driver with 6x240 DMA buffers, GPIO 14/27/32, SD pulldown, and read functions |
| 5 | Build Test | Run `& "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run` and verify clean exit code 0 |

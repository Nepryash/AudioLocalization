# Codebase & Configuration Survey Report: SensorTechINMP441

**Author**: Survey Explorer 1 (Codebase & Config Explorer)  
**Date**: 2026-10-06  
**Workspace**: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441`  

---

## Executive Summary

A comprehensive investigation of the project workspace was conducted to establish the baseline configuration and environment for Phase 1 of the acoustic array system (single INMP441 digital I2S acquisition, 24-bit audio extraction, and real-time UART telemetry for Serial Plotter).

The workspace is a PlatformIO ESP-IDF project targeting an ESP32 microcontroller (`esp32dev`). The underlying ESP-IDF framework is **ESP-IDF v6.1.0** (installed package: `framework-espidf @ 4.60100.0` with GCC 15.2.0). The project currently contains only a minimal stub `app_main` in `src/main.c` (18 bytes) and standard boilerplate directories. The baseline project compiles successfully via PlatformIO CLI (`pio.exe` at `C:\Users\hp\.platformio\penv\Scripts\pio.exe`) in 31.32 seconds.

`MEMORY_ACOUSTIC_ARRAY.md` is present (11.9 KB, 204 lines) and fully defines the multi-phase acoustic localization architecture, including the 3-microphone mapping across ESP32 I2S controllers.

---

## 1. Project Configuration & PlatformIO Setup

### 1.1 `platformio.ini` Inspection
- **File path**: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\platformio.ini`
- **Current content**:
  ```ini
  [env:esp32dev]
  platform = espressif32
  board = esp32dev
  framework = espidf
  ```
- **Observations & Gaps**:
  1. **Monitor Speed**: Not configured. Defaults to 9600 baud in PlatformIO. Must be set to `monitor_speed = 115200` to satisfy Requirement R2 (`UART, 115200 baud`).
  2. **Platform & Framework Versions**:
     - Platform: `espressif32` installed as version **7.1.3**
     - Framework: `espidf` installed as **ESP-IDF v6.1.0** (`framework-espidf @ 4.60100.0`)
     - Toolchain: `toolchain-xtensa-esp-elf @ 15.2.0+20251204` (`xtensa-esp32-elf-gcc.exe`)
     - Build generator: `tool-cmake @ 3.30.2`, `tool-ninja @ 1.9.0`
  3. **Flash Size Mismatch Warning**:
     - During `pio run`, PlatformIO warns:
       `Warning! Flash memory size mismatch detected. Expected 4MB, found 2MB!`
     - In `sdkconfig.esp32dev`: lines 676 & 690 configure `CONFIG_ESPTOOLPY_FLASHSIZE_2MB=y` and `CONFIG_ESPTOOLPY_FLASHSIZE="2MB"`, while the `esp32dev` board profile expects 4MB flash.
     - Recommended fix: Add `CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y` and `CONFIG_ESPTOOLPY_FLASHSIZE="4MB"` in `sdkconfig.defaults` or configure `board_upload.flash_size = 2MB` in `platformio.ini`.

### 1.2 Toolchain & Execution Path
- The `pio` command is not in the system's global `PATH`.
- Exact executable path: `C:\Users\hp\.platformio\penv\Scripts\pio.exe`
- Verification execution:
  ```powershell
  & "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run
  ```
- Result: **SUCCESS** (Exit Code 0).
  - RAM usage: 13,612 bytes (4.2% of 320 KB)
  - Flash usage: 141,721 bytes (13.5% of 1 MB)

---

## 2. Codebase Inventory & Component Configuration

### 2.1 File & Directory Inventory
| Path | Status / Size | Purpose / Notes |
| :--- | :--- | :--- |
| `platformio.ini` | 453 bytes (15 lines) | Core PlatformIO environment configuration. |
| `CMakeLists.txt` (root) | 119 bytes (4 lines) | Standard ESP-IDF root CMake configuration. |
| `sdkconfig.esp32dev` | 88,971 bytes (3,735 lines) | Generated ESP-IDF 6.1.0 configuration. |
| `INMP441.pdf` | 6,466,944 bytes (6.46 MB) | Official InvenSense INMP441 datasheet. |
| `MEMORY_ACOUSTIC_ARRAY.md` | 11,900 bytes (204 lines) | Project memory, acoustic physics, coordinate system, DOA math, 3-mic I2S mapping, and phased roadmap. |
| `src/main.c` | 18 bytes (1 line) | Minimal stub: `void app_main() {}`. |
| `src/CMakeLists.txt` | 205 bytes (7 lines) | Component registration script. |
| `include/` | Contains `README` (1,301 bytes) | Empty header directory. |
| `test/` | Contains `README` (529 bytes) | Empty test directory. |
| `lib/` | Contains `README` (1,100 bytes) | Empty local library directory. |
| `.gitignore` | 99 bytes (6 lines) | Standard ignores (`.pio`, `.vscode`). |

### 2.2 `src/CMakeLists.txt` Dependency Gap (ESP-IDF v6.1.0)
Currently, `src/CMakeLists.txt` contains:
```cmake
FILE(GLOB_RECURSE app_sources ${CMAKE_SOURCE_DIR}/src/*.*)
idf_component_register(SRCS ${app_sources})
```
In ESP-IDF v6.1.0, driver components (`esp_driver_i2s`, `esp_driver_gpio`) are modularized into independent components and are not part of `common_component_reqs`.
When including `driver/i2s_std.h` or `driver/gpio.h`, `src/CMakeLists.txt` must explicitly declare dependencies and include paths:
```cmake
FILE(GLOB_RECURSE app_sources ${CMAKE_SOURCE_DIR}/src/*.*)
idf_component_register(SRCS ${app_sources}
                       INCLUDE_DIRS "." "../include"
                       REQUIRES esp_driver_i2s esp_driver_gpio driver)
```

---

## 3. Hardware Analysis & Recommended Pin Definitions

### 3.1 INMP441 Interface Specifications
From `INMP441.pdf` and `MEMORY_ACOUSTIC_ARRAY.md`:
- Interface: Standard Philips $I^2S$, 1 SCK delay after WS edge.
- Data format: 24-bit signed two's complement transmitted MSB-first in 32-bit slots.
- Clocks: $f_{\text{SCK}} = 64 \times f_s$ (e.g. $1.024\text{ MHz}$ at $16\text{ kHz}$; $3.072\text{ MHz}$ at $48\text{ kHz}$).
- Supply: $3.3\text{ V}$ (`VDD`), Ground (`GND`).
- Channel selection (`L/R`):
  - `L/R` $\to$ `GND`: Left Channel (active when WS is LOW).
  - `L/R` $\to$ `VDD`: Right Channel (active when WS is HIGH).

### 3.2 ESP32 Pin Assignment Analysis
To prevent boot failures and peripheral conflicts:
- **Avoid Strapping Pins**: GPIO 0 (boot), GPIO 2 (boot/LED), GPIO 5 (timing), GPIO 12 (MTDI flash voltage — critical), GPIO 15 (MTDO boot log).
- **Avoid SPI Flash Pins**: GPIO 6–11 (connected to internal SPI flash).
- **Avoid UART0 Pins**: GPIO 1 (TX0) and GPIO 3 (RX0) must remain dedicated to USB serial telemetry at 115200 baud for the Serial Plotter.
- **Input-Only Pins**: GPIO 34, 35, 36, 39 cannot drive output signals (cannot be SCK or WS output).

### 3.3 Recommended Pin Map

#### Phase 1: Single Microphone
| INMP441 Pin | ESP32 GPIO | Direction | Function | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **`SCK`** (BCLK) | **GPIO 14** | ESP32 Output | I2S0 Bit Clock | Dedicated hardware clock out, non-strapping, safe. |
| **`WS`** (LRCK)  | **GPIO 27** | ESP32 Output | I2S0 Word Select | Non-strapping, avoids GPIO 15 boot-voltage hazard. |
| **`SD`** (Data)  | **GPIO 32** | ESP32 Input  | I2S0 Serial Data In | Clean general GPIO, full matrix routing support. |
| **`L/R`**        | **GND**     | Hardwired    | Left Channel | Required by user specification R3. |
| **`VDD`**        | **3.3V**    | Power        | Power Supply | Direct from ESP32 3V3 rail. |
| **`GND`**        | **GND**     | Ground       | Power Ground | Common ground rail. |

#### Roadmap Compatibility (Phase 2 & Phase 3: 3-Microphone Array)
The recommended Phase 1 pins integrate seamlessly into the 3-microphone array defined in `MEMORY_ACOUSTIC_ARRAY.md` Section 5:
- **Shared BCLK**: GPIO 14 (shared by Mics 1, 2, and 3)
- **Shared WS**: GPIO 27 (shared by Mics 1, 2, and 3)
- **SD0 (I2S0 Data)**: GPIO 32 (Mic 1: Left / GND; Mic 2: Right / VDD)
- **SD1 (I2S1 Data)**: GPIO 33 (Mic 3: Left / GND)

---

## 4. Modern ESP-IDF v6.1.0 I2S Driver API Alignment

Investigation of `components/esp_driver_i2s/include/driver/i2s_std.h` confirms the modern channel driver architecture required:

1. **Channel Handle Allocation**:
   ```c
   i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
   i2s_chan_handle_t rx_handle = NULL;
   ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, NULL, &rx_handle));
   ```

2. **Standard Mode Configuration**:
   ```c
   i2s_std_config_t std_cfg = {
       .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(16000), // or 48000
       .slot_cfg = {
           .data_bit_width = I2S_DATA_BIT_WIDTH_24BIT,
           .slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT,
           .slot_mode = I2S_SLOT_MODE_MONO,
           .slot_mask = I2S_STD_SLOT_LEFT,
           .ws_width = 32,
           .ws_pol = false,
           .bit_shift = true,
           .msb_right = false,
       },
       .gpio_cfg = {
           .mclk = I2S_GPIO_UNUSED,
           .bclk = GPIO_NUM_14,
           .ws = GPIO_NUM_27,
           .dout = I2S_GPIO_UNUSED,
           .din = GPIO_NUM_32,
           .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false },
       },
   };
   ESP_ERROR_CHECK(i2s_channel_init_std_mode(rx_handle, &std_cfg));
   ```

3. **Sample Extraction Arithmetic**:
   The INMP441 puts 24-bit data in the upper bits of a 32-bit slot:
   ```c
   int32_t raw_32 = rx_buf[i];
   int32_t sample_24 = raw_32 >> 8;          // Full 24-bit signed resolution
   int16_t sample_16 = (int16_t)(raw_32 >> 14); // Scaled for 16-bit processing/plotter
   ```

4. **Telemetry Output**:
   Formatted for standard Arduino / PlatformIO Serial Plotter:
   ```c
   printf("sample:%ld,rms:%ld,peak:%ld\r\n", (long)sample_24, (long)rms, (long)peak);
   ```

---

## 5. Verification Checkpoints for Implementer

1. Update `platformio.ini` to add `monitor_speed = 115200`.
2. Add `REQUIRES esp_driver_i2s esp_driver_gpio driver` and `INCLUDE_DIRS "." "../include"` to `src/CMakeLists.txt`.
3. Provide modular code architecture (`i2s_mic.h`/`.c` and `telemetry.h`/`.c` or clean modular structure in `src/`).
4. Include a lightweight Python verification script (e.g. `scripts/plot_serial.py`) using `pyserial` and `matplotlib` as required by acceptance criteria.

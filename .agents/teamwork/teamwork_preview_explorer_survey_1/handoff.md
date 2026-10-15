# Handoff Report: Codebase & Config Survey

**Agent**: Survey Explorer 1 (Codebase & Config Explorer)  
**Recipient**: Orchestrator (`d17832be-bb24-40e4-9ee2-0c353fd26745`)  
**Workspace**: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441`  
**Handoff Type**: Hard (Task Complete)  

---

## 1. Observation

1. **PlatformIO Configuration (`platformio.ini`)**:
   - Path: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\platformio.ini`
   - Content:
     ```ini
     [env:esp32dev]
     platform = espressif32
     board = esp32dev
     framework = espidf
     ```
   - Lines 11–14 define the single environment `[env:esp32dev]`. `monitor_speed` and `build_flags` are absent.

2. **Framework & Toolchain Installation**:
   - `sdkconfig.esp32dev` line 3:
     `# Espressif IoT Development Framework (ESP-IDF) 6.1.0 Project Configuration`
   - PlatformIO build execution via command `& "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run` output:
     ```
     PLATFORM: Espressif 32 (7.1.3) > Espressif ESP32 Dev Module
     HARDWARE: ESP32 240MHz, 320KB RAM, 4MB Flash
     PACKAGES:
      - framework-espidf @ 4.60100.0 (6.1.0)
      - tool-cmake @ 3.30.2
      - tool-ninja @ 1.9.0
      - toolchain-xtensa-esp-elf @ 15.2.0+20251204
     ```
   - Warning observed in build output:
     `Warning! Flash memory size mismatch detected. Expected 4MB, found 2MB!`
   - `sdkconfig.esp32dev` lines 676 and 690:
     `CONFIG_ESPTOOLPY_FLASHSIZE_2MB=y`
     `CONFIG_ESPTOOLPY_FLASHSIZE="2MB"`
   - Result: Build succeeded in 31.32s with exit code 0 (`firmware.elf` and `firmware.bin` generated; 141,721 bytes flash, 13,612 bytes RAM).

3. **Current Source Code & CMake Component Setup**:
   - `src/main.c` line 1: `void app_main() {}` (18 bytes).
   - `src/CMakeLists.txt` lines 4–6:
     ```cmake
     FILE(GLOB_RECURSE app_sources ${CMAKE_SOURCE_DIR}/src/*.*)
     idf_component_register(SRCS ${app_sources})
     ```
   - `project_description.json` lines 4119–4131 confirms `src` component has empty `reqs: []`, `priv_reqs: []`, and `include_dirs: []`.
   - Headers for modern I2S driver are located in `C:/Users/hp/.platformio/packages/framework-espidf/components/esp_driver_i2s/include/driver/i2s_std.h`.

4. **Project Memory & Documentation**:
   - `MEMORY_ACOUSTIC_ARRAY.md` exists in project root (11,900 bytes, 204 lines).
   - Section 1 defines INMP441 electrical timing: 24-bit audio in 32-bit slot, Philips mode, $f_{\text{SCK}} = 64 \times f_s$, MSB-aligned data (`sample_24 = raw_32 >> 8`).
   - Section 5 defines ESP32 multi-channel mapping: Dual I2S controllers (I2S0 & I2S1), 3 mics mapped Left-Right-Left (Mic 1 -> I2S0 L, Mic 2 -> I2S0 R, Mic 3 -> I2S1 L; Slot 4 I2S1 R discarded).
   - `INMP441.pdf` datasheet is present in root (6,466,944 bytes).
   - `include/`, `test/`, and `lib/` contain only default README files. No prior source or header files exist.
   - Grep search confirmed zero existing GPIO pin definitions in the repository.

---

## 2. Logic Chain

1. From **Observation 2**, the active toolchain is ESP-IDF v6.1.0 running on GCC 15.2.0 under PlatformIO Core 6.2.0. Therefore, all I2S code must utilize the modern driver (`driver/i2s_std.h`) rather than the deprecated legacy driver (`driver/i2s.h`).
2. From **Observation 3**, `src/CMakeLists.txt` registers `src` without specifying `REQUIRES` or `INCLUDE_DIRS`. Because ESP-IDF v6.1.0 isolates peripheral drivers into dedicated components (`esp_driver_i2s`, `esp_driver_gpio`), failing to declare `REQUIRES esp_driver_i2s esp_driver_gpio driver` in `src/CMakeLists.txt` will result in compilation or linkage errors when including `driver/i2s_std.h`.
3. From **Observation 1**, `platformio.ini` lacks `monitor_speed`. PlatformIO defaults to 9600 baud, which conflicts with user requirement R2 (`UART, 115200 baud`). Adding `monitor_speed = 115200` to `platformio.ini` is required.
4. From **Observation 2**, the flash size mismatch warning occurs because `sdkconfig.esp32dev` defaults to 2MB whereas `board = esp32dev` expects 4MB. Defining `CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y` in `sdkconfig.defaults` or setting `board_upload.flash_size = 2MB` will resolve this cleanly.
5. From **Observation 4**, no GPIO pins are currently assigned. On the ESP32 (`esp32dev`), UART0 uses GPIO 1 (TX) and GPIO 3 (RX) for console and serial plotter. Pins 6–11 are connected to SPI flash, and pins 0, 2, 5, 12, 15 have boot strapping functions (especially GPIO 12, which can cause boot flash brownout if driven). GPIO 34, 35, 36, 39 are input-only and cannot drive BCLK/WS. Therefore, selecting GPIO 14 (SCK), GPIO 27 (WS), and GPIO 32 (SD) provides an optimal, collision-free pin configuration that readily extends to Phase 2/3 (shared clock on GPIO 14/27, Mic 3 on GPIO 33).

---

## 3. Caveats

1. Physical hardware is not currently probed via serial port during this survey; all hardware assumptions are derived from the official INMP441 datasheet (`INMP441.pdf`), `MEMORY_ACOUSTIC_ARRAY.md`, and ESP32 technical reference manuals.
2. The PlatformIO CLI binary is located at `C:\Users\hp\.platformio\penv\Scripts\pio.exe` and is not in the system global PATH; build/run commands must reference this absolute path or invoke it through PlatformIO scripts.
3. No alternative interpretations considered: the environment is unambiguously ESP-IDF 6.1.0 on ESP32 Dev Module.

---

## 4. Conclusion

The project workspace is verified and fully ready for Phase 1 development. The baseline build succeeds with zero errors.

### Key Implementation Directives:
1. **Toolchain / Build**: Use `C:\Users\hp\.platformio\penv\Scripts\pio.exe run` for compiling.
2. **`platformio.ini`**: Add `monitor_speed = 115200`.
3. **`src/CMakeLists.txt`**: Add `REQUIRES esp_driver_i2s esp_driver_gpio driver` and `INCLUDE_DIRS "." "../include"`.
4. **Pin Allocation**:
   - `SCK` (BCLK): **GPIO 14**
   - `WS` (LRCK): **GPIO 27**
   - `SD` (Data In): **GPIO 32**
   - `L/R`: **GND** (Left Channel)
5. **API & Math**: Use `driver/i2s_std.h`, 24-bit data in 32-bit slot, Philips mode, `raw >> 8` for 24-bit audio extraction, streaming formatted telemetry `sample:VAL,rms:VAL,peak:VAL\r\n` over UART at 115200 baud.

---

## 5. Verification Method

To independently verify the observations and conclusions:
1. **Verify Toolchain & Build**:
   Run in PowerShell:
   ```powershell
   & "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run
   ```
   Expected output: `[SUCCESS]` in ~30 seconds, `firmware.elf` generated in `.pio/build/esp32dev/`.
2. **Verify ESP-IDF Version**:
   Inspect line 3 of `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\sdkconfig.esp32dev`.
   Expected text: `# Espressif IoT Development Framework (ESP-IDF) 6.1.0 Project Configuration`.
3. **Verify Component Paths**:
   Inspect `C:\Users\hp\.platformio\packages\framework-espidf\components\esp_driver_i2s\include\driver\i2s_std.h`.

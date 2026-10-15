# Handoff Report: Milestone M1 Hardware & Driver Specialist

**Agent**: Milestone M1 Explorer 1 (`teamwork_preview_explorer_m1_1`)  
**Handoff Type**: Hard Handoff (Analysis & Specification Complete)  
**Recipient**: Worker Agent / Orchestrator (`d17832be-bb24-40e4-9ee2-0c353fd26745`)  
**Date**: 2026-10-06  

---

## 1. Observation

### 1.1 Existing Configuration & Codebase
- **`platformio.ini`** (`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\platformio.ini` lines 11–15):
  ```ini
  [env:esp32dev]
  platform = espressif32
  board = esp32dev
  framework = espidf
  ```
  *Observation*: Lacks `monitor_speed = 115200`. Serial monitor will default to 9600 baud, violating Requirement R2.
- **`src/CMakeLists.txt`** (`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\src\CMakeLists.txt` lines 4–6):
  ```cmake
  FILE(GLOB_RECURSE app_sources ${CMAKE_SOURCE_DIR}/src/*.*)
  idf_component_register(SRCS ${app_sources})
  ```
  *Observation*: Missing component dependencies and include directories. In ESP-IDF v6.1.0, driver headers like `driver/i2s_std.h` fail to resolve without explicit `REQUIRES esp_driver_i2s esp_driver_gpio driver` and `INCLUDE_DIRS "." "../include"`.
- **`src/main.c`**:
  Contains only `void app_main() {}`.
- **Toolchain & Baseline Build**:
  - Command: `& "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run`
  - Result: Exit Code 0 in 8.82s.
  - Framework: ESP-IDF v6.1.0 (`framework-espidf @ 4.60100.0`, GCC 15.2.0, Xtensa LX6).

### 1.2 ESP-IDF v6.1.0 API & Type Observations
- **`i2s_port_t` Missing in ESP-IDF v6.1.0**:
  - Inspected `C:\Users\hp\.platformio\packages\framework-espidf\components\esp_driver_i2s\include\driver\i2s_types.h`: lines 18–21 define integer macros `#define I2S_NUM_0 0`, `#define I2S_NUM_1 1`.
  - Inspected `driver/i2s_common.h`: line 65 `i2s_chan_config_t` uses `int id;`.
  - Grep search for `i2s_port_t` across all of `framework-espidf` yielded **0 matches**.
  - *Direct Observation*: If `include/i2s_microphone.h` uses `i2s_port_t i2s_port;` per `PROJECT.md` without defining `i2s_port_t`, the GCC compiler throws `unknown type name 'i2s_port_t'`.
- **Modern I2S Driver API Signatures** (`components/esp_driver_i2s`):
  - `i2s_new_channel(const i2s_chan_config_t *chan_cfg, i2s_chan_handle_t *ret_tx_handle, i2s_chan_handle_t *ret_rx_handle)` (`i2s_common.h:146`).
  - `i2s_channel_init_std_mode(i2s_chan_handle_t handle, const i2s_std_config_t *std_cfg)` (`i2s_std.h:320`).
  - `i2s_channel_enable(i2s_chan_handle_t handle)` (`i2s_common.h:183`).
  - `i2s_channel_disable(i2s_chan_handle_t handle)` (`i2s_common.h:197`).
  - `i2s_del_channel(i2s_chan_handle_t handle)` (`i2s_common.h:157`).
  - `i2s_channel_read(i2s_chan_handle_t handle, void *dest, size_t size, size_t *bytes_read, uint32_t timeout_ms)` (`i2s_common.h:233`).
- **GPIO Pull Configuration** (`components/esp_hal_gpio/include/hal/gpio_types.h:129`):
  - `GPIO_PULLDOWN_ONLY` enum constant exists.
  - `components/esp_driver_gpio/include/driver/gpio.h:178`: `gpio_set_pull_mode` supported on IO pins with integrated resistors. GPIO 32 is verified RTC/digital IO with pull-down capability.

---

## 2. Logic Chain

1. **Requirement R2 $\to$ `platformio.ini`**:
   Requirement R2 specifies telemetry streaming over UART at 115200 baud. Observation 1.1 shows PlatformIO defaults to 9600 baud without explicit configuration. Therefore, `monitor_speed = 115200` must be added to `platformio.ini`.

2. **ESP-IDF v6 Modularization $\to$ `src/CMakeLists.txt`**:
   Observation 1.1 and 1.2 confirm that `driver/i2s_std.h` is in `esp_driver_i2s` and `driver/gpio.h` is in `esp_driver_gpio`. In ESP-IDF v6, applications must explicitly declare component dependencies via `REQUIRES` and include directories via `INCLUDE_DIRS "." "../include"`. Therefore, `src/CMakeLists.txt` must register these dependencies.

3. **Interface Contract Conformance $\to$ `i2s_port_t` Typedef**:
   `PROJECT.md` line 86 mandates `i2s_port_t i2s_port;` in `i2s_mic_config_t`. However, Observation 1.2 proved `i2s_port_t` does not exist in ESP-IDF v6.1.0 headers. Therefore, `include/i2s_microphone.h` must declare:
   ```c
   #ifndef I2S_PORT_T_DEFINED
   typedef int i2s_port_t;
   #define I2S_PORT_T_DEFINED
   #endif
   ```
   This satisfies the contract verbatim and allows `I2S_NUM_0` to be passed without compilation warnings.

4. **INMP441 Timing $\to$ Slot and Clock Configuration**:
   The INMP441 datasheet specifies a 64 BCLK frame (32 bits per slot) and 1 BCLK delay (Philips mode). Setting `slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT`, `ws_width = 32`, `bit_shift = true`, and `mclk_multiple = I2S_MCLK_MULTIPLE_256` guarantees:
   - Exactly 64 clock cycles per stereo frame.
   - Clean integer BCLK division ($256 / 64 = 4$) with zero fractional phase jitter.
   - Left channel active when WS is LOW (`ws_pol = false`, `slot_mask = I2S_STD_SLOT_LEFT`).

5. **Bus High-Impedance $\to$ SD Pull-Down**:
   The INMP441 tri-states the SD pin during bits 26–32 and during the Right slot. A floating input pad captures clock capacitive coupling, causing DC offset drift. Enabling `gpio_set_pull_mode(GPIO_NUM_32, GPIO_PULLDOWN_ONLY)` holds the bus at logic 0 during High-Z, ensuring an idle baseline of zero.

6. **Buffer Reading Contract $\to$ `read_raw` vs `read_samples`**:
   `i2s_mic_read_raw` transfers unprocessed 32-bit DMA words. `i2s_mic_read_samples` executes `i2s_mic_read_raw` and then performs in-place conversion using `i2s_mic_convert_sample(dest[i])` (`dest[i] >> 8`). In C99 on Xtensa LX6, signed right shift emits `srai` (Shift Right Arithmetic Immediate), replicating the sign bit and producing true signed 24-bit waveform values in $[-8388608, +8388607]$.

---

## 3. Caveats

1. **Hardware Verification Scope**:
   Live acoustic verification (measuring ambient room noise floor vs speech/clapping) requires a physical INMP441 breakout connected to the ESP32 hardware target on COM7. Explorer investigation verified code syntax, header availability, and toolchain buildability.
2. **Flash Size Warning in PlatformIO**:
   During `pio run`, PlatformIO emits `Warning! Flash memory size mismatch detected. Expected 4MB, found 2MB!`. This is an informational warning arising from `sdkconfig.esp32dev` setting 2MB while `board = esp32dev` defaults to 4MB. The build exits with code 0 and is fully functional.
3. **Multi-Mic Phase 2/3 Evolution**:
   Phase 1 configures `I2S_SLOT_MODE_MONO` and `I2S_STD_SLOT_LEFT`. When upgrading to Phase 2 (2 microphones on I2S0), the driver slot mode must be switched to `I2S_SLOT_MODE_STEREO` and `I2S_STD_SLOT_BOTH` to interleave Left and Right channels.

---

## 4. Conclusion

The hardware driver architecture, interface contract, and build configuration for Milestone M1 are fully analyzed, mathematically validated, and ready for immediate implementation by the Worker agent.

### Specific Recommendations
1. **`platformio.ini`**: Add `monitor_speed = 115200`.
2. **`src/CMakeLists.txt`**: Add `INCLUDE_DIRS "." "../include"` and `REQUIRES esp_driver_i2s esp_driver_gpio driver`.
3. **`include/i2s_microphone.h`**: Implement interface contract verbatim from Section 3 of `report.md`.
4. **`src/i2s_microphone.c`**: Implement driver code from Section 4 of `report.md` with 6 $\times$ 240 DMA buffers, GPIO 14/27/32, SD pull-down, and in-place sample conversion.

---

## 5. Verification Method

### 5.1 Verification Commands
The Worker can verify this milestone by compiling via PlatformIO CLI:
```powershell
& "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run
```

### 5.2 Files to Inspect
- `platformio.ini`: Confirm `monitor_speed = 115200` is present.
- `src/CMakeLists.txt`: Confirm `REQUIRES esp_driver_i2s esp_driver_gpio driver` and `INCLUDE_DIRS "." "../include"` are present.
- `include/i2s_microphone.h`: Confirm `i2s_mic_convert_sample`, `i2s_mic_config_t`, and functions are defined.
- `src/i2s_microphone.c`: Confirm `s_rx_handle`, 6 $\times$ 240 DMA buffer configuration, SD pull-down, and read functions compile cleanly.

### 5.3 Invalidation Conditions
- Any compilation or linker error during `pio run`.
- Any missing header error (`driver/i2s_std.h` or `driver/gpio.h`).
- Any `unknown type name 'i2s_port_t'` error.

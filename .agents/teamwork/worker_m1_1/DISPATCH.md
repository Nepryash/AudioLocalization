# DISPATCH: Worker M1 (Core Audio Engine & Configuration)

## Identity
- Archetype: teamwork_preview_worker
- Role: M1 Audio Engine Implementer
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m1_1\
- Parent Orchestrator: teamwork_preview_orchestrator_1 (Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745)

## Authoritative Inputs
MANDATORY: You MUST read:
1. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md`
3. Explorer reports for Milestone M1:
   - `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_1\report.md`
   - `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_spec_miner_m1_1\report.md`
   - `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_2\report.md`

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
You EXCLUSIVELY own:
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\platformio.ini`
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\src\CMakeLists.txt`
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\include\i2s_microphone.h`
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\src\i2s_microphone.c`

DO NOT modify files in `test/`, `tools/`, or downstream module files (`audio_dsp.*`, `telemetry.*`, `main.c`).

## Implementation Tasks
1. `platformio.ini`:
   Add `monitor_speed = 115200`.
2. `src/CMakeLists.txt`:
   Update component registration:
   ```cmake
   FILE(GLOB_RECURSE app_sources ${CMAKE_SOURCE_DIR}/src/*.*)
   idf_component_register(SRCS ${app_sources}
                          INCLUDE_DIRS "." "../include"
                          REQUIRES esp_driver_i2s esp_driver_gpio driver)
   ```
3. `include/i2s_microphone.h`:
   Implement interface contract declared in `PROJECT.md § Interface Contracts`:
   - Fallback `typedef int i2s_port_t;` for ESP-IDF v6 compatibility
   - Default definitions: `I2S_MIC_DEFAULT_SAMPLE_RATE` (16000), `I2S_MIC_DEFAULT_SCK_PIN` (14), `I2S_MIC_DEFAULT_WS_PIN` (27), `I2S_MIC_DEFAULT_SD_PIN` (32)
   - Configuration struct `i2s_mic_config_t`
   - Function signatures: `i2s_mic_init`, `i2s_mic_read_raw`, `i2s_mic_read_samples`, `i2s_mic_deinit`
   - Inline sample conversion helper `static inline int32_t i2s_mic_convert_sample(int32_t raw_32) { return raw_32 >> 8; }`
4. `src/i2s_microphone.c`:
   - Allocate RX channel using `i2s_new_channel` with role `I2S_ROLE_MASTER`, `dma_desc_num = 6`, `dma_frame_num = 240`.
   - Configure Philips standard mode with `i2s_channel_init_std_mode`:
     - Clock: `sample_rate_hz`, `clk_src = I2S_CLK_SRC_DEFAULT`, `mclk_multiple = I2S_MCLK_MULTIPLE_256`
     - Slot: `slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT`, `data_bit_width = I2S_DATA_BIT_WIDTH_24BIT`, `slot_mode = I2S_SLOT_MODE_MONO`, `slot_mask = I2S_STD_SLOT_LEFT`, `ws_width = 32`, `bit_shift = true`, `ws_pol = false`
     - GPIO: SCK (GPIO 14), WS (GPIO 27), SD (GPIO 32), MCLK (I2S_GPIO_UNUSED)
   - Internal pull-down: call `gpio_set_pull_mode(config->sd_pin, GPIO_PULLDOWN_ONLY)` after GPIO configuration.
   - Channel enable: `i2s_channel_enable(rx_handle)`.
   - Reading:
     - `i2s_mic_read_raw`: reads raw 32-bit DMA words via `i2s_channel_read`.
     - `i2s_mic_read_samples`: reads raw DMA words and converts in-place using `raw >> 8` into signed 24-bit waveform.
   - Deinitialization: `i2s_mic_deinit` disables channel and deletes channel, setting handles to NULL.
   - Robust error checking on all ESP-IDF driver calls.
   - Clean re-entrancy / state guard (prevent double initialization or reading uninitialized driver).

## Verification Requirements
Run the PlatformIO build to verify zero compilation and linking errors:
`& "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run`
Ensure the build succeeds with exit code 0.

## Output Requirements
Write your handoff report to:
`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m1_1\handoff.md`
Report the exact files modified, build output, memory usage, and verification results.
When complete, notify the orchestrator (Recipient: d17832be-bb24-40e4-9ee2-0c353fd26745).

## 2026-10-06T12:35:34Z
You are Worker M1 (Core Audio Engine Implementer).
Your working directory is: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m1_1\
Read your task assignment in: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m1_1\DISPATCH.md
Read the authoritative user request at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md
Read the project architecture and contracts at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md
Read the Explorer reports at:
- C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_1\report.md
- C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_spec_miner_m1_1\report.md
- C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_2\report.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Implement Milestone M1:
1. platformio.ini: add monitor_speed = 115200
2. src/CMakeLists.txt: update component registration with REQUIRES esp_driver_i2s esp_driver_gpio driver and INCLUDE_DIRS "." "../include"
3. include/i2s_microphone.h: implement interface contract
4. src/i2s_microphone.c: implement I2S standard driver, DMA buffers, GPIO pinout (14/27/32), SD pulldown, sample extraction (>> 8), and error handling.
5. Verify build with & "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run
Write your handoff report to handoff.md and notify the orchestrator (conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745).

# DISPATCH: Sub-Orchestrator M1 (Core Audio Engine & Configuration)

## Identity
- Archetype: orchestrator
- Role: Sub-orchestrator M1
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\sub_orch_m1\
- Parent Orchestrator: teamwork_preview_orchestrator_1 (Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745)

## Authoritative Inputs
MANDATORY: You MUST read:
1. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md`

## Scope: Milestone M1 — Core Audio Engine & Configuration
Deliverables:
1. `platformio.ini`: add `monitor_speed = 115200`
2. `src/CMakeLists.txt`: update component requirements: `REQUIRES esp_driver_i2s esp_driver_gpio driver` and `INCLUDE_DIRS "." "../include"`
3. `include/i2s_microphone.h`: C header declaring interface contract per `PROJECT.md § Interface Contracts`:
   - Config struct `i2s_mic_config_t` (sample_rate, sck_pin, ws_pin, sd_pin, i2s_port)
   - Function signatures: `i2s_mic_init`, `i2s_mic_read_raw`, `i2s_mic_read_samples`, `i2s_mic_deinit`
   - Inline sample conversion helper `i2s_mic_convert_sample(int32_t raw_32)` performing signed arithmetic `raw_32 >> 8`
4. `src/i2s_microphone.c`:
   - Modern ESP-IDF v6 `driver/i2s_std.h` configuration:
     - `i2s_new_channel` (RX master, DMA descriptors 6, frame count 240)
     - `i2s_channel_init_std_mode` with Philips standard format, `slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT`, `data_bit_width = I2S_DATA_BIT_WIDTH_24BIT`, `ws_width = 32`, `bit_shift = true`, `mclk_multiple = I2S_MCLK_MULTIPLE_256`
     - Pin configuration: SCK GPIO 14, WS GPIO 27, SD GPIO 32. Enable internal pull-down on SD pin (`gpio_set_pull_mode(sd_pin, GPIO_PULLDOWN_ONLY)`).
     - Robust error checking on all driver calls.
     - Sample conversion: reads DMA buffers and converts raw 32-bit words to signed 24-bit waveform (`>> 8`) without bit inversion or DC offset.
     - Architecture ready for future multi-channel expansion (I2S0 L/R, I2S1 L) per `MEMORY_ACOUSTIC_ARRAY.md`.
5. Unit tests / verification:
   - Build compiles cleanly via `& "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run` with 0 errors.

## Execution Procedure
Follow the Project Pattern:
1. Assess & write `SCOPE.md`, `BRIEFING.md`, `progress.md`.
2. Run iteration loop:
   - a. Spawn Explorer(s)
   - b. Spawn Worker (with Mandatory Integrity Warning)
   - c. Spawn Reviewers
   - d. Spawn Challengers
   - e. Spawn Forensic Auditor (`teamwork_preview_auditor`)
   - f. Gate check in `GATE_STATUS.md` (Pass only if builds pass, reviews approve, challengers approve, audit clean)
3. When complete, write `handoff.md` and send message to parent orchestrator (`d17832be-bb24-40e4-9ee2-0c353fd26745`).

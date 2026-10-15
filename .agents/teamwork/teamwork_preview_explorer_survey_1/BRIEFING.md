# BRIEFING — 2026-10-06T12:17:00Z

## Mission
Conduct a read-only survey of the SensorTechINMP441 codebase, PlatformIO configuration, ESP-IDF version, board target, pin definitions, and existing files to inform Phase 1 development.

## 🔒 My Identity
- Archetype: teamwork_preview_explorer
- Roles: Codebase & Config Explorer
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_1\
- Original parent: d17832be-bb24-40e4-9ee2-0c353fd26745
- Milestone: survey

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Write only inside working directory `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_1\`
- Output structured findings in report.md and handoff.md

## Current Parent
- Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745
- Updated: not yet

## Investigation State
- **Explored paths**: `platformio.ini`, `CMakeLists.txt`, `sdkconfig.esp32dev`, `src/main.c`, `src/CMakeLists.txt`, `include/`, `test/`, `lib/`, `MEMORY_ACOUSTIC_ARRAY.md`, `INMP441.pdf`, `driver/i2s_std.h`, `driver/i2s_common.h`, `.pio/build/esp32dev/project_description.json`.
- **Key findings**:
  1. Framework is ESP-IDF v6.1.0 (`framework-espidf @ 4.60100.0`, GCC 15.2.0, platform 7.1.3).
  2. PlatformIO executable is at `C:\Users\hp\.platformio\penv\Scripts\pio.exe`. Baseline build completes with code 0 in 31s.
  3. `platformio.ini` needs `monitor_speed = 115200`.
  4. `src/CMakeLists.txt` needs `REQUIRES esp_driver_i2s esp_driver_gpio driver` and `INCLUDE_DIRS "." "../include"`.
  5. Recommended collision-free pins: SCK = GPIO 14, WS = GPIO 27, SD = GPIO 32, L/R = GND.
  6. MEMORY_ACOUSTIC_ARRAY.md exists and specifies full 3-mic architecture across I2S0 and I2S1.
- **Unexplored areas**: None within the survey scope.

## Key Decisions Made
- Confirmed modern ESP-IDF `driver/i2s_std.h` APIs (channel handle, standard slot config, 32-bit slot with 24-bit data, bit shift `>> 8`).
- Selected safe GPIO pins: GPIO 14 (SCK), GPIO 27 (WS), GPIO 32 (SD).

## Artifact Index
- C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_1\BRIEFING.md — Persistent memory index
- C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_1\progress.md — Liveness heartbeat
- C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_1\report.md — Comprehensive survey report
- C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_1\handoff.md — 5-component hard handoff report

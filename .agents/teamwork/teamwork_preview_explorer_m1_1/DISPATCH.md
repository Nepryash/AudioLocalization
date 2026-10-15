# DISPATCH: Milestone M1 Explorer 1 (Hardware & Driver Specialist)

## Identity
- Archetype: teamwork_preview_explorer
- Role: M1 Hardware & Driver Explorer
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_1\
- Parent Orchestrator: teamwork_preview_orchestrator_1 (Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745)

## Authoritative Inputs
MANDATORY: You MUST read:
1. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md`
3. Survey reports in `.agents/teamwork/teamwork_preview_explorer_survey_1/report.md` and `teamwork_preview_spec_miner_survey_1/report.md`

## Milestone M1 Scope
Core Audio Engine & Configuration:
1. `platformio.ini`: `monitor_speed = 115200`
2. `src/CMakeLists.txt`: `REQUIRES esp_driver_i2s esp_driver_gpio driver`, `INCLUDE_DIRS "." "../include"`
3. `include/i2s_microphone.h`: interface contract for I2S microphone driver
4. `src/i2s_microphone.c`: hardware initialization with `driver/i2s_std.h`, DMA buffers (6 x 240 frames), Philips standard format, 32-bit slot width, 24-bit data width, 64 SCK/frame, GPIO 14/27/32, internal pull-down on SD, sample reading and conversion.

## Objective
Analyze and produce a detailed, implementation-ready technical recommendation for the Worker agent:
- Exact CMake and platformio.ini changes
- Complete C code structures, function signatures, and error checking for `i2s_microphone.h` and `i2s_microphone.c`
- DMA reading loop with zero underruns
- How to verify the compilation and build cleanly with `pio run`
DO NOT write source code files yourself (Explorers are read-only). Write recommendations to your report.

## Output Requirements
Write report to: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_1\report.md`
Write handoff to: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_1\handoff.md`
When done, notify the orchestrator (Recipient: d17832be-bb24-40e4-9ee2-0c353fd26745).


## 2026-10-06T12:26:54Z
You are Milestone M1 Explorer 1 (Hardware & Driver Specialist).
Your working directory is: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_1\
Read your task assignment in: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_1\DISPATCH.md
Read the authoritative user request at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md
Read the project architecture at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md

Analyze Milestone M1 (Core Audio Engine & Configuration):
- platformio.ini updates (monitor_speed = 115200)
- src/CMakeLists.txt updates (REQUIRES esp_driver_i2s esp_driver_gpio driver, INCLUDE_DIRS "." "../include")
- include/i2s_microphone.h interface contract implementation
- src/i2s_microphone.c driver implementation with modern driver/i2s_std.h, DMA buffers, GPIO pin configuration, pull-down on SD, robust error handling, and build verification.
Write your recommendations to report.md and handoff.md.
When done, notify the orchestrator (conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745).

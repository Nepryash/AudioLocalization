# DISPATCH: Worker M3 (Application Integration & Python Visualizer)

## Identity
- Archetype: teamwork_preview_worker
- Role: M3 Application & Tooling Implementer
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m3_1\
- Parent Orchestrator: teamwork_preview_orchestrator_1 (Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745)

## Authoritative Inputs
MANDATORY: You MUST read:
1. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md`
3. Survey reports:
   - `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_2\report.md`
4. Previous worker handoffs:
   - `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m1_1\handoff.md`
   - `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m2_1\handoff.md`

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
You EXCLUSIVELY own:
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\src\main.c`
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\tools\audio_plotter.py`

DO NOT modify files in `test/`, or files owned by M1/M2 (`i2s_microphone.*`, `audio_dsp.*`, `telemetry.*`, `platformio.ini`, `CMakeLists.txt`).

## Implementation Tasks

### 1. `src/main.c`: Complete ESP32 Application Orchestration
- Include headers: `esp_log.h`, `freertos/FreeRTOS.h`, `freertos/task.h`, `i2s_microphone.h`, `audio_dsp.h`, `telemetry.h`.
- Architecture per `PROJECT.md § Concurrency & Data Flow`:
  - `telemetry_init()` call to initialize FreeRTOS queue.
  - `i2s_mic_init(NULL)` (or with explicit default config: 16kHz, GPIO 14, 27, 32).
  - Create `telemetry_task` pinned to Core 0 (Priority 2, Stack 4096 bytes) executing `telemetry_task_run`.
  - Create `audio_capture_task` pinned to Core 1 (Priority 10, Stack 4096 bytes):
    - Reads chunks of 128 samples via `i2s_mic_read_samples` into a stack/static buffer.
    - Calls `audio_dsp_process_window` to compute `audio_telemetry_packet_t` (sample, RMS, peak).
    - Calls `telemetry_send_packet` to enqueue packet non-blocking to UART telemetry task.
    - Robust error checking on all calls: log warnings on DMA timeouts or queue drops, but never crash or deadlock.
  - In `app_main()`:
    - Log system startup banner with configuration details (Sample rate, Pins, Baud rate).
    - Initialize telemetry and I2S microphone with error checking.
    - Spawn FreeRTOS tasks on designated cores.
    - Clean main task exit (`vTaskDelete(NULL)`).

### 2. `tools/audio_plotter.py`: Lightweight Python Visualizer & Live Capture
- Standalone Python 3 script using `pyserial` (with graceful fallback if running headless or mock):
  - CLI argument parsing:
    - `--port PORT`: Serial COM port (default `COM7`)
    - `--baud BAUD`: Baud rate (default `115200`)
    - `--mock`: Run synthetic mock generator generating sine wave + noise + simulated clap impulses
    - `--duration SEC`: Run for fixed duration and exit
    - `--cli`: Text-based ANSI terminal VU-meter / plotter mode (headless friendly)
    - `--save-wav FILE`: Record received audio samples into a 16-bit / 24-bit PCM WAV file
  - Protocol parsing:
    - Parse lines formatted as `sample:VAL,rms:VAL` (or `sample:VAL,rms:VAL,peak:VAL`).
    - Robust line parsing: ignores startup boot messages or corrupt partial UART lines.
  - Interactive GUI mode (using `matplotlib` if available, or ANSI mode if matplotlib not installed / headless).
  - Metrics display: Current sample value, RMS level (dBFS and linear), Peak level, packet arrival rate (Hz).

## Verification Requirements
1. Build firmware:
   `& "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run`
   Must compile and link completely with exit code 0.
2. Verify Python script in mock mode:
   `& "C:\Users\hp\.platformio\penv\Scripts\python.exe" tools/audio_plotter.py --mock --duration 3 --cli`
   Must run cleanly, parse synthetic samples, display metrics, and exit 0.
3. Run full E2E test suite:
   `& "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py`
   Must pass 113/113 tests (100%).

## Output Requirements
Write your handoff report to:
`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m3_1\handoff.md`
When complete, notify the orchestrator (Recipient: d17832be-bb24-40e4-9ee2-0c353fd26745).

## 2026-10-06T13:13:37Z
You are Worker M3 (Application Integration & Python Visualizer Implementer).
Your working directory is: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m3_1\
Read your task assignment in: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m3_1\DISPATCH.md
Read the authoritative user request at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md
Read the project architecture and contracts at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Implement Milestone M3:
1. src/main.c: FreeRTOS application orchestration pinning audio_capture_task to Core 1 (priority 10) and telemetry_task to Core 0 (priority 2), reading I2S, processing DSP windows, enqueuing packets, and handling errors.
2. tools/audio_plotter.py: Lightweight Python verification & plotting script supporting live UART capture on COM7, ANSI terminal mode, synthetic --mock mode, and WAV export.
3. Verification:
   - Build firmware: & "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run
   - Test Python tool: & "C:\Users\hp\.platformio\penv\Scripts\python.exe" tools/audio_plotter.py --mock --duration 3 --cli
   - Test E2E test runner: & "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py
Write your handoff report to handoff.md and notify the orchestrator (conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745).

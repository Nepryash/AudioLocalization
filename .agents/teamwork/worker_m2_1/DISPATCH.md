# DISPATCH: Worker M2 (DSP Processing & Real-Time Telemetry Pipeline)

## Identity
- Archetype: teamwork_preview_worker
- Role: M2 DSP & Telemetry Implementer
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m2_1\
- Parent Orchestrator: teamwork_preview_orchestrator_1 (Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745)

## Authoritative Inputs
MANDATORY: You MUST read:
1. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md`
3. Explorer reports:
   - `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_2\report.md`
   - `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_2\report.md`

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
You EXCLUSIVELY own:
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\include\audio_dsp.h`
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\src\audio_dsp.c`
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\include\telemetry.h`
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\src\telemetry.c`

DO NOT modify files in `test/`, `tools/`, or files owned by M1 (`i2s_microphone.*`).

## Implementation Tasks
1. `include/audio_dsp.h` & `src/audio_dsp.c`:
   - Implement contract from `PROJECT.md § Interface Contracts`:
     - Constant `AUDIO_DSP_DECIMATION_FACTOR` (128)
     - Constant `AUDIO_DSP_FULL_SCALE` (8388607.0f)
     - Packet struct `audio_telemetry_packet_t` (`decimated_sample`, `rms_level`, `peak_level`)
     - Function `void audio_dsp_process_window(const int32_t *samples, size_t num_samples, audio_telemetry_packet_t *out_packet)`
   - Processing logic:
     - Window size $N = 128$ (or `num_samples`)
     - Downsampled sample: select middle or first sample (e.g. `samples[num_samples / 2]` or `samples[0]`) to represent acoustic waveform.
     - Peak level: `max(|samples[i]|)` across all samples in window, preserved in 24-bit range $[0, 8388607]$.
     - RMS level: normalize samples to float $x_i = \text{sample}_i / 8388607.0f$, compute sum of squares $\sum x_i^2$, compute $\text{rms}_{\text{norm}} = \sqrt{\sum x_i^2 / N}$, and convert back to 24-bit integer $\text{rms} = (\text{int32\_t})(\text{rms}_{\text{norm}} \times 8388607.0f)$. Ensure no overflow, handle NULL pointer or $N=0$ safely.
2. `include/telemetry.h` & `src/telemetry.c`:
   - Implement contract from `PROJECT.md § Interface Contracts`:
     - Queue creation: FreeRTOS queue `telemetry_queue` with depth 8 (holding `audio_telemetry_packet_t`).
     - `esp_err_t telemetry_init(void)`: allocates FreeRTOS queue.
     - `esp_err_t telemetry_send_packet(const audio_telemetry_packet_t *packet)`: pushes packet to `telemetry_queue` with non-blocking timeout `0` (`portNO_DELAY`). If queue full, drops packet and returns `ESP_ERR_TIMEOUT` (never stalls caller audio task).
     - `void telemetry_task_run(void *pvParameters)`: consumer task loop that blocks on `xQueueReceive(telemetry_queue, &packet, portMAX_DELAY)`, formats line into stack buffer: `"sample:%ld,rms:%ld\r\n"` (or optional `"sample:%ld,rms:%ld,peak:%ld\r\n"`), and writes to UART console (`printf` or `esp_rom_printf` or `uart_write_bytes`).
     - `esp_err_t telemetry_deinit(void)`: deletes queue if initialized.
   - Robust error checking on all queue and FreeRTOS operations.

## Verification Requirements
1. Build firmware via:
   `& "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run`
   Verify zero compilation or linking errors.
2. Execute E2E test suite:
   `& "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py`
   Verify all tests continue to pass 100%.

## Output Requirements
Write your handoff report to:
`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m2_1\handoff.md`
When done, notify the orchestrator (Recipient: d17832be-bb24-40e4-9ee2-0c353fd26745).


## 2026-10-06T12:57:53Z
You are Worker M2 (DSP Processing & Telemetry Pipeline Implementer).
Your working directory is: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m2_1\
Read your task assignment in: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\worker_m2_1\DISPATCH.md
Read the authoritative user request at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md
Read the project architecture and contracts at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Implement Milestone M2:
1. include/audio_dsp.h & src/audio_dsp.c: window RMS sqrtf(sum(sample^2)/N) and peak tracking over D=128 samples using single-precision FPU normalized float math.
2. include/telemetry.h & src/telemetry.c: FreeRTOS telemetry queue (depth 8, portNO_DELAY non-blocking push), telemetry consumer task writing "sample:%ld,rms:%ld\r\n" to UART.
3. Verify compilation: & "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run
4. Verify E2E tests: & "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py
Write your handoff report to handoff.md and notify the orchestrator (conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745).

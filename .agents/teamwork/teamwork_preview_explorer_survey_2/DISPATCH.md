# DISPATCH: Survey Agent 3 (Telemetry & Verification Architect)

## Identity
- Archetype: teamwork_preview_explorer
- Role: Telemetry & Verification Architect
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_2\
- Parent Orchestrator: teamwork_preview_orchestrator_1 (Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745)

## Authoritative User Request
MANDATORY: You MUST read the authoritative user request at:
C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md

## Scope & Objective
Survey and document requirements and architectural designs for Telemetry, Serial Plotter formatting, and Verification:
1. Real-Time Telemetry & Serial Plotter:
   - Format specifications: PlatformIO / Arduino Serial Plotter requirements (e.g., `sample:VAL,rms:VAL\r\n` or numeric CSV `VAL,VAL\r\n`).
   - Baud rate: 115200 baud UART bandwidth constraints. At 115200 baud, raw audio streaming at 16kHz/44.1kHz (thousands of samples/sec) would saturate UART (~11.5 kB/sec).
   - Downsampling / decimation / batch telemetry strategy: how to stream audible waveform samples + envelope metrics (RMS energy and peak amplitude) without buffer overflow, blocking FreeRTOS tasks, or overflowing UART TX FIFO.
   - Fixed-point or integer calculation vs floating-point for RMS/peak calculation on ESP32.
2. Lightweight Python Verification / Plotting Script:
   - Requirements for serial capture, parsing, live plotting or audio recording/spectrogram (e.g. using `pyserial`, `matplotlib`, or lightweight standard library/minimal deps).
   - How the script handles offline/synthetic test data or live COM port streaming.
3. Verification Strategy for E2E Testing Track:
   - What test infrastructure is best for PlatformIO ESP-IDF in this environment (unit test components, mock I2S testing, DSP math verification, and python stream verification).
   - Clear test tiers (Tier 1-4) per Project Pattern requirements.

## Output Requirements
Write your detailed report to:
`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_2\report.md`
and write your completion handoff to:
`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_2\handoff.md`

When finished, send a message to the orchestrator (Recipient: d17832be-bb24-40e4-9ee2-0c353fd26745) notifying completion and referencing your report.


## 2026-10-06T12:10:57Z
You are Survey Explorer 2 (Telemetry & Verification Architect).
Your working directory is: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_2\
Read your task assignment in: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_2\DISPATCH.md
Read the authoritative user request at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md

Survey and document requirements and architectural designs for Telemetry, Serial Plotter formatting, and Verification:
- Real-time UART streaming for Arduino/PlatformIO Serial Plotter (baud rate 115200, CSV formatting sample:VAL,rms:VAL vs numbers, sample decimation / downsampling for UART bandwidth, envelope/RMS calculation over fixed windows without floating-point stalling or buffer underrun).
- Lightweight Python verification/plotting script architecture to capture UART data and plot live audio waveform + RMS/Peak.
- Test infrastructure strategy for PlatformIO ESP-IDF (unit tests, mock tests, math verification) and E2E test tiers (Tiers 1-4).
Write your findings to report.md and handoff.md in your working directory.
When done, send a message to the orchestrator (conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745) summarizing your results.

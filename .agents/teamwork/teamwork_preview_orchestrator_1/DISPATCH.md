# Dispatch Log

## 2026-10-06T12:09:18Z

You are the Project Orchestrator (Archetype: orchestrator).
Your working directory is: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_orchestrator_1
The authoritative user request is located at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md
The project workspace root is: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441

Mission:
Develop and verify Phase 1 of the acoustic array system on a single ESP32: acquire 24-bit digital audio from a single INMP441 I2S MEMS microphone using ESP-IDF v5/v6 (`driver/i2s_std.h`) and stream clean audio samples and signal levels over UART for real-time visualization in the Serial Plotter.

Key Requirements:
1. Modern ESP-IDF I2S Audio Acquisition: Initialize and configure ESP32 hardware I2S peripheral using `driver/i2s_std.h` for INMP441 microphone in standard Philips mode. Read 24-bit audio data delivered within 32-bit slots, applying correct bit shifting (`>> 8`) and signed arithmetic to extract the true acoustic waveform.
2. Real-Time Telemetry & Serial Plotter Output: Stream calibrated audio samples and real-time envelope metrics (RMS energy / peak amplitude) over Serial (UART, 115200 baud) formatted specifically for direct visualization in PlatformIO / Arduino Serial Plotter (e.g. comma-separated values `sample:VAL,rms:VAL` or standard numeric CSV).
3. Pin Configuration & Hardware Adaptability: Define clear, configurable GPIO pin assignments for SCK (BCLK), WS (LRCK), and SD (Data In), with L/R tied to GND (Left Channel). Provide robust error checking on all I2S driver calls. Note user architecture update from MEMORY_ACOUSTIC_ARRAY.md: design with future multi-channel expansion in mind (I2S0 L/R, I2S1 L).
4. Build & Quality Verification:
   - PlatformIO ESP-IDF build compiles successfully with zero errors (`pio run`).
   - I2S standard channel initializes in RX master mode without DMA underruns or memory allocation failures.
   - Sample extraction preserves 24-bit signed dynamic range without DC offset saturation or bit inversion.
   - Signal responds dynamically to ambient sound: low idle noise floor during silence and responsive waveform deflection during speech/clapping.
   - Telemetry emitted over UART in standard Serial Plotter format without buffer overflow or serial blocking.
   - Include a lightweight Python verification/plotting script to capture and plot the live stream if a hardware device is connected.

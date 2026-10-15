# Original User Request

## 2026-10-06T12:05:06Z

Develop and verify Phase 1 of the acoustic array system on a single ESP32: acquire 24-bit digital audio from a single INMP441 I2S MEMS microphone using ESP-IDF v5/v6 (`driver/i2s_std.h`) and stream clean audio samples and signal levels over UART for real-time visualization in the Serial Plotter.

Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441
Integrity mode: development

## Requirements

### R1. Modern ESP-IDF I2S Audio Acquisition
Initialize and configure the ESP32 hardware I2S peripheral using `driver/i2s_std.h` for the INMP441 microphone in standard Philips mode. Read 24-bit audio data delivered within 32-bit slots, applying correct bit shifting (`>> 8`) and signed arithmetic to extract the true acoustic waveform.

### R2. Real-Time Telemetry & Serial Plotter Output
Stream calibrated audio samples and real-time envelope metrics (RMS energy / peak amplitude) over Serial (UART, 115200 baud) formatted specifically for direct visualization in PlatformIO / Arduino Serial Plotter (e.g., comma-separated values `sample:VAL,rms:VAL` or standard numeric CSV).

### R3. Pin Configuration & Hardware Adaptability
Define clear, configurable GPIO pin assignments for `SCK` (BCLK), `WS` (LRCK), and `SD` (Data In), with `L/R` tied to GND (Left Channel). Provide robust error checking on all I2S driver calls.

## Acceptance Criteria

### Build Verification
- [ ] PlatformIO ESP-IDF build compiles successfully with zero errors (`pio run`).

### I2S & Audio Quality Verification
- [ ] I2S standard channel initializes in RX master mode without DMA underruns or memory allocation failures.
- [ ] Sample extraction preserves 24-bit signed dynamic range without DC offset saturation or bit inversion.
- [ ] Signal responds dynamically to ambient sound: low idle noise floor during silence and responsive waveform deflection during speech/clapping.

### Telemetry & Visualization
- [ ] Telemetry data is emitted over UART in standard Serial Plotter format without buffer overflow or serial blocking.
- [ ] A lightweight Python verification/plotting script is included to capture and plot the live stream if a hardware device is connected.


## 2026-10-06T12:06:16Z

User update to project memory (MEMORY_ACOUSTIC_ARRAY.md Section 5):
The ESP32 has two stereo I2S controllers yielding 4 channel slots across both controllers:
- Controller 0: Left & Right
- Controller 1: Left & Right
For the 3 omnidirectional microphones, map them 1-Left, 1-Right, 1-Left:
- Mic 1 -> I2S0 Left (L/R to GND)
- Mic 2 -> I2S0 Right (L/R to VDD)
- Mic 3 -> I2S1 Left (L/R to GND)
- Slot 4 (I2S1 Right) is discarded/ignored.
Please take this mapping into account as you build out the architecture.

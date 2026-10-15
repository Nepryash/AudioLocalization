# HANDOFF: Telemetry, Serial Plotter & Verification Architecture

**Sender**: Survey Explorer 2 (Telemetry & Verification Architect)  
**Recipient**: Parent Orchestrator (`teamwork_preview_orchestrator_1`, ID: `d17832be-bb24-40e4-9ee2-0c353fd26745`)  
**Working Directory**: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_2\`  
**Milestone**: Phase 1 Architecture Survey Complete  

---

## 1. Observation

1. **Workspace Toolchain & Packages**:
   - PlatformIO Core is installed at `C:\Users\hp\.platformio\penv\Scripts\pio.exe` (v6.2.0).
   - ESP-IDF package: `framework-espidf @ 4.60100.0 (6.1.0)` located at `C:\Users\hp\.platformio\packages\framework-espidf`.
   - ESP-IDF v6 standard I2S header verified present at:
     `C:\Users\hp\.platformio\packages\framework-espidf\components\esp_driver_i2s\include\driver\i2s_std.h`.
   - ESP-IDF Unity test framework verified present at:
     `C:\Users\hp\.platformio\packages\framework-espidf\components\unity`.
   - Host Python environment: `Python 3.12.13` with `pyserial 3.5` present in PlatformIO environment (`C:\Users\hp\.platformio\penv\Scripts\python.exe`).
   - Host system lacks native desktop C compilers (`gcc`/`clang`), but possesses `toolchain-xtensa-esp-elf @ 15.2.0+20251204` cross-compiler.

2. **Connected Hardware**:
   - Device query via `Get-CimInstance Win32_PnPEntity` and `esptool.py` identified connected target:
     - Port: `COM7` (`USB-SERIAL CH340 (COM7)`, VID `1A86`, PID `7523`).
     - Chip: `ESP32-D0WD-V3` (revision v3.1), Dual Core @ 240 MHz, MAC: `20:50:0d:34:81:c4`.

3. **Baseline Compilation**:
   - Command: `& "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run`
   - Result: `========================= [SUCCESS] Took 15.58 seconds =========================`
   - Memory usage: RAM 13,612 B (4.2% of 320 KB), Flash 141,721 B (13.5% of 1 MB).

4. **Authoritative Project Memory & Requirements**:
   - `ORIGINAL_REQUEST.md`: R1 (acquire 24-bit audio using `driver/i2s_std.h`, `>> 8` bit shifting), R2 (stream calibrated samples and RMS/peak over UART 115200 baud in Serial Plotter format `sample:VAL,rms:VAL` or numeric CSV), R3 (configurable GPIOs, L/R to GND).
   - `MEMORY_ACOUSTIC_ARRAY.md` Section 5: Roadmaps 3-mic mapping across I2S0 (L/R) and I2S1 (L). Phase 1 establishes the single-channel foundation on I2S0 Left.

---

## 2. Logic Chain

1. **UART 115200 Baud Bandwidth Ceiling**:
   - *From Observation 4 (R2 requirement: 115200 baud)*: Standard 8-N-1 UART framing transmits 1 byte per 10 baud cycles, yielding a maximum theoretical throughput of $11,520 \text{ bytes/s}$.
   - *From Observation 4 (R1 requirement: 16 kHz or 48 kHz audio)*: Transmitting 16,000 text lines per second formatted as `sample:VAL,rms:VAL\r\n` (~22 bytes) requires $352,000 \text{ bytes/s}$ ($30.5\times$ maximum baud capacity).
   - *Inference*: Decimation / downsampling is mathematically required. Audio acquisition rate ($16\text{ kHz}$) and telemetry rate ($125\text{ Hz}$) must be decoupled. With decimation factor $D = 128$, the telemetry rate is $125 \text{ Hz}$, generating $\approx 3,000 \text{ bytes/s}$ ($26\%$ of UART capacity), ensuring an ample safety margin (>70%) against TX FIFO stalls.

2. **FreeRTOS Non-Blocking Architecture to Prevent DMA Underrun**:
   - *From Observation 1 & 3*: The ESP-IDF I2S driver relies on hardware DMA circular buffers. If the task reading DMA blocks on UART transmission when the 128-byte UART TX FIFO fills, the task misses the DMA buffer completion interrupt.
   - *Inference*: Audio capture and UART transmission must be isolated into two distinct FreeRTOS tasks:
     - `audio_capture_task` (Core 1, Priority 10) captures DMA frames and computes RMS/Peak.
     - `telemetry_task` (Core 0, Priority 2) formats CSV and writes to UART.
     - Inter-task communication uses a FreeRTOS queue (`telemetry_queue`, depth 8) with non-blocking enqueue (`portNO_DELAY`). If the queue fills, packets are dropped rather than stalling audio acquisition.

3. **Envelope / RMS Arithmetic Optimization on Xtensa LX6**:
   - *From Observation 2 (ESP32 Dual Core 240 MHz)*: The ESP32 Xtensa LX6 includes a hardware single-precision FPU with single-cycle multiply-accumulate (`MADD.S`), but lacks a 64-bit hardware integer divide instruction.
   - *From Observation 4 (24-bit audio range $[-8388608, +8388607]$)*: Squaring a 24-bit sample exceeds 32-bit integer range instantly ($7.03 \times 10^{13} > 2.14 \times 10^9$).
   - *Inference*: Normalizing 24-bit samples to single-precision float in $[-1.0\text{f}, +1.0\text{f}]$ allows single-cycle hardware FPU accumulation without overflow risk, executes full-window RMS via hardware `sqrtf()` in <0.04% of CPU core time, and directly matches downstream Phase 4/5 beamforming and FFT pipeline requirements.

4. **Serial Plotter Format Compatibility**:
   - *From Observation 4 (Serial Plotter requirement)*: Arduino IDE 2.x and PlatformIO Serial Plotter natively extract series names from key-value tokens: `sample:VAL,rms:VAL\r\n`.
   - *Inference*: Emitting `sample:%ld,rms:%ld\r\n` produces self-labeling traces in the GUI while remaining trivially parseable by Python regex.

5. **Test Strategy & Python Tooling**:
   - *From Observation 1 (no host GCC/Clang, Python 3.12 available) & Observation 2 (ESP32 on COM7)*:
   - *Inference*: A 4-tier test strategy is optimal:
     - **Tier 1**: Host-based Python unit tests (`test/test_dsp_math.py`) verifying bit extraction (`raw >> 8`), signed range preservation, RMS mathematical accuracy, and CSV regex compliance.
     - **Tier 2**: PlatformIO compilation check (`pio run -e esp32dev`).
     - **Tier 3**: Target HIL integration on COM7 (verifying `i2s_new_channel`, `i2s_channel_init_std_mode`, and DMA reading).
     - **Tier 4**: Acoustic validation via `tools/audio_plotter.py` (measuring silence noise floor, clapping impulse response, and live visualization).

---

## 3. Caveats

1. **USB-to-UART Host Latency**: On Windows, CH340 drivers typically buffer incoming bytes in 1 ms USB frames. While this causes slight packet batching at the millisecond scale in Python, it does not alter the average packet rate ($125 \text{ Hz}$).
2. **Ambient Noise Floor Variability**: Tier 4 silence test thresholds depend on acoustic environment. A threshold of $<-50 \text{ dBFS}$ is recommended for typical indoor rooms.
3. **Flash Size Warning in PlatformIO**: PlatformIO reports a 2MB vs 4MB flash warning during build. This does not block compilation or execution on the ESP32-D0WD-V3, but should be unified in `platformio.ini` or `sdkconfig.defaults`.

---

## 4. Conclusion

The architectural design for Phase 1 Telemetry and Verification is fully defined, mathematically validated, and ready for implementation:
1. **Telemetry Protocol**: Labeled CSV `sample:%ld,rms:%ld\r\n` (and optional `peak:%ld`), decimated by $D = 128$ for $125 \text{ Hz}$ transmission rate at 115200 baud ($\approx 3.0 \text{ kB/s}$, 26% UART load).
2. **Task Concurrency**: Decoupled FreeRTOS producer-consumer pattern (Core 1 high-priority audio capture, Core 0 low-priority UART telemetry, non-blocking queue) preventing DMA buffer underruns.
3. **DSP Math**: Hardware single-precision FPU normalized float accumulation for window RMS and peak detection.
4. **Verification Tool**: `tools/audio_plotter.py` featuring dual GUI and ANSI terminal modes, `--mock` synthetic generator, and audio WAV exporter.
5. **4-Tier Test Matrix**: Fully mapped across Host logic tests (Tier 1), PlatformIO compilation (Tier 2), HIL target driver validation on COM7 (Tier 3), and Acoustic excitation (Tier 4).

Full architectural details, mathematical proofs, and C header contracts are documented in:
`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_survey_2\report.md`

---

## 5. Verification Method

To independently verify the findings in this report:

1. **Verify Baseline Firmware Build (Tier 2)**:
   ```powershell
   & "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run -e esp32dev
   ```
   *Expected*: Build completes with `[SUCCESS]` in <20s.

2. **Verify Connected ESP32 Target (Tier 3)**:
   ```powershell
   & "C:\Users\hp\.platformio\penv\Scripts\python.exe" "C:\Users\hp\.platformio\packages\tool-esptoolpy\esptool.py" --port COM7 chip_id
   ```
   *Expected*: Identifies `ESP32-D0WD-V3` on `COM7`.

3. **Verify ESP-IDF v6 Header Availability**:
   ```powershell
   Test-Path "C:\Users\hp\.platformio\packages\framework-espidf\components\esp_driver_i2s\include\driver\i2s_std.h"
   ```
   *Expected*: Returns `True`.

4. **Verify Host Python Environment**:
   ```powershell
   python --version
   & "C:\Users\hp\.platformio\penv\Scripts\python.exe" -m pip list | Select-String "pyserial"
   ```
   *Expected*: Python 3.12 detected, `pyserial 3.5` present.

5. **Invalidation Conditions**:
   - If audio acquisition and UART transmission share a single blocking task, DMA underruns will invalidate the architecture under serial load.
   - If telemetry is transmitted without downsampling ($D=1$), UART TX FIFO will overflow within 5 milliseconds at 115200 baud.

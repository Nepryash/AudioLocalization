# Telemetry, Serial Plotter & Verification Architecture Report

**Project**: Acoustic Array Localization System — Phase 1 (Single INMP441 I2S Acquisition & Real-Time Visualization)  
**Author**: Survey Explorer 2 (Telemetry & Verification Architect)  
**Date**: October 2026  
**Target Hardware**: ESP32 Dev Module (`ESP32-D0WD-V3` revision v3.1, Dual Core @ 240 MHz, COM7)  
**Framework**: ESP-IDF v6.1.0 (`framework-espidf @ 4.60100.0`, GCC 15.2.0, PlatformIO Core 6.2.0)  

---

## Executive Summary

This report establishes the technical requirements, mathematical limits, system architecture, and verification strategy for **Phase 1** of the acoustic array system on the ESP32. Specifically, it resolves how to continuously acquire 24-bit audio from an INMP441 I2S microphone and stream telemetry over a 115200-baud UART connection to the PlatformIO / Arduino Serial Plotter without starving FreeRTOS tasks, dropping audio DMA buffers, or congesting the serial line.

### Key Discoveries & Architectural Decisions
1. **The UART 115200 Baud Bottleneck**: The maximum theoretical throughput at 115200 baud (8-N-1) is **11,520 bytes/sec** (~11.25 KiB/s). Streaming raw 16 kHz audio as text would require **>350,000 bytes/sec** (>30x baud capacity). Audio acquisition ($16\text{ kHz}$) and telemetry streaming ($125\text{ Hz}$) must be **decoupled** using a **decimation factor $D = 128$**.
2. **Serial Plotter Format**: Arduino IDE 2.x and PlatformIO Serial Plotter natively parse labeled key-value tokens: `sample:VAL,rms:VAL\r\n`. This format provides named legends ("sample" and "rms") in the GUI without manual configuration.
3. **Decoupled FreeRTOS Architecture**: Direct calls to `printf()` or `uart_write_bytes()` inside the I2S capture loop will block when the UART TX FIFO fills, causing fatal I2S DMA underruns. We design a **FreeRTOS Producer-Consumer pattern**: high-priority `audio_task` (Priority 10, Core 1) captures DMA frames and computes metrics; low-priority `telemetry_task` (Priority 2, Core 0) consumes from a non-blocking queue (`portNO_DELAY`) and transmits over UART.
4. **DSP Envelope / RMS Calculation**: ESP32's dual-core Xtensa LX6 features a **hardware single-precision Floating-Point Unit (FPU)** executing single-precision multiply-accumulate in 1 CPU cycle. Using normalized single-precision float ($[-1.0, +1.0]$) eliminates 64-bit integer overflow, avoids software integer 64-bit division, and computes full-window RMS in <0.04% of CPU core capacity.
5. **Lightweight Python Visualizer & Verification Suite**: We design `tools/audio_plotter.py` featuring dual visualizer modes (interactive Matplotlib oscilloscope and zero-dependency ANSI terminal VU-meter), offline synthetic signal generator (`--mock`), serial packet analyzer, and audio WAV exporter.
6. **4-Tier Verification Matrix**: Full compliance with the Project Pattern:
   - **Tier 1**: Host-based logic & DSP math unit tests (`python -m unittest discover test`) verifying bit extraction, sign extension, RMS math, and CSV formatting.
   - **Tier 2**: PlatformIO firmware build & static resource analysis (`pio run -e esp32dev`).
   - **Tier 3**: Hardware-in-the-Loop (HIL) peripheral integration on connected ESP32 (`COM7`).
   - **Tier 4**: Acoustic validation (silence noise floor, dynamic clapping response, real-time plotting).

---

## 1. Real-Time UART Streaming & Serial Plotter Architecture

### 1.1 Baud Rate & Bandwidth Analysis (115200 Baud Math)

The serial communication link operates under standard asynchronous framing:
- **Baud Rate**: $115,200 \text{ bps}$
- **Framing**: 8-N-1 (1 start bit, 8 data bits, no parity, 1 stop bit = 10 bits per byte).
- **Maximum Theoretical Throughput ($B_{\max}$)**:
  $$B_{\max} = \frac{115,200 \text{ bits/s}}{10 \text{ bits/byte}} = 11,520 \text{ bytes/s} \approx 11.25 \text{ KiB/s}$$
- **Safe Sustained Throughput ($B_{\text{safe}}$)**:
  Due to USB-to-UART bridge scheduling (CH340 / CP2102 1 ms USB polling interval), FreeRTOS task context switches, and UART TX FIFO latency, safe operating load must not exceed $70\% - 80\%$ of $B_{\max}$:
  $$B_{\text{safe}} \approx 8,000 \text{ to } 9,000 \text{ bytes/s}$$

#### Audio Data vs UART Capacity Comparison
| Audio Sample Rate ($f_s$) | Raw Data Type | Data Size/Sample | Required Bandwidth | Ratio vs 115200 Baud | Feasible over UART 115200? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **16 kHz** | Text `sample:VAL,rms:VAL\r\n` | ~22 bytes | $352,000 \text{ B/s}$ ($343.8 \text{ KiB/s}$) | **30.56x** | ❌ Impossible (massive overflow) |
| **16 kHz** | Text raw CSV `VAL,VAL\r\n` | ~16 bytes | $256,000 \text{ B/s}$ ($250.0 \text{ KiB/s}$) | **22.22x** | ❌ Impossible |
| **16 kHz** | Binary `int16_t` raw audio | 2 bytes | $32,000 \text{ B/s}$ ($31.25 \text{ KiB/s}$) | **2.78x** | ❌ Exceeds UART ceiling |
| **48 kHz** | Text `sample:VAL,rms:VAL\r\n` | ~22 bytes | $1,056,000 \text{ B/s}$ ($1.00 \text{ MiB/s}$) | **91.67x** | ❌ Impossible |
| **16 kHz (Decimated $D=64$)** | Text `sample:VAL,rms:VAL\r\n` | ~24 bytes | $6,000 \text{ B/s}$ ($5.86 \text{ KiB/s}$) | **0.52x** (52% load) | ✅ Feasible (smooth waveform) |
| **16 kHz (Decimated $D=128$)** | Text `sample:VAL,rms:VAL\r\n` | ~24 bytes | $3,000 \text{ B/s}$ ($2.93 \text{ KiB/s}$) | **0.26x** (26% load) | ✅ **Optimal (high safety margin)** |
| **48 kHz (Decimated $D=384$)** | Text `sample:VAL,rms:VAL\r\n` | ~24 bytes | $3,000 \text{ B/s}$ ($2.93 \text{ KiB/s}$) | **0.26x** (26% load) | ✅ Optimal for 48 kHz |

---

### 1.2 Serial Plotter Formatting Standards

Visualizers interpret incoming serial text using distinct parsing models. The telemetry format must be fully compatible across standard embedded tooling:

#### 1. Arduino IDE 2.x Serial Plotter
- **Syntax**: `label1:value1,label2:value2\r\n` (comma, tab, or space delimited).
- **Behavior**: Automatically extracts variable names `label1` and `label2` and creates color-coded graph legends.
- **Example**: `sample:125430,rms:41200\r\n`

#### 2. PlatformIO / VS Code Serial Plotter
- **Extensions**: *Serial Plotter* (François Campagno), *Teleplot*.
- **Syntax**: Supports both `label:value,label:value\r\n` and raw numeric CSV `value1,value2\r\n`.
- Teleplot also supports prefix syntax: `>sample:125430,rms:41200\n`.

#### 3. Arduino IDE 1.8.x Legacy Serial Plotter
- **Syntax**: `value1,value2\r\n` or `label:value1 label:value2\r\n`.

#### Telemetry Format Recommendation
We recommend the dual-variable labeled key-value standard:
```text
sample:%ld,rms:%ld\r\n
```
Optionally including peak amplitude:
```text
sample:%ld,rms:%ld,peak:%ld\r\n
```
- **Line Length**: 20–32 ASCII characters including `\r\n`.
- **Compile-Time Switch**: In `telemetry.h`:
  ```c
  #define TELEMETRY_FORMAT_LABELED  1  // "sample:VAL,rms:VAL\r\n"
  #define TELEMETRY_FORMAT_RAW_CSV  0  // "VAL,VAL\r\n"
  ```
  Setting `TELEMETRY_FORMAT_LABELED` provides labeled traces out of the box in Arduino 2.x and PlatformIO.

---

### 1.3 Decimation & Subsampling Strategy

To transmit meaningful audio information without exceeding 115200 baud, we decouple the high-rate audio acquisition from the low-rate telemetry transmission:

```
[INMP441 Microphone] 
        │ 16 kHz / 48 kHz (24-bit I2S Philips)
        ▼
[ESP32 I2S DMA Buffer] (Frames of N_dma = 256 samples, 16 ms)
        │
        ├────────────────────────────────────────┐
        ▼                                        ▼
[Full-Window DSP Metrics]            [Subsampled Waveform]
- Window RMS Energy (over 128 samples) - Instantaneous sample at decimation interval
- Window Peak Amplitude (over 128 samples)
        │                                        │
        └──────────────────┬─────────────────────┘
                           ▼
            [Telemetry Packet (125 Hz)]
            sample:VAL,rms:VAL,peak:VAL
                           │
                           ▼
            [UART TX (115200 Baud, ~3 kB/s)]
```

#### Why Subsampling Alone Is Insufficient
- If we merely transmit every 128th sample without window energy calculation, brief acoustic impulses (hand claps, sharp clicks, consonant transients) occurring between decimation points will be completely skipped (spatial/temporal aliasing).
- **The Dual-Path Strategy**:
  1. **Instantaneous Decimated Sample (`sample`)**: Picks the current audio sample at the decimation boundary, allowing the visualizer to trace the low-frequency acoustic waveform and pitch oscillations (~100 Hz to 250 Hz fundamental human voice frequencies).
  2. **Window Energy Envelope (`rms` & `peak`)**: Calculated over **all 128 samples** in the window. No transient is lost. If a 1-sample clap occurs, `peak` captures its maximum absolute deflection, and `rms` captures the integrated acoustic energy.

#### Window Size Parameterization
- At $f_s = 16,000 \text{ Hz}$:
  - Window $N_{\text{win}} = 128$ samples ($8.0 \text{ ms}$ window length).
  - Telemetry output rate = $16,000 / 128 = 125.0 \text{ Hz}$.
  - Serial throughput = $125 \times 24 \text{ bytes} \approx 3,000 \text{ bytes/s}$ ($26.0\%$ of UART capacity).
- At $f_s = 48,000 \text{ Hz}$:
  - Window $N_{\text{win}} = 384$ samples ($8.0 \text{ ms}$ window length).
  - Telemetry output rate = $48,000 / 384 = 125.0 \text{ Hz}$.
  - Serial throughput remains identical ($3,000 \text{ bytes/s}$).

---

### 1.4 Non-Blocking FreeRTOS Task Architecture

#### The Buffer Underrun Problem
The ESP32 I2S peripheral uses circular DMA descriptors. While the CPU reads one descriptor, the hardware DMA engine fills the next.
- If a task calls `printf()` or `uart_write_bytes(..., portMAX_DELAY)` inside the I2S loop:
  - If the host PC serial terminal pauses or USB buffer backs up, the UART TX FIFO fills (128 bytes).
  - `uart_write_bytes` blocks for multiple milliseconds.
  - The I2S DMA buffers continue filling with live microphone audio.
  - When all DMA buffers fill, incoming audio frames are dropped (**DMA underrun / overflow**).
  - This results in audible pops, permanent phase loss between channels, and corrupted signals.

#### The Producer-Consumer Solution
We decouple audio acquisition and telemetry into separate FreeRTOS tasks with isolated priorities and core affinity:

```
 CORE 1 (Real-Time Audio DSP)                CORE 0 (System & Telemetry)
 ─────────────────────────────                ───────────────────────────
 ┌───────────────────────────┐
 │    audio_capture_task     │
 │    (Priority 10)          │
 └─────────────┬─────────────┘
               │ 1. Read I2S DMA (i2s_channel_read)
               │ 2. Extract 24-bit samples (>> 8)
               │ 3. Accumulate RMS & Peak over N_win
               │ 4. xQueueSend(..., portNO_DELAY)
               ▼
 ┌───────────────────────────┐
 │ telemetry_queue (depth: 8)│ ◄─── If full, drop packet immediately!
 └─────────────┬─────────────┘      (Audio task NEVER blocks)
               │
               │ xQueueReceive(..., portMAX_DELAY)
               ▼
                                              ┌───────────────────────────┐
                                              │      telemetry_task       │
                                              │      (Priority 2)         │
                                              └─────────────┬─────────────┘
                                                            │ 1. snprintf(buf, ...)
                                                            │ 2. uart_write_bytes(...)
                                                            ▼
                                              ┌───────────────────────────┐
                                              │  UART0 TX (COM7 / 115200) │
                                              └───────────────────────────┘
```

#### Task Specifications
1. **`audio_capture_task`**:
   - **Priority**: 10 (High priority, higher than standard system tasks).
   - **Core Pinned**: Core 1 (dedicated to signal processing).
   - **Stack Size**: 4096 bytes (accommodates FPU context and DMA frame pointers).
   - **Execution Loop**:
     ```c
     i2s_channel_read(rx_chan, dma_buffer, sizeof(dma_buffer), &bytes_read, portMAX_DELAY);
     // Process samples, calculate RMS and Peak...
     if (window_complete) {
         telemetry_msg_t msg = {
             .sample = decimated_sample,
             .rms = calculated_rms,
             .peak = calculated_peak
         };
         // Non-blocking send: if queue is full, drop packet, DO NOT BLOCK
         xQueueSend(s_telemetry_queue, &msg, 0);
     }
     ```
2. **`telemetry_task`**:
   - **Priority**: 2 (Low priority, runs in background).
   - **Core Pinned**: Core 0 (shares core with WiFi/BT and system idle).
   - **Stack Size**: 3072 bytes.
   - **Execution Loop**:
     ```c
     telemetry_msg_t msg;
     if (xQueueReceive(s_telemetry_queue, &msg, portMAX_DELAY) == pdTRUE) {
         char line[48];
         int len = snprintf(line, sizeof(line), "sample:%ld,rms:%ld,peak:%ld\r\n",
                            (long)msg.sample, (long)msg.rms, (long)msg.peak);
         uart_write_bytes(UART_NUM_0, line, len);
     }
     ```

---

### 1.5 Envelope, RMS & Peak Detection Algorithm Design

#### Mathematical Definition
For a discrete audio window of $N$ samples $x[0], x[1], \dots, x[N-1]$:
- **Peak Amplitude ($V_{\text{peak}}$)**:
  $$V_{\text{peak}} = \max_{i=0}^{N-1} |x[i]|$$
- **Root Mean Square ($V_{\text{RMS}}$)**:
  $$V_{\text{RMS}} = \sqrt{\frac{1}{N} \sum_{i=0}^{N-1} x[i]^2}$$

#### Precision & Dynamic Range on 24-bit Audio
INMP441 audio is 24-bit two's complement integer:
$$x[i] \in [-8,388,608, \ +8,388,607]$$
- Maximum squared value for a single sample:
  $$x_{\max}^2 = (-8,388,608)^2 \approx 7.03687 \times 10^{13}$$
- Sum of squares over $N = 128$ samples:
  $$\sum_{i=0}^{127} x[i]^2 \le 128 \times 7.03687 \times 10^{13} \approx 9.007 \times 10^{15}$$
- **Integer Limits**:
  - $2^{31} - 1 \approx 2.147 \times 10^9 \implies$ **32-bit integer overflows instantly on a single sample!**
  - $2^{63} - 1 \approx 9.223 \times 10^{18} \implies$ **64-bit unsigned integer (`uint64_t`) holds up to $131,072$ samples without overflow.**

#### Comparison: Single-Precision FPU vs Fixed-Point Integer
| Metric | Option A: Hardware Single-Precision FPU (Float) | Option B: 64-bit Integer Fixed-Point |
| :--- | :--- | :--- |
| **Input Normalization** | $s_f = \frac{x[i]}{8388608.0\text{f}} \in [-1.0\text{f}, +1.0\text{f}]$ | Down-shift to 16-bit: $s_{16} = x[i] \gg 8$ |
| **Accumulator** | `float sum_sq = 0.0f;` | `uint64_t sum_sq_64 = 0;` |
| **Instruction per Sample** | Single-cycle `MADD.S` (FPU MAC) | 32x32 mul $\to$ 64-bit + 64-bit add |
| **CPU Cycles per Sample** | **~2 to 3 CPU cycles** | **~5 to 8 CPU cycles** |
| **Window Mean Calculation** | `float mean = sum_sq * (1.0f / N);` (1 cycle mul) | 64-bit software integer divide (Xtensa lacks 64-bit div) |
| **Square Root** | Hardware `sqrtf()` (~30 cycles) | Integer sqrt approximation loop (~35 cycles) |
| **Dynamic Range** | Mantissa: 24 bits, Exponent: 8 bits (no overflow possible) | Must guard against accumulator overflow |
| **Acoustic Calibrations** | Direct conversion to dBFS: $20 \log_{10}(V_{\text{RMS}})$ | Requires log lookup table |
| **Downstream Compatibility** | Directly compatible with Phase 4/5 FFT and GCC-PHAT | Requires later float conversion |

#### Recommended Implementation
The ESP32 Xtensa LX6 hardware single-precision FPU is **faster and cleaner** than 64-bit integer division:

```c
typedef struct {
    float sum_squares;
    float peak_abs;
    uint32_t count;
    uint32_t window_size;
} dsp_envelope_t;

static inline void dsp_envelope_init(dsp_envelope_t *env, uint32_t window_size) {
    env->sum_squares = 0.0f;
    env->peak_abs = 0.0f;
    env->count = 0;
    env->window_size = window_size;
}

static inline bool dsp_envelope_push(dsp_envelope_t *env, int32_t sample_24, 
                                     int32_t *out_rms, int32_t *out_peak) {
    // Normalize to [-1.0f, +1.0f]
    float sf = (float)sample_24 * (1.0f / 8388608.0f);
    float abs_sf = fabsf(sf);
    
    if (abs_sf > env->peak_abs) {
        env->peak_abs = abs_sf;
    }
    env->sum_squares += sf * sf;
    env->count++;
    
    if (env->count >= env->window_size) {
        float mean_sq = env->sum_squares / (float)env->window_size;
        float rms_f = sqrtf(mean_sq);
        
        // Scale back to 24-bit range for Serial Plotter display
        *out_rms = (int32_t)(rms_f * 8388607.0f);
        *out_peak = (int32_t)(env->peak_abs * 8388607.0f);
        
        // Reset accumulator
        env->sum_squares = 0.0f;
        env->peak_abs = 0.0f;
        env->count = 0;
        return true; // Window completed
    }
    return false;
}
```

---

## 2. Lightweight Python Verification & Plotting Script Architecture

### 2.1 Tool Blueprint: `tools/audio_plotter.py`

To satisfy Acceptance Criteria ("A lightweight Python verification/plotting script is included to capture and plot the live stream if a hardware device is connected"), we design a standalone Python utility located at `tools/audio_plotter.py`.

#### Key Design Capabilities
1. **Dual Operating Modes**:
   - **Mode A: Live Graphical GUI (Matplotlib)**: Dual-pane live updating oscilloscope. Top pane: live audio waveform ($250 \text{ Hz}$ window); Bottom pane: live RMS energy & Peak history over time with dBFS grid.
   - **Mode B: Terminal ANSI VU-Meter (Zero GUI Dependencies)**: High-speed live ASCII bar graph visualizer displaying instantaneous RMS energy in dBFS, peak hold, clipping indicator, packet rate, and packet loss counter. Operates in headless environments, over SSH, and without GUI libraries.
2. **Flexible Ingestion Pipeline**:
   - **Live Serial**: Automatically detects or connects to specified COM port (`COM7` default) at 115200 baud.
   - **Synthetic Mock Mode (`--mock`)**: Built-in signal generator produces synthetic 440 Hz / 1 kHz tones, white noise, and acoustic impulse claps formatted as `sample:VAL,rms:VAL\r\n`. Enables full offline pipeline verification without hardware.
   - **CSV Replay Mode (`--replay <file.csv>`)**: Replays recorded serial streams for post-test verification.
3. **Stream Diagnostic Engine**:
   - Real-time line parsing with regex fallback.
   - Packet arrival rate measurement (Hz).
   - Frame loss and corruption detection.
   - DC Offset calculation: $\text{DC} = \frac{1}{M}\sum x_i$ (verifies signed bit-shift correctness).
   - Noise floor and SNR estimation.
4. **Data Exporter**:
   - `--csv <path>`: Dumps raw timestamped samples to CSV.
   - `--wav <path>`: Exports acquired audio to standard 16-bit PCM WAV file.

---

### 2.2 Serial Ingestion & Fault-Tolerant Stream Parser

ESP32 bootloader prints diagnostic text (`rst:0x1 (POWERON_RESET),boot:0x13...`) at boot time. The parser must ignore non-telemetry log lines and maintain lock on telemetry packets.

```python
import re

TELEMETRY_REGEX = re.compile(
    r"(?:sample:\s*(?P<sample>-?\d+))"
    r"(?:,\s*rms:\s*(?P<rms>\d+))"
    r"(?:,\s*peak:\s*(?P<peak>\d+))?",
    re.IGNORECASE
)

RAW_CSV_REGEX = re.compile(
    r"^(?P<sample>-?\d+),\s*(?P<rms>\d+)(?:,\s*(?P<peak>\d+))?$"
)

def parse_telemetry_line(line: str):
    """
    Parses a telemetry line in either labeled format or raw CSV format.
    Returns dict {'sample': int, 'rms': int, 'peak': int} or None.
    """
    line = line.strip()
    if not line:
        return None
    
    # Try labeled format first
    m = TELEMETRY_REGEX.search(line)
    if m:
        sample = int(m.group("sample"))
        rms = int(m.group("rms"))
        peak = int(m.group("peak")) if m.group("peak") else abs(sample)
        return {"sample": sample, "rms": rms, "peak": peak}
    
    # Fallback to raw CSV format
    m = RAW_CSV_REGEX.match(line)
    if m:
        sample = int(m.group("sample"))
        rms = int(m.group("rms"))
        peak = int(m.group("peak")) if m.group("peak") else abs(sample)
        return {"sample": sample, "rms": rms, "peak": peak}
    
    return None # Non-telemetry line (e.g. bootloader or log output)
```

---

### 2.3 Acoustic Verification Metrics Engine

The Python script calculates five quantitative quality indicators:

1. **DC Offset Ratio**:
   $$\text{Ratio}_{\text{DC}} = \frac{|\frac{1}{N}\sum_{i=1}^N x_i|}{8,388,608}$$
   *Pass criteria*: $\text{Ratio}_{\text{DC}} < 0.02$ (<2% of full scale). Confirms signed arithmetic (`>> 8`) preserves zero center.
2. **Idle Noise Floor (dBFS)**:
   $$\text{Floor}_{\text{dBFS}} = 20 \log_{10} \left( \frac{\text{RMS}_{\text{silence}}}{8,388,608} \right)$$
   *Pass criteria*: $\text{Floor}_{\text{dBFS}} < -50 \text{ dBFS}$ in quiet room.
3. **Dynamic Crest Factor (Clap Response)**:
   $$\text{Crest Factor} = \frac{\text{Peak}}{\text{RMS}}$$
   *Pass criteria*: During clapping/speech, crest factor rises above $> 12 \text{ dB}$, confirming sharp impulse response.
4. **Packet Arrival Rate**:
   $$\text{Rate} = \frac{\Delta N}{\Delta t}$$
   *Pass criteria*: $125 \text{ Hz} \pm 5 \text{ Hz}$ (or $250 \text{ Hz} \pm 10 \text{ Hz}$).
5. **Packet Loss Rate**:
   $$\text{Loss Rate} = \frac{N_{\text{corrupt}}}{N_{\text{total}}} \times 100\%$$
   *Pass criteria*: $< 0.1\%$ after boot sequence.

---

### 2.4 Terminal ANSI Visualizer Mode (ASCII Meter)

When `--no-gui` is specified or Matplotlib is unavailable:

```text
======================= LIVE AUDIO TELEMETRY =======================
 Port: COM7 @ 115200 baud | Rate: 125.2 Hz | Loss: 0.0% | Status: OK
────────────────────────────────────────────────────────────────────
 Sample : [                    |======             ] +142,850
 RMS    : [████████████████████░░░░░░░░░░░░] -34.2 dBFS (  162,100)
 Peak   : [█████████████████████████░░░░░░░] -18.5 dBFS (  984,300) [PEAK]
────────────────────────────────────────────────────────────────────
 DC Offset: +0.08% FS | Noise Floor: -58.2 dBFS | Clipping: NONE
 [Ctrl+C to stop and save audio summary]
```

---

## 3. Test Infrastructure Strategy & 4-Tier Verification Matrix

### 3.1 Verification Hierarchy Overview

Following the Project Pattern standards, verification is divided into 4 ascending validation tiers:

```
┌─────────────────────────────────────────────────────────────┐
│  Tier 4: Acoustic Validation & End-to-End System Performance│
│  (Live microphone, acoustic stimulus, Serial Plotter GUI)   │
├─────────────────────────────────────────────────────────────┤
│  Tier 3: Hardware-in-the-Loop (HIL) Driver Integration     │
│  (Target ESP32 on COM7, I2S DMA streaming, UART rate check) │
├─────────────────────────────────────────────────────────────┤
│  Tier 2: Static Analysis & Firmware Build Verification      │
│  (pio run -e esp32dev, zero warnings, memory limits)        │
├─────────────────────────────────────────────────────────────┤
│  Tier 1: Host-based Unit Tests (Logic & DSP Math)           │
│  (python -m unittest, bit shift, sign extension, RMS math)   │
└─────────────────────────────────────────────────────────────┘
```

---

### 3.2 Tier 1: Host-based Unit Tests (Logic & DSP Math Verification)

- **Objective**: Deterministic verification of arithmetic and extraction algorithms without requiring MCU flashing.
- **Test Suite Location**: `test/test_dsp_math.py`
- **Execution**:
  ```powershell
  python -m unittest test/test_dsp_math.py
  ```

#### Detailed Test Cases
1. `test_24bit_slot_extraction_positive_full_scale`:
   - Raw input: `0x7FFFFF00` (24-bit max positive, padded with `0x00`).
   - Expected: `(int32_t)0x7FFFFF00 >> 8 == +8388607` (`0x7FFFFF`).
2. `test_24bit_slot_extraction_negative_full_scale`:
   - Raw input: `0x80000000` (24-bit max negative, padded with `0x00`).
   - Expected: `(int32_t)0x80000000 >> 8 == -8388608` (`0xFF800000`).
   - Verifies arithmetic right shift performs two's complement sign extension.
3. `test_24bit_slot_extraction_small_values`:
   - Raw input: `0x00000100` $\to +1$.
   - Raw input: `0xFFFFFF00` $\to -1$.
   - Raw input: `0x00000000` $\to 0$.
4. `test_rms_known_waveforms`:
   - **DC Signal**: $x[i] = 1,000,000 \implies \text{RMS} = 1,000,000 \ (\pm 1)$.
   - **Sine Wave**: $x[i] = A \sin(2\pi f t)$ with $A = 2,000,000 \implies \text{RMS} = \frac{A}{\sqrt{2}} \approx 1,414,213 \ (\pm 1\%)$.
   - **Square Wave**: $x[i] = \pm 1,500,000 \implies \text{RMS} = 1,500,000 \ (\pm 1)$.
   - **Silence**: $x[i] = 0 \implies \text{RMS} = 0$.
5. `test_peak_tracking`:
   - Array containing $+300,000$, $-850,000$, $+120,000 \implies \text{Peak} = 850,000$.
6. `test_serial_plotter_format_regex`:
   - Formatted string `sample:1250,rms:340\r\n` must match `^sample:-?[0-9]+,rms:[0-9]+(\r\n|\n)$`.
   - String length must remain $< 40$ bytes to guarantee stack safety.
7. `test_stream_parser_recovery`:
   - Inject corrupted garbage bytes, incomplete lines, and boot messages; verify parser recovers valid packets on the next clean line.

---

### 3.3 Tier 2: Static Analysis & Firmware Build Verification

- **Objective**: Ensure the complete ESP-IDF firmware compiles cleanly with zero warnings and stays within hardware memory constraints.
- **Execution**:
  ```powershell
  & "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run -e esp32dev
  ```

#### Pass/Fail Criteria
| Check | Requirement | Verification Method |
| :--- | :--- | :--- |
| **Compiler Status** | Zero errors, exit code 0 | `pio run` output ends with `[SUCCESS]` |
| **Compiler Warnings** | `-Wall -Werror` clean | No uninitialized variables, format string mismatches, or implicit conversions |
| **Include Paths** | ESP-IDF v6.1.0 driver headers | `driver/i2s_std.h`, `driver/uart.h`, `esp_err.h` resolve without warnings |
| **RAM Consumption** | $< 15\%$ of 320 KB (<48 KB) | PlatformIO size report |
| **Flash Consumption** | $< 25\%$ of 1 MB / 4 MB (<250 KB) | PlatformIO size report |
| **FreeRTOS Stack** | Audio: $\ge 4096\text{ B}$; Telemetry: $\ge 3072\text{ B}$ | Inspect `xTaskCreatePinnedToCore` stack depths |

---

### 3.4 Tier 3: Hardware-in-the-Loop (HIL) Driver Integration

- **Target Hardware**: ESP32 Dev Module connected on `COM7` (`USB-SERIAL CH340`).
- **Execution**:
  ```powershell
  & "C:\Users\hp\.platformio\penv\Scripts\pio.exe" run -e esp32dev -t upload --upload-port COM7
  ```

#### HIL Checkpoints & Assertions
1. **Power-On Boot Assertion**:
   - ESP32 boots cleanly without brownout reset (`rst:0x1 (POWERON_RESET)`).
2. **I2S Channel Allocation**:
   - `i2s_new_channel(&chan_cfg, NULL, &rx_handle)` returns `ESP_OK`.
   - Free heap verification: Heap memory decreases by expected DMA buffer size (~2–4 KB) and recovers if deinitialized.
3. **I2S Standard Mode Initialization**:
   - `i2s_channel_init_std_mode(rx_handle, &std_cfg)` returns `ESP_OK`.
   - GPIO configuration succeeds: BCLK on GPIO 14, WS on GPIO 27, SD on GPIO 32.
4. **Channel Enablement**:
   - `i2s_channel_enable(rx_handle)` returns `ESP_OK`.
   - No FreeRTOS watchdog timeout or core panic.
5. **Continuous DMA Reading**:
   - `i2s_channel_read(rx_handle, buf, sizeof(buf), &bytes_read, 1000)` returns `ESP_OK`.
   - `bytes_read` equals requested buffer size.
6. **Telemetry Cadence Measurement**:
   - Serial monitor captures timestamps of incoming lines.
   - Mean line interval $= 8.0 \text{ ms} \pm 0.5 \text{ ms}$ (at $125 \text{ Hz}$).
   - Jitter standard deviation $< 1.0 \text{ ms}$.

---

### 3.5 Tier 4: Acoustic Validation & End-to-End System Performance

- **Objective**: Complete end-to-end acoustic acquisition from physical sound waves to live visualization.
- **Execution**:
  ```powershell
  python tools/audio_plotter.py --port COM7 --baud 115200
  ```

#### Validation Scenarios
1. **Quiescent Silence Test**:
   - Environment: Quiet room, microphone resting undisturbed.
   - **Measurements**:
     - Waveform baseline: Centered around zero ($\pm 5,000$ counts out of $\pm 8,388,607$).
     - DC Offset: $< 0.1\%$ of full scale.
     - Noise Floor: RMS $< 15,000$ counts ($< -55 \text{ dBFS}$).
     - FFT Spectrogram: Uniform low-level white noise without 50/60 Hz hum or periodic DMA glitches.
2. **Acoustic Excitation Test (Hand Clapping / Speech)**:
   - Environment: Sharp hand clap at $0.5\text{ m}$ distance.
   - **Measurements**:
     - Instantaneous Peak deflection: Reaches $> 1,000,000$ counts ($> -18 \text{ dBFS}$).
     - RMS Energy: Rapid rise and exponential decay matching acoustic room reverberation.
     - Crest factor: $> 12 \text{ dB}$.
3. **Serial Plotter Real-Time Verification**:
   - Open Arduino IDE Serial Plotter or PlatformIO Serial Plotter on `COM7`.
   - Verify two distinct traces appear:
     - Blue trace: `sample` (fast acoustic waveform oscillations).
     - Orange/Red trace: `rms` (smooth acoustic energy envelope).
   - Display must update cleanly at ~60 FPS without serial lag, freezes, or disconnection.

---

## 4. Module Interface Contracts for Implementation

To ensure seamless coordination with Spec Miner 1 and the upcoming implementation agent, we define the concrete C header contracts:

### 4.1 Telemetry Header: `include/telemetry.h`
```c
#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define TELEMETRY_UART_NUM        UART_NUM_0
#define TELEMETRY_BAUD_RATE       115200
#define TELEMETRY_QUEUE_DEPTH     8
#define TELEMETRY_LINE_MAX_LEN    48

typedef struct {
    int32_t sample;    /**< Instantaneous decimated audio sample */
    int32_t rms;       /**< Root Mean Square energy over window */
    int32_t peak;      /**< Peak absolute amplitude over window */
} telemetry_packet_t;

/**
 * @brief Initialize telemetry queue, UART parameters, and FreeRTOS TX task.
 * @return ESP_OK on success, ESP_FAIL otherwise.
 */
esp_err_t telemetry_init(void);

/**
 * @brief Post a telemetry packet to the non-blocking transmission queue.
 * @note This function is non-blocking (portNO_DELAY). If the queue is full,
 *       the packet is dropped to prevent stalling the audio DSP task.
 * @param packet Pointer to telemetry packet.
 * @return true if enqueued, false if dropped.
 */
bool telemetry_send(const telemetry_packet_t *packet);

#ifdef __cplusplus
}
#endif
```

---

### 4.2 DSP Metrics Header: `include/dsp_metrics.h`
```c
#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <math.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float sum_squares;
    float peak_abs;
    uint32_t count;
    uint32_t window_size;
} dsp_metrics_tracker_t;

/**
 * @brief Initialize the DSP metrics tracker for a specific window length.
 */
void dsp_metrics_init(dsp_metrics_tracker_t *tracker, uint32_t window_size);

/**
 * @brief Ingest a 24-bit audio sample and accumulate RMS/Peak metrics.
 * @param tracker Pointer to metrics tracker state.
 * @param sample_24 24-bit signed audio sample in range [-8388608, +8388607].
 * @param out_rms Pointer to output RMS (scaled to 24-bit range).
 * @param out_peak Pointer to output Peak (scaled to 24-bit range).
 * @return true if window completed and outputs are valid, false otherwise.
 */
bool dsp_metrics_process_sample(dsp_metrics_tracker_t *tracker, 
                               int32_t sample_24, 
                               int32_t *out_rms, 
                               int32_t *out_peak);

#ifdef __cplusplus
}
#endif
```

---

## 5. Summary & Actionable Recommendations for Implementation

1. **Adopt Decimation Factor $D = 128$**:
   At $f_s = 16\text{ kHz}$, downsample telemetry to $125\text{ Hz}$. This consumes only $3\text{ kB/s}$ ($26\%$ of UART capacity), ensuring zero TX FIFO congestion while preserving human-audible speech cadence and waveform visibility.
2. **Format as `sample:%ld,rms:%ld\r\n`**:
   Delivers out-of-the-box named trace visualization in Arduino IDE 2.x and PlatformIO Serial Plotter.
3. **Use Single-Precision FPU for RMS**:
   Leverage ESP32 Xtensa LX6 hardware FPU with normalized floats ($[-1.0f, +1.0f]$) to compute single-cycle multiply-accumulate and avoid 64-bit integer overflow.
4. **Isolate FreeRTOS Tasks**:
   Pin `audio_capture_task` (priority 10) to Core 1 and `telemetry_task` (priority 2) to Core 0 with a non-blocking queue (`portNO_DELAY`).
5. **Implement `tools/audio_plotter.py`**:
   Provide dual GUI/CLI visualizer with `--mock` testing mode to satisfy Acceptance Criteria.
6. **Deploy Tier 1 Unit Tests**:
   Create `test/test_dsp_math.py` to independently verify signed bit extraction and RMS math.

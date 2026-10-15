# Project: SensorTechINMP441 Phase 1 Audio Acquisition & Telemetry

## Architecture

The system acquires 24-bit digital audio from an INMP441 MEMS microphone using ESP-IDF v6.1.0 (`driver/i2s_std.h`), computes real-time envelope metrics (RMS energy and peak amplitude), and streams downsampled acoustic telemetry over UART0 at 115200 baud for visualization in the PlatformIO / Arduino Serial Plotter.

### Concurrency & Data Flow
```
[INMP441 Mic]
     │ (SCK, WS, SD)
     ▼
[ESP32 I2S0 Peripheral (RX Master)]
     │ (DMA Circular Buffers: 6 x 240 frames)
     ▼
[audio_capture_task (Core 1, Priority 10)]
     │ 1. Read DMA buffer (raw 32-bit words)
     │ 2. Extract 24-bit audio: sample = raw >> 8 (int32_t arithmetic shift)
     │ 3. Normalize to float [-1.0f, +1.0f] via Xtensa LX6 single-precision FPU
     │ 4. Accumulate RMS: sqrtf(sum(sample^2) / N) over D=128 window
     │ 5. Track Peak: max(|sample|)
     │ 6. Push telemetry packet non-blocking (portNO_DELAY)
     ▼
[telemetry_queue (FreeRTOS Queue, Depth 8)]
     ▼
[telemetry_task (Core 0, Priority 2)]
     │ 1. Receive packet
     │ 2. Format: "sample:%ld,rms:%ld\r\n"
     │ 3. Output via UART0 at 115200 baud (125 Hz stream rate, ~3.0 kB/s load)
     ▼
[Serial Plotter / tools/audio_plotter.py]
```

---

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Modern ESP-IDF I2S Setup | Initialize I2S0 channel in RX master Philips standard mode using `driver/i2s_std.h` (32-bit slot, 24-bit data, 64 SCK/frame, 32-bit WS, 256 MCLK multiple) | M1 | ORIGINAL_REQUEST R1, Survey |
| F2 | Configurable GPIO Pinout | Configurable pin definitions (GPIO 14 SCK, GPIO 27 WS, GPIO 32 SD, L/R to GND) with internal pulldown on SD to prevent bus floating | M1 | ORIGINAL_REQUEST R3, Survey |
| F3 | Multi-Mic Architecture Groundwork | Structure I2S config and pin abstraction to prepare for 3-mic array (I2S0 L/R, I2S1 L) per MEMORY_ACOUSTIC_ARRAY.md without Phase 1 breakage | M1 | ORIGINAL_REQUEST Follow-up, Survey |
| F4 | 24-in-32 Bit Sample Extraction | Convert raw 32-bit DMA words to signed 24-bit integer waveform using arithmetic right shift `>> 8` with sign bit preservation (dynamic range [-8388608, +8388607]) | M1 | ORIGINAL_REQUEST R1, Survey |
| F5 | Real-Time Hardware FPU RMS & Peak Math | Single-precision FPU window RMS energy `sqrtf(sum / N)` and peak amplitude tracking over 128 samples without integer overflow or task blocking | M2 | ORIGINAL_REQUEST R2, Survey |
| F6 | Decoupled FreeRTOS Concurrency | Core 1 high-priority audio capture task + Core 0 low-priority UART telemetry task communicating via non-blocking queue (prevents DMA underruns) | M2 | ORIGINAL_REQUEST Acceptance Criteria, Survey |
| F7 | Decimated Serial Plotter Telemetry | Stream calibrated samples and envelope metrics at 125 Hz (D=128) over UART0 115200 baud formatted as `sample:%ld,rms:%ld\r\n` without buffer overflow | M2 | ORIGINAL_REQUEST R2, Survey |
| F8 | Application Lifecycle & Error Handling | Complete `app_main` lifecycle, robust error checking on all ESP-IDF driver calls, CMake dependencies, and PlatformIO configuration | M3 | ORIGINAL_REQUEST Acceptance Criteria, Survey |
| F9 | Python Verification & Plotting Tool | Lightweight script `tools/audio_plotter.py` supporting COM7 live plotting, ANSI terminal meter, synthetic `--mock` mode, and audio WAV export | M3 | ORIGINAL_REQUEST Acceptance Criteria, Survey |
| F10 | Opaque-Box E2E Test Suite | 4-tier test suite (Tiers 1-4) verifying feature coverage, boundaries, concurrency, and real-world audio scenarios | E2E Track | ORIGINAL_REQUEST Acceptance Criteria, Survey |
| F11 | Final Milestone Acceptance | Pass 100% of E2E test suite + Tier 5 adversarial coverage hardening | M4 | Project Pattern |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Audio Engine & Configuration | PlatformIO config, `src/CMakeLists.txt`, `include/i2s_microphone.h`, `src/i2s_microphone.c`, pinout, 24-in-32 bit extraction | none | DONE |
| M2 | DSP Processing & Real-Time Telemetry | `include/audio_dsp.h`, `src/audio_dsp.c`, `include/telemetry.h`, `src/telemetry.c`, FreeRTOS queue, Serial Plotter formatting | M1 | DONE |
| M3 | Application Integration & Python Visualizer | `src/main.c`, `tools/audio_plotter.py`, PlatformIO build verification, COM7 HIL live stream test | M1, M2 | DONE |
| E2E | E2E Testing Track | `TEST_INFRA.md`, test runner, Tiers 1-4 automated test cases, `TEST_READY.md` | none (requirements-driven) | DONE |
| M4 | Final Milestone | Pass 100% E2E tests (Tiers 1-4) + System Forensic Audit & Victory Verification | M3, E2E | DONE |

---

## Interface Contracts

### `i2s_microphone` ↔ `audio_dsp` / `main`
```c
// include/i2s_microphone.h
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "driver/i2s_std.h"

#define I2S_MIC_DEFAULT_SAMPLE_RATE     (16000)
#define I2S_MIC_DEFAULT_SCK_PIN         (14)
#define I2S_MIC_DEFAULT_WS_PIN          (27)
#define I2S_MIC_DEFAULT_SD_PIN          (32)

typedef struct {
    uint32_t sample_rate;
    int sck_pin;
    int ws_pin;
    int sd_pin;
    i2s_port_t i2s_port;
} i2s_mic_config_t;

esp_err_t i2s_mic_init(const i2s_mic_config_t *config);
esp_err_t i2s_mic_read_raw(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms);
esp_err_t i2s_mic_read_samples(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms);
esp_err_t i2s_mic_deinit(void);

// Sample conversion inline helper
static inline int32_t i2s_mic_convert_sample(int32_t raw_32) {
    return raw_32 >> 8; // Arithmetic right shift sign-extends 24-bit to 32-bit
}
```

### `audio_dsp` ↔ `telemetry`
```c
// include/audio_dsp.h
#pragma once
#include <stdint.h>
#include <stddef.h>

#define AUDIO_DSP_DECIMATION_FACTOR   (128)
#define AUDIO_DSP_FULL_SCALE          (8388607.0f) // 2^23 - 1

typedef struct {
    int32_t decimated_sample; // Downsampled acoustic sample
    int32_t rms_level;        // Full-window RMS energy in 24-bit range [0, 8388607]
    int32_t peak_level;       // Full-window peak absolute amplitude [0, 8388607]
} audio_telemetry_packet_t;

void audio_dsp_process_window(const int32_t *samples, size_t num_samples, audio_telemetry_packet_t *out_packet);
```

### `telemetry` ↔ `main`
```c
// include/telemetry.h
#pragma once
#include "esp_err.h"
#include "audio_dsp.h"

esp_err_t telemetry_init(void);
esp_err_t telemetry_send_packet(const audio_telemetry_packet_t *packet);
void telemetry_task_run(void *pvParameters);
```

---

## Code Layout

```
C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\
├── platformio.ini              # PlatformIO config: monitor_speed = 115200
├── sdkconfig.defaults          # Flash size and system defaults
├── src/
│   ├── CMakeLists.txt          # REQUIRES esp_driver_i2s esp_driver_gpio driver
│   ├── main.c                  # Application entry point, FreeRTOS tasks
│   ├── i2s_microphone.c        # I2S hardware initialization & DMA read
│   ├── audio_dsp.c             # 24-bit math, sign extension, FPU RMS/Peak
│   └── telemetry.c             # FreeRTOS queue consumer & UART formatted stream
├── include/
│   ├── i2s_microphone.h        # I2S interface contract
│   ├── audio_dsp.h             # DSP math interface contract
│   └── telemetry.h             # Telemetry interface contract
├── tools/
│   └── audio_plotter.py        # Python Serial visualizer & COM7 verification tool
├── test/
│   ├── test_runner.py          # Automated E2E test runner
│   ├── test_tier1_features.py  # Tier 1 feature coverage tests
│   ├── test_tier2_boundaries.py# Tier 2 boundary and corner case tests
│   ├── test_tier3_combinations.py # Tier 3 cross-feature interaction tests
│   └── test_tier4_scenarios.py # Tier 4 real-world application tests
└── .agents/teamwork/           # Coordination metadata
    ├── PROJECT.md              # Living global project index
    └── ...
```

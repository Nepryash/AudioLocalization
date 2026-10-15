# Test Infrastructure Specification: SensorTechINMP441 Phase 1

> **Document Version**: 1.0.0  
> **Target Framework**: ESP-IDF v6.1.0 / Python 3.11 Automated Test Engine  
> **Status**: APPROVED  
> **Integrity Mode**: Development / Progressive Testability  

---

## 1. Executive Summary & Testing Philosophy

This document defines the automated end-to-end (E2E) opaque-box test infrastructure for Phase 1 of the INMP441 acoustic array system. The primary objective is to verify audio acquisition, bit conversion, mathematical envelope detection, concurrent telemetry queuing, and UART Serial Plotter streaming against authoritative requirements without dependence on internal private implementation hacks.

The test infrastructure employs a **4-tier test architecture** structured around industry-standard formal testing methodologies:
1. **Category-Partition Testing (Tier 1 - Feature Coverage)**: Each feature (F1 through F9) is partitioned into functional behavioral categories with >= 5 dedicated test cases per feature.
2. **Boundary Value Analysis (Tier 2 - Boundary & Stress)**: Evaluates full-scale numerical extrema, buffer capacity limits, clock edges, and saturation conditions.
3. **Pairwise Combinatorial Testing (Tier 3 - Cross-Feature Interactions)**: Validates concurrent subsystems, high-to-low priority queuing, impulse transitions, and decimation ratios.
4. **Workload & Real-World Scenario Testing (Tier 4 - Application Scenarios)**: Sustained streaming simulation, live telemetry stream decoding, acoustic event triggers, and uncompressed WAV export verification.

---

## 2. Feature-to-Tier Traceability Matrix

Every feature defined in `PROJECT.md` is mapped across all test tiers to ensure full requirements traceability:

| Feature ID | Feature Description | Primary Requirement | Tier 1 (Features) | Tier 2 (Boundaries) | Tier 3 (Combinations) | Tier 4 (Scenarios) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **F1** | Modern ESP-IDF I2S Setup | `ORIGINAL_REQUEST.md` R1 | >= 5 tests | >= 5 tests | Pairwise | Stream Simulation |
| **F2** | Configurable GPIO Pinout | `ORIGINAL_REQUEST.md` R3 | >= 5 tests | >= 5 tests | Pairwise | Stream Simulation |
| **F3** | Multi-Mic Architecture Groundwork | `MEMORY_ACOUSTIC_ARRAY.md` §5 | >= 5 tests | >= 5 tests | Pairwise | Multichannel Mapping |
| **F4** | 24-in-32 Bit Sample Extraction | `ORIGINAL_REQUEST.md` R1 | >= 5 tests | >= 5 tests | Pairwise | Waveform Validation |
| **F5** | Hardware FPU RMS & Peak Math | `ORIGINAL_REQUEST.md` R2 | >= 5 tests | >= 5 tests | Pairwise | Envelope & Trigger |
| **F6** | Decoupled FreeRTOS Concurrency | `PROJECT.md` § Architecture | >= 5 tests | >= 5 tests | Pairwise | Queue Backpressure |
| **F7** | Decimated Serial Plotter Telemetry| `ORIGINAL_REQUEST.md` R2 | >= 5 tests | >= 5 tests | Pairwise | Telemetry Parser |
| **F8** | Lifecycle & Error Handling | `PROJECT.md` § Milestones | >= 5 tests | >= 5 tests | Pairwise | Fault Injection |
| **F9** | Python Visualizer & Export Tool | `ORIGINAL_REQUEST.md` R2, R3 | >= 5 tests | >= 5 tests | Pairwise | Plotter & WAV Export |

---

## 3. Test Tier Specifications

### 3.1 Tier 1: Feature Coverage (`test_tier1_features.py`)
- **Objective**: Verify functional correctness of each isolated feature under standard operating conditions.
- **Coverage**: Minimum 5 test cases per feature F1–F9 (minimum 45 test cases total).
- **Core Verification Points**:
  - `F1`: Master role configuration, BCLK calculation ($64 \times f_s$), MCLK multiple ($256 \times f_s$), 32-bit slot width, DMA ring descriptor sizing.
  - `F2`: Default GPIO pin mapping (SCK: 14, WS: 27, SD: 32), internal pulldown configuration on SD, pin collision validation, out-of-range GPIO rejection.
  - `F3`: Triple-microphone array mapping (Mic 1 -> I2S0 L, Mic 2 -> I2S0 R, Mic 3 -> I2S1 L, Slot 4 ignored), stereo DMA demux indexing.
  - `F4`: Arithmetic right shift (`>> 8`) sign extension for positive and negative 24-bit numbers, zero preservation, sign bit preservation, rejection of logical shift corruption.
  - `F5`: RMS energy calculation ($\sqrt{\sum x^2 / N}$) over window $N=128$, peak amplitude tracking ($\max(|x|)$), silence response, sine wave verification ($\text{RMS} \approx A / \sqrt{2}$).
  - `F6`: FreeRTOS queue depth (8 packets), non-blocking push with `portNO_DELAY`, FIFO ordering, non-blocking empty pop.
  - `F7`: Serial Plotter format compliance (`sample:%ld,rms:%ld\r\n`), 125 Hz decimation rate calculation ($16000 / 128$), UART baud rate capacity (< 30% load at 115200 baud).
  - `F8`: Robust error handling, NULL pointer validation (`ESP_ERR_INVALID_ARG`), lifecycle state transitions, clean deinitialization.
  - `F9`: Telemetry packet regex/parser validation, corrupted line resilience, mock data generation, ANSI meter calculations, WAV header format structure.

### 3.2 Tier 2: Boundary & Corner Cases (`test_tier2_boundaries.py`)
- **Objective**: Stress-test extreme mathematical limits, peripheral hardware constraints, and buffer bounds.
- **Coverage**: Minimum 5 test cases per feature (minimum 45 test cases total).
- **Core Verification Points**:
  - `F1`: Extreme sample rates (minimum $8\text{ kHz}$, maximum $50\text{ kHz}$ INMP441 rating), fractional clock divider limits, minimum DMA descriptors.
  - `F2`: Boundary GPIO pin numbers (0 and 39), input-only GPIOs (34-39) rejection as clock outputs, negative pin validation.
  - `F3`: Boundary spatial coordinate calculations, baseline distance tolerances, discarded slot isolation.
  - `F4`: Maximum full-scale positive ($+8388607$), minimum full-scale negative ($-8388608$), single-LSB positive ($+1$), single-LSB negative ($-1$), boundary sign bit flipping.
  - `F5`: Single-sample window ($N=1$), huge window ($N=1024$), alternating polarity full-scale square wave, DC offset saturation drift.
  - `F6`: Queue depth boundary (1 packet), full queue saturation, rapid burst pushes, 100% capacity drain.
  - `F7`: Maximum formatted string length with full-scale values, zero string length rejection, bare newline vs CRLF compliance.
  - `F8`: Double-initialization prevention, double-deinitialization safety, zero-length read requests, zero timeout handling.
  - `F9`: Empty serial frame handling, 1024-character line overflow protection, 0-byte WAV export rejection, full-scale meter saturation.

### 3.3 Tier 3: Cross-Feature Combinations (`test_tier3_combinations.py`)
- **Objective**: Verify interactions between interdependent subsystems under dynamic conditions.
- **Coverage**: Multi-variable combination test cases.
- **Core Verification Points**:
  - Concurrent audio capture and UART packet streaming under sustained throughput.
  - Instantaneous step transition response: prolonged silence transitioning to 100% full-scale impulse clap, verifying RMS rise time and peak tracking.
  - High noise floor mixed with sinusoidal acoustic signal (RMS power summation accuracy).
  - Queue backpressure resilience: high-rate capture task never blocked by slower telemetry task.
  - Sample rate and decimation factor variations ($16\text{ kHz} \dots 48\text{ kHz}$ with decimation $64, 128, 256$).
  - Multi-channel demuxing combined with 24-in-32 bit conversion.
  - Noisy serial link simulation with dropped characters and concatenated frames.

### 3.4 Tier 4: Real-World Workload Scenarios (`test_tier4_scenarios.py`)
- **Objective**: Validate end-to-end workflows in realistic deployment conditions.
- **Coverage**: Comprehensive realistic application scenarios.
- **Core Scenarios**:
  - **Scenario 1**: Continuous 1000+ frame audio streaming simulation (verifying zero frame loss, no memory leaks, no NaN/Inf values).
  - **Scenario 2**: Real-time UART telemetry decoder and stream jitter monitor.
  - **Scenario 3**: Arduino / PlatformIO Serial Plotter compatibility and live envelope visualizer.
  - **Scenario 4**: Acoustic Event Detection (voice/clap onset detector based on dynamic RMS energy threshold).
  - **Scenario 5**: End-to-end WAV audio file export (16000 Hz, 16-bit PCM standard RIFF WAV file generation and validation).

---

## 4. Test Runner & Execution Protocol

### 4.1 Test Harness (`test/test_runner.py`)
The automated runner is built using Python's standard `unittest` framework to execute without external third-party dependencies.
- **Features**:
  - Automatic discovery and aggregation of all 4 test tiers.
  - Command-line flags: `--tier 1..4`, `--verbose`, `--failfast`, `--summary`.
  - Structured console output with per-tier pass/fail breakdown and feature checklist.
  - Strict exit code contract: `0` on 100% pass, `1` on any failure or error.

### 4.2 Standard Execution Commands
Execute from the project root directory:

```powershell
# Run the complete E2E test suite (all tiers)
& "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py

# Run a specific test tier
& "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py --tier 1
& "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py --tier 2
& "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py --tier 3
& "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py --tier 4
```

---

## 5. Test Integrity & Verification Standards

1. **Deterministic Execution**: Every test sets up its own state, isolates data buffers, and leaves no residual files or open handles.
2. **Authoritative Output Derivation**: Expected mathematical values (such as RMS, peak, 24-bit shifted two's complement values, RIFF header offsets) are mathematically derived from first principles and datasheet specifications.
3. **No Facade Tests**: Assertions verify genuine arithmetic, bitwise transformations, buffer sizes, and formatting strings.

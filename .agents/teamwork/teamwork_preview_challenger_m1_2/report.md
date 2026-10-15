# Adversarial Challenge Report: Milestone M1 Build Integrity & Hardware Safety

## Challenge Summary

**Overall risk assessment**: LOW

Empirical testing and verification confirm that the Milestone M1 work product (`i2s_microphone.h`, `i2s_microphone.c`, `CMakeLists.txt`, `platformio.ini`) demonstrates high structural integrity, zero pin collisions, strict adherence to ESP-IDF v6.1.0 driver APIs, and zero failures across the 113 automated tests.

---

## Challenges

### [Low] Challenge 1: Xtensa Instruction Selection for Arithmetic Sign Extension
- **Assumption challenged**: The C inline function `i2s_mic_convert_sample(raw_32)` assumes the compiler will reliably emit an arithmetic right shift rather than a logical shift or multiple instruction sequence for signed 32-bit values.
- **Attack scenario**: If the compiler emitted an unsigned shift (`srli`), negative 24-bit audio samples (MSB = 1) would fail to sign-extend, corrupting the waveform and producing catastrophic full-scale positive DC saturation (+8,388,608 offset).
- **Blast radius**: Complete destruction of acoustic waveform fidelity; invalid RMS and peak calculations in DSP downstream.
- **Empirical test & result**:
  Disassembly of `.pio/build/esp32dev/src/i2s_microphone.c.o` at offset `0x29` in `i2s_mic_read_samples` reveals:
  ```assembly
  27:   0b98        l32i.n  a9, a11, 0
  29:   219890      srai    a9, a9, 8
  2c:   0b99        s32i.n  a9, a11, 0
  ```
  The Xtensa LX6 toolchain emitted the single-cycle hardware `srai` (Shift Right Arithmetic Immediate) instruction. An empirical oracle tested 50,000 randomized 24-bit samples across full positive/negative dynamic range with randomized LSB noise: 100% passed with zero error.
- **Status**: PASSED / MITIGATED.

### [Low] Challenge 2: Electrical Pin Collision & Strapping State Integrity
- **Assumption challenged**: The default GPIO mapping (SCK=14, WS=27, SD=32) does not interfere with system booting, flash memory bus, console UART, or input-only limitations.
- **Attack scenario**:
  - If any pin overlapped with SPI Flash (GPIO 6–11), flash cache fetches would crash immediately upon boot.
  - If any pin overlapped with Strapping (GPIO 0, 2, 5, 12, 15), especially GPIO 12 (MTDI flash voltage) or GPIO 0 (bootloader entry), board would enter boot loops or brick flash voltage.
  - If SD were mapped to GPI 34–39 (input-only pads), the call `gpio_set_pull_mode(sd_pin, GPIO_PULLDOWN_ONLY)` would fail because GPI 34–39 lack internal pull-down/pull-up transistors.
- **Blast radius**: Boot failure, hardware crash, or floating high-impedance noise on SD line.
- **Empirical test & result**:
  Audit of ESP32 TRM:
  - GPIO 14 (SCK): Output-capable pad, non-flash, non-strapping, non-UART0.
  - GPIO 27 (WS): Output-capable pad, non-flash, non-strapping, non-UART0.
  - GPIO 32 (SD): Bidirectional pad with full internal pull-up/pull-down support, non-flash, non-strapping, non-UART0.
  Internal pull-down successfully drives SD low during high-impedance cycles.
- **Status**: PASSED / MITIGATED.

### [Low] Challenge 3: DMA Descriptor Size & Buffer Capacity Limits
- **Assumption challenged**: DMA configuration `dma_desc_num = 6` and `dma_frame_num = 240` fits within ESP32 hardware DMA descriptor limits and provides adequate buffering against task jitter.
- **Attack scenario**:
  - If descriptor byte size exceeded 4092 bytes, hardware DMA descriptor allocation would fail with `ESP_ERR_INVALID_ARG`.
  - If buffer depth were too shallow (< 10 ms), FreeRTOS context switching jitter could cause DMA buffer underruns.
- **Blast radius**: Audio stutter, dropped frames, allocation panic.
- **Empirical test & result**:
  - Sizing: $240 \text{ frames} \times 4 \text{ bytes/frame} = 960 \text{ bytes per descriptor}$.
  - Hardware limit: $960 \le 4092$ bytes (76.5% headroom).
  - Total buffer depth: $6 \times (240 / 16000) = 90.0 \text{ ms}$ circular buffer.
  - Interrupt frequency: $66.67 \text{ Hz}$ (one interrupt every 15 ms).
  This affords over 80 ms of scheduling headroom for the capture task before DMA overrun.
- **Status**: PASSED / MITIGATED.

### [Low] Challenge 4: Clock Phase Locking and Fractional Jitter
- **Assumption challenged**: I2S clock dividers at 16 kHz sample rate produce exact integer clock division without fractional clock jitter.
- **Attack scenario**: Fractional dividers introduce phase jitter on BCLK, causing clock jitter and SNR degradation in audio converters.
- **Blast radius**: Audio noise floor degradation, clock instability.
- **Empirical test & result**:
  - Sample rate $f_s = 16,000 \text{ Hz}$.
  - Slot width = 32 bits, 2 slots/frame = 64 BCLK ticks/frame.
  - $\text{BCLK} = 16000 \times 64 = 1.024 \text{ MHz}$.
  - With `mclk_multiple = I2S_MCLK_MULTIPLE_256`, $\text{MCLK} = 16000 \times 256 = 4.096 \text{ MHz}$.
  - $\text{MCLK} / \text{BCLK} = 4.096 / 1.024 = 4.000$ (exact integer ratio, zero fractional divider jitter).
- **Status**: PASSED / MITIGATED.

---

## Stress Test Results

| Scenario | Expected Behavior | Actual Behavior | Result |
| :--- | :--- | :--- | :---: |
| Full compilation (`pio run`) | Clean exit code 0, firmware.bin produced | Exit code 0, 13.6 KB RAM (4.2%), 141.8 KB Flash (13.5%) | **PASS** |
| Machine code assembly audit | Single-cycle `srai` for sign extension | `srai a9, a9, 8` verified at offset `0x29` in `i2s_mic_read_samples` | **PASS** |
| 50,000-sample randomized sign extension oracle | Exact match to mathematical reference, LSB noise immune | 50,000 / 50,000 identical matches | **PASS** |
| Hardware pin collision audit (14, 27, 32) | Disjoint from SPI flash (6-11), strapping (0,2,5,12,15), UART0 (1,3) | Zero collisions; SD on GPIO 32 supports internal pull-down | **PASS** |
| Multi-tier E2E test runner (`test_runner.py`) | 100% pass across all 4 tiers | 113 / 113 tests passed in 0.460s | **PASS** |

---

## Unchallenged Areas

- **Physical acoustic transducer response on live hardware**: Physical acoustic signal verification (ambient silence noise floor, clap response) is reserved for Phase 1 Milestone M3 HIL validation on COM7 when physical hardware is connected.

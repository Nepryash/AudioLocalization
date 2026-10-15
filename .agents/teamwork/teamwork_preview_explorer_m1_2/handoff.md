# Milestone M1 Explorer 2 Handoff Report: Audio Math & Interface Contracts

**Author**: Milestone M1 Explorer 2 (Audio Math & Contract Specialist)  
**Date**: 2026-10-06  
**Working Directory**: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_2\`  
**Target Recipient**: Orchestrator (`d17832be-bb24-40e4-9ee2-0c353fd26745`) and M1 Worker  

---

## 1. Observation

1. **Workspace and Toolchain**:
   - PlatformIO project root: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\`.
   - Toolchain: `xtensa-esp-elf-gcc.exe (crosstool-NG esp-15.2.0_20251204) 15.2.0`.
   - ESP-IDF Framework: v6.1.0 (`framework-espidf @ 4.60100.0`).

2. **Assembly Compilation Result**:
   - Compiled `test_assembly.c` using:
     `& "C:\Users\hp\.platformio\packages\toolchain-xtensa-esp-elf\bin\xtensa-esp32-elf-gcc.exe" -O2 -S -mlongcalls .agents/teamwork/teamwork_preview_explorer_m1_2/test_assembly.c -o .agents/teamwork/teamwork_preview_explorer_m1_2/test_assembly.s`
   - Observed assembly in `test_assembly.s` lines 6–9:
     ```assembly
     convert_sample_arith:
         entry   sp, 32
         srai    a2, a2, 8
         retw.n
     ```
   - Observed in-place buffer loop in `test_assembly.s` lines 42–48:
     ```assembly
         loop    a8, .L13_LEND
     .L13:
         l32i.n  a9, a2, 0
         srai    a9, a9, 8
         s32i.n  a9, a2, 0
         addi.n  a2, a2, 4
     .L13_LEND:
     ```

3. **Arithmetic Right Shift Verification**:
   - Ran `python .agents/teamwork/teamwork_preview_explorer_m1_2/verify_math.py`:
     - Positive full-scale: `0x7FFFFF00 >> 8 == +8388607` (`0x007FFFFF`).
     - Negative full-scale: `0x80000000 >> 8 == -8388608` (`0xFF800000`).
     - Low-byte noise: `0x000000FF >> 8 == 0`.
     - Negative low-byte noise: `0xFFFFFF80 >> 8 == -1`.
   - Evaluated pitfall `(uint32_t)0x80000000 >> 8`: produces `+8388608` instead of `-8388608` (error: $+16,777,216$).
   - Evaluated pitfall `(raw_32 >> 8) & 0x00FFFFFF`: produces `+8388608` instead of `-8388608` (error: $+16,777,216$).

4. **Downstream M2 DSP Integration Script**:
   - Executed `python .agents/teamwork/teamwork_preview_explorer_m1_2/test_dsp_integration.py`.
   - Output confirmed:
     ```
     DC Max Positive: Dec=8388607, RMS=8388606, Peak=8388607
     DC Max Negative: Dec=-8388608, RMS=8388607, Peak=8388607
     Pure Silence: Dec=0, RMS=0, Peak=0
     Trailing Bus Noise: Dec=0, RMS=0, Peak=0
     Full-Scale Sine: RMS=5931640 (Exp=5931641), Peak=8388607
     Impulse Clap: RMS=370728, Peak=4194304
     ALL INTEGRATION TESTS PASSED!
     ```

5. **Interface Contract References**:
   - `PROJECT.md` lines 89–98 specify:
     ```c
     esp_err_t i2s_mic_init(const i2s_mic_config_t *config);
     esp_err_t i2s_mic_read_raw(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms);
     esp_err_t i2s_mic_read_samples(int32_t *dest, size_t num_samples, size_t *samples_read, uint32_t timeout_ms);
     esp_err_t i2s_mic_deinit(void);
     static inline int32_t i2s_mic_convert_sample(int32_t raw_32) {
         return raw_32 >> 8;
     }
     ```

---

## 2. Logic Chain

1. **Premise 1 (Hardware Bit Layout)**: In standard Philips I2S mode with 32-bit slots, the INMP441 delivers 24 bits MSB-first in cycles 2–25, followed by 7 tri-state cycles (cycles 26–32). When sampled into a 32-bit register, the 24 audio bits occupy bits `[31:8]`, and the trailing 8 bits `[7:0]` are pulled to zero by the internal/external pull-down resistor (Observation 1, 3).
2. **Premise 2 (Mathematical Transformation)**: The formula $f(r) = r \gg 8$ on signed `int32_t` computes $\lfloor (256x + \epsilon) / 256 \rfloor = x$ for any noise $\epsilon \in [0, 255]$. This strictly preserves the signed dynamic range $[-8388608, +8388607]$ without DC bias, and rejects any bus noise residing in bits `[7:0]` (Observation 3).
3. **Premise 3 (Instruction Pipeline)**: GCC 15.2.0 on Xtensa LX6 translates `raw_32 >> 8` into the single instruction `srai aX, aX, 8`. Within an in-place array loop, the Xtensa hardware zero-overhead loop engine executes this in 4 CPU cycles per sample, consuming $4.0\,\mu\text{s}$ per 240-sample DMA frame ($0.026\%$ of CPU capacity at 240 MHz) (Observation 2).
4. **Premise 4 (Failure Mode Severity)**: Using unsigned shifts or bitwise masks (`& 0x00FFFFFF`) clears the replicated sign bits `[31:24]`, introducing an error of exactly $+2^{24} = +16,777,216$ on negative samples. This shifts the signal mean to $+8,388,608$ (50% of full scale) and completely destroys downstream RMS energy and waveform fidelity (Observation 3).
5. **Premise 5 (Interface Design)**: A two-tier reading API (`i2s_mic_read_raw` and `i2s_mic_read_samples`) cleanly decouples diagnostic hardware reads from high-level DSP reads. `i2s_mic_read_samples` operates in-place on caller-allocated memory, achieving zero heap allocations and 100% type safety for M2 DSP ingestion (Observation 4, 5).

---

## 3. Caveats

1. **Hardware Silence Noise Floor**: In an ideal noiseless simulation, pure silence yields exact RMS 0. In physical hardware, the INMP441 has a specified SNR of $61\text{ dBA}$, so idle room noise will produce small acoustic oscillations of around $\pm 2,000$ to $\pm 10,000$ counts (RMS $\approx -55\text{ dBFS}$). Test assertions must not expect exact integer 0 in hardware runs.
2. **DC Normalization Discrepancy ($\pm 1$ Count)**: When scaling RMS between float normalization ($/ 8388608.0\text{f}$) and integer re-scaling ($\times 8388607.0\text{f}$), positive full-scale DC evaluates to $8,388,606$ instead of $8,388,607$. Test suites must accept a $\pm 1$ count tolerance ($0.00001\%$).
3. **Multi-Channel DMA Alignment**: In Phase 1, DMA reads single-channel data. In Phase 2/3 (stereo / 3-mic), DMA words will be interleaved (`[Left, Right, ...]`). The conversion helper `i2s_mic_convert_sample()` remains identical, but buffer demuxing will separate channels prior to conversion.

---

## 4. Conclusion

1. **Adopt `raw_32 >> 8` as Mandatory Standard**: The Worker must implement `i2s_mic_convert_sample(raw_32)` as `return raw_32 >> 8;` with `int32_t raw_32`. All forms of `uint32_t` shifting and masking with `0x00FFFFFF` are strictly forbidden.
2. **Implement Dual-Read Contract**:
   - `i2s_mic_read_raw()`: Reads raw DMA words from `i2s_channel_read()`.
   - `i2s_mic_read_samples()`: Calls `i2s_mic_read_raw()` and converts samples in-place.
3. **Standardize M2 DSP Conformance**:
   - M2 DSP input samples are guaranteed in $[-8388608, +8388607]$.
   - Float normalization uses `8388608.0f`.
   - Peak amplitude is tracked in the integer domain with clamping at $8,388,607$.
   - RMS re-scaling allows $\pm 1$ count tolerance on positive full-scale.

---

## 5. Verification Method

1. **Host-Based Unit Testing**:
   Run the verification scripts:
   ```powershell
   python .agents/teamwork/teamwork_preview_explorer_m1_2/verify_math.py
   python .agents/teamwork/teamwork_preview_explorer_m1_2/test_dsp_integration.py
   ```
   *Expected output*: Both scripts print `ALL TESTS PASSED` / `ALL INTEGRATION TESTS PASSED` with exit code 0.

2. **Xtensa Compiler & Assembly Verification**:
   Recompile and inspect the assembly:
   ```powershell
   & "C:\Users\hp\.platformio\packages\toolchain-xtensa-esp-elf\bin\xtensa-esp32-elf-gcc.exe" -O2 -S -mlongcalls .agents/teamwork/teamwork_preview_explorer_m1_2/test_assembly.c -o .agents/teamwork/teamwork_preview_explorer_m1_2/test_assembly.s
   ```
   *Inspection*: Verify `srai aX, aX, 8` instruction is generated without logical shifts (`srli`).

3. **Invalidation Conditions**:
   The findings would be invalidated if:
   - The INMP441 slot width is configured as 24-bit instead of 32-bit (`slot_bit_width = 24`), which would alter bit alignment and violate the 64-SCK hardware cycle requirement.
   - The ESP-IDF driver is configured in MSB-justified mode instead of Philips standard mode (`bit_shift = false`), shifting audio bits by 1 clock cycle.

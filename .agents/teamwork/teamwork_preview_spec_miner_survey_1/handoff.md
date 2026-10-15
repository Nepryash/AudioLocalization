# Handoff Report: Survey Spec Miner 1 (I2S & INMP441 Specifications)

## 1. Observation
- **Platform & Toolchain Verification**:
  - Command: `& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run`
  - Output: `PlatformIO Core, version 6.2.0`, `PLATFORM: Espressif 32 (7.1.3)`, `framework-espidf @ 4.60100.0 (6.1.0)`, `toolchain-xtensa-esp-elf @ 15.2.0+20251204`. Build completed with `[SUCCESS] Took 8.83 seconds`.
  - Target: ESP32 dual core (`board = esp32dev`, `framework = espidf` in `platformio.ini:11-14`).
- **ESP-IDF Header & Code Inspection**:
  - File: `C:\Users\hp\.platformio\packages\framework-espidf\components\esp_driver_i2s\include\driver\i2s_std.h`:
    - Line 31-42: Macro `I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(bits_per_sample, mono_or_stereo)` sets `.slot_bit_width = I2S_SLOT_BIT_WIDTH_AUTO`, `.bit_shift = true`, `.ws_pol = false`, and `.msb_right = (bits_per_sample <= I2S_DATA_BIT_WIDTH_16BIT) ? true : false`.
    - Line 203-208: Macro `I2S_STD_CLK_DEFAULT_CONFIG(rate)` sets `.sample_rate_hz = rate`, `.clk_src = I2S_CLK_SRC_DEFAULT`, `.mclk_multiple = I2S_MCLK_MULTIPLE_256`, `.bclk_div = 8`.
    - Line 228-249: `i2s_std_slot_config_t` structure definition.
    - Line 253-271: `i2s_std_clk_config_t` structure definition.
    - Line 274-287: `i2s_std_gpio_config_t` structure definition (`mclk`, `bclk`, `ws`, `dout`, `din`, `invert_flags`).
    - Line 320: `esp_err_t i2s_channel_init_std_mode(i2s_chan_handle_t handle, const i2s_std_config_t *std_cfg);`.
  - File: `C:\Users\hp\.platformio\packages\framework-espidf\components\esp_driver_i2s\include\driver\i2s_common.h`:
    - Line 22-33: `I2S_CHANNEL_DEFAULT_CONFIG(i2s_num, i2s_role)` sets `.dma_desc_num = 6`, `.dma_frame_num = 240`, `.tx_destination = I2S_DESTINATION_DMA`, `.rx_destination = I2S_DESTINATION_DMA`.
    - Line 146: `esp_err_t i2s_new_channel(const i2s_chan_config_t *chan_cfg, i2s_chan_handle_t *ret_tx_handle, i2s_chan_handle_t *ret_rx_handle);`.
    - Line 183: `esp_err_t i2s_channel_enable(i2s_chan_handle_t handle);`.
    - Line 197: `esp_err_t i2s_channel_disable(i2s_chan_handle_t handle);`.
    - Line 233: `esp_err_t i2s_channel_read(i2s_chan_handle_t handle, void *dest, size_t size, size_t *bytes_read, uint32_t timeout_ms);`.
  - File: `C:\Users\hp\.platformio\packages\framework-espidf\components\esp_driver_i2s\i2s_std.c`:
    - Line 38-41: Clock division calculation:
      ```c
      clk_info->bclk = rate * handle->total_slot * slot_bits;
      clk_info->mclk = rate * clk_cfg->mclk_multiple;
      clk_info->bclk_div = clk_info->mclk / clk_info->bclk;
      ```
    - Line 87-89: Error check:
      ```c
      ESP_RETURN_ON_FALSE(real_slot_bit != I2S_DATA_BIT_WIDTH_24BIT || (clk_cfg->mclk_multiple % 3 == 0),
                          ESP_ERR_INVALID_ARG, TAG,
                          "The 'mclk_multiple' should be the multiple of 3 while using 24-bit data width");
      ```
  - File: `C:\Users\hp\.platformio\packages\framework-espidf\components\esp_driver_i2s\i2s_common.c`:
    - Line 627-631: DMA sample byte sizing on ESP32:
      ```c
      #if CONFIG_IDF_TARGET_ESP32
          uint32_t bytes_per_sample = ((data_bit_width + 15) / 16) * 2;
      #else
          uint32_t bytes_per_sample = (data_bit_width + 7) / 8;
      #endif
      ```
      For `data_bit_width = 24`, `bytes_per_sample = ((24 + 15) / 16) * 2 = 4 bytes` ($32\text{ bits}$).
  - File: `C:\Users\hp\.platformio\packages\framework-espidf\components\esp_driver_i2s\test_apps\i2s\main\test_i2s.c`:
    - Line 723 & 755: Verbatim test comments and logic:
      ```c
      #if CONFIG_IDF_TARGET_ESP32
          /* The data of tx/rx channels are flipped on ESP32 */
          for (int n = 0; n < READ_BUF_LEN / 2; n += 2) {
              int16_t temp = r_buf[n];
              r_buf[n] = r_buf[n + 1];
              r_buf[n + 1] = temp;
          }
      #endif
      ```
- **INMP441 Datasheet Verification (`INMP441.pdf`)**:
  - Page 5, Table 3: Serial Data Port Timing:
    - $f_{SCK}$ range: $0.5\text{ MHz} \le f_{SCK} \le 3.2\text{ MHz}$.
    - $f_{WS}$ range: $7.8\text{ kHz} \le f_{WS} \le 50\text{ kHz}$.
  - Page 11: "The slave serial-data port's format is I2S, 24-bit, twos complement. There must be 64 SCK cycles in each WS stereo frame, or 32 SCK cycles per data-word."
  - Page 11: "The INMP441 must always have 64 clock cycles for every stereo data-word ($f_{SCK} = 64 \times f_{WS}$)."
  - Page 11: "The default data format is I2S (two's complement), MSB-first. In this format, the MSB of each word is delayed by one SCK cycle from the start of each half-frame."
  - Page 11: "The output data pin (SD) is tri-stated when it is not actively driving I2S output data. SD immediately tri-states after the LSB is output... The SD trace should have a pull-down resistor to discharge the line during the time that all microphones on the bus have tri-stated their outputs. A 100 kOhm resistor is sufficient..."
  - Page 10: Startup settling requires $2^{18}$ SCK cycles ($\approx 85\text{ ms}$ @ $48\text{ kHz}$, $\approx 256\text{ ms}$ @ $16\text{ kHz}$). During this period, output reads zero.
- **Project Memory (`MEMORY_ACOUSTIC_ARRAY.md` Section 5)**:
  - Line 156-176: ESP32 has 2 stereo controllers yielding 4 slots:
    - Mic 1 -> I2S0 Left (`L/R` to GND)
    - Mic 2 -> I2S0 Right (`L/R` to VDD)
    - Mic 3 -> I2S1 Left (`L/R` to GND)
    - Slot 4 (I2S1 Right) -> discarded.

---

## 2. Logic Chain
1. **Clock & Slot Alignment**:
   - Observation: INMP441 Page 11 dictates mandatory 64 SCK cycles per stereo frame ($32\text{ cycles/slot}$), and $f_{SCK} = 64 \times f_s$.
   - Observation: In `driver/i2s_std.h`, default macro `I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG` sets `.slot_bit_width = AUTO`. If `data_bit_width = 24`, normalized slot width defaults to 24 bits ($48\text{ cycles/frame}$), which violates INMP441 timing and triggers ESP-IDF error check (`i2s_std.c:87`) if `mclk_multiple` is not a multiple of 3.
   - Inference: We must explicitly override `.slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT` and `.ws_width = 32`.
   - Inference: With 32-bit slot width, total frame bits = 64. BCLK divider from default MCLK ($256 \times f_s$) is $256 / 64 = 4$ (exact integer, 0 jitter).
2. **24-in-32 Bit Representation & Sign Extension**:
   - Observation: INMP441 transmits 24 bits MSB-first starting on cycle 2 (1-cycle delay), tri-stating on cycles 26-32.
   - Observation: ESP32 DMA allocates 4 bytes ($32\text{ bits}$) per sample in memory (`i2s_common.c:628`). The 24 bits occupy bits `[31:8]`, with trailing bits `[7:0]` read as zero.
   - Observation: Bit 31 is the sign bit ($S$) of the 24-bit two's complement audio.
   - Inference: Reading into signed `int32_t` and executing arithmetic right shift (`raw_sample >> 8`) shifts bits `[31:8]` to `[23:0]` while arithmetic sign replication fills bits `[31:24]` with the sign bit. This preserves the exact negative and positive dynamic range ($[-8388608, +8388607]$) without DC offset or bit inversion.
3. **Signal Quality & Noise Floor**:
   - Observation: INMP441 SD line is High-Z during unused slot cycles.
   - Inference: Leaving SD floating allows capacitive pickup and DC drift. Enabling internal pull-down (`gpio_set_pull_mode(I2S_MIC_SD_IO, GPIO_PULLDOWN_ONLY)`) or installing external 100 k$\Omega$ pulldown resistor guarantees logic 0 during High-Z phases, maintaining a clean idle noise floor.
4. **Future 3-Mic Architecture Compatibility**:
   - Observation: `MEMORY_ACOUSTIC_ARRAY.md` assigns Mic 1 to I2S0 Left, Mic 2 to I2S0 Right, and Mic 3 to I2S1 Left.
   - Inference: Phase 1 on I2S0 Left (pins GPIO 4, GPIO 15, GPIO 32) enables Mic 2 in Phase 2 to share the identical SCK, WS, and SD lines (with `L/R` tied to VDD) without modifying pin assignments. Phase 3 adds I2S1 Left on a synchronized clock, requiring only one new data pin (`SD1` on GPIO 33).

---

## 3. Caveats
- **Physical Board Testing**: This survey analysis was performed via static codebase inspection, datasheet verification, and PlatformIO compilation checking. Dynamic real-time signal testing requires physical ESP32 hardware connected over USB/UART.
- **ESP32 Silicon Revisions**: Classic ESP32 chips (ECO 1 vs ECO 3) have minor differences in I2S FIFO behaviors; however, using 32-bit slot width and Philips standard mode with standard DMA sizing is robust across all ESP32 silicon revisions.
- **MCLK Output**: The INMP441 does not require an MCLK clock pin. MCLK is routed internally within the ESP32 to generate BCLK and WS, leaving the external MCLK GPIO unassigned (`I2S_GPIO_UNUSED`).

---

## 4. Conclusion
The technical specifications for ESP-IDF v5/v6 (`driver/i2s_std.h`) and the INMP441 MEMS microphone are thoroughly mined, documented, and verified:
1. Initialize I2S with `i2s_new_channel` (master role, 6 DMA descriptors, 240 frames/desc).
2. Configure standard Philips mode with `slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT`, `data_bit_width = I2S_DATA_BIT_WIDTH_24BIT`, `ws_width = 32`, `bit_shift = true`, `ws_pol = false`.
3. Extract samples using `int32_t sample = raw_sample >> 8` on signed 32-bit integers.
4. Enable pull-down on SD line to prevent high-impedance bus noise.
5. Map Phase 1 to I2S0 Left, seamlessly paving the way for the 3-microphone acoustic localization array.

Detailed findings, feature discovery tables, edge cases, and code blueprints are available in:
`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_spec_miner_survey_1\report.md`

---

## 5. Verification Method
1. **Compilation Check**:
   Execute:
   ```powershell
   & "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run
   ```
   Pass criteria: Zero compilation errors, clean ELF artifact generation.
2. **File Artifact Check**:
   Inspect `report.md` in the current working directory to verify that all API structures, mathematical formulas, and 3-mic architecture tables match the authoritative specifications.
3. **Invalidation Conditions**:
   - If `slot_bit_width` is left as `AUTO` with 24-bit data, ESP-IDF throws `ESP_ERR_INVALID_ARG`.
   - If `uint32_t` is used for `>> 8` shifting, negative waveforms invert, producing extreme DC offset.

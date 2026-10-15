# Technical Specification & Requirements Report: ESP-IDF v5/v6 I2S & INMP441 MEMS Microphone

**Target Platform**: Espressif ESP32 (Xtensa dual-core, Rev 1/3)  
**Framework**: ESP-IDF 6.1.0 / v5.x (`driver/i2s_std.h`, `driver/i2s_common.h`) via PlatformIO  
**Sensor**: InvenSense / TDK INMP441 Omnidirectional I2S Digital MEMS Microphone  
**Project Phase**: Phase 1 (Single Mic Acquisition & Validation) with Roadmap to 3-Mic Acoustic Array  

---

## 1. Executive Summary

This report establishes the authoritative hardware and software specifications for capturing high-fidelity 24-bit digital audio from the INMP441 MEMS microphone using ESP-IDF's modern I2S standard driver (`driver/i2s_std.h`). 

Key findings:
1. **Clock Configuration**: The INMP441 requires exactly 64 bit-clock (BCLK / SCK) cycles per stereo frame ($32\text{ cycles/slot}$), mandating `slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT`. With a default master clock multiple of 256 (`I2S_MCLK_MULTIPLE_256`), integer BCLK division is clean ($256 / 64 = 4$), resulting in low jitter and zero sample rate distortion.
2. **Bit Alignment & Sample Extraction**: When reading 32-bit words via DMA, the 24-bit two's complement audio occupies bits `[31:8]`, with bits `[7:0]` padded with zeros. Applying an arithmetic right shift (`raw_sample >> 8`) on a signed 32-bit integer (`int32_t`) performs sign extension to preserve the full 24-bit dynamic range without DC offset or bit inversion.
3. **Hardware Pinout & Configuration**: Phase 1 connects `SCK` (BCLK), `WS` (LRCK), and `SD` (Data In) to general-purpose GPIOs (e.g., GPIO 4, GPIO 15, GPIO 32), with `L/R` tied to GND (Left slot).
4. **3-Microphone Array Mapping**: Per `MEMORY_ACOUSTIC_ARRAY.md` Section 5, the two hardware I2S controllers of the ESP32 provide 4 stereo slots. Mic 1 and Mic 2 share I2S0 lines (`L/R` to GND and VDD respectively). Mic 3 connects to I2S1 Left (`L/R` to GND) with synchronized clocks, and slot 4 is discarded. Phase 1 cleanly transitions to Phase 2 and Phase 3 without hardware redesign.

---

## 2. Specification Discovery Tables

### Features Discovered
| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | I2S Channel Mgmt | `i2s_new_channel` | Allocates I2S controller RX/TX channel and initializes state to `REGISTERED` | `const i2s_chan_config_t *`, `tx_handle`, `rx_handle` | `esp_err_t`, handle pointers | Returns `ESP_ERR_INVALID_ARG` on NULL/invalid config; `ESP_ERR_NOT_FOUND` if port busy | `driver/i2s_common.h:146` |
| 2 | I2S Channel Mgmt | `i2s_channel_init_std_mode` | Configures clock, slot, and GPIOs for standard Philips/MSB/PCM mode (`READY` state) | `i2s_chan_handle_t`, `const i2s_std_config_t *` | `esp_err_t` | Returns `ESP_ERR_INVALID_ARG` if 24-bit slot without mod-3 mclk; `ESP_ERR_NO_MEM` on DMA alloc fail | `driver/i2s_std.h:320`, `i2s_std.c:87` |
| 3 | I2S Channel Mgmt | `i2s_channel_enable` | Starts hardware BCLK and WS generation and begins DMA transfer (`RUNNING` state) | `i2s_chan_handle_t` | `esp_err_t` | Returns `ESP_ERR_INVALID_STATE` if channel is not initialized or already started | `driver/i2s_common.h:183` |
| 4 | I2S Channel Mgmt | `i2s_channel_disable` | Stops hardware BCLK and WS clocks, stops DMA reception (`READY` state) | `i2s_chan_handle_t` | `esp_err_t` | Returns `ESP_ERR_INVALID_STATE` if channel is not running | `driver/i2s_common.h:197` |
| 5 | I2S Channel Mgmt | `i2s_del_channel` | Frees DMA descriptors and releases peripheral hardware instance | `i2s_chan_handle_t` | `esp_err_t` | Returns `ESP_ERR_INVALID_ARG` if handle is NULL; must be stopped before deleting | `driver/i2s_common.h:157` |
| 6 | I2S Data Acquisition | `i2s_channel_read` | Blocking read of incoming audio samples from DMA ring buffer into user buffer | `handle`, `dest`, `size`, `bytes_read`, `timeout_ms` | `esp_err_t`, populated `bytes_read` | Returns `ESP_ERR_TIMEOUT` if no data arrives within timeout; `ESP_ERR_INVALID_ARG` on NULL | `driver/i2s_common.h:233` |
| 7 | I2S Clock Config | `I2S_STD_CLK_DEFAULT_CONFIG` | Helper macro for default clock config: internal PLL/APLL, 256x MCLK multiple, bclk_div=8 | `sample_rate_hz` | `i2s_std_clk_config_t` | N/A (macro initialization) | `driver/i2s_std.h:203` |
| 8 | I2S Slot Config | `I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG` | Configures Philips standard mode with 1-bit delay (`bit_shift=true`), WS low for Left | `data_bit_width`, `slot_mode` | `i2s_std_slot_config_t` | Sets `slot_bit_width=AUTO` which must be explicitly overridden to 32 bits for INMP441 | `driver/i2s_std.h:31` |
| 9 | I2S DMA Buffer Sizing | `i2s_get_buf_size` (Internal) | Computes DMA buffer size per descriptor. On ESP32, 24-bit data allocates 4 bytes per sample | `handle`, `data_bit_width`, `dma_frame_num` | `uint32_t` byte size | Returns 0 on invalid configuration | `i2s_common.c:624` |
| 10 | INMP441 Timing | 64-Cycle Frame Requirement | Hardware requires exactly 64 SCK cycles per stereo frame ($f_{SCK} = 64 \times f_s$) | $f_s$ ($8\text{ kHz} \dots 50\text{ kHz}$) | $f_{SCK}$ ($0.5\text{ MHz} \dots 3.2\text{ MHz}$) | Clock frequencies outside $0.5 - 3.2\text{ MHz}$ cause internal PLL desync and distorted output | `INMP441.pdf:5,11` |
| 11 | INMP441 Tri-State Bus | High-Z on SD Line | Output pin tri-states during unused clocks (cycles 26-32) and during non-selected slot | `L/R` pin (GND or VDD) | Tri-state output on inactive slot | Floating bus without pull-down resistor causes spurious bits and high idle noise floor | `INMP441.pdf:11` |
| 12 | INMP441 Startup | Power-up Delay | Sensor outputs zero for first $2^{18}$ SCK cycles ($85\text{ ms}$ @ 3.072 MHz, $256\text{ ms}$ @ 16 kHz) | Power applied ($V_{DD} \ge 1.62\text{V}$) | Zero samples | Reading immediately upon power-up yields silence/settling transient | `INMP441.pdf:10` |
| 13 | Sample Alignment | 24-in-32 Sign Extension | Shifts signed 32-bit raw DMA word right by 8 with arithmetic sign replication | `int32_t raw_sample` | `int32_t audio_24` | Using unsigned shift `>> 8` causes waveform rectification and full-scale DC offset | `MEMORY_ACOUSTIC_ARRAY.md:46` |
| 14 | Multi-Channel Array | Dual I2S Architecture | ESP32 I2S0 and I2S1 controllers yield 4 slots for 3 physical mics | `I2S0_L`, `I2S0_R`, `I2S1_L` | 3 synchronized audio streams | Discard Slot 4 (`I2S1_R`) | `MEMORY_ACOUSTIC_ARRAY.md:158` |

### Edge Cases
| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | `i2s_channel_init_std_mode` | `slot_bit_width = AUTO`, `data_bit_width = 24`, `mclk_multiple = 256` | Rejects configuration with `ESP_ERR_INVALID_ARG`! On ESP32, if `slot_bit_width == 24`, driver enforces `mclk_multiple % 3 == 0`. Setting `slot_bit_width = 32` resolves this and provides INMP441's mandatory 64 SCK cycles. |
| 2 | Sample Bit Shift | `(uint32_t)raw >> 8` on negative sample (`0x80000000`) | Logical right shift produces `0x00800000` (+8,388,608). Negative peak wraps into positive maximum, destroying the lower half of the acoustic waveform and introducing catastrophic DC offset. Arithmetic shift `(int32_t)raw >> 8` produces `0xFF800000` (-8,388,608). |
| 3 | Sample Bit Shift | `((raw >> 8) & 0x00FFFFFF)` on negative sample | Bitwise AND clears bits [31:24], stripping sign extension. Value becomes an unsigned positive integer ($8.38 \times 10^6$ to $1.67 \times 10^7$), corrupting all DSP/RMS calculations. |
| 4 | INMP441 SCK Frequency | Sample rate $f_s = 96\text{ kHz}$ | Generates $f_{SCK} = 96000 \times 64 = 6.144\text{ MHz}$. Exceeds INMP441 maximum clock rating of $3.2\text{ MHz}$, violating datasheet Table 3. Max allowable sample rate is $50\text{ kHz}$. Recommended: $16\text{ kHz}$ or $48\text{ kHz}$. |
| 5 | SD Bus Termination | INMP441 SD line without pull-down resistor | During inactive slots and padding clocks, SD is high-impedance. Capacitive coupling from adjacent high-speed SCK/WS lines injects glitches, causing false non-zero samples and DC drift. A 100 k$\Omega$ pulldown resistor or ESP32 internal pulldown stabilizes the bus to logic 0. |
| 6 | ESP32 Mono vs Stereo RX | Mono mode (`I2S_SLOT_MODE_MONO`) on classic ESP32 silicon | In classic ESP32 (`SOC_I2S_HW_VERSION_1`), channel flipping is observed in hardware tests (`test_i2s.c:723`). If mono Left is selected, driver sets `rx_chan_mod = 1` when `msb_right = false`. If timing desynchronization occurs, mono FIFO can slip. Reading in Stereo mode and extracting the Left channel is unconditionally immune to FIFO slipping. |
| 7 | Driver Initialization | Calling `i2s_channel_enable` before `i2s_channel_init_std_mode` | Driver returns `ESP_ERR_INVALID_STATE` because channel remains in `REGISTERED` state instead of `READY`. |
| 8 | DMA Buffer Sizing | `dma_frame_num` not a multiple of 3 when using 24-bit packed data | Causes DMA buffer alignment warnings. With `slot_bit_width = 32`, each sample is 4 bytes on classic ESP32, so standard default `dma_frame_num = 240` (divisible by 2, 3, 4, 5, 6, 8, 10, 12, 16) is fully aligned. |

---

## 3. ESP-IDF v5/v6 `driver/i2s_std.h` Driver Specifications

### 3.1 Driver State Machine & Lifecycle
The ESP-IDF v5/v6 driver implements an explicit state machine:
```
           i2s_new_channel()               i2s_channel_init_std_mode()
UNREGISTERED -----------------> REGISTERED -----------------------------> READY
                                                                            |  ^
                                                  i2s_channel_enable()      |  | i2s_channel_disable()
                                                                            v  |
                                                                          RUNNING
```
- **UNREGISTERED $\to$ REGISTERED**: Call `i2s_new_channel(&chan_cfg, NULL, &rx_handle)`. Allocates channel control blocks, binds to hardware peripheral `I2S_NUM_0`.
- **REGISTERED $\to$ READY**: Call `i2s_channel_init_std_mode(rx_handle, &std_cfg)`. Configures clocks, slot formats, GPIO matrix routes, and allocates DMA descriptors and buffers.
- **READY $\to$ RUNNING**: Call `i2s_channel_enable(rx_handle)`. Starts hardware clock generation (BCLK and WS) and activates the DMA receiver.
- **RUNNING $\to$ READY**: Call `i2s_channel_disable(rx_handle)`. Stops BCLK and WS generation; halts DMA transfers.
- **Teardown**: Call `i2s_del_channel(rx_handle)` while in `READY` or `REGISTERED` state. Frees all DMA memory and unbinds GPIOs.

### 3.2 Channel Configuration (`i2s_chan_config_t`)
Authoritative structure defined in `driver/i2s_common.h`:
```c
i2s_chan_config_t chan_cfg = {
    .id = I2S_NUM_0,                    // Controller port 0
    .role = I2S_ROLE_MASTER,            // ESP32 generates BCLK and WS
    .dma_desc_num = 6,                  // 6 DMA descriptors (ring buffer)
    .dma_frame_num = 240,               // 240 audio frames per DMA descriptor
    .auto_clear = false,                // RX mode does not require auto_clear
    .allow_pd = false,                  // Keep power domain active
    .intr_priority = 0,                 // Default low priority interrupt (1-3)
    .tx_destination = I2S_DESTINATION_DMA,
    .rx_destination = I2S_DESTINATION_DMA,
};
```
- **Buffer Latency Sizing**:
  At $f_s = 16\text{ kHz}$: $240 \text{ frames} / 16000\text{ Hz} = 15\text{ ms}$ per DMA buffer.
  Total ring buffer capacity: $6 \times 15\text{ ms} = 90\text{ ms}$.
  This provides substantial headroom against FreeRTOS task scheduling jitter while maintaining low read latency.
  At $f_s = 48\text{ kHz}$: $240 / 48000 = 5\text{ ms}$ per buffer ($30\text{ ms}$ total).

### 3.3 Clock Configuration (`i2s_std_clk_config_t`)
Authoritative structure defined in `driver/i2s_std.h`:
```c
i2s_std_clk_config_t clk_cfg = {
    .sample_rate_hz = 16000,            // Target sample rate (e.g. 16000 or 48000)
    .clk_src = I2S_CLK_SRC_DEFAULT,     // System PLL (or APLL)
    .mclk_multiple = I2S_MCLK_MULTIPLE_256, // MCLK = 256 * fs
    .bclk_div = 8,                      // Master role calculates bclk_div internally
};
```
- **BCLK Generation Verification**:
  $$\text{Total Frame Bits} = 2 \times \text{slot\_bit\_width} = 2 \times 32 = 64\text{ bits}$$
  $$f_{\text{BCLK}} = f_s \times 64$$
  $$f_{\text{MCLK}} = f_s \times 256$$
  $$\text{Hardware Divider} = \frac{f_{\text{MCLK}}}{f_{\text{BCLK}}} = \frac{256}{64} = 4$$
  Because $256 \pmod{64} = 0$, the division is an integer. The ESP32 fractional clock divider produces zero phase jitter.

### 3.4 Slot Configuration (`i2s_std_slot_config_t`)
To interface with the INMP441, the slot configuration must be initialized using `I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG` and tailored with explicit slot width:
```c
i2s_std_slot_config_t slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(
    I2S_DATA_BIT_WIDTH_24BIT, 
    I2S_SLOT_MODE_MONO
);
// CRITICAL OVERRIDES FOR INMP441:
slot_cfg.slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT; // Force 32 SCK cycles per slot (64 per frame)
slot_cfg.ws_width = 32;                             // 32 SCK cycles WS high / 32 SCK cycles WS low
slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;             // Read Left slot (INMP441 L/R tied to GND)
slot_cfg.ws_pol = false;                            // Philips standard: WS is LOW for Left channel
slot_cfg.bit_shift = true;                          // 1-bit SCK delay between WS edge and MSB
slot_cfg.msb_right = false;                         // Required for >16-bit words on classic ESP32
```
- **Mono vs Stereo Acquisition Strategy**:
  - **Option A (Pure Mono)**:
    Configuring `slot_mode = I2S_SLOT_MODE_MONO` and `slot_mask = I2S_STD_SLOT_LEFT`.
    DMA buffer receives 1 sample per frame ($4\text{ bytes}$).
    DMA buffer size = $240 \times 4 = 960\text{ bytes}$.
    Direct linear readout: `int32_t sample = raw_buffer[i] >> 8;`.
  - **Option B (Stereo Mode with Left Slot Extraction — Future-Proof)**:
    Configuring `slot_mode = I2S_SLOT_MODE_STEREO` and `slot_mask = I2S_STD_SLOT_BOTH`.
    DMA buffer receives 2 samples per frame ($8\text{ bytes}$): `[Left_0, Right_0, Left_1, Right_1, ...]`.
    DMA buffer size = $240 \times 8 = 1920\text{ bytes}$.
    Mic 1 is extracted via: `sample = raw_buffer[2 * i] >> 8;`.
    Right slot (`raw_buffer[2 * i + 1]`) is discarded in Phase 1.
    *Architectural Benefit*: Upgrading to Phase 2 (dual mics on I2S0) requires **zero** changes to driver configuration, only reading the second array index!

### 3.5 GPIO Configuration (`i2s_std_gpio_config_t`)
```c
i2s_std_gpio_config_t gpio_cfg = {
    .mclk = I2S_GPIO_UNUSED,            // INMP441 has no MCLK pin
    .bclk = GPIO_NUM_4,                 // SCK (Serial Bit Clock)
    .ws   = GPIO_NUM_15,                // WS / LRCK (Word Select)
    .dout = I2S_GPIO_UNUSED,            // Microphone is RX only
    .din  = GPIO_NUM_32,                // SD (Serial Data In)
    .invert_flags = {
        .mclk_inv = false,
        .bclk_inv = false,
        .ws_inv   = false,
    },
};
```
*Pin Safety Justification*:
- GPIO 4 (BCLK): General-purpose IO, fully accessible, supports high-speed matrix output.
- GPIO 15 (WS): General-purpose IO. Outputs boot ROM log during reset, but acts as clean high-speed clock output during operation without strapping interference.
- GPIO 32 (DIN): In RTC and digital matrix domain; clean input pad with internal pull-down capability.
- Avoids flash pins (GPIO 6-11) and strapping pins (GPIO 0, 2, 12).

---

## 4. INMP441 MEMS Microphone Hardware Specifications

Authoritative extraction from InvenSense datasheet `DS-INMP441-00` Rev 1.1:

### 4.1 Acoustic and Electrical Ratings
| Parameter | Specification | Practical Implication |
| :--- | :--- | :--- |
| **Operating Voltage ($V_{DD}$)** | $1.62\text{ V}$ to $3.63\text{ V}$ | Directly compatible with ESP32 $3.3\text{ V}$ rail. Do NOT power with 5V. |
| **Current Consumption** | $1.4\text{ mA}$ (active), $10\,\mu\text{A}$ (standby) | Extremely low power; can run off ESP32 3.3V LDO regulator. |
| **Acoustic Directivity** | Omnidirectional | Uniform spherical sensitivity; optimal for spatial TDOA arrays. |
| **Sensitivity** | $-26\text{ dBFS} \pm 3\text{ dB}$ ($1\text{ kHz}, 94\text{ dB SPL}$) | $94\text{ dB SPL} \implies$ peak digital amplitude is $2^{23} \times 10^{-26/20} \approx 420,426$. |
| **Signal-to-Noise Ratio (SNR)** | $61\text{ dBA}$ | Noise floor equivalent to $\approx 33\text{ dB SPL}$. |
| **Dynamic Range** | $87\text{ dB}$ | High dynamic range capturing whisper to loud clapping. |
| **Acoustic Overload Point (AOP)** | $120\text{ dB SPL}$ | Undistorted capture up to loud shouting/percussion. |
| **Frequency Response** | $60\text{ Hz} - 15\text{ kHz}$ | Built-in high-pass roll-off below $60\text{ Hz}$ rejects subsonic vibrations. |
| **Supported Sample Rates ($f_s$)** | $7.8\text{ kHz}$ to $50\text{ kHz}$ | Ideal operation at $16\text{ kHz}$ (speech) or $48\text{ kHz}$ (full bandwidth). |
| **Clock Range ($f_{SCK}$)** | $0.5\text{ MHz}$ to $3.2\text{ MHz}$ | Must equal $64 \times f_s$. At $16\text{ kHz} \implies 1.024\text{ MHz}$; at $48\text{ kHz} \implies 3.072\text{ MHz}$. |
| **Startup Delay** | $2^{18}$ SCK cycles | $\approx 85\text{ ms}$ @ $48\text{ kHz}$; $\approx 256\text{ ms}$ @ $16\text{ kHz}$. Audio reads zero during startup. |

### 4.2 Breakout Pinout & Wiring Connections
The standard 6-pin INMP441 breakout board exposes:
1. **`VDD`**: Connect to ESP32 $3.3\text{ V}$. Place a $0.1\,\mu\text{F}$ decoupling capacitor near the pin.
2. **`GND`**: Connect to ESP32 Ground.
3. **`SD` (Serial Data)**: Tri-state output. Connect to ESP32 `GPIO 32`. Requires a $100\text{ k}\Omega$ pull-down resistor or ESP32 internal pull-down enabled.
4. **`WS` (Word Select / LRCK)**: Frame clock. Connect to ESP32 `GPIO 15`.
5. **`SCK` (Serial Clock / BCLK)**: Continuous bit clock. Connect to ESP32 `GPIO 4`.
6. **`L/R` (Left/Right Channel Select)**:
   - Connect to **`GND`**: Microphone drives SD during Left slot ($WS = \text{LOW}$).
   - Connect to **`VDD`**: Microphone drives SD during Right slot ($WS = \text{HIGH}$).
   - For Phase 1, tie `L/R` firmly to **`GND`**.

### 4.3 Detailed Timing & Slot Framing (Figure 8 & Figure 9 in Datasheet)
- **Start of Frame**: WS transitions from HIGH to LOW (Left channel begins).
- **Cycle 1**: 1-bit SCK delay (Philips standard). SD is in High-Z.
- **Cycles 2 to 25 (24 bits)**: INMP441 shifts out the 24-bit two's complement audio word, **MSB-first**.
  - Cycle 2: Bit 23 (Sign bit $S$)
  - Cycle 3: Bit 22
  - ...
  - Cycle 25: Bit 0 (LSB)
- **Cycles 26 to 32 (7 bits)**: INMP441 immediately tri-states the SD pin (High-Z). The pull-down resistor pulls SD to logic 0.
- **WS transitions LOW to HIGH (Right channel begins)**:
  - If `L/R` is GND: INMP441 remains completely High-Z for all 32 cycles of the Right channel.
  - If a second INMP441 with `L/R` tied to VDD is connected to the same SD line, it drives cycles 34 to 57 without bus contention.

---

## 5. 24-in-32 Bit Alignment, Sign Extension & Distortion Prevention

### 5.1 Bit Mapping in 32-Bit Memory
When the ESP32 I2S hardware receives a 32-bit slot via DMA into a 32-bit word (`int32_t raw_sample`):
```
Bit 31: S (Sign Bit / Bit 23 of audio)
Bits 30..8: Audio Data Bits [22..0]
Bits 7..0: 0x00 (Trailing 8 bits during High-Z / pull-down)
```
In hexadecimal:
- Positive maximum ($+8,388,607$): `0x7FFFFF00`
- Negative maximum ($-8,388,608$): `0x80000000`
- Zero ($0$): `0x00000000`
- Negative one ($-1$): `0xFFFFFF00`

### 5.2 Arithmetic Sign Extension Formula
Because the 24 audio bits occupy the most significant bits `[31:8]` of the signed 32-bit integer, extraction is achieved via a single arithmetic right shift:
$$\text{audio}_{24} = \text{raw\_sample} \gg 8$$

In C / C99 (Xtensa GCC compiler):
```c
int32_t raw_sample = dma_buffer[i];
int32_t audio_24 = raw_sample >> 8;
```
**Proof of Sign Preservation**:
1. When `raw_sample >= 0` ($S = 0$):
   Upper 8 bits become `0x00`.
   `0x7FFFFF00 >> 8` $\implies$ `0x007FFFFF` ($+8,388,607$).
2. When `raw_sample < 0` ($S = 1$):
   The arithmetic right shift (`ASR`) replicates the sign bit into bits `[31:24]`, filling them with `0xFF`.
   `0x80000000 >> 8` $\implies$ `0xFF800000` ($-8,388,608$).
   `0xFFFFFF00 >> 8` $\implies$ `0xFFFFFFFF` ($-1$).
Sign extension is exact, preserving the full signed dynamic range.

### 5.3 Normalization for DSP & Plotting
- **To Floating Point ($[-1.0, +1.0)$)**:
  ```c
  float sample_norm = (float)audio_24 / 8388608.0f; // 8388608 = 2^23
  ```
  Or directly from the raw 32-bit word:
  ```c
  float sample_norm = (float)raw_sample / 2147483648.0f; // 2147483648 = 2^31
  ```
- **To 16-Bit Signed Integer ($[-32768, +32767]$)**:
  ```c
  int16_t audio_16 = (int16_t)(raw_sample >> 16); // Direct top-16 bit extraction
  ```

### 5.4 Pitfalls Causing DC Saturation, Bit Inversion & Distortion
1. **Unsigned Shift Bug**:
   Declaring the buffer as `uint32_t *raw_buf` and shifting: `uint32_t val = raw_buf[i] >> 8;`.
   Logical shift right pads with zeros, turning negative values into large positive numbers ($+8.38 \times 10^6$), completely inverting the negative half of the waveform and causing severe clipping and DC offset.
2. **Masking after Shift**:
   Executing `int32_t audio = (raw_sample >> 8) & 0x00FFFFFF;`.
   The `& 0x00FFFFFF` mask clears the replicated sign bits `[31:24]`, destroying negative sign representation.
3. **Floating SD Line**:
   Omitting a pull-down resistor on SD. During the 8 idle clocks at the end of each slot, a floating input drifts high or couples to BCLK, injecting non-zero bits into bits `[7:0]` and causing high idle noise floor.
4. **Inverting WS Polarity**:
   Setting `ws_pol = true`. The ESP32 will read during the Right half-cycle where the Left microphone is in High-Z, reading only zeroes or bus noise.
5. **Disabling Bit Shift**:
   Setting `bit_shift = false`. Disables the Philips 1-bit delay. The ESP32 samples 1 cycle early, reading the 1-bit idle state as the MSB and shifting the audio bits by 1 bit, halving signal amplitude and creating bit toggle distortion.

---

## 6. Future 3-Microphone Array Architecture Alignment

Per `MEMORY_ACOUSTIC_ARRAY.md` Section 5 and the user update:
The acoustic source localization array consists of 3 INMP441 microphones arranged in an equilateral triangle ($d = 20\text{ cm}$).

### 6.1 Hardware Resource Allocation & 4-Slot Architecture
The ESP32 microcontroller integrates two independent hardware I2S controllers (`I2S_NUM_0` and `I2S_NUM_1`), each with stereo DMA capability (4 total slots):

| Slot # | Controller & Slot | Sensor Assignment | Wiring Connection | Breakout L/R Pin | Status |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **Slot 1** | **I2S0 Left** | **Microphone 1** ($\mathbf{p}_1$, Top) | `SCK0`, `WS0`, `SD0` | Tied to **GND** | **Active in Phase 1** |
| **Slot 2** | **I2S0 Right** | **Microphone 2** ($\mathbf{p}_2$, Bottom-Left) | Shares `SCK0`, `WS0`, `SD0` | Tied to **VDD** | Added in Phase 2 |
| **Slot 3** | **I2S1 Left** | **Microphone 3** ($\mathbf{p}_3$, Bottom-Right) | Shares `SCK0`, `WS0`; `SD1` | Tied to **GND** | Added in Phase 3 |
| **Slot 4** | **I2S1 Right** | Unused / Discarded | No connection | N/A | Ignored in software |

```
                       ESP32 Microcontroller
              +-------------------------------------+
              | I2S Controller 0 (Master)           |
              |   BCLK (GPIO 4) -----------------+--+---------> Mic 1 SCK, Mic 2 SCK, Mic 3 SCK
              |   WS   (GPIO 15) --------------+-+--+---------> Mic 1 WS,  Mic 2 WS,  Mic 3 WS
              |   DIN  (GPIO 32) <-----------+-+----+--------- Mic 1 SD (L/R=GND)
              |                              |      |          Mic 2 SD (L/R=VDD)
              | I2S Controller 1 (Slave/Sync)+      |
              |   DIN  (GPIO 33) <-----------+------+--------- Mic 3 SD (L/R=GND)
              +-------------------------------------+
```

### 6.2 Clock Synchronization for Phase Coherence
Acoustic source localization relies on measuring sub-millisecond Time Differences of Arrival ($\Delta t_{ij} \le 583.1\,\mu\text{s}$). If I2S0 and I2S1 ran on independent, unsynchronized clock dividers, phase drift would invalidate cross-correlation and FFT phase extraction.
- **Synchronization Strategy**:
  - `I2S_NUM_0` runs as the **Clock Master**, driving physical pins `SCK` and `WS`.
  - All 3 microphones receive the identical `SCK` and `WS` clock traces.
  - `I2S_NUM_1` is configured with identical clock parameters and synchronizes its reception to the master BCLK/WS, ensuring sample-accurate phase coherence across all 3 channels.

### 6.3 Buffer Demuxing Pipeline
When DMA buffers are filled:
```c
// I2S0 DMA buffer provides interleaved Mic 1 (Left) and Mic 2 (Right)
int32_t mic1_sample = i2s0_buf[2 * i] >> 8;
int32_t mic2_sample = i2s0_buf[2 * i + 1] >> 8;

// I2S1 DMA buffer provides Mic 3 (Left) and unused Slot 4 (Right)
int32_t mic3_sample = i2s1_buf[2 * i] >> 8;
// i2s1_buf[2 * i + 1] is discarded
```

### 6.4 Phase 1 Non-Breaking Migration Path
By implementing Phase 1 with modular driver isolation:
1. Phase 1 defines GPIO assignments for `SCK`, `WS`, and `SD` on I2S0.
2. In Phase 2, soldering Mic 2 onto the exact same PCB/breadboard header pins (`SCK`, `WS`, `SD`) with `L/R` to VDD requires zero pin changes.
3. In Phase 3, adding Mic 3 requires connecting only 1 additional GPIO pin (`SD1` on GPIO 33), while reusing `SCK` and `WS`.

---

## 7. Robust Error Handling & Driver Verification Patterns

### 7.1 ESP-IDF v5/v6 Error Handling Conventions
1. **Macro `ESP_RETURN_ON_ERROR` vs `ESP_ERROR_CHECK`**:
   - In initialization routines (`app_main` or driver setup): `ESP_ERROR_CHECK` is acceptable for critical hardware allocation failure where execution cannot continue without the microphone.
   - In modular library functions: Always return `esp_err_t` and use `ESP_RETURN_ON_ERROR(ret, TAG, "error message")` or `ESP_GOTO_ON_ERROR` to ensure clean resource deallocation.
2. **Resource Deallocation Order (Clean Teardown)**:
   ```c
   void i2s_microphone_deinit(i2s_chan_handle_t rx_handle) {
       if (rx_handle) {
           i2s_channel_disable(rx_handle);
           i2s_del_channel(rx_handle);
       }
   }
   ```
3. **Data Acquisition Loop Error Handling**:
   In `i2s_channel_read(rx_handle, buf, size, &bytes_read, timeout_ms)`:
   - Handle `ESP_ERR_TIMEOUT` gracefully (e.g. increment timeout counter, do not panic).
   - Verify `bytes_read == size` before processing audio samples.

---

## 8. Reference Implementation Blueprint (Phase 1)

```c
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_check.h"

#define TAG "INMP441_DRIVER"

// Pin Definitions
#define I2S_MIC_SCK_IO      GPIO_NUM_4   // BCLK
#define I2S_MIC_WS_IO       GPIO_NUM_15  // LRCK
#define I2S_MIC_SD_IO       GPIO_NUM_32  // Data In

#define SAMPLE_RATE_HZ      16000
#define DMA_BUFFER_FRAMES   240
#define DMA_DESCRIPTOR_NUM  6

static i2s_chan_handle_t s_rx_handle = NULL;

esp_err_t inmp441_i2s_init(void)
{
    // 1. Channel allocation
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = DMA_DESCRIPTOR_NUM;
    chan_cfg.dma_frame_num = DMA_BUFFER_FRAMES;
    ESP_RETURN_ON_ERROR(i2s_new_channel(&chan_cfg, NULL, &s_rx_handle), TAG, "Alloc channel failed");

    // 2. Standard mode configuration
    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(SAMPLE_RATE_HZ),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_24BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = I2S_MIC_SCK_IO,
            .ws   = I2S_MIC_WS_IO,
            .dout = I2S_GPIO_UNUSED,
            .din  = I2S_MIC_SD_IO,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv   = false,
            },
        },
    };
    
    // Crucial INMP441 timing overrides
    std_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
    std_cfg.slot_cfg.slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT; // 32 bits per slot (64 cycles per frame)
    std_cfg.slot_cfg.ws_width = 32;
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;
    std_cfg.slot_cfg.ws_pol = false;
    std_cfg.slot_cfg.bit_shift = true;
    std_cfg.slot_cfg.msb_right = false;

    // Enable internal pull-down on SD pin to prevent floating High-Z noise
    gpio_set_pull_mode(I2S_MIC_SD_IO, GPIO_PULLDOWN_ONLY);

    ESP_RETURN_ON_ERROR(i2s_channel_init_std_mode(s_rx_handle, &std_cfg), TAG, "Init std mode failed");

    // 3. Enable channel
    ESP_RETURN_ON_ERROR(i2s_channel_enable(s_rx_handle), TAG, "Enable channel failed");

    ESP_LOGI(TAG, "INMP441 I2S standard driver initialized successfully at %d Hz", SAMPLE_RATE_HZ);
    return ESP_OK;
}

void audio_read_task(void *pvParameters)
{
    int32_t raw_samples[DMA_BUFFER_FRAMES];
    size_t bytes_read = 0;

    while (1) {
        esp_err_t ret = i2s_channel_read(s_rx_handle, raw_samples, sizeof(raw_samples), &bytes_read, pdMS_TO_TICKS(100));
        if (ret == ESP_OK && bytes_read > 0) {
            uint32_t sample_count = bytes_read / sizeof(int32_t);
            int64_t sum_squares = 0;

            for (uint32_t i = 0; i < sample_count; i++) {
                // Arithmetic sign extension: extract 24-bit audio
                int32_t sample = raw_samples[i] >> 8;
                sum_squares += ((int64_t)sample * sample);
            }

            int32_t rms = (int32_t)sqrt((double)sum_squares / sample_count);
            // Telemetry output for Serial Plotter
            printf("sample:%ld,rms:%ld\n", (long)(raw_samples[0] >> 8), (long)rms);
        } else if (ret == ESP_ERR_TIMEOUT) {
            ESP_LOGW(TAG, "I2S read timeout");
        }
    }
}
```

---

## 9. Conclusion & Recommendations

1. **Adopt `slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT`**: The INMP441 hardware requires 64 SCK cycles per frame. This configuration guarantees timing compliance and enables clean 256x MCLK integer clock division.
2. **Apply `raw_sample >> 8` with Signed `int32_t`**: Guarantees true arithmetic sign extension, preserving the complete 24-bit dynamic range without DC offset or inversion.
3. **Internal Pull-Down on SD**: Always enable `gpio_set_pull_mode(SD_PIN, GPIO_PULLDOWN_ONLY)` or ensure a $100\text{ k}\Omega$ resistor is present to ground floating High-Z cycles.
4. **Hardware Continuity to Phase 2/3**: The chosen GPIO layout and I2S0 Left channel assignment ensure that Phase 2 (I2S0 Right) and Phase 3 (I2S1 Left) can be incrementally built upon this foundation without rework.

# Milestone M1 Specification Mining Report: ESP-IDF v5/v6 I2S Standard Driver & INMP441 Integration

**Target Platform**: Espressif ESP32 (Xtensa 32-bit LX6 dual-core)  
**Framework**: ESP-IDF v6.1.0 / v5.x (`driver/i2s_std.h`, `driver/i2s_common.h`, `hal/i2s_types.h`)  
**Microphone**: InvenSense / TDK INMP441 Omnidirectional Digital MEMS Microphone  
**Milestone Focus**: M1 (Core Audio Engine & Configuration)  
**Mining Date**: 2026-10-06  

---

## 1. Executive Summary

This report delivers the authoritative specification mining results for Milestone M1 (Core Audio Engine). All data structures, enum constants, error returns, lifecycle states, and timing constraints have been verified against the active ESP-IDF framework headers and source files in `C:\Users\hp\.platformio\packages\framework-espidf\components\esp_driver_i2s\` and `esp_hal_i2s\`.

### Key Technical Findings:
1. **Mandatory 32-Bit Slot Width**: The INMP441 requires exactly 64 bit clock (SCK/BCLK) cycles per stereo frame (32 cycles per slot). In `i2s_std_slot_config_t`, the default helper macro sets `slot_bit_width = I2S_SLOT_BIT_WIDTH_AUTO`, which normalizes to 24 bits. On ESP32, this causes `i2s_channel_init_std_mode` to reject `mclk_multiple = 256` with `ESP_ERR_INVALID_ARG` (enforcing `mclk_multiple % 3 == 0`). Explicitly setting `.slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT` and `.ws_width = 32` satisfies the INMP441 physical 64-cycle requirement and yields an exact integer BCLK divider ($256 / 64 = 4$) with zero fractional phase jitter.
2. **ESP32 24-in-32 DMA Allocation**: Per `i2s_common.c:628`, classic ESP32 calculates bytes per sample as `((data_bit_width + 15) / 16) * 2`. For 24-bit data, this evaluates to 4 bytes (32-bit signed word `int32_t`). The 24 bits of valid audio occupy bits `[31:8]`, with trailing bits `[7:0]` padded with zeros.
3. **Exact Deallocation Lifecycle**:
   - `i2s_channel_disable(handle)` requires `handle->state == I2S_CHAN_STATE_RUNNING`; calling it on `READY` or `REGISTERED` returns `ESP_ERR_INVALID_STATE`.
   - `i2s_del_channel(handle)` requires `handle->state < I2S_CHAN_STATE_RUNNING`; calling it while `RUNNING` returns `ESP_ERR_INVALID_STATE`.
   - Therefore, a clean deinit sequence for an active driver MUST be `i2s_channel_disable(handle)` followed by `i2s_del_channel(handle)`. If initialization aborted before enabling, ONLY `i2s_del_channel(handle)` must be called.
4. **No Legacy `i2s_port_t`**: In ESP-IDF v6.1.0, the legacy `i2s_port_t` enum is deprecated/removed from modern headers; port IDs are passed as integers (`int id`) with macros `I2S_NUM_0` (0), `I2S_NUM_1` (1), and `I2S_NUM_AUTO` (-1).
5. **3-Microphone Array Alignment**: The ESP32 provides 4 slots across its 2 stereo controllers: `I2S0_L` (Mic 1, Phase 1), `I2S0_R` (Mic 2, Phase 2), `I2S1_L` (Mic 3, Phase 3), and `I2S1_R` (Slot 4, discarded). Configuring `i2s_mic_config_t` with explicit `i2s_port` and modular pin definitions enables zero-overhead expansion to Phase 2 and 3.

---

## 2. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Channel Lifecycle | `i2s_new_channel` | Allocates channel object, FreeRTOS message queue and semaphores, binds peripheral controller (`UNREGISTERED` $\to$ `REGISTERED`) | `const i2s_chan_config_t *chan_cfg`, `i2s_chan_handle_t *tx_handle`, `i2s_chan_handle_t *rx_handle` | `esp_err_t`, populated handles | Returns `ESP_ERR_INVALID_ARG` on NULL pointers, `dma_desc_num < 2`, invalid `id`, or `intr_priority > 7`; `ESP_ERR_NOT_FOUND` if controller busy; `ESP_ERR_NO_MEM` on allocation failure | `driver/i2s_common.h:146`, `i2s_common.c:1192` |
| 2 | Channel Lifecycle | `i2s_channel_init_std_mode` | Configures clock tree, slot format, GPIO matrix routing, and allocates DMA descriptor ring buffer (`REGISTERED` $\to$ `READY`) | `i2s_chan_handle_t handle`, `const i2s_std_config_t *std_cfg` | `esp_err_t` | Returns `ESP_ERR_INVALID_STATE` if channel is not in `REGISTERED` state; `ESP_ERR_INVALID_ARG` on invalid pins, sample rate out of bounds, or 24-bit slot without mod-3 MCLK; `ESP_ERR_NO_MEM` on DMA buffer allocation failure | `driver/i2s_std.h:320`, `i2s_std.c:317` |
| 3 | Channel Lifecycle | `i2s_channel_enable` | Starts hardware clock output (BCLK, WS) and triggers DMA peripheral reception (`READY` $\to$ `RUNNING`) | `i2s_chan_handle_t handle` | `esp_err_t` | Returns `ESP_ERR_INVALID_ARG` on NULL; `ESP_ERR_INVALID_STATE` if channel is not `READY` (not initialized or already started) | `driver/i2s_common.h:183`, `i2s_common.c:1480` |
| 4 | Channel Lifecycle | `i2s_channel_disable` | Halts hardware BCLK and WS generation and stops DMA reception (`RUNNING` $\to$ `READY`) | `i2s_chan_handle_t handle` | `esp_err_t` | Returns `ESP_ERR_INVALID_ARG` on NULL; `ESP_ERR_INVALID_STATE` if channel is not in `RUNNING` state | `driver/i2s_common.h:197`, `i2s_common.c:1510` |
| 5 | Channel Lifecycle | `i2s_del_channel` | Frees DMA descriptors, DMA buffers, FreeRTOS queue, binary semaphore, mutex, revokes GPIOs, and clears channel occupancy | `i2s_chan_handle_t handle` | `esp_err_t` | Returns `ESP_ERR_INVALID_ARG` on NULL; returns `ESP_ERR_INVALID_STATE` if called while channel is `RUNNING` (must disable first!) | `driver/i2s_common.h:157`, `i2s_common.c:1314` |
| 6 | Data Acquisition | `i2s_channel_read` | Synchronously reads audio frames from the DMA ring buffer queue into caller-provided memory | `i2s_chan_handle_t handle`, `void *dest`, `size_t size`, `size_t *bytes_read`, `uint32_t timeout_ms` | `esp_err_t`, populated `bytes_read` | Returns `ESP_ERR_INVALID_ARG` on NULL handle/dest or if handle is TX; `ESP_ERR_INVALID_STATE` if not `RUNNING`; `ESP_ERR_TIMEOUT` if no DMA buffer completes within timeout | `driver/i2s_common.h:233`, `i2s_common.c:1658` |
| 7 | Channel Diagnostics | `i2s_channel_get_info` | Retrieves runtime channel information including port ID, role, direction, clock frequencies (sclk, mclk, bclk), and total DMA buffer size | `i2s_chan_handle_t handle`, `i2s_chan_info_t *chan_info` | `esp_err_t`, populated `chan_info` | Returns `ESP_ERR_INVALID_ARG` on NULL pointer; `ESP_ERR_NOT_FOUND` if handle does not match registered controllers | `driver/i2s_common.h:169` |
| 8 | Dynamic Tuning | `i2s_channel_reconfig_std_clock` | Updates sample rate or clock parameters while remaining registered without full teardown | `i2s_chan_handle_t handle`, `const i2s_std_clk_config_t *clk_cfg` | `esp_err_t` | Returns `ESP_ERR_INVALID_STATE` if channel is running (must call `i2s_channel_disable` first) or not initialized; `ESP_ERR_INVALID_ARG` on NULL or invalid clock | `driver/i2s_std.h:335`, `i2s_std.c:386` |
| 9 | Dynamic Tuning | `i2s_channel_reconfig_std_slot` | Reconfigures slot parameters and reallocates DMA buffers if buffer size changes | `i2s_chan_handle_t handle`, `const i2s_std_slot_config_t *slot_cfg` | `esp_err_t` | Returns `ESP_ERR_INVALID_STATE` if running; `ESP_ERR_NO_MEM` if reallocated DMA buffers fail; `ESP_ERR_INVALID_ARG` on NULL | `driver/i2s_std.h:352` |
| 10 | Dynamic Tuning | `i2s_channel_reconfig_std_gpio` | Re-routes BCLK, WS, DIN pins without destroying channel object | `i2s_chan_handle_t handle`, `const i2s_std_gpio_config_t *gpio_cfg` | `esp_err_t` | Returns `ESP_ERR_INVALID_STATE` if running; `ESP_ERR_INVALID_ARG` on invalid GPIO numbers | `driver/i2s_std.h:367` |
| 11 | Clock Helper Macro | `I2S_STD_CLK_DEFAULT_CONFIG` | Initializes `i2s_std_clk_config_t` with default system PLL clock source and 256x MCLK multiplier | `rate` (sample rate in Hz) | `i2s_std_clk_config_t` | Macro initialization; evaluates `sample_rate_hz = rate`, `clk_src = I2S_CLK_SRC_DEFAULT`, `mclk_multiple = I2S_MCLK_MULTIPLE_256`, `bclk_div = 8` | `driver/i2s_std.h:203` |
| 12 | Slot Helper Macro | `I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG` | Initializes standard Philips mode with 1-bit delay (`bit_shift=true`), WS low for Left slot, `slot_bit_width=AUTO` | `bits_per_sample`, `mono_or_stereo` | `i2s_std_slot_config_t` | Macro initialization; sets `slot_bit_width = I2S_SLOT_BIT_WIDTH_AUTO`, which MUST be manually overridden to `I2S_SLOT_BIT_WIDTH_32BIT` for INMP441 | `driver/i2s_std.h:31` |
| 13 | Channel Helper Macro | `I2S_CHANNEL_DEFAULT_CONFIG` | Initializes default DMA channel parameters: 6 descriptors, 240 frames/desc, DMA destination | `i2s_num`, `i2s_role` | `i2s_chan_config_t` | Macro initialization; configures `dma_desc_num = 6`, `dma_frame_num = 240`, `tx_destination = DMA`, `rx_destination = DMA` | `driver/i2s_common.h:22` |
| 14 | Sample Math | Signed Arithmetic Shift | Arithmetic right shift `>> 8` on signed 32-bit word (`int32_t`) extracts 24-bit waveform with full sign bit extension | `int32_t raw_32` | `int32_t audio_24` (range: $[-8388608, +8388607]$) | Unsigned shift `(uint32_t)raw >> 8` causes sign inversion (+8.38M DC step); Bitmask `& 0x00FFFFFF` truncates sign extension bits `[31:24]` | `MEMORY_ACOUSTIC_ARRAY.md:46` |
| 15 | GPIO Signal Conditioning | Internal Pulldown | Configures internal pull-down resistor on SD (Data In) pin | `gpio_num_t gpio`, `GPIO_PULLDOWN_ONLY` | `esp_err_t` | Floating SD pin during High-Z slot cycles (cycles 26-32) causes bus capacitance crosstalk and high idle noise floor | `driver/gpio.h`, `i2s_microphone.c` |

---

## 3. Edge Cases Discovered

| # | Feature | Input / Condition | Observed Behavior | Root Cause & Resolution |
|---|---------|-------------------|-------------------|-------------------------|
| 1 | `i2s_channel_init_std_mode` | `slot_bit_width = AUTO`, `data_bit_width = 24`, `mclk_multiple = 256` | Rejects configuration with `ESP_ERR_INVALID_ARG` | `i2s_std.c:87`: If `slot_bit_width` is 24, driver checks `(mclk_multiple % 3 == 0)`. Because $256 \pmod 3 = 1$, check fails. **Resolution**: Explicitly override `slot_bit_width = I2S_SLOT_BIT_WIDTH_32BIT`. |
| 2 | Deallocation Ordering | Calling `i2s_del_channel` while channel is in `RUNNING` state | Returns `ESP_ERR_INVALID_STATE` and fails to free resources | `i2s_common.c:1317`: Driver explicitly enforces `handle->state < I2S_CHAN_STATE_RUNNING`. **Resolution**: Must call `i2s_channel_disable(handle)` before `i2s_del_channel(handle)`. |
| 3 | Deallocation on Init Failure | Calling `i2s_channel_disable` after `i2s_channel_init_std_mode` fails | Returns `ESP_ERR_INVALID_STATE` | `i2s_common.c:1516`: `i2s_channel_disable` enforces `handle->state > I2S_CHAN_STATE_READY`. If init fails, state remains `REGISTERED`. Calling disable triggers error. **Resolution**: If initialization fails, call `i2s_del_channel(handle)` directly without calling `i2s_channel_disable`. |
| 4 | Channel Allocation | `chan_cfg.dma_desc_num = 1` | `i2s_new_channel` fails with `ESP_ERR_INVALID_ARG` | `i2s_common.c:1201`: Driver enforces `chan_cfg->dma_desc_num >= 2` because the FreeRTOS message queue depth is allocated as `desc_num - 1` (`i2s_common.c:468`). Depth 1 requires at least 2 descriptors. Recommended: `dma_desc_num = 6`. |
| 5 | Classic ESP32 Silicon Mono RX | Classic ESP32 (`SOC_I2S_HW_VERSION_1`) Mono Left RX | Errata can cause FIFO channel flipping / phase inversion | `test_i2s.c:723`: Hardware tests document channel flipping on classic ESP32 in mono mode. **Resolution**: In Phase 1, mono Left with `slot_mask = I2S_STD_SLOT_LEFT` operates reliably if `msb_right = false`; or Stereo mode (`I2S_STD_SLOT_BOTH`) with extracting index `2*i` provides total immunity to FIFO slipping and aligns with Phase 2. |
| 6 | DMA Frame Sizing | `dma_frame_num` when using 24-bit audio | Buffer sizes must align with hardware words | On classic ESP32, 24-bit samples occupy 4 bytes each (`bytes_per_sample = 4`). Standard `dma_frame_num = 240` yields $240 \times 4 = 960$ bytes per buffer (divisible by 16, cache-aligned). |
| 7 | Sample Extraction Bit-Shift | Shifting unsigned integer: `(uint32_t)raw >> 8` on negative sample (`0x80000000`) | Logical right shift produces `0x00800000` (+8,388,608), inverting the negative waveform | Logical shift fills upper 8 bits with 0 instead of 1. Negative peak wraps into positive maximum, destroying the signal. **Resolution**: Cast raw DMA word strictly to signed `int32_t` before shifting (`(int32_t)raw >> 8`). |
| 8 | Sample Extraction Masking | Shifting followed by 24-bit mask: `((int32_t)raw >> 8) & 0x00FFFFFF` | Mask zeroes bits `[31:24]`, stripping sign extension | Negative values ($< 0$) have bits `[31:24] = 0xFF`. Masking forces them to $0x00$, converting negative samples into large positive numbers ($+8.38 \times 10^6$ to $+1.67 \times 10^7$). **Resolution**: Do NOT apply a 24-bit mask after arithmetic shifting. |
| 9 | Unused / High-Z SD Bus | INMP441 SD line without pull-down resistor during non-selected slot cycles | Floating bus couples capacitive noise into DMA buffer | INMP441 tri-states SD during cycles 26-32 and entire Right slot. High-impedance traces pick up SCK/WS edges, producing spurious bits in lower byte and elevating noise floor. **Resolution**: Call `gpio_set_pull_mode(sd_pin, GPIO_PULLDOWN_ONLY)` during initialization. |
| 10 | INMP441 Startup Settling | Reading audio immediately after peripheral clock start | Audio samples read as 0 or DC transient for first $2^{18}$ clocks | Datasheet Section 4 specifies $2^{18}$ SCK cycles power-up delay ($\approx 256\text{ ms}$ at 16 kHz, $\approx 85\text{ ms}$ at 48 kHz). **Resolution**: Discard first 2-3 DMA buffers after starting capture before computing RMS/Peak metrics. |
| 11 | Excessive Clock Frequency | Sample rate configured to $f_s = 96\text{ kHz}$ | Generates $f_{SCK} = 6.144\text{ MHz}$, exceeding INMP441 maximum rating | Datasheet Table 3 limits $f_{SCK}$ to $3.2\text{ MHz}$ ($f_s \le 50\text{ kHz}$). Exceeding this causes internal decimator clock desynchronization and corrupted audio. **Resolution**: Enforce $f_s \le 48000\text{ Hz}$ (default $16000\text{ Hz}$). |

---

## 4. Exact Struct Definitions & Enum Constants

### 4.1 Channel Configuration: `i2s_chan_config_t`
Authoritative source: `components/esp_driver_i2s/include/driver/i2s_common.h:64`
```c
typedef struct {
    int                 id;                 /*!< I2S port id: I2S_NUM_0, I2S_NUM_1, or I2S_NUM_AUTO */
    i2s_role_t          role;               /*!< I2S role: I2S_ROLE_MASTER or I2S_ROLE_SLAVE */
    uint32_t            dma_desc_num;       /*!< DMA descriptor count (ring buffer depth), must be >= 2 (default: 6) */
    uint32_t            dma_frame_num;      /*!< Number of audio frames per DMA descriptor (default: 240) */
    union {
        bool            auto_clear;         /*!< Alias of auto_clear_after_cb */
        bool            auto_clear_after_cb;/*!< Clear DMA TX buffer after on_sent callback (false for RX) */
    };
    bool                auto_clear_before_cb;/*!< Clear DMA TX buffer before on_sent callback (false for RX) */
    bool                allow_pd;           /*!< Allow power down retention (false for classic ESP32) */
    int                 intr_priority;      /*!< Interrupt priority [0..7], 0 = default low/medium priority (1-3) */
    i2s_destination_t   tx_destination;     /*!< TX data path: I2S_DESTINATION_DMA or I2S_DESTINATION_BT */
    i2s_destination_t   rx_destination;     /*!< RX data path: I2S_DESTINATION_DMA or I2S_DESTINATION_BT */
} i2s_chan_config_t;
```

**Default Macro**: `I2S_CHANNEL_DEFAULT_CONFIG(i2s_num, i2s_role)`
```c
#define I2S_CHANNEL_DEFAULT_CONFIG(i2s_num, i2s_role) { \
    .id = i2s_num, \
    .role = i2s_role, \
    .dma_desc_num = 6, \
    .dma_frame_num = 240, \
    .auto_clear_after_cb = false, \
    .auto_clear_before_cb = false, \
    .allow_pd = false, \
    .intr_priority = 0, \
    .tx_destination = I2S_DESTINATION_DMA, \
    .rx_destination = I2S_DESTINATION_DMA, \
}
```

### 4.2 Standard Mode Composite Config: `i2s_std_config_t`
Authoritative source: `components/esp_driver_i2s/include/driver/i2s_std.h:292`
```c
typedef struct {
    i2s_std_clk_config_t    clk_cfg;    /*!< Standard mode clock configuration */
    i2s_std_slot_config_t   slot_cfg;   /*!< Standard mode slot configuration */
    i2s_std_gpio_config_t   gpio_cfg;   /*!< Standard mode GPIO pin configuration */
} i2s_std_config_t;
```

### 4.3 Standard Clock Configuration: `i2s_std_clk_config_t`
Authoritative source: `components/esp_driver_i2s/include/driver/i2s_std.h:254`
```c
typedef struct {
    uint32_t                sample_rate_hz;     /*!< Audio sampling rate (e.g., 16000) */
    i2s_clock_src_t         clk_src;            /*!< Clock source: I2S_CLK_SRC_DEFAULT (PLL_D2) */
#if SOC_I2S_HW_VERSION_2
    uint32_t                ext_clk_freq_hz;    /*!< External MCLK frequency (only on chips with HW v2) */
#endif
    i2s_mclk_multiple_t     mclk_multiple;      /*!< MCLK multiplier: I2S_MCLK_MULTIPLE_256 (256 * fs) */
    uint32_t                bclk_div;           /*!< MCLK to BCLK divider (slave role only; master computes internally) */
} i2s_std_clk_config_t;
```

**Default Macro**: `I2S_STD_CLK_DEFAULT_CONFIG(rate)`
```c
#define I2S_STD_CLK_DEFAULT_CONFIG(rate) { \
    .sample_rate_hz = rate, \
    .clk_src = I2S_CLK_SRC_DEFAULT, \
    .mclk_multiple = I2S_MCLK_MULTIPLE_256, \
    .bclk_div = 8, \
}
```

### 4.4 Standard Slot Configuration: `i2s_std_slot_config_t`
Authoritative source: `components/esp_driver_i2s/include/driver/i2s_std.h:228`
```c
typedef struct {
    i2s_data_bit_width_t    data_bit_width;     /*!< Sample data bit width: I2S_DATA_BIT_WIDTH_24BIT */
    i2s_slot_bit_width_t    slot_bit_width;     /*!< Total slot bit width: I2S_SLOT_BIT_WIDTH_32BIT (MANDATORY) */
    i2s_slot_mode_t         slot_mode;          /*!< Format: I2S_SLOT_MODE_MONO or I2S_SLOT_MODE_STEREO */
    i2s_std_slot_mask_t     slot_mask;          /*!< Active slots: I2S_STD_SLOT_LEFT, I2S_STD_SLOT_RIGHT, I2S_STD_SLOT_BOTH */
    uint32_t                ws_width;           /*!< WS pulse width in BCLK cycles (32 for 64-cycle stereo frame) */
    bool                    ws_pol;             /*!< WS polarity: false = LOW for Left (Philips standard) */
    bool                    bit_shift;          /*!< 1-bit SCK delay after WS edge: true (Philips standard) */
#if SOC_I2S_HW_VERSION_1
    bool                    msb_right;          /*!< Place right channel at MSB in FIFO: false (for >16-bit words) */
#else
    bool                    left_align;         /*!< HW v2 only */
    bool                    big_endian;         /*!< HW v2 only */
    bool                    bit_order_lsb;      /*!< HW v2 only */
#endif
} i2s_std_slot_config_t;
```

**Default Macro**: `I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(bits_per_sample, mono_or_stereo)` (ESP32 variant, line 31):
```c
#define I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(bits_per_sample, mono_or_stereo) { \
    .data_bit_width = bits_per_sample, \
    .slot_bit_width = I2S_SLOT_BIT_WIDTH_AUTO, \
    .slot_mode = mono_or_stereo, \
    .slot_mask = (mono_or_stereo == I2S_SLOT_MODE_MONO) ? \
                I2S_STD_SLOT_LEFT : I2S_STD_SLOT_BOTH, \
    .ws_width = bits_per_sample, \
    .ws_pol = false, \
    .bit_shift = true, \
    .msb_right = (bits_per_sample <= I2S_DATA_BIT_WIDTH_16BIT) ? \
                true : false, \
}
```

### 4.5 Standard GPIO Configuration: `i2s_std_gpio_config_t`
Authoritative source: `components/esp_driver_i2s/include/driver/i2s_std.h:276`
```c
typedef struct {
    gpio_num_t mclk;               /*!< Master clock pin: I2S_GPIO_UNUSED (GPIO_NUM_NC = -1) */
    gpio_num_t bclk;               /*!< Serial bit clock (SCK) pin: e.g. GPIO_NUM_14 */
    gpio_num_t ws;                 /*!< Word select (WS/LRCK) pin: e.g. GPIO_NUM_27 */
    gpio_num_t dout;               /*!< Serial data out: I2S_GPIO_UNUSED (GPIO_NUM_NC = -1) */
    gpio_num_t din;                /*!< Serial data in (SD): e.g. GPIO_NUM_32 */
    struct {
        uint32_t   mclk_inv: 1;    /*!< Invert MCLK (0 = normal) */
        uint32_t   bclk_inv: 1;    /*!< Invert BCLK (0 = normal) */
        uint32_t   ws_inv: 1;      /*!< Invert WS (0 = normal) */
    } invert_flags;
} i2s_std_gpio_config_t;
```

### 4.6 Enum Constants & Value Mapping
Authoritative sources: `components/esp_hal_i2s/include/hal/i2s_types.h` and `driver/i2s_types.h`

| Enum Type | Constant | Numerical Value | Description |
|---|---|---|---|
| Port Identifiers | `I2S_NUM_0` | `0` | Hardware I2S controller 0 |
| Port Identifiers | `I2S_NUM_1` | `1` | Hardware I2S controller 1 |
| Port Identifiers | `I2S_NUM_AUTO` | `-1` | Auto-allocate available controller |
| `i2s_role_t` | `I2S_ROLE_MASTER` | `0` | ESP32 generates BCLK and WS clocks |
| `i2s_role_t` | `I2S_ROLE_SLAVE` | `1` | External device supplies BCLK and WS clocks |
| `i2s_dir_t` | `I2S_DIR_RX` | `BIT(0)` = `1` | Receive channel |
| `i2s_dir_t` | `I2S_DIR_TX` | `BIT(1)` = `2` | Transmit channel |
| `i2s_destination_t` | `I2S_DESTINATION_DMA` | `0` | Route audio to/from memory via DMA |
| `i2s_destination_t` | `I2S_DESTINATION_BT` | `1` | Route audio to Bluetooth peripheral |
| `i2s_slot_mode_t` | `I2S_SLOT_MODE_MONO` | `1` | Single slot active |
| `i2s_slot_mode_t` | `I2S_SLOT_MODE_STEREO` | `2` | Dual slots active (Left & Right) |
| `i2s_std_slot_mask_t` | `I2S_STD_SLOT_LEFT` | `BIT(0)` = `1` | Receive/transmit Left slot only |
| `i2s_std_slot_mask_t` | `I2S_STD_SLOT_RIGHT` | `BIT(1)` = `2` | Receive/transmit Right slot only |
| `i2s_std_slot_mask_t` | `I2S_STD_SLOT_BOTH` | `BIT(0) \| BIT(1)` = `3` | Receive/transmit both slots |
| `i2s_data_bit_width_t` | `I2S_DATA_BIT_WIDTH_24BIT` | `24` | 24 bits of valid sample data |
| `i2s_data_bit_width_t` | `I2S_DATA_BIT_WIDTH_32BIT` | `32` | 32 bits of sample data |
| `i2s_slot_bit_width_t` | `I2S_SLOT_BIT_WIDTH_AUTO` | `0` | Equal to `data_bit_width` |
| `i2s_slot_bit_width_t` | `I2S_SLOT_BIT_WIDTH_32BIT` | `32` | 32 clock cycles per slot |
| `i2s_mclk_multiple_t` | `I2S_MCLK_MULTIPLE_256` | `256` | MCLK = $256 \times f_s$ |
| Pin NC Constant | `I2S_GPIO_UNUSED` | `-1` (`GPIO_NUM_NC`) | Pin not routed to peripheral |

---

## 5. Driver State Machine & Lifecycle Transitions

The driver strictly maintains channel states in `handle->state`:
```
                i2s_new_channel()
[UNREGISTERED] -------------------> [REGISTERED] (State 1)
                                         |
                                         | i2s_channel_init_std_mode()
                                         v
                                      [READY] (State 2)
                                       |   ^
                  i2s_channel_enable() |   | i2s_channel_disable()
                                       v   |
                                     [RUNNING] (State 3)
```

### Transition Invariants:
1. `UNREGISTERED` $\to$ `REGISTERED`:
   - Trigger: `i2s_new_channel(&chan_cfg, NULL, &rx_handle)`
   - Allocates `i2s_channel_obj_t`, `msg_queue` (depth `desc_num - 1`), `binary` semaphore, and `mutex`.
   - Sets state: `handle->state = I2S_CHAN_STATE_REGISTER` (1).
2. `REGISTERED` $\to$ `READY`:
   - Trigger: `i2s_channel_init_std_mode(rx_handle, &std_cfg)`
   - Validates configuration; allocates `mode_info` (`sizeof(i2s_std_config_t)`); allocates DMA descriptors and buffers (`i2s_alloc_dma_desc`); configures GPIO matrix.
   - Sets state: `handle->state = I2S_CHAN_STATE_READY` (2).
3. `READY` $\to$ `RUNNING`:
   - Trigger: `i2s_channel_enable(rx_handle)`
   - Starts BCLK and WS clocks; resets RX message queue; releases binary semaphore.
   - Sets state: `handle->state = I2S_CHAN_STATE_RUNNING` (3).
4. `RUNNING` $\to$ `READY`:
   - Trigger: `i2s_channel_disable(rx_handle)`
   - Sets state: `handle->state = I2S_CHAN_STATE_READY` (2).
   - Halts hardware clock generation and halts DMA transfer.
5. `READY` or `REGISTERED` $\to$ `UNREGISTERED` (Teardown):
   - Trigger: `i2s_del_channel(rx_handle)`
   - Can ONLY be called when `handle->state < I2S_CHAN_STATE_RUNNING`.
   - Frees DMA buffers, DMA descriptors, `mode_info`, FreeRTOS queues, semaphores, and channel object.

---

## 6. Exact Deallocation & Teardown Sequences

### 6.1 Clean Runtime Shutdown (`i2s_mic_deinit`)
When the microphone driver is currently running:
```c
esp_err_t i2s_mic_deinit(void)
{
    if (s_rx_handle == NULL) {
        return ESP_OK; // Idempotent no-op
    }

    // 1. Disable channel (halts DMA and clock generation, transitions RUNNING -> READY)
    esp_err_t ret = i2s_channel_disable(s_rx_handle);
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "Failed to disable I2S channel: %s", esp_err_to_name(ret));
    }

    // 2. Delete channel (frees DMA descriptors, buffers, queues, semaphores)
    ret = i2s_del_channel(s_rx_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to delete I2S channel: %s", esp_err_to_name(ret));
        return ret;
    }

    s_rx_handle = NULL;
    ESP_LOGI(TAG, "I2S microphone driver deinitialized successfully");
    return ESP_OK;
}
```

### 6.2 Partial Initialization Failure Abort Sequence
If an error occurs midway through `i2s_mic_init`:
```c
esp_err_t i2s_mic_init(const i2s_mic_config_t *config)
{
    // ...
    // Step 1: Allocate channel
    ret = i2s_new_channel(&chan_cfg, NULL, &s_rx_handle);
    if (ret != ESP_OK) {
        return ret;
    }

    // Step 2: Initialize STD mode
    ret = i2s_channel_init_std_mode(s_rx_handle, &std_cfg);
    if (ret != ESP_OK) {
        // Channel is in REGISTERED state; calling disable will return ESP_ERR_INVALID_STATE!
        // Call i2s_del_channel directly to clean up allocated control block and OS objects.
        i2s_del_channel(s_rx_handle);
        s_rx_handle = NULL;
        return ret;
    }

    // Step 3: Enable channel
    ret = i2s_channel_enable(s_rx_handle);
    if (ret != ESP_OK) {
        // Channel is in READY state; call i2s_del_channel directly.
        i2s_del_channel(s_rx_handle);
        s_rx_handle = NULL;
        return ret;
    }

    return ESP_OK;
}
```

---

## 7. Memory Management & DMA Sizing Analysis

### 7.1 DMA Sizing Formula on Classic ESP32
From `i2s_common.c:628`:
$$\text{bytes\_per\_sample} = \left\lfloor\frac{\text{data\_bit\_width} + 15}{16}\right\rfloor \times 2$$
For $\text{data\_bit\_width} = 24$:
$$\left\lfloor\frac{24 + 15}{16}\right\rfloor \times 2 = \left\lfloor\frac{39}{16}\right\rfloor \times 2 = 2 \times 2 = 4\text{ bytes per sample}$$
Each sample in DMA memory is stored as a 32-bit word (`int32_t`).

### 7.2 Buffer Sizing & Memory Footprint
$$\text{bytes\_per\_frame} = \text{bytes\_per\_sample} \times \text{active\_slot}$$
- **Mono Mode** ($\text{active\_slot} = 1$):
  $$\text{Descriptor Buffer Size} = 240 \text{ frames} \times 4 = 960\text{ bytes}$$
  $$\text{Total DMA Pool (6 Descriptors)} = 6 \times 960 = 5,760\text{ bytes } (\approx 5.62\text{ KB})$$
- **Stereo Mode** ($\text{active\_slot} = 2$):
  $$\text{Descriptor Buffer Size} = 240 \text{ frames} \times 8 = 1,920\text{ bytes}$$
  $$\text{Total DMA Pool (6 Descriptors)} = 6 \times 1,920 = 11,520\text{ bytes } (\approx 11.25\text{ KB})$$

Both allocations fit easily into the ESP32's internal SRAM without causing heap fragmentation.

### 7.3 `ESP_ERR_NO_MEM` Prevention
`ESP_ERR_NO_MEM` occurs when `heap_caps_calloc(..., I2S_MEM_ALLOC_CAPS)` fails in `i2s_alloc_dma_desc` or `i2s_register_channel`. By maintaining standard descriptor count $N=6$ and frames $F=240$, the peak allocation is only 5.76 KB (mono) or 11.25 KB (stereo), guaranteeing robust initialization.

---

## 8. INMP441 Timing & 24-in-32 Bit Arithmetic Extraction

### 8.1 64-Cycle Frame Requirement & Integer MCLK Divider
- INMP441 specifies:
  $$f_{\text{SCK}} = 64 \times f_s$$
  At $f_s = 16\text{ kHz} \implies f_{\text{SCK}} = 1.024\text{ MHz}$.
  At $f_s = 48\text{ kHz} \implies f_{\text{SCK}} = 3.072\text{ MHz}$.
- With `mclk_multiple = I2S_MCLK_MULTIPLE_256`:
  $$f_{\text{MCLK}} = 256 \times f_s$$
  $$\text{Hardware Divider} = \frac{f_{\text{MCLK}}}{f_{\text{SCK}}} = \frac{256 \times f_s}{64 \times f_s} = \frac{256}{64} = 4$$
- Because $256 \pmod{64} = 0$, the divider is an exact integer. The ESP32 fractional clock divider achieves zero phase jitter ($b/a = 0$).

### 8.2 Proof of Two's Complement Sign Extension
In memory, the 32-bit DMA word contains:
```
Bit 31: Sign bit (S)
Bits [30:8]: Audio data [22:0]
Bits [7:0]: 0x00 (padding)
```
Let `int32_t raw_sample` be the word:
$$\text{sample}_{24} = \text{raw\_sample} \gg 8$$
1. **Positive Sample ($S = 0$)**:
   $0\text{x}7\text{FFFFF00} \gg 8 = 0\text{x}007\text{FFFFF} = +8,388,607$ (Full-scale positive peak).
2. **Zero ($S = 0$)**:
   $0\text{x}00000000 \gg 8 = 0\text{x}00000000 = 0$.
3. **Negative One ($S = 1$)**:
   $0\text{xFFFFFF00} \gg 8 = 0\text{xFFFFFFFF} = -1$.
4. **Negative Peak ($S = 1$)**:
   $0\text{x}80000000 \gg 8 = 0\text{xFF}800000 = -8,388,608$ (Full-scale negative peak).

Because Xtensa LX6 implements arithmetic right shift (`ASR`) on signed types, the sign bit $S$ is replicated across bits `[31:24]`. The dynamic range $[-8388608, +8388607]$ is preserved with zero DC bias.

---

## 9. 3-Microphone Array Mapping & Architectural Alignment

### 9.1 Multi-Channel Slot Allocation (MEMORY_ACOUSTIC_ARRAY.md Section 5)
The ESP32 features two independent I2S hardware peripherals (`I2S_NUM_0` and `I2S_NUM_1`), each offering 2 stereo slots (4 total slots):

| Slot # | Peripheral & Channel | Assigned Sensor | Breakout Pin `L/R` | Target Phase | Status in Phase 1 |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **Slot 1** | **I2S0 Left** | **Microphone 1** ($\mathbf{p}_1$, Top) | Tied to **GND** | **Phase 1** | **Active & Verified** |
| **Slot 2** | **I2S0 Right** | **Microphone 2** ($\mathbf{p}_2$, Bottom-Left) | Tied to **VDD** | Phase 2 | Shared lines on I2S0 |
| **Slot 3** | **I2S1 Left** | **Microphone 3** ($\mathbf{p}_3$, Bottom-Right) | Tied to **GND** | Phase 3 | Clock sync from I2S0 |
| **Slot 4** | **I2S1 Right** | Unused / Discarded | N/A | Phase 3 | Ignored in software |

### 9.2 Hardware Wiring Plan
```
                    ESP32 Development Board
               +-------------------------------+
               | I2S Controller 0 (Master)     |
               |   GPIO 14 (SCK / BCLK) --------+-----> Mic 1 SCK, Mic 2 SCK, Mic 3 SCK
               |   GPIO 27 (WS / LRCK)  --------+-----> Mic 1 WS,  Mic 2 WS,  Mic 3 WS
               |   GPIO 32 (SD / DIN)   <-------+------ Mic 1 SD (L/R=GND), Mic 2 SD (L/R=VDD)
               |                               |
               | I2S Controller 1 (Slave/Sync) |
               |   GPIO 33 (SD / DIN)   <------+------ Mic 3 SD (L/R=GND)
               +-------------------------------+
```

### 9.3 Architectural Continuity
In `i2s_microphone.h`:
```c
typedef struct {
    uint32_t sample_rate;
    int sck_pin;
    int ws_pin;
    int sd_pin;
    int i2s_port; // Explicit port selection (I2S_NUM_0 vs I2S_NUM_1)
} i2s_mic_config_t;
```
By making `i2s_port` a field of `i2s_mic_config_t` and exposing clean `read_raw` and `read_samples` APIs:
- Phase 1 initializes `I2S_NUM_0` with Mic 1.
- Phase 2 simply enables Stereo mode on `I2S_NUM_0` and reads both Left and Right samples.
- Phase 3 initializes a second instance on `I2S_NUM_1` using `SD1` with identical clock routing.
Zero breaking changes are imposed on the codebase across all 3 phases.

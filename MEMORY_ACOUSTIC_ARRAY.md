# Acoustic Source Localization System: Project Memory & Specifications

> **Project Goal**: Estimate **Azimuth** ($0^\circ - 360^\circ$) and **Elevation** ($0^\circ - 90^\circ$) of an acoustic source using **3 INMP441 digital I2S MEMS microphones** in an **equilateral triangular array** ($d = 20\text{ cm}$) driven by a **single ESP32** microcontroller.
> **Current Status (2026-10-15)**: The active firmware uses 48 kHz, three forward 2048-point FFTs, direct cross-spectrum phase, and front-facing horizontal/vertical angles. See README.md for the current algorithm and telemetry. The design notes below are historical and may describe an earlier azimuth/elevation or delay-based approach. Cross-peripheral sample alignment still requires a controlled hardware check.
> **Date Initiated**: October 2026

---

## 1. INMP441 Hardware & Datasheet Analysis

### 1.1 Sensor Summary
The **INMP441** (InvenSense / TDK) is a high-performance, low-power, digital-output omnidirectional MEMS microphone with a bottom port. It integrates a MEMS sensor, signal conditioning, analog-to-digital converter (ADC), decimation and anti-aliasing filter, and an industry-standard 24-bit $I^2S$ interface.

### 1.2 Key Electrical & Acoustic Specifications
| Parameter | Value / Range | Notes |
| :--- | :--- | :--- |
| **Supply Voltage ($V_{DD}$)** | $1.62\text{ V}$ to $3.63\text{ V}$ | Typically powered from ESP32 $3.3\text{ V}$ rail |
| **Current Consumption** | $1.4\text{ mA}$ (active) / $10\,\mu\text{A}$ (standby) | Very low power |
| **Acoustic Directivity** | Omnidirectional | Uniform sensitivity across 3D angles |
| **Sensitivity** | $-26\text{ dBFS} \pm 3\text{ dB}$ | At $1\text{ kHz}, 94\text{ dB SPL}$ |
| **Signal-to-Noise Ratio (SNR)** | $61\text{ dBA}$ | Equivalent input noise $\approx 33\text{ dB SPL}$ |
| **Dynamic Range** | $87\text{ dB}$ | |
| **Acoustic Overload Point (AOP)**| $120\text{ dB SPL}$ | Maximum undistorted acoustic level |
| **Frequency Response** | $60\text{ Hz} - 15\text{ kHz}$ | Covers human voice, acoustic chirps, claps |
| **Output Digital Format** | 24-bit two's complement | Transmitted MSB first in standard $I^2S$ format |
| **Supported Sample Rates ($f_s$)**| $8\text{ kHz}$ to $50\text{ kHz}$ | Typical targets: $16\text{ kHz}, 44.1\text{ kHz}, 48\text{ kHz}$ |
| **Clock Requirements ($f_{\text{SCK}}$)**| $64 \times f_s$ | $1.024\text{ MHz}$ at $16\text{ kHz}$; $3.072\text{ MHz}$ at $48\text{ kHz}$ |

### 1.3 Breakout Pinout & Wiring Connections
The standard 6-pin breakout board exposes:
- **`VDD`**: Power ($3.3\text{ V}$).
- **`GND`**: Power ground.
- **`SD` (Serial Data)**: Tri-state output. Outputs audio data in either the Left or Right slot according to `L/R`. Tri-stated when inactive.
- **`WS` (Word Select / LRCK)**: Frame synchronization clock. LOW = Left channel, HIGH = Right channel.
- **`SCK` (Serial Clock / BCLK)**: Continuous bit clock.
- **`L/R` (Left/Right Channel Select)**:
  - Connect to **`GND`**: Outputs on **Left Channel** ($WS = \text{LOW}$).
  - Connect to **`VDD`**: Outputs on **Right Channel** ($WS = \text{HIGH}$).
  > **Note**: Because `SD` enters high impedance during the non-selected channel slot, two INMP441 microphones can share the exact same `SD`, `WS`, and `SCK` lines by setting one `L/R` to GND and the other `L/R` to VDD.

### 1.4 ESP32 $I^2S$ Frame & Sample Alignment
- The INMP441 adheres to standard Philips $I^2S$ timing: **1 SCK clock cycle delay** between the edge of `WS` and the MSB of the data.
- INMP441 sends 24 bits of valid audio data in a 32-bit slot (total 64 clock cycles per stereo frame).
- When ESP32 reads 32 bits (`int32_t`), the 24 bits occupy the upper bits (bits [31:8]), with the lower 8 bits padded with zeros.
- **Extraction**:
  $$\text{sample}_{24} = \text{raw\_32bit\_sample} \gg 8$$
  Or down-shifted to 16-bit signed audio:
  $$\text{sample}_{16} = \text{raw\_32bit\_sample} \gg 14 \quad (\text{or } \gg 16)$$

---

## 2. Array Physical Geometry & Acoustic Parameters

### 2.1 Environmental Constants
- **Speed of sound in air ($c$)**: $343\text{ m/s}$ (at $20^\circ\text{C}$).
- **Inter-microphone distance ($d$)**: $0.20\text{ m}$ ($20\text{ cm}$).
- **Maximum Time Difference of Arrival ($\tau_{\max}$)**:
  $$\tau_{\max} = \frac{d}{c} = \frac{0.20\text{ m}}{343\text{ m/s}} \approx 5.8309 \times 10^{-4}\text{ s} \approx 583.1\,\mu\text{s}$$
- **Sample period & max sample shift**:
  - At $f_s = 48\text{ kHz}$: $T_s = 20.83\,\mu\text{s} \implies N_{\max} \approx \frac{583.1}{20.83} \approx 28\text{ samples}$.
  - At $f_s = 16\text{ kHz}$: $T_s = 62.5\,\mu\text{s} \implies N_{\max} \approx 9.3\text{ samples}$.

### 2.2 Equilateral Triangle Coordinate System
Let the 3 microphones lie on the horizontal plane $z = 0$, centered at the origin $(0, 0, 0)$:
- Circumradius $R = \frac{d}{\sqrt{3}} = \frac{0.20}{\sqrt{3}} \approx 0.11547\text{ m} = 11.55\text{ cm}$.

```
                 +Y (North, 90°)
                 Mic 3 (0, R)
                         /\
                        /  \
                       /    \
                      /   +  \
                     /  (0,0) \
                    /          \
  Mic 1 (-d/2, -R/2) ----------- Mic 2 (+d/2, -R/2)  --> +X (0°)
```

Microphone Positions:
- **$\mathbf{p}_1$ (Mic 1, Bottom-Left)**: $\left(-\frac{d}{2}, \, -\frac{R}{2}, \, 0\right) = (-0.1000, \, -0.05774, \, 0)$
- **$\mathbf{p}_2$ (Mic 2, Bottom-Right)**: $\left(+\frac{d}{2}, \, -\frac{R}{2}, \, 0\right) = (+0.1000, \, -0.05774, \, 0)$
- **$\mathbf{p}_3$ (Mic 3, Top)**: $(0, \, R, \, 0) = (0, \, 0.11547, \, 0)$

Baseline vectors:
- $\mathbf{b}_{21} = \mathbf{p}_2 - \mathbf{p}_1 = (d, \, 0, \, 0)$ (Purely horizontal along X axis)
- $\mathbf{b}_{31} = \mathbf{p}_3 - \mathbf{p}_1 = \left(+\frac{d}{2}, \, +\frac{\sqrt{3}d}{2}, \, 0\right)$
- $\mathbf{b}_{32} = \mathbf{p}_3 - \mathbf{p}_2 = \left(-\frac{d}{2}, \, +\frac{\sqrt{3}d}{2}, \, 0\right)$

---

## 3. Direction of Arrival (DOA) Mathematical Derivation

### 3.1 Far-Field Plane Wave Model
Let $\mathbf{u}$ be the unit propagation vector pointing towards the sound source:
$$\mathbf{u} = \begin{bmatrix} u_x \\ u_y \\ u_z \end{bmatrix} = \begin{bmatrix} \cos\phi \cos\theta \\ \cos\phi \sin\theta \\ \sin\phi \end{bmatrix}$$
where:
- **$\theta \in [0^\circ, 360^\circ)$**: Azimuth angle (measured counter-clockwise from the $+X$ axis).
- **$\phi \in [0^\circ, 90^\circ]$**: Elevation angle (measured upwards from the array plane $z = 0$).

The arrival time at microphone $i$ is:
$$t_i = t_0 - \frac{\mathbf{p}_i \cdot \mathbf{u}}{c}$$
The Time Difference of Arrival (TDOA) between mic $i$ and mic $j$ is:
$$\Delta t_{ij} = t_j - t_i = -\frac{(\mathbf{p}_j - \mathbf{p}_i) \cdot \mathbf{u}}{c} = -\frac{\mathbf{b}_{ij} \cdot \mathbf{u}}{c}$$

### 3.2 Closed-Form Solution for In-Plane Projections
Evaluating for our equilateral configuration:
1. Horizontal baseline ($M_1 \to M_2$):
   $$\Delta t_{21} = -\frac{d \cdot u_x}{c} \implies u_x = -\frac{c \cdot \Delta t_{21}}{d}$$
2. Symmetric baselines to $M_3$:
   $$\Delta t_{31} = -\frac{d}{2c} u_x - \frac{\sqrt{3}d}{2c} u_y$$
   $$\Delta t_{32} = +\frac{d}{2c} u_x - \frac{\sqrt{3}d}{2c} u_y$$
   Adding both equations:
   $$\Delta t_{31} + \Delta t_{32} = -\frac{\sqrt{3}d}{c} u_y \implies u_y = -\frac{c}{\sqrt{3}d} (\Delta t_{31} + \Delta t_{32})$$

### 3.3 Angle Computation
From $u_x$ and $u_y$:
1. **Azimuth ($\theta$)**:
   $$\theta = \operatorname{atan2}(u_y, u_x) \quad (\text{convert to } [0^\circ, 360^\circ])$$
2. **In-plane magnitude ($r_{xy}$)**:
   $$r_{xy} = \sqrt{u_x^2 + u_y^2} = \cos\phi$$
   *(Constrain $r_{xy} \le 1.0$ to safeguard against acoustic noise)*
3. **Elevation ($\phi$)**:
   $$\phi = \arccos(r_{xy}) = \arcsin\left(\sqrt{\max(0, 1 - r_{xy}^2)}\right)$$
   *(Note: Planar arrays exhibit hemispherical ambiguity between $+z$ and $-z$; we assume source is in upper hemisphere $\phi \ge 0^\circ$)*.

---

## 4. Direct Narrowband FFT Cross-Spectrum Phase-Difference DOA Estimation

*(Source: System Design Document & Sensitivity Analysis by Vladyslav Nepriakhin & Aleksey Kapustjonoks)*

### 4.1 Strict Algorithm Architecture (Zero GCC-PHAT / Zero IFFT)
- **Target Band**: $80 - 200\text{ Hz}$ (fundamental human speech band).
- **Spatial Aliasing Margin**: With $d = 0.20\text{ m}$ and $c = 343\text{ m/s}$, the spatial aliasing cutoff is $f_{\text{wrap}} = \frac{c}{2d} = 857.5\text{ Hz}$. Because $200\text{ Hz} \ll 857.5\text{ Hz}$, maximum physical phase shift across 20 cm is only $41.98^\circ < 180^\circ$. Phase wrapping **never occurs** in the 80–200 Hz band!
- **Strictly Banned**:
  - NO GCC-PHAT magnitude normalization.
  - NO time-domain cross-correlation.
  - NO IFFT.
  - NO search for correlation peaks.

### 4.2 Mathematical Steps
1. **Extract Complex FFT Values**:
   Forward FFT of Hanning-windowed samples yields frequency bins. Find the dominant bin $k_{\text{dom}}$ with maximum spectral energy in the $80 - 200\text{ Hz}$ band ($f = k_{\text{dom}} \frac{f_s}{N}$):
   $$X_i(f) \quad \text{and} \quad X_j(f)$$
2. **Calculate Phase Difference**:
   Multiply complex value $X_j(f)$ by complex conjugate $X_i^*(f)$ and extract argument:
   $$\phi_{ji} = \arg\left(X_j(f) X_i^*(f)\right) = \operatorname{atan2}\left(\operatorname{Im}(X_j X_i^*), \operatorname{Re}(X_j X_i^*)\right)$$
3. **Convert Phase to Fractional Time Delay ($\Delta t$)**:
   $$\Delta t_{ji} = -\frac{\phi_{ji}}{2\pi f}$$
4. **Direct Direction Unit Vector ($\hat{\mathbf{u}}$) for Equilateral Triangle**:
   With $M_1 = (-d/2, -\frac{\sqrt{3}d}{6}, 0)$, $M_2 = (d/2, -\frac{\sqrt{3}d}{6}, 0)$, $M_3 = (0, \frac{\sqrt{3}d}{3}, 0)$:
   $$u_x = \frac{c (2\phi_{21} + \phi_{31} - \phi_{32})}{6 \pi f d}$$
   $$u_y = \frac{c (\phi_{31} + \phi_{32})}{2 \sqrt{3} \pi f d}$$
   $$u_z = \sqrt{\max\left(0, 1 - u_x^2 - u_y^2\right)}$$
5. **Output Angles**:
   $$\text{Azimuth} = \operatorname{atan2}(u_y, u_x) \times \frac{180}{\pi}\pmod{360^\circ}, \quad \text{Elevation} = \operatorname{atan2}(u_z, \sqrt{u_x^2+u_y^2}) \times \frac{180}{\pi}$$
   Stereo Pair (1D): $\theta = \arcsin\left(\operatorname{clamp}\left(\frac{c \cdot \phi_{21}}{2\pi f d}, -1.0, 1.0\right)\right) \times \frac{180}{\pi}$

---

## 5. ESP32 Multi-Channel Hardware Architecture

### 5.1 ESP32 $I^2S$ Hardware Resources & 4-Slot Buffer Structure
The classic ESP32 has **two hardware $I^2S$ controllers**: `I2S_NUM_0` and `I2S_NUM_1`.
Each controller natively samples stereo slots (Left and Right). Operating both controllers yields **4 channel slots / buffers**:
1. `I2S0_L` (I2S0 Left)
2. `I2S0_R` (I2S0 Right)
3. `I2S1_L` (I2S1 Left)
4. `I2S1_R` (I2S1 Right - unused / discarded)

### 5.2 3-Microphone Mapping (Left - Right - Left)
Because the INMP441 microphones are **omnidirectional**, spatial directionality depends solely on the physical coordinates in the array, making channel assignment straightforward:
- **Microphone 1 ($\mathbf{p}_1$, Bottom-Left)**: Mapped to **`I2S0_L`**
  - Breakout pin `L/R` $\to$ `GND`
  - Connected to `I2S_NUM_0` (`SD0`, `SCK0`, `WS0`)
- **Microphone 2 ($\mathbf{p}_2$, Bottom-Right)**: Mapped to **`I2S0_R`**
  - Breakout pin `L/R` $\to$ `VDD`
  - Shares `I2S_NUM_0` lines (`SD0`, `SCK0`, `WS0`) with Mic 1
- **Microphone 3 ($\mathbf{p}_3$, Top)**: Mapped to **`I2S1_L`**
  - Breakout pin `L/R` $\to$ `GND`
  - Connected to `I2S_NUM_1` data line (`SD1`), synchronized to master `SCK0` and `WS0`
- **Slot 4 (`I2S1_R`)**: Ignored/discarded in software DMA extraction.

### 5.3 Buffer Extraction Pipeline
When the DMA buffers fill:
- I2S0 DMA buffer provides interleaved stereo: $[L_0, R_0, L_1, R_1, \dots] \implies \text{Mic 1} = L, \text{Mic 2} = R$.
- I2S1 DMA buffer provides stereo: $[L_0, R_0, L_1, R_1, \dots] \implies \text{Mic 3} = L$ (discard $R$).
- The DSP pipeline extracts the 3 synchronized audio streams: $\text{Mic}_1[n], \text{Mic}_2[n], \text{Mic}_3[n]$ into contiguous float buffers for FFT processing.

---

## 6. Implementation Phases & Roadmap

- [x] **Phase 1: Single Microphone Capture & Real-Time Plotting** *(Historical implementation; current firmware uses stereo mode)*
  - Modern ESP-IDF v6.1.0 driver (`driver/i2s_std.h`) implemented in `i2s_microphone.c` / `i2s_microphone.h`.
  - Pin assignments: `SCK = GPIO 14`, `WS = GPIO 27`, `SD = GPIO 32`, `L/R = GND` (Left channel).
  - 24-bit dynamic range decoded via arithmetic shift (`raw >> 8`) generating native Xtensa `srai` instructions.
  - Dual-core FreeRTOS pipeline: I2S DMA on Core 1 (Prio 10), telemetry queue & UART on Core 0 (Prio 2).
  - Serial Plotter telemetry formatted at 115200 baud (`sample:VAL,rms:VAL,peak:VAL`).
  - Python visualizer tool created in `tools/audio_plotter.py` (CLI ANSI meter, Matplotlib GUI, WAV export).
  - The Phase 1 Python tests exercise reference models and mock streams; they do not verify live ESP32 microphone capture.
- [x] **Phase 2: Stereo Dual-Microphone Capture & 1D Angle Estimation (I2S0)** *(Historical algorithm; current firmware plots the two signals)*
  - Connect Mic 1 (`L/R = GND`) and Mic 2 (`L/R = 3V3`) to shared `I2S0` bus (`SD=GPIO 32`, `WS=GPIO 27`, `SCK=GPIO 14`).
  - Configured `I2S_SLOT_MODE_STEREO` / `I2S_STD_SLOT_BOTH` to capture interleaved stereo samples.
  - Implemented Cooley-Tukey Radix-2 Real-to-Complex FFT ($N=512$, $f_s=16\text{ kHz}$) with Hanning windowing in `src/fft_tdoa.c`.
  - Compute the phase of $S_{12}[k] = X_1^*[k] \cdot X_2[k]$ at the strongest 80–200 Hz bin. GCC-PHAT, IFFT, and time-domain peak search are not used.
  - Calculate fractional TDOA directly from phase and estimate the one-dimensional angle:
    $$\Delta t = -\frac{\arg(S_{12})}{2\pi f}, \qquad \theta = \arcsin\left(\operatorname{clamp}\left(-\frac{c\Delta t}{d}, -1, 1\right)\right).$$
  - The current `app_main` bypasses the angle solver and sends two synchronized, 16-sample averaged microphone traces to Teleplot as `>mic1:VAL` and `>mic2:VAL` at 460800 baud.
- [x] **Phase 3: 3-Microphone Capture (I2S0 + I2S1), firmware implementation**
  - Add Mic 3 (`L/R = GND`) on `I2S1_L` (`SD1`) with synchronized clocks (`SCK0`, `WS0`).
  - Demux 4 buffer slots (`I2S0_L`, `I2S0_R`, `I2S1_L`, `I2S1_R` discarded) into 3 synchronized audio streams.
- [x] **Phase 4: Multi-Channel FFT & Phase Pipeline, firmware implementation**
  - Compute cross-spectra: $S_{12}(f)$, $S_{13}(f)$, $S_{23}(f)$.
  - Extract $\Delta t_{12}, \Delta t_{13}, \Delta t_{23}$ from cross-spectrum phase at a shared dominant frequency.
- [x] **Phase 5: Geometric TDOA Solver $\to$ Azimuth & Elevation Output, firmware implementation**
  - Solve for in-plane vector $(u_x, u_y)$ and compute $\theta$ (azimuth) and $\phi$ (elevation).
  - Output real-time polar coordinates over Serial / Web UI radar.

Physical validation remains open: a build and DMA block counters are not proof that I2S0 and I2S1 DMA frame zero refer to the same WS edge. The dashboard marks a calibrated phase solution but cannot certify sample-index synchronization; verify with an electrical stimulus or a controlled repeatable acoustic fixture before precision measurements.


# Three-microphone direct FFT-phase DOA

The ESP32 captures three INMP441 channels through I2S DMA at **48,000 samples/s**. It estimates a front-hemisphere direction from the phase of one dominant FFT bin between 80 and 200 Hz. The angle visualizer has separate raw and calibrated views.

## Wiring and geometry

Supply each microphone from ESP32 **3V3** and common **GND**. Connect all SCK pins to **GPIO14** and all WS pins to **GPIO27**.

| Microphone | Array position | L/R | SD | Receiver |
| --- | --- | --- | --- | --- |
| mic1 | bottom left | GND | GPIO32 | I2S0 left |
| mic2 | bottom right | 3V3 | GPIO32 | I2S0 right |
| mic3 | top | GND | GPIO33 | I2S1 left |

Mic3 uses its own SD wire. The microphone ports should form a **20 cm equilateral triangle** in the XY plane: mic1 at `(-d/2,-√3d/6)`, mic2 at `(d/2,-√3d/6)`, mic3 at `(0,√3d/3)`. The positive Z axis is the front normal to that plane.

## Algorithm

For each synchronized 2,048-sample frame, the firmware subtracts each channel mean, applies a Hann window, and computes three forward FFTs. It selects the **single** bin with greatest combined three-channel power among bins whose frequencies are between 80 and 200 Hz. The spacing is **23.4375 Hz**, so the eligible bin centers are 93.75, 117.1875, 140.625, 164.0625, and 187.5 Hz. All channels use the same selected bin.

At that bin it extracts complex `X1`, `X2`, and `X3` and computes three cross-spectrum phases in radians:

```text
φ21 = atan2(Im(X2 conj(X1)), Re(X2 conj(X1)))
φ31 = atan2(Im(X3 conj(X1)), Re(X3 conj(X1)))
φ32 = atan2(Im(X3 conj(X2)), Re(X3 conj(X2)))
```

With `d=0.20 m`, `c=343.0 m/s`, and selected bin frequency `f`, the least-squares solution for the array's three baselines is:

```text
B = d [[1,0], [1/2,√3/2], [-1/2,√3/2]]
B⁺ = (1/d) [[2/3,1/3,-1/3], [0,1/√3,1/√3]]
u_xy = (c/(2πf)) B⁺ [φ21,φ31,φ32]ᵀ

ux = (c/(2πfd)) (2φ21 + φ31 − φ32)/3
uy = (c/(2πfd)) (φ31 + φ32)/√3
```

**There is no extra π in the inner denominators.** The formulas with `/(3π)` and `/(π√3)` would shrink the projected direction by π. The reported `r` is the unconstrained magnitude `√(ux²+uy²)`. For angles, if `r>1`, XY is scaled to the unit circle; then `uz=√max(0,1−ux²−uy²)`. Conventional spherical outputs are `azimuth=atan2(uy,ux)·180/π` normalized to `[0°,360°)`, and `elevation=atan2(uz,√(ux²+uy²))·180/π`. At the vertical axis, elevation is 90° and azimuth is undefined.

This planar array has identical phase predictions for `+uz` and `−uz`; the positive-Z solution is an assumption. These formulas also assume no phase wrapping for the source geometry and band. At 200 Hz and 20 cm, the largest baseline phase is under π in air at 343 m/s.

## Build and visualizer

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -e esp32dev
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run -e esp32dev -t upload
.\.venv\Scripts\python.exe tools\angle_visualizer.py --port COM7 --baud 460800
```

Close Teleplot or any serial monitor before opening the dashboard on COM7 (use the current port if it changes). To preview without hardware, run `.\.venv\Scripts\python.exe tools\angle_visualizer.py --demo`. Teleplot can plot `mic1`, `mic2`, `mic3` at 500 averaged points/s. The dashboard shows the mic1–mic2–mic3 triangle on the XY azimuth compass, azimuth and elevation values, three pair phases, microphone traces, and both DMA counters.

The **UNCALIBRATED** button shows a provisional raw phase estimate when a stable band signal and plausible projection are present. The **CALIBRATED** button uses stored phase offsets for the current FFT bin and stricter firmware validity checks. The buttons only change the view. To gather a per-bin reference, co-locate the three microphone openings, point them the same way, play a stable exact-bin tone such as 187.5 Hz, then press **CAL**. The firmware stores 20 stable windows in RAM. Restore the triangle without resetting the ESP32. **CLEAR** erases the offsets; **START** restarts warmup. A clap may trigger activity but usually does not sustain one coherent bin long enough to give a trustworthy direction.

I2S0 and I2S1 share BCLK/WS but have independent DMA receivers. The firmware detects DMA overflows and restarts both receivers if alignment is lost. DMA continuity and phase consistency do **not** prove absolute sample-index alignment between the peripherals. Precision use requires a controlled, repeated synchronization check after startup and restarts; room sound alone cannot establish it.

The active DOA path uses only forward FFTs and complex phase. Historical two-microphone analysis scripts in `tools/` are not used by the firmware or dashboard.

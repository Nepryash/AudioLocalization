#!/usr/bin/env python3
"""
SensorTechINMP441 - Audio Telemetry Plotter & Verification Tool
Real-time serial telemetry viewer for the earlier single-mic and stereo
angle-estimation firmware. The current firmware sends mic1/mic2 to Teleplot.

Supports:
- Live UART capture with automatic port selection when one port is present
- Synthetic mock generator (--mock) simulating speech, ambient noise, and claps
- Text-based ANSI terminal VU-meter (--cli) for headless/terminal environments
- Interactive Matplotlib GUI mode (with automatic graceful fallback to CLI)
- WAV audio export (--save-wav)
- Fixed duration capture (--duration SEC)
"""

import sys
import os
import time
import math
import random
import re
import argparse
import wave
import struct
from typing import Optional, Tuple, List

# Optional dependencies with graceful fallback
try:
    import serial
except ImportError:
    serial = None

try:
    import matplotlib
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    HAS_MATPLOTLIB = True
except (ImportError, Exception):
    HAS_MATPLOTLIB = False

# Authoritative Constants
DEFAULT_PORT = None
DEFAULT_BAUD = 460800
SAMPLE_RATE = 16000
DECIMATION_FACTOR = 16  # Telemetry stream decimation (16 yields 1000 paired points/sec)
LEGACY_DECIMATION_FACTOR = 128
TELEMETRY_STREAM_HZ = 1000.0  # 16000 / 16
AUDIO_DSP_FULL_SCALE = 8388607  # 2^23 - 1
AUDIO_DSP_MIN_SCALE = -8388608  # -2^23

# Regex for parsing telemetry lines
_TELEMETRY_REGEX = re.compile(r"^sample:([+-]?\d+),rms:(\d+)(?:,peak:(\d+))?\r?\n?$")
_TELEPLOT_VAR_REGEX = re.compile(r"^>([a-zA-Z0-9_]+):([+-]?\d+)\r?\n?$")

_current_teleplot_state = {"sample": 0, "rms": 0, "peak": 0}


class StereoTelemetryParser:
    """Collects paired (mic1, mic2) samples from Teleplot (>mic1:VAL, >mic2:VAL) or CSV lines."""

    def __init__(self):
        self.mic1: Optional[int] = None
        self.mic2: Optional[int] = None

    def feed(self, line: str) -> Optional[Tuple[int, int]]:
        line = line.strip()
        if not line:
            return None

        # Format A: Teleplot style >mic1:VAL or >mic2:VAL
        if line.startswith(">mic1:") or line.startswith(">m1:"):
            try:
                self.mic1 = int(line.split(":", 1)[1])
            except ValueError:
                return None
            if self.mic2 is not None:
                pair = (self.mic1, self.mic2)
                self.mic1 = None
                self.mic2 = None
                return pair
            return None

        if line.startswith(">mic2:") or line.startswith(">m2:"):
            try:
                self.mic2 = int(line.split(":", 1)[1])
            except ValueError:
                return None
            if self.mic1 is not None:
                pair = (self.mic1, self.mic2)
                self.mic1 = None
                self.mic2 = None
                return pair
            return None

        # Format B: CSV style mic1:VAL,mic2:VAL or >mic1:VAL,>mic2:VAL
        if "mic1:" in line and "mic2:" in line:
            clean = line.replace(">", "")
            parts = clean.split(",")
            d = {}
            for p in parts:
                k, sep, v = p.partition(":")
                if sep:
                    try:
                        d[k.strip()] = int(v.strip())
                    except ValueError:
                        pass
            if "mic1" in d and "mic2" in d:
                return (d["mic1"], d["mic2"])

        return None


def compute_stereo_delay_and_coherence(
    sig1: List[int],
    sig2: List[int],
    max_lag: int = 15,
    sample_rate_hz: float = 1000.0
) -> Tuple[float, float]:
    """
    Computes inter-channel fractional delay (in microseconds) and cross-correlation coherence
    between sig1 (Mic 1) and sig2 (Mic 2) over the recent window.
    Returns (delay_us, coherence).
    """
    n = min(len(sig1), len(sig2))
    if n < 8:
        return 0.0, 1.0

    x = [float(v) for v in sig1[-n:]]
    y = [float(v) for v in sig2[-n:]]

    mean_x = sum(x) / n
    mean_y = sum(y) / n
    x_zero = [v - mean_x for v in x]
    y_zero = [v - mean_y for v in y]

    var_x = sum(v * v for v in x_zero)
    var_y = sum(v * v for v in y_zero)

    if var_x < 1e-4 or var_y < 1e-4:
        return 0.0, 0.0

    norm = math.sqrt(var_x * var_y)

    best_lag = 0
    max_corr = -1.0
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            c = sum(x_zero[-lag + i] * y_zero[i] for i in range(n + lag))
        else:
            c = sum(x_zero[i] * y_zero[i + lag] for i in range(n - lag))
        c_norm = c / norm
        if c_norm > max_corr:
            max_corr = c_norm
            best_lag = lag

    delay_us = best_lag * (1000000.0 / sample_rate_hz)
    coherence = max(0.0, min(1.0, max_corr))
    return delay_us, coherence


class AngleTelemetryParser:
    """Collect one complete stereo DOA packet from CSV or Teleplot lines."""

    REQUIRED = {"angle", "rms1", "rms2", "conf", "active"}

    def __init__(self):
        self.fields = {}

    def feed(self, line: str):
        line = line.strip()
        if not line or ("angle:" not in line and not line.startswith(">")):
            return None

        if line.startswith(">"):
            parts = [line[1:]]
            if line.startswith(">dt_us:"):
                self.fields = {}
        else:
            parts = line.split(",")
            self.fields = {}

        for part in parts:
            key, sep, value = part.partition(":")
            if not sep:
                continue
            if key not in {"dt_us", "dt_smp", "f_dom", "phi", "angle", "rms1", "rms2", "conf", "active"}:
                continue
            try:
                parsed_value = float(value)
                if not math.isfinite(parsed_value):
                    raise ValueError("non-finite telemetry value")
                self.fields[key] = parsed_value
            except ValueError:
                self.fields = {}
                return None

        if self.REQUIRED.issubset(self.fields) and (not line.startswith(">") or line.startswith(">active:")):
            packet = dict(self.fields)
            self.fields = {}
            return packet
        return None


def render_angle_status(packet: dict, rate_hz: float) -> str:
    return (
        f"ANGLE: {packet['angle']:>6.1f} deg | DELAY: {packet.get('dt_us', 0.0):>7.1f} us | "
        f"RMS L/R: {int(packet['rms1']):>7}/{int(packet['rms2']):<7} | "
        f"CONF: {packet['conf']:.2f} | ACTIVE: {int(packet['active'])} | RATE: {rate_hz:>5.1f} Hz"
    )


def resolve_port(requested_port):
    if requested_port:
        return requested_port
    if serial is None:
        raise RuntimeError("pyserial is not installed. Install it with 'python -m pip install pyserial'.")
    from serial.tools import list_ports
    ports = [port.device for port in list_ports.comports()]
    if len(ports) == 1:
        return ports[0]
    if not ports:
        raise RuntimeError("No serial ports found. Connect the ESP32 and check its USB driver.")
    raise RuntimeError(f"Multiple serial ports found ({', '.join(ports)}). Select one with --port.")


def parse_telemetry_line(line: str) -> Optional[Tuple[int, int, int]]:
    """
    Parses a serial telemetry line formatted as:
    - CSV: sample:VAL,rms:VAL (or sample:VAL,rms:VAL,peak:VAL)
    - Teleplot: >sample:VAL, >rms:VAL, >peak:VAL

    Returns (sample, rms, peak) or None if the line is not a valid telemetry packet.
    """
    line_clean = line.strip()

    # 1. Check CSV format
    match = _TELEMETRY_REGEX.match(line_clean)
    if match:
        try:
            sample = int(match.group(1))
            rms = int(match.group(2))
            if match.group(3) is not None:
                peak = int(match.group(3))
            else:
                peak = max(abs(sample), rms)
            return sample, rms, peak
        except ValueError:
            return None

    # 2. Check Teleplot format (>var:val)
    match_tp = _TELEPLOT_VAR_REGEX.match(line_clean)
    if match_tp:
        try:
            var_name = match_tp.group(1)
            val = int(match_tp.group(2))
            _current_teleplot_state[var_name] = val
            if var_name == "peak":
                return (
                    _current_teleplot_state.get("sample", 0),
                    _current_teleplot_state.get("rms", 0),
                    _current_teleplot_state.get("peak", 0),
                )
        except ValueError:
            return None

    return None


def linear_to_dbfs(val: float, full_scale: float = float(AUDIO_DSP_FULL_SCALE)) -> float:
    """Converts a linear amplitude/RMS value to dBFS (relative to 24-bit full scale)."""
    if val <= 0.0:
        return -96.0
    val_clamped = min(val, full_scale)
    return 20.0 * math.log10(val_clamped / full_scale)


def render_ansi_meter(
    rms: int,
    peak: int,
    sample: int,
    rate_hz: float,
    width: int = 35,
    use_color: bool = True
) -> str:
    """
    Renders a single-line ANSI VU-meter and telemetry metrics string.
    """
    rms_db = linear_to_dbfs(float(rms))
    peak_db = linear_to_dbfs(float(peak))

    # Calculate bar fill fraction based on 24-bit range
    frac = max(0.0, min(1.0, float(rms) / float(AUDIO_DSP_FULL_SCALE)))
    filled = int(round(frac * width))
    empty = width - filled

    if use_color:
        # Determine bar color based on level
        if rms_db > -3.0:
            bar_color = "\033[91m"  # Red (Clipping warning)
        elif rms_db > -12.0:
            bar_color = "\033[93m"  # Yellow (High level)
        elif rms_db > -40.0:
            bar_color = "\033[92m"  # Green (Good signal)
        else:
            bar_color = "\033[90m"  # Gray / Low level
        reset = "\033[0m"
        bold = "\033[1m"
    else:
        bar_color = ""
        reset = ""
        bold = ""

    bar = f"{bar_color}{'#' * filled}{'.' * empty}{reset}"
    return (
        f"[{bar}] {bold}RMS:{reset} {rms:>7} ({rms_db:>6.1f} dBFS) | "
        f"{bold}PEAK:{reset} {peak:>7} ({peak_db:>6.1f} dBFS) | "
        f"{bold}SMP:{reset} {sample:>8} | "
        f"{bold}RATE:{reset} {rate_hz:>5.1f} Hz"
    )


def render_dual_ansi_meter(
    m1: int,
    m2: int,
    rms1: int,
    rms2: int,
    delay_us: float,
    coherence: float,
    rate_hz: float,
    width: int = 15,
    use_color: bool = True
) -> str:
    """Renders side-by-side ANSI level meters for Mic 1 and Mic 2 with inter-channel delay and sync coherence."""
    rms1_db = linear_to_dbfs(float(rms1))
    rms2_db = linear_to_dbfs(float(rms2))

    def make_bar(rms_db: float, rms_val: int) -> str:
        frac = max(0.0, min(1.0, float(rms_val) / float(AUDIO_DSP_FULL_SCALE)))
        filled = int(round(frac * width))
        empty = width - filled
        if use_color:
            if rms_db > -3.0:
                color = "\033[91m"
            elif rms_db > -12.0:
                color = "\033[93m"
            elif rms_db > -40.0:
                color = "\033[92m"
            else:
                color = "\033[90m"
            reset = "\033[0m"
        else:
            color = ""
            reset = ""
        return f"{color}{'#' * filled}{'.' * empty}{reset}"

    bar1 = make_bar(rms1_db, rms1)
    bar2 = make_bar(rms2_db, rms2)

    bold = "\033[1m" if use_color else ""
    reset = "\033[0m" if use_color else ""
    sync_col = "\033[92m" if coherence > 0.7 else "\033[93m" if coherence > 0.4 else "\033[90m"
    if not use_color:
        sync_col = ""

    return (
        f"{bold}MIC1:{reset} [{bar1}] {rms1_db:>5.1f} dBFS | "
        f"{bold}MIC2:{reset} [{bar2}] {rms2_db:>5.1f} dBFS | "
        f"{bold}DELAY:{reset} {delay_us:>+6.1f} us | "
        f"{bold}SYNC:{reset} {sync_col}{coherence:>4.2f}{reset} | "
        f"{rate_hz:>5.1f} Hz"
    )


def export_wav(filepath: str, samples_24: List[int], sample_rate: int = 16000, repeat_decimation: bool = True):
    """
    Exports a sequence of 24-bit samples to a 16-bit mono PCM RIFF WAV file.
    If repeat_decimation is True, repeats each decimated sample by LEGACY_DECIMATION_FACTOR (128)
    so the WAV playback duration matches real elapsed recording time.
    """
    dir_name = os.path.dirname(filepath)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    if repeat_decimation:
        # Reconstruct 16 kHz stream from decimated 125 Hz stream via zero-order hold
        expanded_samples = []
        for s in samples_24:
            expanded_samples.extend([s] * LEGACY_DECIMATION_FACTOR)
    else:
        expanded_samples = samples_24

    # Convert 24-bit [-8388608, 8388607] to 16-bit [-32768, 32767]
    pcm16 = []
    for s in expanded_samples:
        s16 = s >> 8
        s16 = max(-32768, min(32767, s16))
        pcm16.append(s16)

    raw_bytes = struct.pack(f"<{len(pcm16)}h", *pcm16)

    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit (2 bytes)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_bytes)


def export_stereo_wav(
    filepath: str,
    samples_m1: List[int],
    samples_m2: List[int],
    sample_rate: int = 16000,
    repeat_factor: int = 16
):
    """
    Exports synchronized dual-channel samples to a 16-bit 2-channel stereo PCM RIFF WAV file.
    Left channel = Mic 1, Right channel = Mic 2.
    """
    dir_name = os.path.dirname(filepath)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    n = min(len(samples_m1), len(samples_m2))
    s1 = samples_m1[:n]
    s2 = samples_m2[:n]

    pcm_interleaved = []
    for l, r in zip(s1, s2):
        l16 = max(-32768, min(32767, l >> 8))
        r16 = max(-32768, min(32767, r >> 8))
        for _ in range(repeat_factor):
            pcm_interleaved.append(l16)
            pcm_interleaved.append(r16)

    raw_bytes = struct.pack(f"<{len(pcm_interleaved)}h", *pcm_interleaved)

    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(2)  # Stereo: Left = Mic 1, Right = Mic 2
        wf.setsampwidth(2)  # 16-bit (2 bytes per channel)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_bytes)


class SyntheticTelemetryGenerator:
    """
    Generates realistic synthetic acoustic telemetry stream (both stereo 1000 Hz and legacy 125 Hz)
    mimicking ambient noise, human speech, and periodic loud acoustic claps with tight inter-channel sync.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, window_size: int = LEGACY_DECIMATION_FACTOR):
        self.sample_rate = sample_rate
        self.window_size = window_size
        self.dt = window_size / sample_rate
        self.stereo_dt = DECIMATION_FACTOR / sample_rate  # 1.0 ms for decimation=16 (1000 Hz)
        self.t = 0.0
        self.frame_idx = 0

    def generate_packet(self) -> Tuple[str, int, int, int]:
        """Synthesizes a legacy single-mic window."""
        self.frame_idx += 1
        t_start = self.t
        self.t += self.dt

        # Periodic clap every 2.0 seconds
        is_clap = (self.frame_idx % 250) in (20, 21, 22)
        speech_env = max(0.0, math.sin(2.0 * math.pi * 2.5 * t_start))
        voice_amp = 350000.0 * speech_env

        samples = []
        for i in range(self.window_size):
            t_s = t_start + (i / self.sample_rate)
            carrier = 0.8 * math.sin(2.0 * math.pi * 440.0 * t_s) + 0.2 * math.sin(2.0 * math.pi * 880.0 * t_s)
            val = voice_amp * carrier + random.gauss(0.0, 1500.0)
            if is_clap:
                val += random.choice([-1, 1]) * random.uniform(3000000.0, 6000000.0)
            val_int = int(max(float(AUDIO_DSP_MIN_SCALE), min(float(AUDIO_DSP_FULL_SCALE), val)))
            samples.append(val_int)

        decimated_sample = samples[0]
        sum_sq = sum(s * s for s in samples)
        rms = min(int(math.sqrt(sum_sq / self.window_size)), int(AUDIO_DSP_FULL_SCALE))
        peak = min(max(abs(s) for s in samples), int(AUDIO_DSP_FULL_SCALE))
        line = f"sample:{decimated_sample},rms:{rms}\r\n"
        return line, decimated_sample, rms, peak

    def generate_stereo_pair(self) -> Tuple[str, int, int, int, int]:
        """
        Synthesizes a synchronized stereo sample pair.
        Returns: (line, mic1, mic2, rms1, rms2)
        """
        self.frame_idx += 1
        t_start = self.t
        self.t += self.stereo_dt

        is_clap = (self.frame_idx % 1500) in (30, 31, 32, 33, 34)
        speech_env = max(0.0, math.sin(2.0 * math.pi * 2.0 * t_start))
        voice_amp = 400000.0 * speech_env

        carrier = 0.85 * math.sin(2.0 * math.pi * 440.0 * t_start) + 0.15 * math.sin(2.0 * math.pi * 880.0 * t_start)
        base = voice_amp * carrier

        if is_clap:
            base += random.choice([-1, 1]) * random.uniform(3500000.0, 6500000.0)

        # Microphones are tightly synchronized with small sensor noise
        n1 = random.gauss(0.0, 1200.0)
        n2 = random.gauss(0.0, 1200.0)

        val1 = base + n1
        val2 = base * 0.99 + n2

        m1 = int(max(float(AUDIO_DSP_MIN_SCALE), min(float(AUDIO_DSP_FULL_SCALE), val1)))
        m2 = int(max(float(AUDIO_DSP_MIN_SCALE), min(float(AUDIO_DSP_FULL_SCALE), val2)))

        rms1 = min(abs(m1), int(AUDIO_DSP_FULL_SCALE))
        rms2 = min(abs(m2), int(AUDIO_DSP_FULL_SCALE))

        line = f">mic1:{m1}\n>mic2:{m2}\n"
        return line, m1, m2, rms1, rms2


def run_cli_mode(args):
    """Executes the visualizer in ANSI terminal / VU-meter mode."""
    if not args.mock:
        try:
            args.port = resolve_port(args.port)
        except RuntimeError as ex:
            print(f"[ERROR] {ex}")
            return
    print("=" * 78)
    print("      SensorTechINMP441 - Real-Time Audio Telemetry Visualizer (CLI)")
    if args.mock:
        print("      Mode: SYNTHETIC MOCK (125 Hz simulated acoustic stream)")
    else:
        print(f"      Mode: LIVE UART ({args.port} @ {args.baud} baud)")
    if args.duration:
        print(f"      Duration: {args.duration:.1f} seconds")
    if args.save_wav:
        print(f"      Recording to WAV: {args.save_wav}")
    print("=" * 78)

    # Initialize data source
    ser = None
    mock_gen = None

    if args.mock:
        mock_gen = SyntheticTelemetryGenerator()
    else:
        if serial is None:
            print("[ERROR] pyserial is not installed. Install via 'pip install pyserial' or use --mock.")
            sys.exit(1)
        try:
            ser = serial.Serial(port=args.port, baudrate=args.baud, timeout=1.0)
            print(f"[INFO] Connected to {args.port} at {args.baud} baud.")
        except serial.SerialException as ex:
            print(f"[ERROR] Failed to open {args.port}: {ex}")
            print("        Tip: Verify connection or test using synthetic stream with --mock")
            sys.exit(1)

    start_time = time.time()
    last_ui_update = start_time
    packet_count = 0
    recent_timestamps = []
    recorded_samples = []
    recorded_m1 = []
    recorded_m2 = []
    angle_parser = AngleTelemetryParser()
    stereo_parser = StereoTelemetryParser()
    angle_count = 0
    stereo_count = 0

    rate_hz = 0.0
    last_sample = 0
    last_rms = 0
    last_peak = 0
    max_peak_observed = 0
    max_rms_observed = 0

    m1_window = []
    m2_window = []
    last_m1 = 0
    last_m2 = 0
    last_rms1 = 0
    last_rms2 = 0
    last_delay_us = 0.0
    last_coh = 1.0
    max_m1_observed = 0
    max_m2_observed = 0

    try:
        while True:
            now = time.time()
            elapsed = now - start_time

            if args.duration and elapsed >= args.duration:
                break

            # Acquire next line
            if mock_gen:
                time.sleep(0.001)  # ~1000 Hz pacing
                line, m1, m2, r1, r2 = mock_gen.generate_stereo_pair()
                stereo_packet = (m1, m2)
                angle_packet = None
                parsed = None
            else:
                raw_bytes = ser.readline()
                if not raw_bytes:
                    continue
                line = raw_bytes.decode("utf-8", errors="ignore")
                stereo_packet = stereo_parser.feed(line)
                if stereo_packet is None:
                    angle_packet = angle_parser.feed(line)
                    parsed = parse_telemetry_line(line) if angle_packet is None else None
                else:
                    angle_packet = None
                    parsed = None

            if not stereo_packet and not angle_packet and not parsed:
                # Ignore non-telemetry logs (e.g. ESP-IDF boot banners)
                continue

            if stereo_packet is not None:
                stereo_count += 1
                m1, m2 = stereo_packet
                last_m1, last_m2 = m1, m2
                max_m1_observed = max(max_m1_observed, abs(m1))
                max_m2_observed = max(max_m2_observed, abs(m2))
                m1_window.append(m1)
                m2_window.append(m2)
                if len(m1_window) > 64:
                    m1_window.pop(0)
                    m2_window.pop(0)
                last_delay_us, last_coh = compute_stereo_delay_and_coherence(
                    m1_window, m2_window, max_lag=15, sample_rate_hz=rate_hz if rate_hz > 50 else 1000.0
                )
                last_rms1 = int(math.sqrt(sum(v * v for v in m1_window) / len(m1_window)))
                last_rms2 = int(math.sqrt(sum(v * v for v in m2_window) / len(m2_window)))
                if args.save_wav:
                    recorded_m1.append(m1)
                    recorded_m2.append(m2)
            elif angle_packet is not None:
                angle_count += 1
                max_rms_observed = max(max_rms_observed, int(angle_packet["rms1"]), int(angle_packet["rms2"]))
            else:
                s, r, p = parsed
                last_sample, last_rms, last_peak = s, r, p
                max_peak_observed = max(max_peak_observed, p)
                max_rms_observed = max(max_rms_observed, r)
                if args.save_wav:
                    recorded_samples.append(s)

            packet_count += 1

            # Rolling rate estimation
            recent_timestamps.append(now)
            if len(recent_timestamps) > 50:
                recent_timestamps.pop(0)
            if len(recent_timestamps) >= 2:
                time_span = recent_timestamps[-1] - recent_timestamps[0]
                if time_span > 0:
                    rate_hz = (len(recent_timestamps) - 1) / time_span

            # Update terminal UI at ~15 Hz to prevent terminal lag
            if now - last_ui_update >= 0.066:
                if stereo_count > 0:
                    meter_str = render_dual_ansi_meter(
                        m1=last_m1, m2=last_m2, rms1=last_rms1, rms2=last_rms2,
                        delay_us=last_delay_us, coherence=last_coh,
                        rate_hz=rate_hz, width=15, use_color=True
                    )
                elif angle_packet is not None:
                    meter_str = render_angle_status(angle_packet, rate_hz)
                else:
                    meter_str = render_ansi_meter(
                        rms=last_rms, peak=last_peak, sample=last_sample,
                        rate_hz=rate_hz, width=30, use_color=True
                    )
                sys.stdout.write(f"\r{meter_str}")
                sys.stdout.flush()
                last_ui_update = now

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
    finally:
        if ser and ser.is_open:
            ser.close()

    total_time = time.time() - start_time
    print("\n" + "-" * 78)
    print("Capture Session Summary:")
    print(f"  Duration:         {total_time:.2f} seconds")
    print(f"  Packets Received: {packet_count}")
    if stereo_count:
        print(f"  Stereo Paired Points: {stereo_count}")
        print(f"  Max Mic 1 Peak:   {max_m1_observed} ({linear_to_dbfs(float(max_m1_observed)):.1f} dBFS)")
        print(f"  Max Mic 2 Peak:   {max_m2_observed} ({linear_to_dbfs(float(max_m2_observed)):.1f} dBFS)")
        print(f"  Final Time Delay: {last_delay_us:>+6.1f} us | Sync Coherence: {last_coh:.2f}")
    if angle_count:
        print(f"  Stereo DOA Packets: {angle_count}")
    avg_rate = packet_count / total_time if total_time > 0 else 0.0
    print(f"  Average Rate:     {avg_rate:.1f} Hz")
    if angle_count:
        print(f"  Max Mic RMS:      {max_rms_observed} ({linear_to_dbfs(float(max_rms_observed)):.1f} dBFS)")
    elif not stereo_count:
        print(f"  Peak Amplitude:   {max_peak_observed} ({linear_to_dbfs(float(max_peak_observed)):.1f} dBFS)")
        print(f"  Max RMS Energy:   {max_rms_observed} ({linear_to_dbfs(float(max_rms_observed)):.1f} dBFS)")

    if args.save_wav and recorded_m1:
        print(f"  Saving {len(recorded_m1)} stereo samples to {args.save_wav}...")
        export_stereo_wav(args.save_wav, recorded_m1, recorded_m2, sample_rate=SAMPLE_RATE, repeat_factor=DECIMATION_FACTOR)
        print(f"  Stereo WAV exported successfully: {args.save_wav} (2 channels, 16-bit PCM)")
    elif args.save_wav and recorded_samples:
        print(f"  Saving {len(recorded_samples)} samples to {args.save_wav}...")
        export_wav(args.save_wav, recorded_samples, sample_rate=SAMPLE_RATE, repeat_decimation=True)
        print(f"  WAV exported successfully: {args.save_wav}")
    elif args.save_wav and angle_count:
        print("  WAV unavailable: angle telemetry contains no raw audio samples.")

    print("=" * 78)


def run_gui_mode(args):
    """Executes the visualizer with live interactive Matplotlib plots."""
    if not HAS_MATPLOTLIB:
        print("[INFO] Matplotlib not installed; falling back to ANSI CLI mode.")
        run_cli_mode(args)
        return

    if not args.mock:
        try:
            args.port = resolve_port(args.port)
        except RuntimeError as ex:
            print(f"[ERROR] {ex}")
            return

    # Check if a graphical display is available
    try:
        backend = matplotlib.get_backend()
        if "agg" in backend.lower() and "tk" not in backend.lower() and "qt" not in backend.lower():
            print("[INFO] Headless display detected; falling back to ANSI CLI mode.")
            run_cli_mode(args)
            return
    except Exception:
        run_cli_mode(args)
        return

    # If matplotlib GUI is available, run animated plot
    # Setup data buffers
    buffer_len = 250  # ~2.5 seconds of history at 100 Hz / ~250 ms at 1000 Hz
    time_buf = [0.0] * buffer_len
    sample_buf = [0] * buffer_len
    sample_buf_m2 = [0] * buffer_len
    rms_buf = [0] * buffer_len
    peak_buf = [0] * buffer_len

    if args.mock:
        mock_gen = SyntheticTelemetryGenerator()
        ser = None
    else:
        if serial is None:
            print("[ERROR] pyserial is not installed. Use --mock or install pyserial.")
            sys.exit(1)
        try:
            ser = serial.Serial(port=args.port, baudrate=args.baud, timeout=0.02)
        except serial.SerialException as ex:
            print(f"[ERROR] Failed to open {args.port}: {ex}")
            sys.exit(1)
        mock_gen = None

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    fig.canvas.manager.set_window_title("SensorTech INMP441 - Dual-Microphone Real-Time Synchronization")

    line_wave, = ax1.plot(time_buf, sample_buf, label="Mic 1 (Left - GPIO 14/27/32)", color="#1f77b4", lw=1.3)
    line_wave2, = ax1.plot(time_buf, sample_buf_m2, label="Mic 2 (Right - GPIO 14/27/32)", color="#ff7f0e", lw=1.3, linestyle="--")
    ax1.set_ylim(-AUDIO_DSP_FULL_SCALE * 1.1, AUDIO_DSP_FULL_SCALE * 1.1)
    ax1.set_ylabel("Amplitude (24-bit)")
    ax1.grid(True, linestyle="--", alpha=0.6)
    ax1.legend(loc="upper right")

    line_rms, = ax2.plot(time_buf, rms_buf, label="Mic 1 Energy", color="#2ca02c", lw=1.5)
    line_peak, = ax2.plot(time_buf, peak_buf, label="Mic 2 Energy", color="#d62728", lw=1.2, linestyle=":")
    ax2.set_ylim(0, AUDIO_DSP_FULL_SCALE * 1.1)
    ax2.set_ylabel("Energy (24-bit)")
    ax2.set_xlabel("Time (s)")
    ax2.grid(True, linestyle="--", alpha=0.6)
    ax2.legend(loc="upper right")

    start_time = time.time()
    recorded_samples = []
    recorded_m1 = []
    recorded_m2 = []
    angle_parser = AngleTelemetryParser()
    stereo_parser = StereoTelemetryParser()
    angle_mode = False
    stereo_mode = False

    def update_frame(frame_num):
        nonlocal start_time, angle_mode, stereo_mode
        now = time.time()
        elapsed = now - start_time

        if args.duration and elapsed >= args.duration:
            plt.close(fig)
            return line_wave, line_wave2, line_rms, line_peak

        # Drain available UART lines
        if mock_gen:
            line, m1, m2, r1, r2 = mock_gen.generate_stereo_pair()
            stereo_packet = (m1, m2)
            parsed = None
            angle_packet = None
        else:
            parsed = None
            angle_packet = None
            stereo_packet = None
            for _ in range(64):
                if not ser.in_waiting:
                    break
                line_bytes = ser.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="ignore")
                new_stereo = stereo_parser.feed(line)
                if new_stereo is not None:
                    stereo_packet = new_stereo
                    parsed = None
                    angle_packet = None
                elif stereo_packet is None:
                    new_angle = angle_parser.feed(line)
                    if new_angle is not None:
                        angle_packet = new_angle
                        parsed = None
                    elif angle_packet is None:
                        new_legacy = parse_telemetry_line(line)
                        if new_legacy is not None:
                            parsed = new_legacy

        if stereo_packet or parsed or angle_packet:
            if stereo_packet:
                if not stereo_mode:
                    stereo_mode = True
                    line_wave2.set_visible(True)
                    line_wave.set_label("Mic 1 (Left)")
                    line_wave2.set_label("Mic 2 (Right)")
                    line_rms.set_label("Mic 1 Level")
                    line_peak.set_label("Mic 2 Level")
                    ax1.legend(loc="upper right")
                    ax2.legend(loc="upper right")

                m1, m2 = stereo_packet
                time_buf.append(elapsed)
                sample_buf.append(m1)
                sample_buf_m2.append(m2)
                rms_buf.append(abs(m1))
                peak_buf.append(abs(m2))

                time_buf.pop(0)
                sample_buf.pop(0)
                sample_buf_m2.pop(0)
                rms_buf.pop(0)
                peak_buf.pop(0)

                if args.save_wav:
                    recorded_m1.append(m1)
                    recorded_m2.append(m2)

                delay_us, coh = compute_stereo_delay_and_coherence(sample_buf, sample_buf_m2)

                line_wave.set_data(time_buf, sample_buf)
                line_wave2.set_data(time_buf, sample_buf_m2)
                line_rms.set_data(time_buf, rms_buf)
                line_peak.set_data(time_buf, peak_buf)

                ax1.set_xlim(time_buf[0], time_buf[-1])
                m1_db = linear_to_dbfs(float(abs(m1)))
                m2_db = linear_to_dbfs(float(abs(m2)))
                ax1.set_title(
                    f"INMP441 Dual-Mic Sync | Delay: {delay_us:+.1f} us | Coherence: {coh:.2f} | M1: {m1_db:.1f} dBFS | M2: {m2_db:.1f} dBFS"
                )
                return line_wave, line_wave2, line_rms, line_peak

            elif angle_packet:
                if not angle_mode:
                    angle_mode = True
                    line_wave2.set_visible(False)
                    ax1.set_ylabel("1D angle (degrees)")
                    ax1.set_ylim(-95, 95)
                    line_wave.set_label("Angle")
                    ax1.legend(loc="upper right")
                    line_rms.set_label("Left RMS")
                    line_peak.set_label("Right RMS")
                    ax2.legend(loc="upper right")
                s = angle_packet["angle"]
                r = angle_packet["rms1"]
                p = angle_packet["rms2"]
            else:
                s, r, p = parsed
                line_wave2.set_visible(False)

            time_buf.append(elapsed)
            sample_buf.append(s)
            rms_buf.append(r)
            peak_buf.append(p)

            time_buf.pop(0)
            sample_buf.pop(0)
            rms_buf.pop(0)
            peak_buf.pop(0)

            if args.save_wav and parsed:
                recorded_samples.append(s)

            line_wave.set_data(time_buf, sample_buf)
            line_rms.set_data(time_buf, rms_buf)
            line_peak.set_data(time_buf, peak_buf)

            ax1.set_xlim(time_buf[0], time_buf[-1])

            if angle_packet:
                ax1.set_title(f"INMP441 Stereo DOA | Angle: {s:.1f} deg | "
                              f"Delay: {angle_packet.get('dt_us', 0.0):.1f} us | "
                              f"Confidence: {angle_packet['conf']:.2f} | Active: {int(angle_packet['active'])}")
            else:
                rms_db = linear_to_dbfs(float(r))
                peak_db = linear_to_dbfs(float(p))
                ax1.set_title(
                    f"INMP441 Live Stream | RMS: {r} ({rms_db:.1f} dBFS) | Peak: {p} ({peak_db:.1f} dBFS)"
                )

        return line_wave, line_wave2, line_rms, line_peak

    try:
        anim = FuncAnimation(fig, update_frame, interval=15, blit=False)
        plt.tight_layout()
        plt.show()
    except Exception as ex:
        print(f"[WARNING] GUI runtime error: {ex}. Switching to CLI mode.")
        run_cli_mode(args)
    finally:
        if ser and ser.is_open:
            ser.close()
        if args.save_wav and recorded_m1:
            export_stereo_wav(args.save_wav, recorded_m1, recorded_m2, sample_rate=SAMPLE_RATE, repeat_factor=DECIMATION_FACTOR)
            print(f"Stereo WAV saved: {args.save_wav}")
        elif args.save_wav and recorded_samples:
            export_wav(args.save_wav, recorded_samples, sample_rate=SAMPLE_RATE, repeat_decimation=True)
        elif args.save_wav and angle_mode:
            print("WAV unavailable: angle telemetry contains no raw audio samples.")


def main():
    parser = argparse.ArgumentParser(
        description="SensorTechINMP441 Real-Time Audio Telemetry Visualizer & Verification Tool"
    )
    parser.add_argument("--port", default=DEFAULT_PORT, help="Serial COM port (auto-detect if only one port is present)")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"Serial baud rate (default: {DEFAULT_BAUD})")
    parser.add_argument("--mock", action="store_true", help="Run synthetic mock audio stream generator")
    parser.add_argument("--duration", type=float, default=None, help="Capture duration in seconds (then exit)")
    parser.add_argument("--cli", action="store_true", help="Force text-based ANSI terminal VU-meter mode")
    parser.add_argument("--save-wav", type=str, default=None, help="Save received samples to 16-bit PCM WAV file")

    args = parser.parse_args()

    if args.cli or not HAS_MATPLOTLIB:
        run_cli_mode(args)
    else:
        run_gui_mode(args)


if __name__ == "__main__":
    main()

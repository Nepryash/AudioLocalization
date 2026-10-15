"""
SensorTechINMP441 Phase 1 Audio Test Framework & Reference Models
Authoritative Reference Implementations derived from:
- ORIGINAL_REQUEST.md
- PROJECT.md
- MEMORY_ACOUSTIC_ARRAY.md
- InvenSense DS-INMP441-00 Rev 1.1
"""

import math
import re
import struct
import io
import wave
from typing import List, Tuple, Optional, Dict, Any

# Authoritative Hardware Constants
I2S_DEFAULT_SAMPLE_RATE = 16000
I2S_DEFAULT_SCK_PIN = 14
I2S_DEFAULT_WS_PIN = 27
I2S_DEFAULT_SD_PIN = 32

AUDIO_DSP_DECIMATION_FACTOR = 128
AUDIO_DSP_FULL_SCALE = 8388607  # 2^23 - 1
AUDIO_DSP_MIN_SCALE = -8388608  # -2^23

TELEMETRY_QUEUE_DEPTH = 8
TELEMETRY_BAUD_RATE = 115200


def to_int32(val: int) -> int:
    """Ensure a value is constrained to signed 32-bit integer range [-2^31, 2^31 - 1]."""
    val = val & 0xFFFFFFFF
    if val >= 0x80000000:
        return val - 0x100000000
    return val


def to_uint32(val: int) -> int:
    """Represent an integer as unsigned 32-bit."""
    return val & 0xFFFFFFFF


def i2s_mic_convert_sample(raw_32: int) -> int:
    """
    Arithmetic right shift conversion per include/i2s_microphone.h:
    static inline int32_t i2s_mic_convert_sample(int32_t raw_32) {
        return raw_32 >> 8;
    }
    Sign extension preserves 24-bit dynamic range in signed 32-bit integer.
    """
    s32 = to_int32(raw_32)
    return s32 >> 8


def i2s_mic_convert_sample_logical_broken(raw_32: int) -> int:
    """
    Simulates the incorrect logical (unsigned) right shift bug:
    ((uint32_t)raw_32) >> 8
    Demonstrates failure mode for negative samples.
    """
    u32 = to_uint32(raw_32)
    return u32 >> 8


def audio_dsp_process_window(samples: List[int]) -> Tuple[int, int, int]:
    """
    Computes (decimated_sample, rms_level, peak_level) per include/audio_dsp.h:
    - decimated_sample: samples[0]
    - rms_level: sqrtf(sum(sample^2) / N)
    - peak_level: max(|sample|)
    """
    if not samples:
        return 0, 0, 0

    decimated = samples[0]
    n = len(samples)

    # 64-bit sum of squares to prevent overflow
    sum_sq = sum(s * s for s in samples)
    rms = int(math.sqrt(sum_sq / n))

    peak = max(abs(s) for s in samples)

    # Clamp to 24-bit positive dynamic range
    rms = min(rms, AUDIO_DSP_FULL_SCALE)
    peak = min(peak, AUDIO_DSP_FULL_SCALE)

    return decimated, rms, peak


def telemetry_format_packet(sample: int, rms: int) -> str:
    """
    Formats telemetry line per PROJECT.md:
    "sample:%ld,rms:%ld\r\n"
    """
    return f"sample:{sample},rms:{rms}\r\n"


_TELEMETRY_REGEX = re.compile(r"^sample:([+-]?\d+),rms:(\d+)\r?\n?$")


def telemetry_parse_line(line: str) -> Optional[Tuple[int, int]]:
    """
    Parses a Serial Plotter telemetry line.
    Returns (sample, rms) or None if malformed.
    """
    m = _TELEMETRY_REGEX.match(line.strip())
    if not m:
        return None
    try:
        sample = int(m.group(1))
        rms = int(m.group(2))
        return sample, rms
    except ValueError:
        return None


class SimulatedFreeRTOSQueue:
    """
    Simulates FreeRTOS xQueueSend with portNO_DELAY (non-blocking).
    If queue is full, packet is dropped and overflow counter increments.
    """

    def __init__(self, capacity: int = TELEMETRY_QUEUE_DEPTH):
        self.capacity = capacity
        self.queue: List[Any] = []
        self.overflow_drops = 0
        self.total_pushes = 0
        self.total_pops = 0

    def send_non_blocking(self, item: Any) -> bool:
        self.total_pushes += 1
        if len(self.queue) >= self.capacity:
            self.overflow_drops += 1
            return False  # Queue full, dropped without blocking
        self.queue.append(item)
        return True

    def receive_non_blocking(self) -> Optional[Any]:
        if not self.queue:
            return None
        self.total_pops += 1
        return self.queue.pop(0)

    def is_empty(self) -> bool:
        return len(self.queue) == 0

    def is_full(self) -> bool:
        return len(self.queue) >= self.capacity

    def size(self) -> int:
        return len(self.queue)


def create_synthetic_wav_bytes(
    samples_24: List[int],
    sample_rate: int = I2S_DEFAULT_SAMPLE_RATE
) -> bytes:
    """
    Converts 24-bit samples to 16-bit standard PCM WAV format bytes.
    """
    # Downscale from 24-bit [-8388608, 8388607] to 16-bit [-32768, 32767]
    pcm16_samples = []
    for s in samples_24:
        s16 = s >> 8
        s16 = max(-32768, min(32767, s16))
        pcm16_samples.append(s16)

    raw_bytes = struct.pack(f"<{len(pcm16_samples)}h", *pcm16_samples)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit (2 bytes)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_bytes)

    return buf.getvalue()


def validate_gpio_pin(pin: int, allow_input_only: bool = False) -> bool:
    """
    Validates ESP32 GPIO pin assignments.
    - Valid range: 0 to 39
    - Reserved/flash: 6-11 are prohibited
    - Input only pins: 34-39 cannot be output clock pins
    """
    if pin < 0 or pin > 39:
        return False
    # Flash pins
    if 6 <= pin <= 11:
        return False
    # Input only pins (GPI 34-39) cannot be used as clock outputs
    if not allow_input_only and pin in (34, 35, 36, 37, 38, 39):
        return False
    return True

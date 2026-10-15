"""Create speaker tones; 187.5 Hz is an exact 2048-point bin at 48 kHz."""

import argparse
import math
from pathlib import Path
import struct
import wave


def write_tone(path: Path, frequency_hz: float, seconds: float) -> None:
    sample_rate = 48000
    total = round(sample_rate * seconds)
    fade = min(round(sample_rate * 0.1), total // 2)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for start in range(0, total, 4096):
            chunk = bytearray()
            for index in range(start, min(start + 4096, total)):
                gain = 1.0
                if fade:
                    gain = min(1.0, (index + 1) / fade, (total - index) / fade)
                sample = round(0.4 * 32767 * gain *
                               math.sin(2.0 * math.pi * frequency_hz * index / sample_rate))
                chunk.extend(struct.pack("<h", sample))
            output.writeframesraw(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--outdir", type=Path, default=Path("tools/tones"))
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    args.outdir.mkdir(parents=True, exist_ok=True)
    for frequency, name in ((125.0, "tone_125hz.wav"),
                            (187.5, "tone_187_5hz.wav")):
        path = args.outdir / name
        write_tone(path, frequency, args.seconds)
        print(path.resolve())


if __name__ == "__main__":
    main()

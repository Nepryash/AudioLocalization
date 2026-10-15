"""Check paired Teleplot output from the two INMP441 microphones."""

import argparse
import math
import re
import statistics
import sys
import time

try:
    import serial
except ImportError:
    print("pyserial is required: python -m pip install pyserial", file=sys.stderr)
    raise SystemExit(2)

SAMPLE = re.compile(r">mic([12]):(-?\d+)$")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="ESP32 serial port, for example COM4")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument("--seconds", type=float, default=10.0)
    args = parser.parse_args()

    left, right = [], []
    pending_left = None
    orphan_left = orphan_right = invalid_plot = other_lines = 0
    examples = []
    try:
        with serial.Serial(args.port, args.baud, timeout=0.5) as port:
            start = time.monotonic()
            saw_left = False
            while time.monotonic() - start < args.seconds:
                line = port.readline().decode("ascii", errors="replace").strip()
                if not line:
                    continue
                match = SAMPLE.fullmatch(line)
                if match:
                    channel, value = int(match[1]), int(match[2])
                    if channel == 1:
                        saw_left = True
                        if pending_left is not None:
                            orphan_left += 1
                        pending_left = value
                    elif pending_left is None:
                        if saw_left:
                            orphan_right += 1
                    else:
                        left.append(pending_left)
                        right.append(value)
                        pending_left = None
                elif line.startswith(">"):
                    invalid_plot += 1
                    if len(examples) < 3:
                        examples.append(line[:100])
                else:
                    other_lines += 1
    except serial.SerialException as exc:
        print(f"Could not read {args.port}: {exc}", file=sys.stderr)
        return 2

    # The reader can start on mic2 and stop after mic1; neither is a lost pair.
    print(f"Paired points: {len(left)} ({len(left) / max(args.seconds, 0.001):.0f}/s)")
    print(f"Unpaired mic1/mic2: {orphan_left}/{orphan_right}")
    print(f"Other plot lines: {invalid_plot}; console/boot lines: {other_lines}")
    for example in examples:
        print(f"Unexpected plot line: {ascii(example)}")
    for name, values in (("mic1", left), ("mic2", right)):
        if values:
            rms = math.sqrt(sum(v * v for v in values) / len(values))
            print(f"{name}: min={min(values)} max={max(values)} RMS={rms:.1f} "
                  f"distinct={len(set(values))} stdev={statistics.pstdev(values):.1f}")
    if left:
        identical = sum(a == b for a, b in zip(left, right))
        print(f"Exactly equal left/right values: {identical}/{len(left)}")
    if not left:
        print("FAIL: no valid stereo pairs; check port, baud, firmware, and power")
        return 1
    if orphan_left or orphan_right or invalid_plot:
        print("WARNING: incomplete or unexpected Teleplot messages were seen")
    if len(set(left)) <= 1 or len(set(right)) <= 1:
        print("WARNING: at least one channel is flat; check its power, L/R, and SD wiring")
    print("Serial pairs confirmed; this does not independently measure acoustic sample timing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

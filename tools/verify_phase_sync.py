"""Measure phase-FFT and I2S DMA health during a controlled stereo tone test.

Close Teleplot before opening the same serial port. Use a steady 125 Hz or
187.5 Hz tone, both exact bins of the firmware's 512-point/16 kHz FFT.
"""

import argparse
import math
import statistics
import sys
import time

try:
    import serial
except ImportError:
    print("pyserial is required: python -m pip install pyserial", file=sys.stderr)
    raise SystemExit(2)


def parse_sync(line):
    if not line.startswith("SYNC "):
        return None
    fields = {}
    for part in line.split()[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        try:
            fields[key] = float(value)
        except ValueError:
            return None
    required = {"fps", "dma", "backlog", "ovf", "lost", "fft", "phase_n",
                "f", "phi", "dt_us", "R", "mag1", "mag2", "gap_us", "fft_us"}
    return fields if required <= fields.keys() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="ESP32 port, for example COM7")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--tone-hz", type=float, choices=(125.0, 187.5), default=125.0)
    parser.add_argument("--expected-delay-us", type=float,
                        help="Expected Mic 2 minus Mic 1 delay; omit to measure only")
    parser.add_argument("--tolerance-us", type=float,
                        help="Allowed absolute delay error when expected delay is supplied")
    parser.add_argument("--min-resultant", type=float,
                        help="Minimum circular phase concentration R, for example 0.99")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--calibrate", action="store_true",
                         help="Send CAL after startup; requires a true zero-delay reference tone")
    actions.add_argument("--repeat-starts", type=int, default=0, metavar="N",
                         help="Send START N times, three seconds apart, and check each ISR latch")
    parser.add_argument("--zero-tolerance-us", type=float, default=5.0,
                        help="Maximum corrected delay after --calibrate (default: 5 us)")
    parser.add_argument("--zero-tolerance-deg", type=float, default=0.2,
                        help="Maximum corrected phase after --calibrate (default: 0.2 deg)")
    parser.add_argument("--start-delay-spread-us", type=float, default=25.0,
                        help="Maximum delay spread across repeated START cycles (default: 25 us)")
    args = parser.parse_args()
    if args.repeat_starts < 0:
        parser.error("--repeat-starts must be nonnegative")
    if args.repeat_starts and args.seconds < 2 + 3 * args.repeat_starts + 2:
        parser.error("increase --seconds to allow all START cycles to finish")

    reports = []
    report_times = []
    sent_times = []
    self_tests = []
    start_latches = []
    cal_latches = []
    try:
        with serial.Serial(args.port, args.baud, timeout=0.5) as port:
            start = time.monotonic()
            sent = 0
            command_count = 1 if args.calibrate else args.repeat_starts
            while time.monotonic() - start < args.seconds:
                elapsed = time.monotonic() - start
                if sent < command_count and elapsed >= 2 + 3 * sent:
                    command = b"CAL\n" if args.calibrate else b"START\n"
                    port.write(command)
                    port.flush()
                    print(f"Sent {command.decode().strip()} at {elapsed:.1f} s")
                    sent_times.append(elapsed)
                    sent += 1
                line = port.readline().decode("ascii", errors="replace").strip()
                if "Phase FFT self-test" in line:
                    self_tests.append(line)
                if "ISR-latched START" in line:
                    start_latches.append(line)
                if "ISR-latched CAL" in line:
                    cal_latches.append(line)
                report = parse_sync(line)
                if report is not None:
                    reports.append(report)
                    report_times.append(time.monotonic() - start)
    except serial.SerialException as exc:
        print(f"Could not read {args.port}: {exc}", file=sys.stderr)
        return 2

    if not reports:
        print("FAIL: no SYNC status lines; check firmware, port, and 460800 baud")
        return 1

    for line in self_tests:
        print(line)

    first, last = reports[0], reports[-1]
    fps = [r["fps"] for r in reports]
    overflow_delta = int(last["ovf"] - first["ovf"])
    lost_delta = int(last["lost"] - first["lost"])
    print(f"DMA: {len(reports)} status seconds, frame rate median {statistics.median(fps):.0f}/s "
          f"(range {min(fps):.0f}-{max(fps):.0f})")
    print(f"DMA: completed blocks {int(last['dma'])}, queue overflows {int(last['ovf'])} "
          f"(+{overflow_delta}), lost frames {int(last['lost'])} (+{lost_delta}), "
          f"max backlog {max(r['backlog'] for r in reports):.0f} frames")
    print(f"Capture: max read gap {max(r['gap_us'] for r in reports):.0f} us, "
          f"max FFT compute {max(r['fft_us'] for r in reports):.0f} us, "
          f"FFT windows {sum(r['fft'] for r in reports):.0f}")
    print(f"Capture: read timeouts {int(last.get('timeout', 0))}, "
          f"short reads {int(last.get('short', 0))}, errors {int(last.get('err', 0))}; "
          f"Teleplot queue drops {int(last.get('plot_drop', 0))}")
    if "state" in last:
        states = {int(r["state"]) for r in reports if "state" in r}
        print(f"Pipeline: states observed {sorted(states)}, "
              f"calibration ready {int(last.get('cal_ready', 0))}, "
              f"DMA restarts {int(last.get('restart', 0))}, "
              f"skew setting {int(last.get('skew', 0))} frame(s)")
    if args.repeat_starts:
        for line in start_latches:
            print(line)
        if len(start_latches) < args.repeat_starts:
            print(f"FAIL: only {len(start_latches)} ISR START latches observed for "
                  f"{args.repeat_starts} commands")
            return 1
        if not any(int(r.get("state", -1)) == 2 for r in reports):
            print("FAIL: pipeline did not return to RUNNING")
            return 1
    if args.calibrate:
        for line in cal_latches:
            print(line)
        if not cal_latches or not any(r.get("cal_ready", 0) == 1 for r in reports):
            print("FAIL: no completed reference calibration; check the tone and source position")
            return 1

    chosen = [r for r in reports if r["phase_n"] > 0 and
              abs(r["f"] - args.tone_hz) < 0.5 and
              (not args.calibrate or
               (r.get("cal_ready", 0) == 1 and r.get("state", -1) == 2))]
    if not chosen:
        print(f"NO PHASE RESULT: play a steady {args.tone_hz:g} Hz tone to both microphones "
              "and ensure both magnitudes are above the silence threshold")
        return 1

    # Circular average of FFT phase estimates; no waveform correlation is used.
    x = sum(r["phase_n"] * r["R"] * math.cos(math.radians(r["phi"])) for r in chosen)
    y = sum(r["phase_n"] * r["R"] * math.sin(math.radians(r["phi"])) for r in chosen)
    n = sum(r["phase_n"] for r in chosen)
    phase_deg = math.degrees(math.atan2(y, x))
    concentration = math.hypot(x, y) / n
    delay_us = -phase_deg / (360.0 * args.tone_hz) * 1e6
    coverage = n / sum(r["fft"] for r in reports)
    print(f"Phase at {args.tone_hz:g} Hz: {n:.0f} FFT windows, mean {phase_deg:.3f} deg, "
          f"coverage {coverage:.1%}, resultant {concentration:.4f}, delay {delay_us:.2f} us")
    print(f"FFT magnitudes: mic1 median {statistics.median(r['mag1'] for r in chosen):.0f}, "
          f"mic2 median {statistics.median(r['mag2'] for r in chosen):.0f}")
    print(f"Per-second delay range: {min(r['dt_us'] for r in chosen):.2f} to "
          f"{max(r['dt_us'] for r in chosen):.2f} us")
    if args.repeat_starts:
        cycle_delays = []
        for i, sent_at in enumerate(sent_times):
            next_at = sent_times[i + 1] if i + 1 < len(sent_times) else args.seconds
            values = [r["dt_us"] for r, t in zip(reports, report_times)
                      if sent_at + 0.7 <= t < next_at - 0.1 and
                      r["phase_n"] > 0 and abs(r["f"] - args.tone_hz) < 0.5 and
                      r.get("state", -1) == 2]
            if not values:
                print(f"FAIL: no phase reading after START cycle {i + 1}")
                return 1
            cycle_delays.append(statistics.median(values))
        spread = max(cycle_delays) - min(cycle_delays)
        print(f"START cycle median delays: {', '.join(f'{v:.2f}' for v in cycle_delays)} us; "
              f"spread {spread:.2f} us")
        if spread > args.start_delay_spread_us:
            print("FAIL: repeated starts changed phase delay beyond the requested tolerance")
            return 1
    if args.calibrate:
        corrected = [r for r in chosen if r.get("cal_ready", 0) == 1 and
                     r.get("state", -1) == 2 and r["phase_n"] > 0]
        if len(corrected) < 2:
            print("FAIL: fewer than two corrected status seconds after calibration")
            return 1
        corrected_delay = statistics.median(r["dt_us"] for r in corrected)
        corrected_phase = statistics.median(r["phi"] for r in corrected)
        print(f"Reference after CAL: median delay {corrected_delay:.2f} us, "
              f"phase {corrected_phase:.3f} deg over {len(corrected)} status seconds")
        if (abs(corrected_delay) > args.zero_tolerance_us or
                abs(corrected_phase) > args.zero_tolerance_deg):
            print("FAIL: corrected reference exceeds the requested zero tolerance")
            return 1

    if last["ovf"] or last["lost"]:
        print("FAIL: the I2S RX queue overflowed; sample continuity is not verified")
        return 1
    if last.get("err", 0) or last.get("short", 0) or last.get("timeout", 0) or last.get("restart", 0):
        print("FAIL: I2S read error, timeout, short read, or DMA restart occurred")
        return 1
    if args.min_resultant is not None and concentration < args.min_resultant:
        print("FAIL: phase concentration is below the requested threshold")
        return 1
    if coverage < 0.5:
        print("WARNING: the requested tone was selected in fewer than half of FFT windows")
    if args.expected_delay_us is not None:
        error = abs(delay_us - args.expected_delay_us)
        print(f"Expected delay {args.expected_delay_us:.2f} us; error {error:.2f} us")
        if args.tolerance_us is not None and error > args.tolerance_us:
            print("FAIL: phase delay exceeds requested tolerance")
            return 1
    print("DMA queue continuity observed; absolute acoustic offset depends on the test geometry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

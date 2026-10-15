#!/usr/bin/env python3
"""
SensorTechINMP441 Automated E2E Test Runner
Discovers and executes historical Phase 1 reference-model and angle-telemetry
parser tests. These host-side tests do not flash or run the current ESP32 firmware.
Outputs structured reports, validates feature coverage checklist,
and exits with code 0 on 100% pass (code 1 on any failure).
"""

import sys
import os
import time
import argparse
import unittest
from datetime import datetime, timezone

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TIERS = {
    1: {
        "name": "Tier 1: Feature Coverage (F1-F9)",
        "module": "test.test_tier1_features",
        "desc": "Individual feature functional isolation verification (>=5 cases per F1-F9)"
    },
    2: {
        "name": "Tier 2: Boundary & Corner Cases",
        "module": "test.test_tier2_boundaries",
        "desc": "Numerical extrema, clipping, saturation, DC drift, and queue capacity bounds"
    },
    3: {
        "name": "Tier 3: Cross-Feature Combinations",
        "module": "test.test_tier3_combinations",
        "desc": "Pairwise interactions, step transients, queue backpressure, and transport noise"
    },
    4: {
        "name": "Tier 4: Real-World Application Scenarios",
        "module": "test.test_tier4_scenarios",
        "desc": "1000+ frame streaming simulation, AED clap trigger, plotter format, WAV export"
    },
    5: {
        "name": "Tier 5: Legacy Angle Parsing",
        "module": "test.test_angle_telemetry",
        "desc": "Historical angle firmware Teleplot and CSV packet parsing"
    }
}

FEATURE_CHECKLIST = [
    ("F1", "Modern ESP-IDF I2S Setup (driver/i2s_std.h, RX Master, 32-bit slot, 64 SCK)"),
    ("F2", "Configurable GPIO Pinout (GPIO 14 SCK, 27 WS, 32 SD, internal pulldown)"),
    ("F3", "Multi-Mic Architecture Groundwork (3-mic mapping: I2S0 L/R, I2S1 L)"),
    ("F4", "24-in-32 Bit Sample Extraction (Arithmetic >> 8, sign extension preservation)"),
    ("F5", "Hardware FPU RMS & Peak Math (Window RMS sqrt(sum/N), Peak tracking, no overflow)"),
    ("F6", "Decoupled FreeRTOS Concurrency (Queue depth 8, non-blocking portNO_DELAY)"),
    ("F7", "Decimated Serial Plotter Telemetry (sample:%ld,rms:%ld\\r\\n, 125 Hz stream)"),
    ("F8", "Application Lifecycle & Error Handling (Robust error checking, clean deinit)"),
    ("F9", "Python Verification & Plotting Tool (Telemetry parser, mock stream, WAV export)"),
]


def print_banner():
    print("=" * 80)
    print("      SensorTechINMP441 - Host Reference and Telemetry Tests")
    print(f"      Execution Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"      Python: {sys.version.split()[0]} | Platform: {sys.platform}")
    print("=" * 80)


def run_tier(tier_num: int, verbose: bool = False, failfast: bool = False):
    tier_info = TIERS[tier_num]
    print(f"\n[RUNNING] {tier_info['name']}")
    print(f"          {tier_info['desc']}")
    print("-" * 80)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(tier_info["module"])

    start_time = time.time()
    runner = unittest.TextTestRunner(
        verbosity=2 if verbose else 1,
        failfast=failfast,
        stream=sys.stdout
    )
    result = runner.run(suite)
    elapsed = time.time() - start_time

    return {
        "tier": tier_num,
        "name": tier_info["name"],
        "total": result.testsRun,
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "failed": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "elapsed": elapsed,
        "success": result.wasSuccessful()
    }


def main():
    parser = argparse.ArgumentParser(description="SensorTechINMP441 E2E Test Runner")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4, 5], help="Run only specific tier (1-5)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose test execution")
    parser.add_argument("-f", "--failfast", action="store_true", help="Stop on first failure")
    args = parser.parse_args()

    print_banner()

    tiers_to_run = [args.tier] if args.tier else [1, 2, 3, 4, 5]
    results = []

    overall_start = time.time()
    for t in tiers_to_run:
        res = run_tier(t, verbose=args.verbose, failfast=args.failfast)
        results.append(res)
        if args.failfast and not res["success"]:
            print(f"\n[ABORTED] Failfast triggered in Tier {t}.")
            break

    total_elapsed = time.time() - overall_start

    # Summary Table
    print("\n" + "=" * 80)
    print("                         TEST SUITE EXECUTION SUMMARY")
    print("=" * 80)
    print(f"{'Tier':<42} | {'Tests':<6} | {'Pass':<5} | {'Fail':<5} | {'Time (s)':<8}")
    print("-" * 80)

    total_tests = sum(r["total"] for r in results)
    total_passed = sum(r["passed"] for r in results)
    total_failed = sum(r["failed"] for r in results)
    total_errors = sum(r["errors"] for r in results)

    for r in results:
        print(f"{r['name']:<42} | {r['total']:<6} | {r['passed']:<5} | {r['failed'] + r['errors']:<5} | {r['elapsed']:<8.3f}")

    print("-" * 80)
    print(f"{'TOTAL':<42} | {total_tests:<6} | {total_passed:<5} | {total_failed + total_errors:<5} | {total_elapsed:<8.3f}")
    print("=" * 80)

    # Feature Checklist
    if not args.tier or args.tier == 1:
        print("\n" + "=" * 80)
        print("             PHASE 1 REFERENCE CHECKLIST (NOT FIRMWARE VERIFICATION)")
        print("=" * 80)
        for fid, fdesc in FEATURE_CHECKLIST:
            print(f"  [MODEL] {fid}: {fdesc}")
        print("=" * 80)

    all_successful = all(r["success"] for r in results)

    if all_successful:
        print(f"\n>>> [SUCCESS] All {total_tests} tests in {len(results)} tiers PASSED cleanly in {total_elapsed:.3f}s. <<<")
        sys.exit(0)
    else:
        print(f"\n>>> [FAILURE] {total_failed + total_errors} test(s) FAILED out of {total_tests}. <<<")
        sys.exit(1)


if __name__ == "__main__":
    main()

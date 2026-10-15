# DISPATCH: E2E Test Writer 1 (Opaque-Box E2E Testing Track)

## Identity
- Archetype: teamwork_preview_test_writer
- Role: E2E Test Suite Creator
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\test_writer_e2e_1\
- Parent Orchestrator: teamwork_preview_orchestrator_1 (Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745)

## Authoritative Inputs
MANDATORY: You MUST read:
1. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md`

## Write Ownership
You exclusively own:
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\TEST_INFRA.md`
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\TEST_READY.md`
- `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\test\` directory:
  - `test/test_runner.py`
  - `test/test_tier1_features.py`
  - `test/test_tier2_boundaries.py`
  - `test/test_tier3_combinations.py`
  - `test/test_tier4_scenarios.py`

DO NOT modify files in `src/`, `include/`, or `platformio.ini`.

## Objective
Design and implement the comprehensive, opaque-box, requirement-driven E2E test suite for Phase 1 of the INMP441 acoustic array system:
1. Create `TEST_INFRA.md` in `.agents/teamwork/` following the Project Pattern template:
   - Methodology: Category-Partition + Boundary Value Analysis + Pairwise Combinatorial + Workload Testing.
   - Map all features F1 through F9.
2. Build the automated test runner and test tiers:
   - `test/test_runner.py`: Discovers and executes all tiers, prints structured test results, exits with code 0 on all pass.
   - `test/test_tier1_features.py`: >=5 test cases per feature (F1-F9) covering bit shift math (`>> 8`), sign extension preservation (negative and positive ranges), RMS energy calculation accuracy, peak detection, Serial Plotter format `sample:VAL,rms:VAL`, pin config integrity, and baud rate/decimation compatibility.
   - `test/test_tier2_boundaries.py`: >=5 test cases per feature. Extreme audio values: full-scale positive (`+8388607`), full-scale negative (`-8388608`), zero amplitude, clipping at boundary, DC offset drift, small amplitude signals, buffer size limits.
   - `test/test_tier3_combinations.py`: Pairwise interactions. Concurrent audio acquisition + UART formatting, step transitions (instant silence to loud impulse), high noise floor vs clean audio, queue overflow protection.
   - `test/test_tier4_scenarios.py`: >=5 realistic application scenarios. Continuous streaming simulation over 1000+ frames, real-time telemetry parser verification, Serial Plotter visualizer compatibility, synthetic signal generation, WAV audio export check.
3. Verify test suite execution:
   Run `& "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py` to confirm all tests execute and pass cleanly.
4. Publish `TEST_READY.md` in `.agents/teamwork/` with runner command, test breakdown, and feature checklist.

## Output Requirements
Write your handoff report to:
`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\test_writer_e2e_1\handoff.md`
When done, notify the orchestrator (Recipient: d17832be-bb24-40e4-9ee2-0c353fd26745).


## 2026-10-06T12:26:54Z
You are E2E Test Suite Creator (test_writer_e2e_1).
Your working directory is: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\test_writer_e2e_1\
Read your task assignment in: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\test_writer_e2e_1\DISPATCH.md
Read the authoritative user request at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md
Read the project architecture and features at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md

Build the comprehensive, opaque-box E2E test suite:
1. Create C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\TEST_INFRA.md following the Project Pattern template.
2. Implement automated test suites in C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\test\:
   - test_runner.py (discovers and runs all tiers, exits 0 on all pass)
   - test_tier1_features.py (>=5 test cases per feature F1-F9)
   - test_tier2_boundaries.py (>=5 test cases per feature: max/min 24-bit limits, zero, clipping, DC offset)
   - test_tier3_combinations.py (pairwise combinations: audio + serial streaming, impulse transitions, queue limits)
   - test_tier4_scenarios.py (>=5 realistic application scenarios: streaming simulation, live parser, plotter format, WAV export)
3. Execute the test runner using Python: & "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py
4. Publish C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\TEST_READY.md.
5. Write your handoff.md and notify the orchestrator (conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745).

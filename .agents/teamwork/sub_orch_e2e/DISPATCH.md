# DISPATCH: Sub-Orchestrator E2E Testing Track

## Identity
- Archetype: orchestrator
- Role: E2E Testing Orchestrator
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\sub_orch_e2e\
- Parent Orchestrator: teamwork_preview_orchestrator_1 (Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745)

## Authoritative Inputs
MANDATORY: You MUST read:
1. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md`

## Scope: E2E Testing Track
Build an opaque-box, requirement-driven automated test suite for the INMP441 acoustic array acquisition system:
1. Create `TEST_INFRA.md` in `.agents/teamwork/` per Project Pattern template.
2. Develop comprehensive automated test suites under `test/`:
   - `test/test_runner.py`: Unified test harness with exit code 0 on all pass, structured reporting.
   - `test/test_tier1_features.py`: Tier 1 Feature Coverage (>=5 test cases per feature for F1 through F9). Covers isolated functionality (bit shift math `>> 8`, sign extension, RMS calculation accuracy, Serial Plotter format `sample:VAL,rms:VAL`, pin validation, CMake/config checks). Simple pass/fail mechanisms.
   - `test/test_tier2_boundaries.py`: Tier 2 Boundary & Corner Cases (>=5 test cases per feature). Extreme audio values: full positive scale `+8388607`, full negative scale `-8388608`, zero amplitude, DC offset saturation, boundary clipping, buffer underrun/overflow edge cases.
   - `test/test_tier3_combinations.py`: Tier 3 Cross-Feature Interactions (pairwise coverage). Concurrent audio acquisition and UART telemetry formatting, dynamic envelope tracking under step transitions (silence to clap impulse), queue backpressure resilience.
   - `test/test_tier4_scenarios.py`: Tier 4 Real-World Application Scenarios (>=5 scenarios). Continuous streaming simulation, live UART parsing test against COM7 or synthetic stream, Serial Plotter visualizer compatibility, WAV file export verification.
3. Validate that test execution can run standalone via Python:
   `& "C:\Users\hp\.platformio\penv\Scripts\python.exe" test/test_runner.py`
4. Publish `TEST_READY.md` in `.agents/teamwork/` with runner command, test counts per tier, and feature checklist.

## Execution Procedure
Follow the Project Pattern:
1. Assess & write `SCOPE.md`, `BRIEFING.md`, `progress.md`.
2. Dispatch specialist test writers (`teamwork_preview_test_writer` or workers) to implement test harness and test tiers.
3. Review and audit test suite integrity (no hardcoded passes, genuine verification).
4. Publish `TEST_READY.md`.
5. Write `handoff.md` and send message to parent orchestrator (`d17832be-bb24-40e4-9ee2-0c353fd26745`).

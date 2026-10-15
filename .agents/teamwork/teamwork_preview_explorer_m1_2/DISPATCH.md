# DISPATCH: Milestone M1 Explorer 2 (Audio Math & Contract Specialist)

## Identity
- Archetype: teamwork_preview_explorer
- Role: M1 Audio Math & Contract Specialist
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_2\
- Parent Orchestrator: teamwork_preview_orchestrator_1 (Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745)

## Authoritative Inputs
MANDATORY: You MUST read:
1. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md`
3. Survey reports in `.agents/teamwork/teamwork_preview_explorer_survey_2/report.md`

## Milestone M1 Scope
Core Audio Engine & Configuration:
- Exact 24-in-32 bit sample transformation math:
  - Verifying arithmetic right shift `>> 8` on signed `int32_t` vs bitwise masks vs unsigned conversion.
  - Ensuring sign preservation across full dynamic range `[-8388608, +8388607]`.
  - Preventing DC offset saturation and bit inversion.
  - Buffer reading API design: `i2s_mic_read_raw` vs `i2s_mic_read_samples`.
  - Stub / test verification strategy to validate that `include/i2s_microphone.h` conforms exactly to interface contract for downstream M2 DSP processing.

## Objective
Provide mathematical proofs, edge case verification rules, and interface conformance guidelines for the Worker.

## Output Requirements
Write report to: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_2\report.md`
Write handoff to: `C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_2\handoff.md`
When done, notify the orchestrator (Recipient: d17832be-bb24-40e4-9ee2-0c353fd26745).

## 2026-10-06T12:26:54Z
From: d17832be-bb24-40e4-9ee2-0c353fd26745
Content: You are Milestone M1 Explorer 2 (Audio Math & Contract Specialist).
Your working directory is: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_2\
Read your task assignment in: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_explorer_m1_2\DISPATCH.md
Read the authoritative user request at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md
Read the project architecture at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\PROJECT.md

Analyze sample conversion math and interface contracts for Milestone M1:
- 24-in-32 bit sample transformation: arithmetic right shift >> 8 on signed int32_t vs sign extension
- Verification that [-8388608, +8388607] dynamic range is strictly preserved without DC bias or inversion
- Buffer reading contract design: i2s_mic_read_raw vs i2s_mic_read_samples
- Conformance testing for downstream M2 DSP module integration
Write your recommendations to report.md and handoff.md.
When done, notify the orchestrator (conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745).

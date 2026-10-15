# BRIEFING — 2026-10-06T12:09:18Z

## Mission
Develop and verify Phase 1 of acoustic array system on ESP32 (INMP441 24-bit audio via ESP-IDF v5/v6 driver/i2s_std.h + Serial Plotter telemetry + future multi-channel architecture).

## 🔒 My Identity
- Archetype: orchestrator
- Roles: orchestrator, user_liaison, human_reporter, successor
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_orchestrator_1
- Original parent: Sentinel
- Original parent conversation ID: 2473d003-c446-401d-aa14-d39f0204cc2d

## 🔒 My Workflow
- **Pattern**: Project Pattern (Dual Track: Implementation + E2E Testing)
- **Scope document**: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\PROJECT.md
1. **Decompose**: Survey (3 Explorers/Spec Miners) -> Map features & constraints -> Decompose into milestones -> Interface contracts -> PROJECT.md
2. **Dispatch & Execute**:
   - Implementation Track: Sequential/parallel milestones via Sub-orchestrators or Iteration loop
   - E2E Testing Track: Requirements-driven opaque-box test suite -> TEST_READY.md
   - Final Milestone: 100% E2E test pass + Tier 5 adversarial coverage hardening
3. **On failure** (in this order):
   - Retry: nudge stuck agent or re-send task
   - Replace: spawn fresh agent with partial progress
   - Skip: proceed without (only if non-critical)
   - Redistribute: split stuck agent's remaining work
   - Redesign: re-partition decomposition
   - Escalate: report to parent (sub-orchestrators only, last resort)
4. **Succession**: At 16 spawns, write soft handoff.md, cancel crons, spawn successor
- **Work items**:
  0. Survey full scope [pending]
  1. Decompose & create PROJECT.md [pending]
  2. Dispatch Implementation & E2E Testing Tracks [pending]
  3. Final Milestone & Verification [pending]
- **Current phase**: 0 (Survey)
- **Current focus**: Step 0 Survey

## 🔒 Key Constraints
- NEVER write, modify, or create source code files directly.
- NEVER run build/test commands yourself — require workers to do so.
- NEVER investigate or explore the problem at the code level — dispatch Explorers for technical investigation.
- File-editing tools ONLY for metadata/state files (.md) in .agents/teamwork/ folder.
- Always include path to ORIGINAL_REQUEST.md in every subagent dispatch.
- Never reuse a subagent after it has delivered its handoff — always spawn fresh.
- Binary veto on forensic audit failure.
- Self-succeed at 16 spawns.

## Current Parent
- Conversation ID: 2473d003-c446-401d-aa14-d39f0204cc2d
- Updated: not yet

## Key Decisions Made
- Initializing Step 0 Survey with 3 parallel agents (2 Explorers + 1 Spec Miner).

## Team Roster
| Agent | Type | Work Item | Status | Conv ID |
|-------|------|-----------|--------|---------|
| explorer_survey_1 | teamwork_preview_explorer | Codebase & Config Survey | completed | 85990033-cc00-4a47-9351-49a810176ee0 |
| spec_miner_survey_1 | teamwork_preview_spec_miner | I2S & INMP441 Spec Mining | completed | e61ae0d5-cdf5-4ec1-b26d-dd6f65bd4242 |
| explorer_survey_2 | teamwork_preview_explorer | Telemetry & Verification Survey | completed | 3e8ef1b7-7df0-461b-b7b4-184b362e8eb4 |
| test_writer_e2e_1 | teamwork_preview_test_writer | E2E Testing Track (Tiers 1-4) | completed | 7e9d91e4-4b99-4f26-a576-56bd38f4e692 |
| explorer_m1_1 | teamwork_preview_explorer | M1 Hardware & Driver Survey | completed | 040edcee-2769-45a7-9358-8ee884c4aba1 |
| spec_miner_m1_1 | teamwork_preview_spec_miner | M1 I2S Spec & Timing Mining | completed | 10341001-a3d5-4e3b-9087-e8f5caef804a |
| explorer_m1_2 | teamwork_preview_explorer | M1 Audio Math & Contract Survey | completed | fadc3400-bfbe-41a7-883b-91725b1f25b3 |
| worker_m1_1 | teamwork_preview_worker | M1 Implementation | completed | 5b16853f-36bc-4ba8-bb25-1295a3b467e4 |
| reviewer_m1_1 | teamwork_preview_reviewer | M1 Code Review | completed | ca21ecc3-ae8f-423a-abe9-f19e713b36a2 |
| reviewer_m1_2 | teamwork_preview_reviewer | M1 Robustness Review | completed | 31599f04-e826-4e1e-ba96-e4056f84f688 |
| challenger_m1_1 | teamwork_preview_challenger | M1 Numerical Challenge | completed | 86b8e3f2-a4d4-407c-a04f-73cb12af7464 |
| challenger_m1_2 | teamwork_preview_challenger | M1 Build & HIL Challenge | completed | 6c8b73b9-aaef-463d-8b0b-f0299aac5fea |
| auditor_m1_1 | teamwork_preview_auditor | M1 Forensic Audit | completed | b3c41637-bd9a-406a-a14c-e83930ebd12b |
| worker_m2_1 | teamwork_preview_worker | M2 DSP & Telemetry Implementation | completed | 831695bf-4084-40fc-8941-75d7d99cc06c |
| worker_m3_1 | teamwork_preview_worker | M3 Application & Tooling Implementation | completed | e04bb704-1c89-4933-8af5-25ed05815751 |
| auditor_final | teamwork_preview_auditor | Final System Forensic Audit | completed | b0f60b7e-4d1f-4d75-b4e1-c7af9e16aa03 |

## Succession Status
- Succession required: no
- Spawn count: 16 / 16
- Pending subagents: none
- Predecessor: none
- Successor: not yet spawned

## Active Timers
- Heartbeat cron: d17832be-bb24-40e4-9ee2-0c353fd26745/task-10
- Safety timer: pending

## Artifact Index
- C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md — Authoritative User Request
- C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_orchestrator_1\DISPATCH.md — Orchestrator Dispatch Log
- C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_orchestrator_1\progress.md — Orchestrator Liveness and Progress

# DISPATCH: Survey Agent 2 (I2S & INMP441 Spec Miner)

## Identity
- Archetype: teamwork_preview_spec_miner
- Role: I2S & INMP441 Spec Miner
- Working directory: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_spec_miner_survey_1\
- Parent Orchestrator: teamwork_preview_orchestrator_1 (Conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745)

## Authoritative User Request
MANDATORY: You MUST read the authoritative user request at:
C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md

## Scope & Objective
Mine and document technical specifications and requirements for ESP-IDF v5/v6 (`driver/i2s_std.h`) and the INMP441 MEMS microphone:
1. Examine ESP-IDF v5/v6 `driver/i2s_std.h` standard mode API conventions:
   - Channel allocation: `i2s_new_channel`, `i2s_channel_init_std_mode`, `i2s_channel_enable`, `i2s_channel_read`.
   - Clock config: sample rate (e.g. 16kHz, 44.1kHz, 48kHz), master clock source, BCLK division.
   - Slot config: Philips format, 24-bit data in 32-bit slot (`I2S_DATA_BIT_WIDTH_24`, `I2S_SLOT_BIT_WIDTH_32`), mono vs stereo slot mask (`I2S_STD_SLOT_LEFT`, etc.).
   - DMA config: buffer count, buffer size (frames per buffer), DMA memory allocation.
2. INMP441 hardware specifics:
   - Philips standard mode, 1-bit delay between WS transition and MSB.
   - 24-bit 2's complement audio output MSB-first.
   - Bit alignment in 32-bit words: when reading into a 32-bit integer array (`int32_t`), determine the exact bit shift (`>> 8`) and arithmetic sign extension needed to avoid DC saturation, distortion, or bit inversion.
3. Architecture alignment:
   - Future 3-mic mapping from project memory (`MEMORY_ACOUSTIC_ARRAY.md` Section 5):
     * Mic 1 -> I2S0 Left (L/R to GND)
     * Mic 2 -> I2S0 Right (L/R to VDD)
     * Mic 3 -> I2S1 Left (L/R to GND)
     * Slot 4 (I2S1 Right) discarded.
   - How Phase 1 (single mic on I2S0 Left) cleanly paves the way for this 3-mic architecture without breaking changes.
4. Robust error handling on all driver calls (ESP_ERROR_CHECK vs error return codes, resource cleanup/deinit).

## Output Requirements
Write your detailed report to:
`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_spec_miner_survey_1\report.md`
and write your completion handoff to:
`C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_spec_miner_survey_1\handoff.md`

When finished, send a message to the orchestrator (Recipient: d17832be-bb24-40e4-9ee2-0c353fd26745) notifying completion and referencing your report.

## 2026-10-06T12:10:57Z
You are Survey Spec Miner 1 (I2S & INMP441 Spec Miner).
Your working directory is: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_spec_miner_survey_1\
Read your task assignment in: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\teamwork_preview_spec_miner_survey_1\DISPATCH.md
Read the authoritative user request at: C:\Users\hp\Documents\PlatformIO\Projects\SensorTechINMP441\.agents\teamwork\ORIGINAL_REQUEST.md

Mine and document technical specifications and requirements for ESP-IDF v5/v6 (driver/i2s_std.h) and the INMP441 MEMS microphone:
- ESP-IDF v5/v6 driver/i2s_std.h API requirements (channel allocation, standard mode config, slot config, clock config, DMA buffers, error handling)
- INMP441 hardware specifics (Philips standard mode, 24-bit audio in 32-bit slot, bit shifting >> 8, sign extension to int32_t, avoiding DC offset/bit inversion)
- Future 3-mic architecture mapping (I2S0 L/R, I2S1 L) per MEMORY_ACOUSTIC_ARRAY.md Section 5
Write your findings to report.md and handoff.md in your working directory.
When done, send a message to the orchestrator (conversation ID: d17832be-bb24-40e4-9ee2-0c353fd26745) summarizing your results.

## 2026-10-06T12:21:11Z
**Context**: Step 0 Survey - I2S & INMP441 Spec Mining
**Content**: Checking status on your survey report and handoff. Both Explorer 1 and Explorer 2 have completed their handoffs. Please report your current progress or any blocking issues.
**Action**: Please update progress.md and finalize report.md and handoff.md.



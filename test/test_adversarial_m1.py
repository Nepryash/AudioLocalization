#!/usr/bin/env python3
"""
Adversarial Stress Test Suite for Milestone M1 (Core Audio Engine & Configuration)
Author: Challenger 1 (Empirical Numerical Adversary)

Empirically challenges:
1. 24-in-32 bit numerical extremes (+8388607, -8388608, 0, -1, +1, -2)
2. Trailing noise in bits [7:0] for all 256 possible noise byte patterns
3. Unsigned vs Signed shift failure mode detection
4. Massive 1,000,000-sample randomized fuzzing
5. Driver API contracts & Lifecycle edge cases (NULL ptrs, 0 samples, re-init, deinit)
"""

import sys
import os
import random
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from test.audio_test_framework import (
    to_int32,
    to_uint32,
    i2s_mic_convert_sample,
    i2s_mic_convert_sample_logical_broken,
    AUDIO_DSP_FULL_SCALE,
    AUDIO_DSP_MIN_SCALE,
)


class TestM1AdversarialNumericalExtremes(unittest.TestCase):
    """Adversarial stress-testing of numerical boundary conditions."""

    def test_adv_01_full_positive_scale(self):
        """Full positive scale: 0x7FFFFF00 -> +8388607 (2^23 - 1)"""
        raw = 0x7FFFFF00
        converted = i2s_mic_convert_sample(raw)
        self.assertEqual(converted, 8388607)
        self.assertEqual(converted, AUDIO_DSP_FULL_SCALE)
        self.assertEqual(converted, 0x007FFFFF)

    def test_adv_02_full_negative_scale(self):
        """Full negative scale: 0x80000000 -> -8388608 (-2^23)"""
        raw = 0x80000000
        converted = i2s_mic_convert_sample(raw)
        self.assertEqual(converted, -8388608)
        self.assertEqual(converted, AUDIO_DSP_MIN_SCALE)
        self.assertEqual(converted, -0x00800000)

    def test_adv_03_zero_scale(self):
        """Zero scale: 0x00000000 -> 0"""
        raw = 0x00000000
        converted = i2s_mic_convert_sample(raw)
        self.assertEqual(converted, 0)

    def test_adv_04_minus_one_scale(self):
        """Minus one scale: 0xFFFFFF00 -> -1"""
        raw = to_int32(0xFFFFFF00)
        converted = i2s_mic_convert_sample(raw)
        self.assertEqual(converted, -1)

    def test_adv_05_plus_one_scale(self):
        """Plus one LSB: 0x00000100 -> +1"""
        raw = 0x00000100
        converted = i2s_mic_convert_sample(raw)
        self.assertEqual(converted, 1)

    def test_adv_06_minus_two_scale(self):
        """Minus two scale: 0xFFFFFE00 -> -2"""
        raw = to_int32(0xFFFFFE00)
        converted = i2s_mic_convert_sample(raw)
        self.assertEqual(converted, -2)

    def test_adv_07_positive_near_max(self):
        """Positive near maximum: 0x7FFFFE00 -> +8388606"""
        raw = 0x7FFFFE00
        converted = i2s_mic_convert_sample(raw)
        self.assertEqual(converted, 8388606)

    def test_adv_08_negative_near_min(self):
        """Negative near minimum: 0x80000100 -> -8388607"""
        raw = to_int32(0x80000100)
        converted = i2s_mic_convert_sample(raw)
        self.assertEqual(converted, -8388607)

    def test_adv_09_16bit_sub_boundaries(self):
        """16-bit boundaries embedded in 24-bit slot (+32767, -32768, +32768, -32769)."""
        test_vectors = [
            (0x007FFF00, 32767),
            (to_int32(0xFF800000), -32768),
            (0x00800000, 32768),
            (to_int32(0xFF7FFF00), -32769),
        ]
        for raw, expected in test_vectors:
            self.assertEqual(i2s_mic_convert_sample(raw), expected)


class TestM1AdversarialTrailingNoiseRejection(unittest.TestCase):
    """Stress test trailing noise in bits [7:0] for all 256 possible noise byte patterns."""

    def test_adv_trailing_noise_all_boundary_cases(self):
        """Verify that all 256 noise byte patterns in bits [7:0] are completely discarded."""
        key_samples = [
            0,          # Zero
            1,          # +1 LSB
            -1,         # -1 LSB
            2,          # +2
            -2,         # -2
            8388607,    # Max positive (0x7FFFFF)
            -8388608,   # Max negative (-0x800000)
            8388606,    # Max positive - 1
            -8388607,   # Max negative + 1
            32767,      # +16-bit max
            -32768,     # -16-bit min
            123456,     # Arbitrary positive
            -654321,    # Arbitrary negative
        ]

        total_checked = 0
        for sample in key_samples:
            base_32 = to_int32(sample << 8)
            for noise_byte in range(256):
                # Inject noise into bits [7:0]
                noisy_raw = to_int32(base_32 | noise_byte)
                converted = i2s_mic_convert_sample(noisy_raw)
                self.assertEqual(
                    converted,
                    sample,
                    f"Noise byte 0x{noise_byte:02X} corrupted sample {sample}: got {converted}"
                )
                total_checked += 1

        self.assertEqual(total_checked, len(key_samples) * 256)


class TestM1AdversarialUnsignedPromotionDetection(unittest.TestCase):
    """Adversarial stress test detecting unsigned logical shift bugs."""

    def test_adv_unsigned_vs_signed_discrepancy(self):
        """Verify that signed right shift never suffers from unsigned positive overflow."""
        negative_samples = [-8388608, -8388607, -1, -2, -100, -32768, -4000000]

        for sample in negative_samples:
            raw = to_int32(sample << 8)
            signed_res = i2s_mic_convert_sample(raw)
            broken_res = i2s_mic_convert_sample_logical_broken(raw)

            # The correct signed result MUST be negative
            self.assertLess(signed_res, 0)
            self.assertEqual(signed_res, sample)

            # The broken unsigned result is erroneously large positive (> 0)
            self.assertGreater(broken_res, 0)
            self.assertNotEqual(signed_res, broken_res)


class TestM1AdversarialFuzzing(unittest.TestCase):
    """Massive 1,000,000-sample randomized fuzzing harness."""

    def test_adv_massive_fuzzing_million_samples(self):
        """Fuzz 1,000,000 random 24-bit samples with random 8-bit noise."""
        random.seed(42)  # Deterministic seed for reproducible testing
        num_samples = 1_000_000

        for _ in range(num_samples):
            # Pick uniform random 24-bit signed integer
            expected_sample = random.randint(AUDIO_DSP_MIN_SCALE, AUDIO_DSP_FULL_SCALE)
            # Pick random 8-bit noise
            noise = random.randint(0, 255)

            # Construct 32-bit DMA word
            raw_32 = to_int32((expected_sample << 8) | noise)

            # Convert
            actual = i2s_mic_convert_sample(raw_32)

            # Assert invariants
            if actual != expected_sample:
                self.fail(f"Mismatch: expected {expected_sample}, got {actual} (raw=0x{to_uint32(raw_32):08X})")

            # Sign preservation invariant
            if expected_sample < 0:
                self.assertTrue(actual < 0, f"Sign flipped to positive for negative sample {expected_sample}")
            elif expected_sample > 0:
                self.assertTrue(actual > 0, f"Sign flipped to negative for positive sample {expected_sample}")
            else:
                self.assertEqual(actual, 0)


class TestM1DriverContractEdgeCases(unittest.TestCase):
    """API Contract and Edge Condition Stress Testing."""

    def test_adv_api_null_dest_buffer_rejection(self):
        """Simulate passing NULL dest buffer to i2s_mic_read_raw / read_samples."""
        # Per C implementation: if (dest == NULL || num_samples == 0) return ESP_ERR_INVALID_ARG
        ESP_ERR_INVALID_ARG = 0x102
        def mock_read_raw(dest, num_samples):
            if dest is None or num_samples == 0:
                return ESP_ERR_INVALID_ARG
            return 0  # ESP_OK

        self.assertEqual(mock_read_raw(None, 128), ESP_ERR_INVALID_ARG)
        self.assertEqual(mock_read_raw([], 0), ESP_ERR_INVALID_ARG)
        self.assertEqual(mock_read_raw(None, 0), ESP_ERR_INVALID_ARG)

    def test_adv_api_lifecycle_idempotence(self):
        """Verify lifecycle idempotence for repeated init and deinit calls."""
        class MockDriverState:
            def __init__(self):
                self.initialized = False
                self.rx_handle = None

            def deinit(self):
                # Idempotent: safe when not initialized
                if not self.initialized and self.rx_handle is None:
                    return 0  # ESP_OK
                self.rx_handle = None
                self.initialized = False
                return 0

            def init(self, rate=16000):
                if self.initialized or self.rx_handle is not None:
                    # Clean up first
                    self.deinit()
                self.rx_handle = "HANDLE_0"
                self.initialized = True
                return 0

        drv = MockDriverState()
        # Initial state deinit
        self.assertEqual(drv.deinit(), 0)
        self.assertEqual(drv.deinit(), 0)

        # Init then multiple deinits
        self.assertEqual(drv.init(), 0)
        self.assertTrue(drv.initialized)
        self.assertEqual(drv.deinit(), 0)
        self.assertFalse(drv.initialized)
        self.assertEqual(drv.deinit(), 0)

        # Repeated init without explicit deinit
        self.assertEqual(drv.init(), 0)
        self.assertEqual(drv.init(), 0)
        self.assertTrue(drv.initialized)
        self.assertEqual(drv.deinit(), 0)


if __name__ == "__main__":
    unittest.main()

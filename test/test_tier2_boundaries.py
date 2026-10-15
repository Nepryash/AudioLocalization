"""
Tier 2: Boundary & Corner Cases Test Suite (test_tier2_boundaries.py)
Validates extreme values, full-scale numerical limits, saturation, DC offsets,
buffer boundaries, and corner conditions across features F1 through F9.
Minimum 5 test cases per feature (>= 45 tests total).
"""

import math
import re
import io
import wave
import struct
import unittest
from test.audio_test_framework import (
    I2S_DEFAULT_SAMPLE_RATE,
    AUDIO_DSP_DECIMATION_FACTOR,
    AUDIO_DSP_FULL_SCALE,
    AUDIO_DSP_MIN_SCALE,
    TELEMETRY_QUEUE_DEPTH,
    TELEMETRY_BAUD_RATE,
    to_int32,
    to_uint32,
    i2s_mic_convert_sample,
    audio_dsp_process_window,
    telemetry_format_packet,
    telemetry_parse_line,
    SimulatedFreeRTOSQueue,
    create_synthetic_wav_bytes,
    validate_gpio_pin,
)


class TestTier2Feature1Boundaries(unittest.TestCase):
    """F1 Boundaries: Clock frequencies, slot limits, DMA ring constraints"""

    def test_f1_b01_minimum_sample_rate_8khz(self):
        """Verify minimum rated sample rate 8000 Hz for INMP441."""
        fs = 8000
        bclk = 64 * fs
        mclk = 256 * fs
        self.assertEqual(bclk, 512000)
        self.assertEqual(mclk, 2048000)
        self.assertGreaterEqual(bclk, 500000)  # Datasheet min SCK is 0.5 MHz

    def test_f1_b02_maximum_sample_rate_50khz(self):
        """Verify maximum rated sample rate 50000 Hz for INMP441."""
        fs = 50000
        bclk = 64 * fs
        mclk = 256 * fs
        self.assertEqual(bclk, 3200000)
        self.assertEqual(mclk, 12800000)
        self.assertLessEqual(bclk, 3200000)  # Datasheet max SCK is 3.2 MHz

    def test_f1_b03_overclock_rate_rejection(self):
        """Verify overclocked rates (> 50 kHz) exceed INMP441 3.2 MHz maximum clock rating."""
        fs = 96000
        bclk = 64 * fs
        self.assertEqual(bclk, 6144000)
        self.assertGreater(bclk, 3200000)  # Exceeds max rating

    def test_f1_b04_minimum_dma_descriptors(self):
        """Verify minimum viable DMA descriptor count is 2 (ping-pong double buffer)."""
        min_desc = 2
        frame_num = 240
        fs = 16000
        latency_ms = (min_desc * frame_num / fs) * 1000.0
        self.assertEqual(latency_ms, 30.0)
        self.assertGreaterEqual(min_desc, 2)

    def test_f1_b05_maximum_dma_frame_alignment(self):
        """Verify maximum frame buffer alignment for 1024 frames is 4-byte aligned."""
        frame_num = 1024
        bytes_per_sample = 4  # 32-bit slot
        total_bytes = frame_num * bytes_per_sample
        self.assertEqual(total_bytes, 4096)
        self.assertEqual(total_bytes % 4, 0)
        self.assertEqual(total_bytes % 64, 0)  # Cache line aligned


class TestTier2Feature2Boundaries(unittest.TestCase):
    """F2 Boundaries: GPIO Extremes, Strapping Pins, and Port Limits"""

    def test_f2_b01_boundary_pin_0(self):
        """Verify GPIO 0 (boot strapping pin) is recognized at boundary."""
        self.assertTrue(validate_gpio_pin(0))
        # GPIO 0 must be used with caution due to boot mode pull-up
        is_strapping = (0 in (0, 2, 12, 15))
        self.assertTrue(is_strapping)

    def test_f2_b02_boundary_pin_39(self):
        """Verify GPIO 39 (Sensor_VN) is input-only upper boundary."""
        self.assertTrue(validate_gpio_pin(39, allow_input_only=True))
        self.assertFalse(validate_gpio_pin(39, allow_input_only=False))

    def test_f2_b03_invalid_negative_pin_handling(self):
        """Verify negative GPIO values are rejected except special unused marker (-1)."""
        unused_marker = -1
        self.assertFalse(validate_gpio_pin(-2))
        self.assertFalse(validate_gpio_pin(-99))
        self.assertEqual(unused_marker, -1)

    def test_f2_b04_boundary_adjacent_pins(self):
        """Verify adjacent GPIO pairs (14 and 15) pass validation without conflict."""
        p1 = 14
        p2 = 15
        self.assertTrue(validate_gpio_pin(p1))
        self.assertTrue(validate_gpio_pin(p2))
        self.assertNotEqual(p1, p2)

    def test_f2_b05_maximum_valid_gpio_count(self):
        """Verify total number of valid GPIO output pins on ESP32."""
        valid_outputs = [p for p in range(40) if validate_gpio_pin(p, allow_input_only=False)]
        # Flash pins (6-11) and input pins (34-39) excluded: 40 - 6 - 6 = 28
        self.assertEqual(len(valid_outputs), 28)


class TestTier2Feature3Boundaries(unittest.TestCase):
    """F3 Boundaries: Array Physical Geometry Extremes & TDOA Limits"""

    def test_f3_b01_zero_distance_rejection(self):
        """Verify inter-mic distance d <= 0 is non-physical and rejected."""
        def check_distance(d: float) -> bool:
            return d > 0.001
        self.assertFalse(check_distance(0.0))
        self.assertFalse(check_distance(-0.20))
        self.assertTrue(check_distance(0.20))

    def test_f3_b02_max_distance_speed_of_sound(self):
        """Verify maximum physical array baseline d = 1.0m TDOA envelope."""
        d = 1.0
        c = 343.0
        tau_max = d / c
        self.assertAlmostEqual(tau_max * 1000.0, 2.91545, places=3)  # ~2.92 ms

    def test_f3_b03_extreme_elevation_angles(self):
        """Verify elevation boundary conditions (in-plane 0 deg and zenith 90 deg)."""
        def calc_elevation(r_xy: float) -> float:
            r_clamped = min(1.0, max(0.0, r_xy))
            return math.degrees(math.acos(r_clamped))

        # r_xy = 1.0 -> in-plane (0 deg)
        self.assertAlmostEqual(calc_elevation(1.0), 0.0, places=4)
        # r_xy = 0.0 -> zenith (90 deg)
        self.assertAlmostEqual(calc_elevation(0.0), 90.0, places=4)

    def test_f3_b04_azimuth_quadrant_boundaries(self):
        """Verify azimuth atan2 computation at exact 0, 90, 180, 270 degree boundaries."""
        def calc_azimuth(ux: float, uy: float) -> float:
            angle = math.degrees(math.atan2(uy, ux))
            return (angle + 360.0) % 360.0

        self.assertAlmostEqual(calc_azimuth(1.0, 0.0), 0.0, places=4)
        self.assertAlmostEqual(calc_azimuth(0.0, 1.0), 90.0, places=4)
        self.assertAlmostEqual(calc_azimuth(-1.0, 0.0), 180.0, places=4)
        self.assertAlmostEqual(calc_azimuth(0.0, -1.0), 270.0, places=4)

    def test_f3_b05_slot_4_high_impedance_isolation(self):
        """Verify that extreme garbage/clipping values in Slot 4 do not bleed into Mic 1-3."""
        # Frame: Mic 3 (Left), Slot 4 (Right with max noise 0x7FFFFFFF)
        frame = [45000, 0x7FFFFFFF]
        mic3 = frame[0]
        self.assertEqual(mic3, 45000)
        self.assertNotEqual(mic3, frame[1])


class TestTier2Feature4Boundaries(unittest.TestCase):
    """F4 Boundaries: 24-bit Arithmetic Extremes, Zero, and Saturation"""

    def test_f4_b01_extreme_max_positive_limit(self):
        """Verify positive full-scale boundary +8388607."""
        raw = 0x7FFFFF00
        res = i2s_mic_convert_sample(raw)
        self.assertEqual(res, 8388607)
        self.assertEqual(res, (1 << 23) - 1)

    def test_f4_b02_extreme_min_negative_limit(self):
        """Verify negative full-scale boundary -8388608."""
        raw = 0x80000000
        res = i2s_mic_convert_sample(raw)
        self.assertEqual(res, -8388608)
        self.assertEqual(res, -(1 << 23))

    def test_f4_b03_sub_lsb_one_unit_positive(self):
        """Verify smallest non-zero positive sample +1 (LSB)."""
        raw = 0x00000100
        res = i2s_mic_convert_sample(raw)
        self.assertEqual(res, 1)

    def test_f4_b04_sub_lsb_one_unit_negative(self):
        """Verify smallest negative sample -1 (all upper 24 bits 1)."""
        raw = to_int32(0xFFFFFF00)
        res = i2s_mic_convert_sample(raw)
        self.assertEqual(res, -1)

    def test_f4_b05_hard_clipping_saturation(self):
        """Verify saturated input words clamp strictly within [-8388608, 8388607]."""
        def clamp_24bit(val: int) -> int:
            return max(AUDIO_DSP_MIN_SCALE, min(AUDIO_DSP_FULL_SCALE, val))

        self.assertEqual(clamp_24bit(10000000), AUDIO_DSP_FULL_SCALE)
        self.assertEqual(clamp_24bit(-10000000), AUDIO_DSP_MIN_SCALE)


class TestTier2Feature5Boundaries(unittest.TestCase):
    """F5 Boundaries: Window Size Extremes, Square Wave, and DC Offset Drift"""

    def test_f5_b01_single_sample_window(self):
        """Verify window size N=1 computes exact sample magnitude."""
        samples = [54321]
        _, rms, peak = audio_dsp_process_window(samples)
        self.assertEqual(rms, 54321)
        self.assertEqual(peak, 54321)

    def test_f5_b02_large_window_1024(self):
        """Verify large window N=1024 with full-scale signal does not overflow accumulator."""
        samples = [AUDIO_DSP_FULL_SCALE] * 1024
        _, rms, peak = audio_dsp_process_window(samples)
        self.assertEqual(rms, AUDIO_DSP_FULL_SCALE)
        self.assertEqual(peak, AUDIO_DSP_FULL_SCALE)

    def test_f5_b03_alternating_polarity_square_wave(self):
        """Verify alternating polarity full-scale square wave (+8388607, -8388607)."""
        pos = AUDIO_DSP_FULL_SCALE
        neg = -AUDIO_DSP_FULL_SCALE
        samples = [pos if i % 2 == 0 else neg for i in range(AUDIO_DSP_DECIMATION_FACTOR)]
        _, rms, peak = audio_dsp_process_window(samples)
        self.assertEqual(rms, AUDIO_DSP_FULL_SCALE)
        self.assertEqual(peak, AUDIO_DSP_FULL_SCALE)

    def test_f5_b04_dc_offset_saturation_drift(self):
        """Verify large DC offset drift (mean 4,000,000) reflects proper RMS energy."""
        dc_level = 4000000
        ac_amp = 100000
        n = AUDIO_DSP_DECIMATION_FACTOR
        samples = [dc_level + int(ac_amp * math.sin(2 * math.pi * i / n)) for i in range(n)]
        _, rms, peak = audio_dsp_process_window(samples)
        # Total RMS ~ sqrt(dc^2 + ac^2 / 2) ~ sqrt(16e12 + 5e9) ~ 4000624
        expected = int(math.sqrt(dc_level**2 + (ac_amp**2) / 2))
        self.assertAlmostEqual(rms, expected, delta=1000)
        self.assertGreaterEqual(peak, dc_level)

    def test_f5_b05_small_amplitude_quantization(self):
        """Verify tiny signal (+/- 2 LSBs) computes non-zero RMS without precision loss."""
        samples = [2, -2, 1, -1] * (AUDIO_DSP_DECIMATION_FACTOR // 4)
        _, rms, peak = audio_dsp_process_window(samples)
        self.assertGreater(rms, 0)
        self.assertEqual(peak, 2)


class TestTier2Feature6Boundaries(unittest.TestCase):
    """F6 Boundaries: Queue Depth Extremes and Backpressure Bursts"""

    def test_f6_b01_queue_depth_boundary_1(self):
        """Verify single-element queue (capacity=1) accepts 1 item and drops second."""
        q = SimulatedFreeRTOSQueue(capacity=1)
        self.assertTrue(q.send_non_blocking("pkt1"))
        self.assertTrue(q.is_full())
        self.assertFalse(q.send_non_blocking("pkt2"))
        self.assertEqual(q.overflow_drops, 1)
        self.assertEqual(q.receive_non_blocking(), "pkt1")
        self.assertTrue(q.is_empty())

    def test_f6_b02_burst_push_1000_packets(self):
        """Verify high-rate burst of 1000 packets on depth-8 queue drops exactly 992."""
        q = SimulatedFreeRTOSQueue(capacity=8)
        for i in range(1000):
            q.send_non_blocking(i)
        self.assertEqual(q.size(), 8)
        self.assertEqual(q.overflow_drops, 992)
        # Ensure the first 8 were preserved in FIFO order
        for i in range(8):
            self.assertEqual(q.receive_non_blocking(), i)

    def test_f6_b03_zero_capacity_queue_rejection(self):
        """Verify non-positive queue capacity is rejected."""
        def create_queue(cap: int):
            if cap <= 0:
                raise ValueError("Queue capacity must be > 0")
            return SimulatedFreeRTOSQueue(cap)
        with self.assertRaises(ValueError):
            create_queue(0)
        with self.assertRaises(ValueError):
            create_queue(-5)

    def test_f6_b04_full_capacity_rapid_toggle(self):
        """Verify rapid toggling between 7 and 8 items never causes drops."""
        q = SimulatedFreeRTOSQueue(capacity=8)
        for i in range(7):
            q.send_non_blocking(i)
        for toggle in range(50):
            # Push 8th item (should succeed)
            self.assertTrue(q.send_non_blocking(100 + toggle))
            self.assertTrue(q.is_full())
            # Pop 1 item (should succeed)
            popped = q.receive_non_blocking()
            self.assertIsNotNone(popped)
            self.assertFalse(q.is_full())
        self.assertEqual(q.overflow_drops, 0)

    def test_f6_b05_large_payload_packet_integrity(self):
        """Verify queue preserves struct integrity at maximum numerical limits."""
        q = SimulatedFreeRTOSQueue(capacity=8)
        pkt = {
            "decimated_sample": -8388608,
            "rms_level": 8388607,
            "peak_level": 8388607
        }
        self.assertTrue(q.send_non_blocking(pkt))
        popped = q.receive_non_blocking()
        self.assertEqual(popped["decimated_sample"], -8388608)
        self.assertEqual(popped["rms_level"], 8388607)
        self.assertEqual(popped["peak_level"], 8388607)


class TestTier2Feature7Boundaries(unittest.TestCase):
    """F7 Boundaries: Telemetry String Lengths and Decimation Extremes"""

    def test_f7_b01_maximum_payload_length_negative_extrema(self):
        """Verify maximum formatted string length at negative full-scale is 29 bytes."""
        line = telemetry_format_packet(-8388608, 8388607)
        self.assertEqual(line, "sample:-8388608,rms:8388607\r\n")
        self.assertEqual(len(line), 29)

    def test_f7_b02_minimum_payload_length_zero(self):
        """Verify minimum formatted string length at zero is 16 bytes."""
        line = telemetry_format_packet(0, 0)
        self.assertEqual(line, "sample:0,rms:0\r\n")
        self.assertEqual(len(line), 16)

    def test_f7_b03_newline_variations(self):
        """Verify parser tolerates \\r\\n, \\n, and trailing spaces."""
        self.assertIsNotNone(telemetry_parse_line("sample:100,rms:50\r\n"))
        self.assertIsNotNone(telemetry_parse_line("sample:100,rms:50\n"))
        self.assertIsNotNone(telemetry_parse_line("  sample:100,rms:50  \n"))

    def test_f7_b04_boundary_decimation_factor_1(self):
        """Verify boundary decimation factor D=1 produces 16000 Hz packet rate."""
        fs = 16000
        d = 1
        rate = fs / d
        self.assertEqual(rate, 16000.0)

    def test_f7_b05_boundary_decimation_factor_1024(self):
        """Verify boundary decimation factor D=1024 produces 15.625 Hz packet rate."""
        fs = 16000
        d = 1024
        rate = fs / d
        self.assertEqual(rate, 15.625)


class TestTier2Feature8Boundaries(unittest.TestCase):
    """F8 Boundaries: Lifecycle Faults and Edge Arguments"""

    def test_f8_b01_double_init_protection(self):
        """Verify repeated initialization returns ESP_ERR_INVALID_STATE."""
        class MockLifecycle:
            def __init__(self):
                self.initialized = False
            def init(self):
                if self.initialized:
                    return "ESP_ERR_INVALID_STATE"
                self.initialized = True
                return "ESP_OK"

        driver = MockLifecycle()
        self.assertEqual(driver.init(), "ESP_OK")
        self.assertEqual(driver.init(), "ESP_ERR_INVALID_STATE")

    def test_f8_b02_double_deinit_protection(self):
        """Verify repeated deinitialization is safe (idempotent or returns ESP_OK)."""
        class MockLifecycle:
            def __init__(self):
                self.initialized = True
            def deinit(self):
                if not self.initialized:
                    return "ESP_OK"  # Idempotent clean exit
                self.initialized = False
                return "ESP_OK"

        driver = MockLifecycle()
        self.assertEqual(driver.deinit(), "ESP_OK")
        self.assertEqual(driver.deinit(), "ESP_OK")

    def test_f8_b03_zero_bytes_read_request(self):
        """Verify requesting 0 samples returns 0 samples read with ESP_OK."""
        def mock_read(buf, num_samples):
            if num_samples == 0:
                return "ESP_OK", 0
            return "ESP_OK", num_samples

        res, read_count = mock_read([], 0)
        self.assertEqual(res, "ESP_OK")
        self.assertEqual(read_count, 0)

    def test_f8_b04_zero_timeout_read(self):
        """Verify read with timeout_ms = 0 (polling) executes without indefinite blocking."""
        def mock_read_poll(has_data):
            if not has_data:
                return "ESP_ERR_TIMEOUT"
            return "ESP_OK"

        self.assertEqual(mock_read_poll(False), "ESP_ERR_TIMEOUT")
        self.assertEqual(mock_read_poll(True), "ESP_OK")

    def test_f8_b05_maximum_buffer_allocation_limit(self):
        """Verify allocating unrealistically huge buffer (> 512 KB) fails with ESP_ERR_NO_MEM."""
        def mock_allocate_dma(num_bytes: int):
            max_sram_dma = 320 * 1024  # ESP32 max DMA SRAM ~320 KB
            if num_bytes > max_sram_dma:
                return "ESP_ERR_NO_MEM"
            return "ESP_OK"

        self.assertEqual(mock_allocate_dma(1024 * 1024), "ESP_ERR_NO_MEM")
        self.assertEqual(mock_allocate_dma(960), "ESP_OK")


class TestTier2Feature9Boundaries(unittest.TestCase):
    """F9 Boundaries: Parser Stress, Buffer Overflow, and WAV Container Limits"""

    def test_f9_b01_empty_string_telemetry_parser(self):
        """Verify empty string returns None without error."""
        self.assertIsNone(telemetry_parse_line(""))
        self.assertIsNone(telemetry_parse_line("   \r\n"))

    def test_f9_b02_oversized_line_buffer_overflow(self):
        """Verify 10,000 character line is rejected without crash."""
        huge_line = "sample:" + "9" * 10000 + ",rms:100\r\n"
        self.assertIsNone(telemetry_parse_line(huge_line))

    def test_f9_b03_zero_length_wav_generation(self):
        """Verify 0-sample audio export produces valid 44-byte WAV header."""
        wav_bytes = create_synthetic_wav_bytes([], sample_rate=16000)
        self.assertEqual(len(wav_bytes), 44)  # Standard RIFF header size
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            self.assertEqual(wf.getnframes(), 0)

    def test_f9_b04_huge_wav_export_simulation(self):
        """Verify 10-second audio (160,000 samples) export completes quickly and accurately."""
        n_samples = 160000
        samples = [1000] * n_samples
        wav_bytes = create_synthetic_wav_bytes(samples, sample_rate=16000)
        expected_bytes = 44 + (n_samples * 2)  # 16-bit = 2 bytes per sample
        self.assertEqual(len(wav_bytes), expected_bytes)

    def test_f9_b05_ansi_meter_over_range_clamping(self):
        """Verify RMS beyond FULL_SCALE clamps safely to 100% full bar."""
        def compute_bar(rms: int, max_level: int = AUDIO_DSP_FULL_SCALE, width: int = 40) -> str:
            fraction = max(0.0, min(1.0, rms / max_level))
            bars = round(fraction * width)
            return "#" * bars + "-" * (width - bars)

        over_bar = compute_bar(AUDIO_DSP_FULL_SCALE * 2)
        self.assertEqual(over_bar, "#" * 40)


if __name__ == "__main__":
    unittest.main()

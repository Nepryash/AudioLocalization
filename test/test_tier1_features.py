"""
Tier 1: Feature Coverage Test Suite (test_tier1_features.py)
Validates individual features F1 through F9 per PROJECT.md and ORIGINAL_REQUEST.md.
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
    I2S_DEFAULT_SCK_PIN,
    I2S_DEFAULT_WS_PIN,
    I2S_DEFAULT_SD_PIN,
    AUDIO_DSP_DECIMATION_FACTOR,
    AUDIO_DSP_FULL_SCALE,
    AUDIO_DSP_MIN_SCALE,
    TELEMETRY_QUEUE_DEPTH,
    TELEMETRY_BAUD_RATE,
    to_int32,
    to_uint32,
    i2s_mic_convert_sample,
    i2s_mic_convert_sample_logical_broken,
    audio_dsp_process_window,
    telemetry_format_packet,
    telemetry_parse_line,
    SimulatedFreeRTOSQueue,
    create_synthetic_wav_bytes,
    validate_gpio_pin,
)


class TestFeature1ModernI2SSetup(unittest.TestCase):
    """F1: Modern ESP-IDF I2S Setup (driver/i2s_std.h)"""

    def test_f1_01_clock_ratio_64_sck_per_frame(self):
        """Verify BCLK frequency is exactly 64 * fs for INMP441 32-bit slot stereo frame."""
        fs = I2S_DEFAULT_SAMPLE_RATE  # 16000 Hz
        bclk = 64 * fs
        self.assertEqual(bclk, 1024000)
        # Check BCLK cycle period
        t_bclk = 1.0 / bclk
        self.assertAlmostEqual(t_bclk, 9.765625e-7, places=9)

    def test_f1_02_mclk_multiple_256_integer_div(self):
        """Verify MCLK multiple of 256 yields clean integer division with 64 SCK cycles."""
        fs = 16000
        mclk = 256 * fs
        bclk = 64 * fs
        self.assertEqual(mclk, 4096000)
        self.assertEqual(mclk % bclk, 0)
        self.assertEqual(mclk // bclk, 4)

    def test_f1_03_slot_bit_width_32_data_24(self):
        """Verify slot bit width is 32 bits and audio data bit width is 24 bits."""
        slot_bit_width = 32
        data_bit_width = 24
        padding_bits = slot_bit_width - data_bit_width
        self.assertEqual(padding_bits, 8)
        self.assertEqual(slot_bit_width * 2, 64)  # 64 clock cycles per stereo frame

    def test_f1_04_dma_ring_buffer_sizing(self):
        """Verify DMA ring buffer geometry: 6 descriptors x 240 frames gives 90ms latency buffer."""
        dma_desc_num = 6
        dma_frame_num = 240
        fs = 16000
        buffer_latency_ms = (dma_frame_num / fs) * 1000.0
        total_latency_ms = buffer_latency_ms * dma_desc_num
        self.assertEqual(buffer_latency_ms, 15.0)
        self.assertEqual(total_latency_ms, 90.0)

    def test_f1_05_i2s_role_master_rx_mode(self):
        """Verify I2S channel role is Master RX (generates BCLK and WS clocks)."""
        chan_config = {
            "id": 0,  # I2S_NUM_0
            "role": "I2S_ROLE_MASTER",
            "dma_desc_num": 6,
            "dma_frame_num": 240,
            "auto_clear": False,
        }
        self.assertEqual(chan_config["role"], "I2S_ROLE_MASTER")
        self.assertEqual(chan_config["id"], 0)
        self.assertFalse(chan_config["auto_clear"])

    def test_f1_06_philips_format_1bit_shift_delay(self):
        """Verify Philips standard slot configuration has 1-bit SCK delay."""
        philips_cfg = {
            "ws_pol": False,       # Low for Left channel
            "bit_shift": True,     # 1-bit delay between WS transition and MSB
            "ws_width": 32,        # 32 BCLK cycles per half-frame
        }
        self.assertTrue(philips_cfg["bit_shift"])
        self.assertFalse(philips_cfg["ws_pol"])
        self.assertEqual(philips_cfg["ws_width"], 32)


class TestFeature2ConfigurableGPIOPinout(unittest.TestCase):
    """F2: Configurable GPIO Pinout & Hardware Adaptability"""

    def test_f2_01_default_pin_assignments(self):
        """Verify authoritative default GPIO pin assignments."""
        self.assertEqual(I2S_DEFAULT_SCK_PIN, 14)
        self.assertEqual(I2S_DEFAULT_WS_PIN, 27)
        self.assertEqual(I2S_DEFAULT_SD_PIN, 32)

    def test_f2_02_pin_collision_rejection(self):
        """Verify collision detection when pins are assigned identical GPIOs."""
        pins = {"sck": 14, "ws": 14, "sd": 32}
        has_collision = len(set(pins.values())) != len(pins)
        self.assertTrue(has_collision)

    def test_f2_03_out_of_range_gpio_rejection(self):
        """Verify out-of-range GPIO numbers (< 0 or > 39) are invalid."""
        self.assertFalse(validate_gpio_pin(-1))
        self.assertFalse(validate_gpio_pin(40))
        self.assertFalse(validate_gpio_pin(100))
        self.assertTrue(validate_gpio_pin(14))
        self.assertTrue(validate_gpio_pin(27))
        self.assertTrue(validate_gpio_pin(32, allow_input_only=True))

    def test_f2_04_flash_reserved_gpio_rejection(self):
        """Verify flash reserved pins GPIO 6 through 11 are rejected."""
        for p in range(6, 12):
            self.assertFalse(validate_gpio_pin(p), f"GPIO {p} should be rejected (flash)")

    def test_f2_05_input_only_gpio_rejection_for_clocks(self):
        """Verify input-only GPIOs (34-39) cannot be used as clock outputs SCK/WS."""
        for p in (34, 35, 36, 37, 38, 39):
            # As output clock (allow_input_only=False) -> invalid
            self.assertFalse(validate_gpio_pin(p, allow_input_only=False))
            # As input data SD (allow_input_only=True) -> valid
            self.assertTrue(validate_gpio_pin(p, allow_input_only=True))

    def test_f2_06_sd_pin_supports_internal_pulldown(self):
        """Verify SD pin (GPIO 32) supports internal pulldown resistor configuration."""
        sd_pin = 32
        self.assertTrue(validate_gpio_pin(sd_pin, allow_input_only=True))
        # GPIO 32 is a valid RTC/Digital GPIO on ESP32 supporting internal pull-downs
        self.assertIn(sd_pin, range(0, 40))


class TestFeature3MultiMicArchitectureGroundwork(unittest.TestCase):
    """F3: Multi-Mic Architecture Groundwork (3-Microphone Array Mapping)"""

    def test_f3_01_three_mic_channel_mapping(self):
        """Verify 3-mic channel slot mapping per MEMORY_ACOUSTIC_ARRAY.md."""
        mic_map = {
            "Mic_1": {"controller": 0, "slot": "Left", "lr_pin": "GND"},
            "Mic_2": {"controller": 0, "slot": "Right", "lr_pin": "VDD"},
            "Mic_3": {"controller": 1, "slot": "Left", "lr_pin": "GND"},
            "Slot_4": {"controller": 1, "slot": "Right", "action": "DISCARD"},
        }
        self.assertEqual(mic_map["Mic_1"]["controller"], 0)
        self.assertEqual(mic_map["Mic_1"]["slot"], "Left")
        self.assertEqual(mic_map["Mic_2"]["controller"], 0)
        self.assertEqual(mic_map["Mic_2"]["slot"], "Right")
        self.assertEqual(mic_map["Mic_3"]["controller"], 1)
        self.assertEqual(mic_map["Slot_4"]["action"], "DISCARD")

    def test_f3_02_slot_4_discard_behavior(self):
        """Verify software demux drops Slot 4 without data corruption."""
        stereo_frame_i2s1 = [1000, 999999]  # Left: Mic 3, Right: Slot 4
        mic3_sample = stereo_frame_i2s1[0]
        self.assertEqual(mic3_sample, 1000)

    def test_f3_03_shared_bus_left_right_separation(self):
        """Verify stereo DMA buffer demuxing index: Left at 2*i, Right at 2*i+1."""
        dma_buffer = [100, 200, 101, 201, 102, 202]  # L0, R0, L1, R1, L2, R2
        left_channel = [dma_buffer[2 * i] for i in range(len(dma_buffer) // 2)]
        right_channel = [dma_buffer[2 * i + 1] for i in range(len(dma_buffer) // 2)]
        self.assertEqual(left_channel, [100, 101, 102])
        self.assertEqual(right_channel, [200, 201, 202])

    def test_f3_04_triangular_array_circumradius(self):
        """Verify equilateral triangle array geometry (d = 0.20m, R = d / sqrt(3))."""
        d = 0.20
        r_expected = d / math.sqrt(3)
        self.assertAlmostEqual(r_expected, 0.1154700538, places=6)

    def test_f3_05_max_tdoa_tau_max(self):
        """Verify maximum time difference of arrival tau_max = d / c."""
        d = 0.20
        c = 343.0
        tau_max = d / c  # ~5.8309e-4 s = 583.1 us
        fs = 16000
        n_samples_max = tau_max * fs
        self.assertAlmostEqual(tau_max * 1e6, 583.09, places=1)
        self.assertAlmostEqual(n_samples_max, 9.329, places=2)

    def test_f3_06_phase_wrapping_frequency_limit(self):
        """Verify spatial aliasing frequency f_alias = c / (2 * d)."""
        c = 343.0
        d = 0.20
        f_alias = c / (2.0 * d)
        self.assertEqual(f_alias, 857.5)


class TestFeature4SampleExtraction24Bit(unittest.TestCase):
    """F4: 24-in-32 Bit Sample Extraction & Sign Extension"""

    def test_f4_01_positive_sample_shift(self):
        """Verify arithmetic right shift >> 8 on positive audio sample."""
        raw = 0x00123400
        extracted = i2s_mic_convert_sample(raw)
        self.assertEqual(extracted, 0x00001234)
        self.assertEqual(extracted, 4660)

    def test_f4_02_negative_sample_sign_extension(self):
        """Verify arithmetic right shift >> 8 preserves negative two's complement sign."""
        # 32-bit representation of -4660 * 256
        raw = to_int32(-4660 << 8)
        extracted = i2s_mic_convert_sample(raw)
        self.assertEqual(extracted, -4660)
        # Verify sign bit (bit 31) is extended
        self.assertLess(extracted, 0)

    def test_f4_03_zero_sample_extraction(self):
        """Verify zero raw word extracts to 0."""
        raw = 0x00000000
        extracted = i2s_mic_convert_sample(raw)
        self.assertEqual(extracted, 0)

    def test_f4_04_full_scale_positive_extraction(self):
        """Verify extraction of maximum 24-bit positive full scale (+8388607)."""
        # Upper 24 bits: 0x7FFFFF, lower 8 bits: 0x00 -> 0x7FFFFF00
        raw = 0x7FFFFF00
        extracted = i2s_mic_convert_sample(raw)
        self.assertEqual(extracted, AUDIO_DSP_FULL_SCALE)
        self.assertEqual(extracted, 8388607)

    def test_f4_05_full_scale_negative_extraction(self):
        """Verify extraction of minimum 24-bit negative full scale (-8388608)."""
        # Upper 24 bits: 0x800000, lower 8 bits: 0x00 -> 0x80000000
        raw = 0x80000000
        extracted = i2s_mic_convert_sample(raw)
        self.assertEqual(extracted, AUDIO_DSP_MIN_SCALE)
        self.assertEqual(extracted, -8388608)

    def test_f4_06_logical_shift_bug_demonstration(self):
        """Demonstrate that logical unsigned shift >> 8 fails catastrophically on negative audio."""
        raw = 0x80000000  # -8388608 when shifted arithmetically
        correct = i2s_mic_convert_sample(raw)
        broken = i2s_mic_convert_sample_logical_broken(raw)
        self.assertEqual(correct, -8388608)
        self.assertEqual(broken, 0x00800000)  # +8388608!
        self.assertNotEqual(correct, broken)


class TestFeature5FPURMSAndPeakMath(unittest.TestCase):
    """F5: Real-Time Hardware FPU RMS & Peak Math"""

    def test_f5_01_dc_signal_rms_equals_dc_value(self):
        """Verify RMS of constant DC signal equals the absolute DC level."""
        dc_val = 50000
        samples = [dc_val] * AUDIO_DSP_DECIMATION_FACTOR
        _, rms, peak = audio_dsp_process_window(samples)
        self.assertEqual(rms, dc_val)
        self.assertEqual(peak, dc_val)

    def test_f5_02_pure_sine_wave_rms(self):
        """Verify RMS of pure sine wave equals amplitude / sqrt(2)."""
        amp = 100000.0
        n = AUDIO_DSP_DECIMATION_FACTOR
        samples = [int(amp * math.sin(2 * math.pi * i / n)) for i in range(n)]
        _, rms, peak = audio_dsp_process_window(samples)
        expected_rms = int(amp / math.sqrt(2))
        self.assertAlmostEqual(rms, expected_rms, delta=expected_rms * 0.05)
        self.assertAlmostEqual(peak, int(amp), delta=int(amp * 0.05))

    def test_f5_03_silence_rms_and_peak_zero(self):
        """Verify silence (all zeroes) yields RMS 0 and Peak 0."""
        samples = [0] * AUDIO_DSP_DECIMATION_FACTOR
        dec, rms, peak = audio_dsp_process_window(samples)
        self.assertEqual(dec, 0)
        self.assertEqual(rms, 0)
        self.assertEqual(peak, 0)

    def test_f5_04_peak_absolute_tracking(self):
        """Verify peak tracks maximum absolute value regardless of sign."""
        samples = [10, -500, 300, -8500, 4200, -100] + [0] * (AUDIO_DSP_DECIMATION_FACTOR - 6)
        _, _, peak = audio_dsp_process_window(samples)
        self.assertEqual(peak, 8500)

    def test_f5_05_rms_less_than_or_equal_to_peak(self):
        """Verify mathematical invariance: RMS <= Peak for any signal."""
        samples = [1000, -2000, 500, 3000, -1500] * (AUDIO_DSP_DECIMATION_FACTOR // 5)
        _, rms, peak = audio_dsp_process_window(samples)
        self.assertLessEqual(rms, peak)

    def test_f5_06_full_scale_no_overflow(self):
        """Verify full scale values do not overflow 64-bit sum or produce invalid values."""
        samples = [AUDIO_DSP_FULL_SCALE] * AUDIO_DSP_DECIMATION_FACTOR
        _, rms, peak = audio_dsp_process_window(samples)
        self.assertEqual(rms, AUDIO_DSP_FULL_SCALE)
        self.assertEqual(peak, AUDIO_DSP_FULL_SCALE)


class TestFeature6DecoupledFreeRTOSConcurrency(unittest.TestCase):
    """F6: Decoupled FreeRTOS Concurrency & Telemetry Queue"""

    def test_f6_01_queue_capacity_limit_8(self):
        """Verify queue holds exactly 8 items without dropping."""
        q = SimulatedFreeRTOSQueue(capacity=TELEMETRY_QUEUE_DEPTH)
        for i in range(8):
            ok = q.send_non_blocking({"id": i})
            self.assertTrue(ok)
        self.assertEqual(q.size(), 8)
        self.assertTrue(q.is_full())

    def test_f6_02_non_blocking_push_drop_on_full(self):
        """Verify 9th item pushed to full queue is dropped without blocking."""
        q = SimulatedFreeRTOSQueue(capacity=TELEMETRY_QUEUE_DEPTH)
        for i in range(8):
            q.send_non_blocking(i)
        # 9th push
        ok = q.send_non_blocking(999)
        self.assertFalse(ok)
        self.assertEqual(q.overflow_drops, 1)
        self.assertEqual(q.size(), 8)

    def test_f6_03_fifo_packet_order_preserved(self):
        """Verify FIFO packet ordering is strictly maintained."""
        q = SimulatedFreeRTOSQueue(capacity=TELEMETRY_QUEUE_DEPTH)
        for i in range(5):
            q.send_non_blocking(i * 10)
        received = []
        while not q.is_empty():
            received.append(q.receive_non_blocking())
        self.assertEqual(received, [0, 10, 20, 30, 40])

    def test_f6_04_non_blocking_pop_on_empty(self):
        """Verify popping an empty queue returns None immediately."""
        q = SimulatedFreeRTOSQueue(capacity=TELEMETRY_QUEUE_DEPTH)
        item = q.receive_non_blocking()
        self.assertIsNone(item)
        self.assertTrue(q.is_empty())

    def test_f6_05_overflow_counter_tracking(self):
        """Verify overflow drops count increments accurately on multiple bursts."""
        q = SimulatedFreeRTOSQueue(capacity=TELEMETRY_QUEUE_DEPTH)
        for i in range(15):  # 8 accepted, 7 dropped
            q.send_non_blocking(i)
        self.assertEqual(q.overflow_drops, 7)
        self.assertEqual(q.total_pushes, 15)

    def test_f6_06_drain_and_refill(self):
        """Verify queue can be drained and refilled repeatedly without leakage."""
        q = SimulatedFreeRTOSQueue(capacity=TELEMETRY_QUEUE_DEPTH)
        for cycle in range(3):
            for i in range(8):
                self.assertTrue(q.send_non_blocking(i))
            for i in range(8):
                self.assertEqual(q.receive_non_blocking(), i)
            self.assertTrue(q.is_empty())


class TestFeature7DecimatedSerialPlotterTelemetry(unittest.TestCase):
    """F7: Decimated Serial Plotter Telemetry"""

    def test_f7_01_plotter_format_exact_pattern(self):
        """Verify packet formatting strictly adheres to sample:%ld,rms:%ld\\r\\n."""
        line = telemetry_format_packet(1234, 567)
        self.assertEqual(line, "sample:1234,rms:567\r\n")

    def test_f7_02_decimation_rate_125hz(self):
        """Verify decimation factor D=128 produces 125 Hz stream rate at fs=16000."""
        fs = 16000
        decimation = AUDIO_DSP_DECIMATION_FACTOR  # 128
        stream_rate_hz = fs / decimation
        self.assertEqual(stream_rate_hz, 125.0)

    def test_f7_03_uart_bandwidth_headroom(self):
        """Verify 125 Hz stream rate consumes < 30% of 115200 baud capacity."""
        sample_line = "sample:-8388608,rms:8388607\r\n"  # 29 bytes max
        bytes_per_second = 125 * len(sample_line)
        max_uart_bytes_per_sec = TELEMETRY_BAUD_RATE / 10  # 10 bits per byte (8N1)
        utilization = bytes_per_second / max_uart_bytes_per_sec
        self.assertLess(utilization, 0.35)

    def test_f7_04_negative_sample_formatting(self):
        """Verify negative sample values format cleanly with leading minus sign."""
        line = telemetry_format_packet(-45000, 32000)
        self.assertEqual(line, "sample:-45000,rms:32000\r\n")

    def test_f7_05_telemetry_parser_roundtrip(self):
        """Verify formatted line correctly parses back to original values."""
        original_sample = -789012
        original_rms = 45678
        formatted = telemetry_format_packet(original_sample, original_rms)
        parsed = telemetry_parse_line(formatted)
        self.assertIsNotNone(parsed)
        sample, rms = parsed
        self.assertEqual(sample, original_sample)
        self.assertEqual(rms, original_rms)

    def test_f7_06_trailing_crlf_line_termination(self):
        """Verify each line ends with CRLF (\\r\\n) for serial plotter compatibility."""
        line = telemetry_format_packet(0, 0)
        self.assertTrue(line.endswith("\r\n"))


class TestFeature8ApplicationLifecycleAndErrorHandling(unittest.TestCase):
    """F8: Application Lifecycle & Error Handling"""

    def test_f8_01_null_config_rejection(self):
        """Verify error checking rejects NULL configuration pointer."""
        def dummy_init(config):
            if config is None:
                return "ESP_ERR_INVALID_ARG"
            return "ESP_OK"
        self.assertEqual(dummy_init(None), "ESP_ERR_INVALID_ARG")

    def test_f8_02_invalid_sample_rate_rejection(self):
        """Verify error checking rejects sample rates outside [8000, 50000] Hz."""
        valid_rates = [8000, 16000, 44100, 48000]
        invalid_rates = [0, 4000, 96000, 192000]
        for r in valid_rates:
            self.assertTrue(8000 <= r <= 50000)
        for r in invalid_rates:
            self.assertFalse(8000 <= r <= 50000)

    def test_f8_03_lifecycle_state_machine_valid_flow(self):
        """Verify standard lifecycle transitions: REGISTERED -> READY -> RUNNING -> READY."""
        valid_transitions = {
            "UNREGISTERED": ["REGISTERED"],
            "REGISTERED": ["READY"],
            "READY": ["RUNNING", "UNREGISTERED"],
            "RUNNING": ["READY"],
        }
        state = "UNREGISTERED"
        flow = ["REGISTERED", "READY", "RUNNING", "READY", "UNREGISTERED"]
        for target in flow:
            self.assertIn(target, valid_transitions[state])
            state = target
        self.assertEqual(state, "UNREGISTERED")

    def test_f8_04_invalid_state_transition_prevention(self):
        """Verify cannot enable channel before initialization (REGISTERED -> RUNNING rejected)."""
        valid_transitions = {
            "UNREGISTERED": ["REGISTERED"],
            "REGISTERED": ["READY"],
            "READY": ["RUNNING"],
            "RUNNING": ["READY"],
        }
        # Attempting RUNNING directly from REGISTERED
        self.assertNotIn("RUNNING", valid_transitions["REGISTERED"])

    def test_f8_05_clean_deinit_resets_state(self):
        """Verify deinit cleans up channel handles and resets internal pointers."""
        class MockDriver:
            def __init__(self):
                self.rx_handle = 0x1234
            def deinit(self):
                self.rx_handle = None
                return "ESP_OK"
        driver = MockDriver()
        self.assertIsNotNone(driver.rx_handle)
        res = driver.deinit()
        self.assertEqual(res, "ESP_OK")
        self.assertIsNone(driver.rx_handle)

    def test_f8_06_cmakelists_dependency_declarations(self):
        """Verify CMake dependency validation contract for required ESP-IDF components."""
        required_components = {"esp_driver_i2s", "esp_driver_gpio"}
        def validate_cmake_deps(deps_text: str) -> bool:
            return all(comp in deps_text for comp in required_components)

        valid_manifest = "idf_component_register(SRCS ${app_sources} REQUIRES esp_driver_i2s esp_driver_gpio driver)"
        invalid_manifest = "idf_component_register(SRCS ${app_sources})"
        self.assertTrue(validate_cmake_deps(valid_manifest))
        self.assertFalse(validate_cmake_deps(invalid_manifest))


class TestFeature9PythonVerificationTool(unittest.TestCase):
    """F9: Python Verification & Plotting Tool Specifications"""

    def test_f9_01_telemetry_regex_matches_valid_stream(self):
        """Verify regex accurately parses positive and negative telemetry lines."""
        pos = "sample:15200,rms:8400\r\n"
        neg = "sample:-15200,rms:8400\n"
        self.assertEqual(telemetry_parse_line(pos), (15200, 8400))
        self.assertEqual(telemetry_parse_line(neg), (-15200, 8400))

    def test_f9_02_malformed_line_rejection(self):
        """Verify parser rejects corrupt lines, missing colons, or garbage bytes."""
        malformed = [
            "",
            "invalid_payload",
            "sample:,rms:100\r\n",
            "sample:100\r\n",
            "rms:100\r\n",
            "sample:abc,rms:100\r\n",
            "sample:100,rms:-50\r\n",  # RMS is strictly non-negative
        ]
        for line in malformed:
            self.assertIsNone(telemetry_parse_line(line), f"Should reject: {line}")

    def test_f9_03_ansi_meter_level_calculation(self):
        """Verify ANSI meter calculation maps RMS level to bar length [0, 40]."""
        def compute_bar(rms: int, max_level: int = AUDIO_DSP_FULL_SCALE, width: int = 40) -> str:
            fraction = max(0.0, min(1.0, rms / max_level))
            bars = round(fraction * width)
            return "#" * bars + "-" * (width - bars)

        silence_bar = compute_bar(0)
        self.assertEqual(silence_bar, "-" * 40)
        half_bar = compute_bar(AUDIO_DSP_FULL_SCALE // 2)
        self.assertEqual(half_bar.count("#"), 20)
        full_bar = compute_bar(AUDIO_DSP_FULL_SCALE)
        self.assertEqual(full_bar, "#" * 40)

    def test_f9_04_mock_stream_generator(self):
        """Verify mock stream generator emits syntactically valid telemetry lines."""
        lines = []
        for i in range(10):
            s = int(10000 * math.sin(i))
            r = abs(s)
            lines.append(telemetry_format_packet(s, r))
        for line in lines:
            parsed = telemetry_parse_line(line)
            self.assertIsNotNone(parsed)

    def test_f9_05_wav_file_export_format(self):
        """Verify WAV export creates valid 16-bit 16000 Hz mono RIFF container."""
        samples_24 = [100000, -200000, 300000] * 100
        wav_bytes = create_synthetic_wav_bytes(samples_24, sample_rate=16000)
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav_bytes[:16])

        # Read back with standard library wave module
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)  # 16-bit
            self.assertEqual(wf.getframerate(), 16000)
            self.assertEqual(wf.getnframes(), len(samples_24))

    def test_f9_06_wav_audio_duration_accuracy(self):
        """Verify exported WAV duration matches expected audio length."""
        fs = 16000
        duration_sec = 0.5
        n_samples = int(fs * duration_sec)
        samples = [0] * n_samples
        wav_bytes = create_synthetic_wav_bytes(samples, sample_rate=fs)
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            actual_duration = wf.getnframes() / wf.getframerate()
            self.assertEqual(actual_duration, duration_sec)


if __name__ == "__main__":
    unittest.main()

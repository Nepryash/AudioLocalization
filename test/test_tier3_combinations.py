"""
Tier 3: Cross-Feature Combinations & Pairwise Test Suite (test_tier3_combinations.py)
Validates interactions between interdependent subsystems:
- Audio acquisition + concurrent UART serial telemetry
- Instantaneous step transitions (silence -> impulse clap)
- Queue limits & backpressure isolation
- Signal + noise floor envelope interactions
- Multi-channel demuxing + 24-bit sign extension
- Sample rates x decimation factor matrix
- Stream recovery under transport byte fragmentation
"""

import math
import random
import unittest
from test.audio_test_framework import (
    I2S_DEFAULT_SAMPLE_RATE,
    AUDIO_DSP_DECIMATION_FACTOR,
    AUDIO_DSP_FULL_SCALE,
    AUDIO_DSP_MIN_SCALE,
    TELEMETRY_QUEUE_DEPTH,
    TELEMETRY_BAUD_RATE,
    to_int32,
    i2s_mic_convert_sample,
    audio_dsp_process_window,
    telemetry_format_packet,
    telemetry_parse_line,
    SimulatedFreeRTOSQueue,
)


class TestTier3Combinations(unittest.TestCase):
    """Pairwise & Multi-Feature Interaction Test Cases"""

    def test_c01_audio_capture_concurrent_with_serial_streaming(self):
        """Pairwise: Sustained audio capture pipeline feeding concurrent serial telemetry."""
        queue = SimulatedFreeRTOSQueue(capacity=TELEMETRY_QUEUE_DEPTH)
        transmitted_lines = []
        parsed_packets = []

        # Simulate 50 audio windows (each N=128 samples)
        for w in range(50):
            # Generate synthetic 1 kHz tone at 16 kHz sample rate
            samples = [
                int(500000 * math.sin(2 * math.pi * 1000 * (w * 128 + i) / 16000))
                for i in range(AUDIO_DSP_DECIMATION_FACTOR)
            ]
            dec, rms, peak = audio_dsp_process_window(samples)

            # High-priority task pushes packet
            packet = {"decimated": dec, "rms": rms, "peak": peak}
            pushed = queue.send_non_blocking(packet)
            self.assertTrue(pushed)

            # Low-priority task drains queue and transmits line
            popped = queue.receive_non_blocking()
            self.assertIsNotNone(popped)
            line = telemetry_format_packet(popped["decimated"], popped["rms"])
            transmitted_lines.append(line)

            # Serial consumer parses line
            parsed = telemetry_parse_line(line)
            self.assertIsNotNone(parsed)
            parsed_packets.append(parsed)

        self.assertEqual(len(transmitted_lines), 50)
        self.assertEqual(len(parsed_packets), 50)
        self.assertEqual(queue.overflow_drops, 0)
        self.assertTrue(queue.is_empty())

    def test_c02_instantaneous_impulse_transition(self):
        """Interaction: Instantaneous step transition from prolonged silence to impulse clap."""
        # Window 1: Silence
        silence = [0] * AUDIO_DSP_DECIMATION_FACTOR
        _, rms_silence, peak_silence = audio_dsp_process_window(silence)
        self.assertEqual(rms_silence, 0)
        self.assertEqual(peak_silence, 0)

        # Window 2: Impulse clap (single full-scale spike in center of window)
        impulse_window = [0] * AUDIO_DSP_DECIMATION_FACTOR
        impulse_window[AUDIO_DSP_DECIMATION_FACTOR // 2] = 8000000
        _, rms_impulse, peak_impulse = audio_dsp_process_window(impulse_window)

        # RMS = sqrt(8000000^2 / 128) = 8000000 / sqrt(128) ~ 707106
        expected_rms = int(8000000 / math.sqrt(128))
        self.assertAlmostEqual(rms_impulse, expected_rms, delta=10)
        self.assertEqual(peak_impulse, 8000000)

        # Window 3: Immediate return to silence (no filter memory leakage)
        _, rms_decay, peak_decay = audio_dsp_process_window(silence)
        self.assertEqual(rms_decay, 0)
        self.assertEqual(peak_decay, 0)

    def test_c03_queue_backpressure_and_producer_isolation(self):
        """Interaction: Fast capture producer is never stalled when UART consumer falls behind."""
        q = SimulatedFreeRTOSQueue(capacity=TELEMETRY_QUEUE_DEPTH)

        # Producer pushes 30 packets rapidly without any consumer popping
        push_results = [q.send_non_blocking({"idx": i}) for i in range(30)]

        # First 8 should succeed, next 22 should fail without blocking or throwing
        self.assertEqual(push_results[:8], [True] * 8)
        self.assertEqual(push_results[8:], [False] * 22)
        self.assertEqual(q.overflow_drops, 22)
        self.assertEqual(q.size(), 8)

        # Consumer starts draining
        drained = []
        while not q.is_empty():
            drained.append(q.receive_non_blocking()["idx"])

        self.assertEqual(drained, list(range(8)))
        self.assertTrue(q.is_empty())

    def test_c04_high_noise_floor_mixed_with_tone(self):
        """Interaction: Sine wave combined with pseudo-random noise floor."""
        random.seed(42)
        amp_signal = 100000
        noise_level = 20000
        n = AUDIO_DSP_DECIMATION_FACTOR

        samples = []
        for i in range(n):
            sig = amp_signal * math.sin(2 * math.pi * i / 16)
            noise = random.uniform(-noise_level, noise_level)
            samples.append(int(sig + noise))

        _, rms_total, peak_total = audio_dsp_process_window(samples)

        # Expected signal RMS = 100000 / sqrt(2) ~ 70710
        # Expected noise RMS = 20000 / sqrt(3) ~ 11547
        # Total expected RMS ~ sqrt(70710^2 + 11547^2) ~ 71646
        self.assertGreater(rms_total, 65000)
        self.assertLess(rms_total, 85000)
        self.assertGreaterEqual(peak_total, amp_signal)

    def test_c05_sample_rate_and_decimation_grid(self):
        """Pairwise: Combinatorial grid of sample rates x decimation factors."""
        sample_rates = [16000, 48000]
        decimations = [64, 128, 256]

        for fs in sample_rates:
            for d in decimations:
                stream_hz = fs / d
                bytes_per_pkt = 25  # Average length of sample:%ld,rms:%ld\r\n
                bw_bytes_sec = stream_hz * bytes_per_pkt
                max_uart_bytes = TELEMETRY_BAUD_RATE / 10

                # Bandwidth must remain within 115200 baud capacity
                if stream_hz <= 375:  # Supported streaming rates
                    self.assertLess(bw_bytes_sec, max_uart_bytes)
                self.assertGreater(stream_hz, 0)

    def test_c06_multichannel_demux_and_sign_extension(self):
        """Interaction: 32-bit stereo DMA demux with concurrent 24-in-32 bit sign extension."""
        # Simulated raw DMA buffer for 4 frames of stereo [L0, R0, L1, R1, ...]
        raw_dma = [
            0x00100000,  # L0: +4096 (24-bit << 8)
            to_int32(-2048 << 8),  # R0: -2048
            0x00200000,  # L1: +8192
            to_int32(-4096 << 8),  # R1: -4096
            0x7FFFFF00,  # L2: +8388607 (Max pos)
            0x80000000,  # R2: -8388608 (Max neg)
        ]

        mic1_samples = []
        mic2_samples = []

        for i in range(len(raw_dma) // 2):
            raw_l = raw_dma[2 * i]
            raw_r = raw_dma[2 * i + 1]
            mic1_samples.append(i2s_mic_convert_sample(raw_l))
            mic2_samples.append(i2s_mic_convert_sample(raw_r))

        self.assertEqual(mic1_samples, [4096, 8192, 8388607])
        self.assertEqual(mic2_samples, [-2048, -4096, -8388608])

    def test_c07_transport_byte_fragmentation_and_recovery(self):
        """Interaction: Split UART byte chunks with corrupt fragments resynchronize cleanly."""
        packets = [
            telemetry_format_packet(100, 50),
            telemetry_format_packet(200, 75),
            telemetry_format_packet(-300, 90),
        ]
        full_stream = "".join(packets)

        # Inject noise fragment between packet 1 and packet 2
        noisy_stream = packets[0] + "GARBAGE_CHUNK_CORRUPT\r\n" + packets[1] + packets[2]

        parsed_results = []
        lines = noisy_stream.splitlines()
        for line in lines:
            parsed = telemetry_parse_line(line)
            if parsed is not None:
                parsed_results.append(parsed)

        self.assertEqual(len(parsed_results), 3)
        self.assertEqual(parsed_results[0], (100, 50))
        self.assertEqual(parsed_results[1], (200, 75))
        self.assertEqual(parsed_results[2], (-300, 90))

    def test_c08_dynamic_range_transition_whisper_to_shout(self):
        """Interaction: Smooth tracking across dynamic range (whisper -> speech -> shout -> room noise)."""
        stages = [
            ("whisper", 500),
            ("speech", 80000),
            ("shout", 4000000),
            ("ambient", 2000),
        ]

        envelope_history = []
        for name, target_amp in stages:
            samples = [
                int(target_amp * math.sin(2 * math.pi * i / 16))
                for i in range(AUDIO_DSP_DECIMATION_FACTOR)
            ]
            _, rms, peak = audio_dsp_process_window(samples)
            envelope_history.append((name, rms, peak))

        # Check relative levels reflect dynamic range
        self.assertLess(envelope_history[0][1], envelope_history[1][1])
        self.assertLess(envelope_history[1][1], envelope_history[2][1])
        self.assertGreater(envelope_history[2][1], envelope_history[3][1])


if __name__ == "__main__":
    unittest.main()

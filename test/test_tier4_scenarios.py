"""
Tier 4: Real-World Application Scenarios Test Suite (test_tier4_scenarios.py)
Validates end-to-end realistic workflows:
- Scenario 1: Continuous 1000+ frame streaming simulation
- Scenario 2: Real-time telemetry decoder & stream jitter monitor
- Scenario 3: PlatformIO / Arduino Serial Plotter frontend compatibility
- Scenario 4: Acoustic Event Detection (clap/speech onset trigger)
- Scenario 5: End-to-end WAV audio export & format verification
- Scenario 6: Mock CLI playback and ANSI meter visualization
"""

import math
import random
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
    i2s_mic_convert_sample,
    audio_dsp_process_window,
    telemetry_format_packet,
    telemetry_parse_line,
    SimulatedFreeRTOSQueue,
    create_synthetic_wav_bytes,
)


class TestTier4ApplicationScenarios(unittest.TestCase):
    """Tier 4 Realistic Application Scenarios"""

    def test_s01_continuous_1000_frame_streaming_simulation(self):
        """Scenario 1: Continuous 1000+ frame streaming simulation over 8 seconds of audio."""
        num_frames = 1000
        fs = 16000
        window_size = AUDIO_DSP_DECIMATION_FACTOR  # 128
        total_samples = num_frames * window_size  # 128,000 samples = 8.0 seconds

        queue = SimulatedFreeRTOSQueue(capacity=TELEMETRY_QUEUE_DEPTH)
        processed_packets = []

        for frame_idx in range(num_frames):
            # Simulate speech envelope modulation (phoneme bursts + silence)
            t_sec = (frame_idx * window_size) / fs
            # Modulation envelope at 2 Hz (talking rhythm)
            envelope = max(0.0, math.sin(2 * math.pi * 2.0 * t_sec))
            voice_amp = 500000.0 * envelope

            # Window samples
            samples = []
            for i in range(window_size):
                t_sample = (frame_idx * window_size + i) / fs
                carrier = math.sin(2 * math.pi * 440.0 * t_sample)
                samples.append(int(voice_amp * carrier))

            dec, rms, peak = audio_dsp_process_window(samples)

            # Invariants
            self.assertFalse(math.isnan(rms))
            self.assertFalse(math.isnan(peak))
            self.assertGreaterEqual(rms, 0)
            self.assertLessEqual(rms, AUDIO_DSP_FULL_SCALE)
            self.assertGreaterEqual(peak, 0)
            self.assertLessEqual(peak, AUDIO_DSP_FULL_SCALE)

            # Queue pipeline
            queue.send_non_blocking({"dec": dec, "rms": rms, "peak": peak})

            # Drain queue (simulating UART task running at matching rate)
            item = queue.receive_non_blocking()
            if item:
                line = telemetry_format_packet(item["dec"], item["rms"])
                parsed = telemetry_parse_line(line)
                self.assertIsNotNone(parsed)
                processed_packets.append(parsed)

        self.assertEqual(len(processed_packets), num_frames)
        self.assertEqual(queue.overflow_drops, 0)

    def test_s02_real_time_telemetry_decoder_and_jitter_monitor(self):
        """Scenario 2: Real-time telemetry decoder & stream timing jitter verification."""
        num_packets = 200
        target_period_ms = (AUDIO_DSP_DECIMATION_FACTOR / I2S_DEFAULT_SAMPLE_RATE) * 1000.0  # 8.0 ms
        self.assertEqual(target_period_ms, 8.0)

        # Simulate timestamps with slight jitter (+/- 0.5 ms)
        random.seed(1234)
        current_time_ms = 1000.0
        stream_log = []

        for i in range(num_packets):
            jitter = random.uniform(-0.5, 0.5)
            current_time_ms += target_period_ms + jitter
            line = telemetry_format_packet(int(10000 * math.sin(i)), int(5000 * abs(math.cos(i))))
            stream_log.append((current_time_ms, line))

        # Decoder passes stream log
        decoded_timeline = []
        for timestamp, raw_line in stream_log:
            parsed = telemetry_parse_line(raw_line)
            self.assertIsNotNone(parsed)
            decoded_timeline.append((timestamp, parsed[0], parsed[1]))

        self.assertEqual(len(decoded_timeline), num_packets)

        # Check average inter-packet interval
        intervals = [
            decoded_timeline[i][0] - decoded_timeline[i - 1][0]
            for i in range(1, len(decoded_timeline))
        ]
        avg_interval = sum(intervals) / len(intervals)
        self.assertAlmostEqual(avg_interval, 8.0, delta=0.2)

    def test_s03_arduino_platformio_serial_plotter_compatibility(self):
        """Scenario 3: Verification of PlatformIO & Arduino Serial Plotter format compatibility."""
        # Plotter requires format: `label1:val1,label2:val2\r\n`
        samples = [(-150000, 75000), (0, 0), (250000, 120000), (-8388608, 8388607)]

        for s_val, r_val in samples:
            line = telemetry_format_packet(s_val, r_val)

            # 1. Must end with CRLF
            self.assertTrue(line.endswith("\r\n"))

            # 2. Must split by comma into exactly 2 fields
            body = line.rstrip("\r\n")
            parts = body.split(",")
            self.assertEqual(len(parts), 2)

            # 3. First field must start with 'sample:'
            self.assertTrue(parts[0].startswith("sample:"))
            sample_num_str = parts[0][len("sample:"):]
            self.assertEqual(int(sample_num_str), s_val)

            # 4. Second field must start with 'rms:'
            self.assertTrue(parts[1].startswith("rms:"))
            rms_num_str = parts[1][len("rms:"):]
            self.assertEqual(int(rms_num_str), r_val)

    def test_s04_acoustic_event_detection_clap_trigger(self):
        """Scenario 4: Acoustic Event Detection (AED) clap onset detection trigger."""
        # Setup: 20 windows of quiet background noise (RMS ~ 1500)
        # Followed by a sharp clap spike (RMS ~ 500,000)
        # Followed by 20 windows of return to background noise
        noise_floor_rms = 1500
        clap_rms = 500000
        threshold_multiplier = 5.0
        trigger_threshold = noise_floor_rms * threshold_multiplier

        triggered_events = []
        cooldown = 0

        for frame_idx in range(50):
            if frame_idx == 25:
                current_rms = clap_rms
            else:
                current_rms = noise_floor_rms + (frame_idx % 200)

            # AED logic
            if cooldown > 0:
                cooldown -= 1
            elif current_rms > trigger_threshold:
                triggered_events.append({"frame": frame_idx, "rms": current_rms})
                cooldown = 10  # Prevent re-trigger for 10 frames

        # Exactly 1 clap event must be triggered at frame 25
        self.assertEqual(len(triggered_events), 1)
        self.assertEqual(triggered_events[0]["frame"], 25)
        self.assertEqual(triggered_events[0]["rms"], clap_rms)

    def test_s05_end_to_end_wav_audio_export_and_spectral_verification(self):
        """Scenario 5: End-to-end WAV audio export and format integrity check."""
        fs = 16000
        duration = 1.0  # 1.0 second
        n_samples = int(fs * duration)
        f_tone = 440.0  # 440 Hz A4 note

        # Synthesize 24-bit acoustic sine wave
        samples_24 = [
            int(4000000.0 * math.sin(2 * math.pi * f_tone * t / fs))
            for t in range(n_samples)
        ]

        # Export to WAV container bytes
        wav_data = create_synthetic_wav_bytes(samples_24, sample_rate=fs)
        self.assertGreater(len(wav_data), 44)

        # Inspect using wave module
        with wave.open(io.BytesIO(wav_data), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)  # 16-bit PCM
            self.assertEqual(wf.getframerate(), 16000)
            self.assertEqual(wf.getnframes(), n_samples)
            raw_frames = wf.readframes(n_samples)

        # Unpack PCM 16-bit samples
        pcm16 = struct.unpack(f"<{n_samples}h", raw_frames)
        self.assertEqual(len(pcm16), n_samples)

        # Verify amplitude level: 4000000 >> 8 = 15625 (16-bit range)
        max_pcm16 = max(pcm16)
        expected_amp_16 = 4000000 >> 8
        self.assertAlmostEqual(max_pcm16, expected_amp_16, delta=20)

        # Verify zero-crossing frequency ~ 2 * 440 = 880 crossings/sec
        zero_crossings = 0
        for i in range(1, len(pcm16)):
            if (pcm16[i - 1] < 0 and pcm16[i] >= 0) or (pcm16[i - 1] >= 0 and pcm16[i] < 0):
                zero_crossings += 1
        estimated_freq = zero_crossings / (2.0 * duration)
        self.assertAlmostEqual(estimated_freq, 440.0, delta=2.0)

    def test_s06_mock_cli_playback_and_ansi_meter_visualization(self):
        """Scenario 6: Emulate CLI playback mode and ANSI level meter."""
        rms_values = [0, 500000, 2000000, 4194303, 8388607]
        meter_outputs = []

        def render_meter(rms: int, peak: int, width: int = 30) -> str:
            frac = max(0.0, min(1.0, rms / AUDIO_DSP_FULL_SCALE))
            filled = round(frac * width)
            bar = "#" * filled + "-" * (width - filled)
            return f"[{bar}] RMS:{rms:>8} | PEAK:{peak:>8}"

        for r in rms_values:
            meter = render_meter(r, r)
            meter_outputs.append(meter)
            if r > 0:
                self.assertIn("#", meter)
            else:
                self.assertIn("-", meter)
            self.assertIn("RMS:", meter)
            self.assertIn("PEAK:", meter)

        self.assertEqual(len(meter_outputs), 5)
        # Check first is all dashes
        self.assertIn("------------------------------", meter_outputs[0])
        # Check last is all hashes
        self.assertIn("##############################", meter_outputs[4])


if __name__ == "__main__":
    unittest.main()

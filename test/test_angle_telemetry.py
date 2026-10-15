"""Checks parsing of the earlier angle firmware's serial packet format."""

import unittest
import io
import time
import math
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch

from tools.audio_plotter import (
    AngleTelemetryParser,
    parse_telemetry_line,
    run_cli_mode,
    StereoTelemetryParser,
    compute_stereo_delay_and_coherence,
    export_stereo_wav,
)


class AngleTelemetryTests(unittest.TestCase):
    def test_firmware_teleplot_packet(self):
        parser = AngleTelemetryParser()
        lines = (
            ">dt_us:-125.0\n", ">dt_smp:-2.00\n", ">f_dom:125.0\n",
            ">phi:0.098\n", ">angle:12.4\n", ">rms1:43000\n",
            ">rms2:41000\n", ">conf:0.82\n", ">active:1\n",
        )
        packets = [packet for line in lines if (packet := parser.feed(line)) is not None]
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0]["angle"], 12.4)
        self.assertEqual(packets[0]["dt_us"], -125.0)
        self.assertEqual(packets[0]["rms2"], 41000)

    def test_firmware_csv_packet(self):
        parser = AngleTelemetryParser()
        line = "dt_us:20.0,dt_smp:0.32,f_dom:156.2,phi:-0.02,angle:-2.0,rms1:9000,rms2:8500,conf:0.51,active:1\r\n"
        packet = parser.feed(line)
        self.assertIsNotNone(packet)
        self.assertEqual(packet["angle"], -2.0)
        self.assertEqual(packet["active"], 1)

    def test_incomplete_packet_does_not_reuse_old_fields(self):
        parser = AngleTelemetryParser()
        for line in (">dt_us:1\n", ">angle:30\n", ">rms1:1\n", ">rms2:1\n", ">conf:1\n"):
            self.assertIsNone(parser.feed(line))
        self.assertIsNone(parser.feed(">dt_us:2\n"))
        self.assertIsNone(parser.feed(">active:1\n"))

    def test_non_finite_angle_is_rejected(self):
        parser = AngleTelemetryParser()
        self.assertIsNone(parser.feed("angle:nan,rms1:100,rms2:100,conf:1,active:1\n"))

    def test_legacy_single_mic_format_still_parses(self):
        self.assertEqual(parse_telemetry_line("sample:-123,rms:456,peak:789\r\n"), (-123, 456, 789))

    def test_cli_displays_live_angle_packets(self):
        class FakeSerial:
            def __init__(self, *args, **kwargs):
                self.lines = iter((
                    b">dt_us:-125.0\n", b">dt_smp:-2.00\n", b">f_dom:125.0\n",
                    b">phi:0.098\n", b">angle:12.4\n", b">rms1:43000\n",
                    b">rms2:41000\n", b">conf:0.82\n", b">active:1\n",
                ) * 20)
                self.is_open = True

            def readline(self):
                time.sleep(0.003)
                return next(self.lines, b"")

            def close(self):
                self.is_open = False

        args = Namespace(mock=False, port="COM_TEST", baud=115200, duration=0.12, save_wav=None)
        output = io.StringIO()
        fake_serial_module = SimpleNamespace(Serial=FakeSerial, SerialException=Exception)
        with patch("tools.audio_plotter.serial", fake_serial_module), patch("sys.stdout", output):
            run_cli_mode(args)
        self.assertIn("ANGLE:", output.getvalue())
        self.assertIn("Stereo DOA Packets:", output.getvalue())

    def test_stereo_parser_teleplot_pairing(self):
        parser = StereoTelemetryParser()
        self.assertIsNone(parser.feed(">mic1:12345\n"))
        pair = parser.feed(">mic2:12340\n")
        self.assertEqual(pair, (12345, 12340))

    def test_stereo_parser_reverse_arrival(self):
        parser = StereoTelemetryParser()
        self.assertIsNone(parser.feed(">mic2:9999\n"))
        pair = parser.feed(">mic1:8888\n")
        self.assertEqual(pair, (8888, 9999))

    def test_stereo_parser_csv_pairing(self):
        parser = StereoTelemetryParser()
        pair = parser.feed("mic1:5000,mic2:5010\r\n")
        self.assertEqual(pair, (5000, 5010))

    def test_compute_stereo_delay_and_coherence_in_phase(self):
        sig = [int(100000 * math.sin(2 * math.pi * 0.1 * i)) for i in range(50)]
        delay_us, coh = compute_stereo_delay_and_coherence(sig, sig, max_lag=5, sample_rate_hz=1000.0)
        self.assertEqual(delay_us, 0.0)
        self.assertAlmostEqual(coh, 1.0, places=3)

    def test_compute_stereo_delay_and_coherence_lagged(self):
        sig1 = [int(100000 * math.sin(2 * math.pi * 0.05 * i)) for i in range(60)]
        # sig2 shifted by 2 samples
        sig2 = [int(100000 * math.sin(2 * math.pi * 0.05 * (i - 2))) for i in range(60)]
        delay_us, coh = compute_stereo_delay_and_coherence(sig1, sig2, max_lag=5, sample_rate_hz=1000.0)
        self.assertEqual(delay_us, 2000.0)
        self.assertGreater(coh, 0.98)

    def test_cli_displays_stereo_sync_mock(self):
        args = Namespace(mock=True, port=None, baud=460800, duration=0.1, save_wav=None)
        output = io.StringIO()
        with patch("sys.stdout", output):
            run_cli_mode(args)
        val = output.getvalue()
        self.assertIn("MIC1:", val)
        self.assertIn("MIC2:", val)
        self.assertIn("DELAY:", val)
        self.assertIn("Stereo Paired Points:", val)

    def test_export_stereo_wav_two_channels(self):
        import tempfile
        import wave
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        try:
            m1 = [100000] * 32
            m2 = [200000] * 32
            export_stereo_wav(wav_path, m1, m2, sample_rate=16000, repeat_factor=4)
            with wave.open(wav_path, "rb") as wf:
                self.assertEqual(wf.getnchannels(), 2)
                self.assertEqual(wf.getsampwidth(), 2)
                self.assertEqual(wf.getframerate(), 16000)
                self.assertEqual(wf.getnframes(), 32 * 4)
        finally:
            import os
            if os.path.exists(wav_path):
                os.remove(wav_path)


if __name__ == "__main__":
    unittest.main()

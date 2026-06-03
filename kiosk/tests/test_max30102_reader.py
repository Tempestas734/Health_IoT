from django.test import SimpleTestCase

from kiosk.services.max30102_reader import estimate_heart_rate, estimate_spo2


class Max30102CalculationTests(SimpleTestCase):
    def test_estimate_heart_rate_returns_bpm_from_periodic_ir_signal(self):
        sample_rate_hz = 25.0
        beat_interval = 25
        samples = []
        for index in range(100):
            value = 50000
            if index % beat_interval == 5:
                value = 56000
            elif index % beat_interval in {4, 6}:
                value = 53000
            samples.append(value)

        self.assertEqual(estimate_heart_rate(samples, sample_rate_hz=sample_rate_hz), 60)

    def test_estimate_spo2_returns_percent_for_stable_red_ir_waveforms(self):
        red_samples = []
        ir_samples = []
        red_pattern = [50000, 50200, 50400, 50200, 50000, 49800, 49600, 49800]
        ir_pattern = [60000, 60600, 61200, 60600, 60000, 59400, 58800, 59400]

        for index in range(40):
            red_samples.append(red_pattern[index % len(red_pattern)])
            ir_samples.append(ir_pattern[index % len(ir_pattern)])

        spo2 = estimate_spo2(red_samples, ir_samples)

        self.assertIsNotNone(spo2)
        self.assertGreaterEqual(spo2, 90)
        self.assertLessEqual(spo2, 100)

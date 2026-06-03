from django.test import SimpleTestCase

from kiosk.services.filters import MovingAverageFilter, is_outlier


class MovingAverageFilterTests(SimpleTestCase):
    def test_moving_average_keeps_last_n_values(self):
        filter_ = MovingAverageFilter(window_size=3)

        self.assertEqual(filter_.add(10), 10.0)
        self.assertEqual(filter_.add(20), 15.0)
        self.assertEqual(filter_.add(30), 20.0)
        self.assertEqual(filter_.add(60), 110 / 3)

    def test_outlier_helper_uses_threshold(self):
        self.assertFalse(is_outlier(520, 500, 30))
        self.assertTrue(is_outlier(900, 500, 300))

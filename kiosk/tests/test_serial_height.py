from django.test import SimpleTestCase

from kiosk.services.serial_height import distance_to_height_mm, parse_height_line


class ParseHeightLineTests(SimpleTestCase):
    def test_parses_distance_line(self):
        self.assertEqual(parse_height_line("DISTANCE:523"), 523.0)

    def test_parses_distance_with_spacing(self):
        self.assertEqual(parse_height_line("DISTANCE : 1723"), 1723.0)

    def test_parses_french_distance_in_centimeters(self):
        self.assertEqual(
            parse_height_line("Distance mesuree: 52.3 cm | Taille estimee: 147.7 cm"),
            523.0,
        )

    def test_returns_none_for_unknown_line(self):
        self.assertIsNone(parse_height_line("DISTANCE_ERROR"))

    def test_converts_distance_to_height_with_two_meter_sensor(self):
        self.assertEqual(distance_to_height_mm(523, sensor_height_mm=2000), 1477)

    def test_returns_none_for_height_outside_valid_range(self):
        self.assertIsNone(distance_to_height_mm(1501, sensor_height_mm=2000))

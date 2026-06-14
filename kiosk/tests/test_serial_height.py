from django.test import SimpleTestCase

from kiosk.services.serial_height import (
    distance_to_height_mm,
    parse_height_line,
    parse_height_measurement,
)


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

    def test_parses_accented_french_distance_in_centimeters(self):
        self.assertEqual(
            parse_height_line("Distance mesur\u00e9e: 52.3 cm"),
            523.0,
        )
        self.assertEqual(
            parse_height_line(
                "Distance mesur\u00e9e: 52.3 cm | Taille estim\u00e9e: 147.7 cm"
            ),
            523.0,
        )

    def test_parses_french_distance_and_direct_height_measurement(self):
        self.assertEqual(
            parse_height_measurement("Distance mesuree: 52.3 cm | Taille estimee: 147.7 cm"),
            (523.0, 1477.0),
        )

    def test_parses_accented_french_distance_and_direct_height_measurement(self):
        self.assertEqual(
            parse_height_measurement(
                "Distance mesur\u00e9e: 52.3 cm | Taille estim\u00e9e: 147.7 cm"
            ),
            (523.0, 1477.0),
        )

    def test_parses_direct_height_line(self):
        self.assertEqual(
            parse_height_measurement("HEIGHT_CM=171.4"),
            (None, 1714.0),
        )

    def test_returns_none_for_unknown_line(self):
        self.assertIsNone(parse_height_line("DISTANCE_ERROR"))

    def test_converts_distance_to_height_with_two_meter_sensor(self):
        self.assertEqual(distance_to_height_mm(523, sensor_height_mm=2000), 1477)

    def test_returns_none_for_height_outside_valid_range(self):
        self.assertIsNone(distance_to_height_mm(1501, sensor_height_mm=2000))

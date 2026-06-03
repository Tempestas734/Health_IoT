from django.test import SimpleTestCase

from kiosk.services.serial_height import parse_height_line


class ParseHeightLineTests(SimpleTestCase):
    def test_parses_distance_line(self):
        self.assertEqual(parse_height_line("DISTANCE:523"), 523.0)

    def test_parses_distance_with_spacing(self):
        self.assertEqual(parse_height_line("DISTANCE : 1723"), 1723.0)

    def test_returns_none_for_unknown_line(self):
        self.assertIsNone(parse_height_line("DISTANCE_ERROR"))

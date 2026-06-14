from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from kiosk.services import serial_height
from kiosk.services.serial_height import (
    distance_to_height_mm,
    parse_height_line,
    parse_height_measurement,
    read_height_measurement,
)


class ParseHeightLineTests(SimpleTestCase):
    def tearDown(self):
        serial_height._height_filter.clear()
        serial_height._last_distance_mm = None
        super().tearDown()

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

    def test_parses_french_measurement_with_equals_semicolon_and_comma_decimals(self):
        self.assertEqual(
            parse_height_measurement("Distance mesuree = 52,3 cm ; Taille estimee = 147,7 cm"),
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

    def test_parses_direct_height_line_with_comma_decimal(self):
        self.assertEqual(
            parse_height_measurement("HEIGHT_CM=171,4"),
            (None, 1714.0),
        )

    def test_returns_none_for_unknown_line(self):
        self.assertIsNone(parse_height_line("DISTANCE_ERROR"))

    def test_converts_distance_to_height_with_two_meter_sensor(self):
        self.assertEqual(distance_to_height_mm(523, sensor_height_mm=2000), 1477)

    def test_returns_none_for_height_outside_valid_range(self):
        self.assertIsNone(distance_to_height_mm(1501, sensor_height_mm=2000))

    def test_read_height_measurement_skips_transient_error_until_valid_height(self):
        class FakeSerial:
            def __init__(self, *_args, **_kwargs):
                self._lines = iter(
                    [
                        b"erreur capteur\r\n",
                        b"Distance mesuree: 52.3 cm | Taille estimee: 147.7 cm\r\n",
                    ]
                )

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def readline(self):
                return next(self._lines, b"")

        with patch.object(serial_height, "serial", SimpleNamespace(Serial=FakeSerial)):
            payload = read_height_measurement(max_lines=3)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["height_mm"], 1477)
        self.assertEqual(payload["distance_mm"], 523)
        self.assertEqual(
            payload["source_line"],
            "Distance mesuree: 52.3 cm | Taille estimee: 147.7 cm",
        )

    def test_read_height_measurement_returns_error_if_only_transient_errors_seen(self):
        class FakeSerial:
            def __init__(self, *_args, **_kwargs):
                self._lines = iter(
                    [
                        b"timeout\r\n",
                        b"erreur capteur\r\n",
                    ]
                )

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def readline(self):
                return next(self._lines, b"")

        with patch.object(serial_height, "serial", SimpleNamespace(Serial=FakeSerial)):
            payload = read_height_measurement(max_lines=3)

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["source_line"], "erreur capteur")
        self.assertIsNone(payload["height_mm"])

    def test_read_height_measurement_returns_last_observed_line_when_waiting(self):
        class FakeSerial:
            def __init__(self, *_args, **_kwargs):
                self._lines = iter(
                    [
                        b"boot complete\r\n",
                        b"capteur pret\r\n",
                    ]
                )

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def readline(self):
                return next(self._lines, b"")

        with patch.object(serial_height, "serial", SimpleNamespace(Serial=FakeSerial)):
            payload = read_height_measurement(max_lines=3)

        self.assertEqual(payload["status"], "waiting")
        self.assertEqual(payload["source_line"], "capteur pret")

    def test_read_height_measurement_skips_info_lines_until_valid_height(self):
        class FakeSerial:
            def __init__(self, *_args, **_kwargs):
                self._lines = iter(
                    [
                        b"VL53L1X detecte\r\n",
                        b"capteur pret\r\n",
                        b"Distance mesuree: 52.3 cm | Taille estimee: 147.7 cm\r\n",
                    ]
                )

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def readline(self):
                return next(self._lines, b"")

        with patch.object(serial_height, "serial", SimpleNamespace(Serial=FakeSerial)):
            payload = read_height_measurement(max_lines=5)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["height_cm"], 147.7)

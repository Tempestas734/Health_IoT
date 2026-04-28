from unittest.mock import patch

from django.test import SimpleTestCase
import requests

from kiosk.supabase import SupabaseServiceError, _request


class SupabaseRequestErrorTests(SimpleTestCase):
    @patch.dict(
        "os.environ",
        {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "test-anon-key",
        },
        clear=False,
    )
    @patch("kiosk.supabase.requests.request")
    def test_dns_resolution_error_returns_friendly_message(self, request_mock):
        request_mock.side_effect = requests.ConnectionError(
            "HTTPSConnectionPool(host='bad-host', port=443): Max retries exceeded with url: "
            "/rest/v1/consents (Caused by NameResolutionError(\"<urllib3.connection.HTTPSConnection object>: "
            "Failed to resolve 'bad-host' ([Errno -2] Name or service not known)\"))"
        )

        with self.assertRaises(SupabaseServiceError) as exc:
            _request("GET", "consents")

        self.assertEqual(
            str(exc.exception),
            "Unable to reach Supabase. Check SUPABASE_URL and DNS/network connectivity.",
        )

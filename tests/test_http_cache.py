import unittest

from fastapi import Request

from motto_core.http_cache import etag_response


def request_with(headers=()):
    return Request({
        "type": "http", "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": "/api/all", "raw_path": b"/api/all",
        "query_string": b"", "headers": list(headers),
        "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8910),
    })


class HttpCacheTests(unittest.TestCase):
    def test_etag_supports_conditional_dashboard_requests(self):
        first = etag_response(request_with(), {"schemaVersion": "motto.dashboard.v3", "value": 7})
        etag = first.headers["etag"]
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers["cache-control"], "private, no-cache, must-revalidate")
        second = etag_response(request_with(((b"if-none-match", etag.encode("ascii")),)), {"value": 7, "schemaVersion": "motto.dashboard.v3"})
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.body, b"")


if __name__ == "__main__":
    unittest.main()

"""Security-oriented tests for website retrieval."""

import unittest

from sevah.services.website_content import WebsiteFetchError, fetch_website_document


class WebsiteContentTests(unittest.TestCase):
    def test_loopback_hosts_are_blocked(self) -> None:
        with self.assertRaises(WebsiteFetchError):
            fetch_website_document("http://127.0.0.1/private")

    def test_non_http_urls_are_blocked(self) -> None:
        with self.assertRaises(WebsiteFetchError):
            fetch_website_document("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()


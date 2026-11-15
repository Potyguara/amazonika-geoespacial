"""Test GEO-90 egress route restrictions without network."""
import unittest
from deploy.inpe.egress_proxy import upstream_for


class TestProxy(unittest.TestCase):
    def test_allowed(self):
        url = upstream_for("/collections/CB4A-WPM-L4-DN-1/items?bbox=-51.1,-0.2,-51.0,-0.1&limit=5")
        self.assertTrue(url.startswith("https://data.inpe.br/bdc/stac/v1/collections/CB4A-WPM-L4-DN-1/items?"))

    def test_disallow_arbitrary_hosts(self):
        for path in [
            "https://example.com/",
            "//example.com/",
            "/anything",
            "/collections/OTHER/items?bbox=-51.1,-0.2,-51.0,-0.1&limit=5",
            "/collections/CB4A-WPM-L4-DN-1/items?bbox=-51.1,-0.2,-51.0,-0.1&limit=5&url=https://example.com",
            "/collections/CB4A-WPM-L4-DN-1/items?bbox=-51.1,-0.2,-51.0,-0.1&limit=999",
            "/collections/CB4A-WPM-L4-DN-1/items?bbox=-53,-1,-50,0&limit=5",
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                upstream_for(path)


if __name__ == "__main__":
    unittest.main()

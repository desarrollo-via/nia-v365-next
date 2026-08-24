import unittest

from fastapi import FastAPI

from optional_r1_oauth_refresh_internal import mount_optional_r1_oauth_refresh_internal


class OptionalR1OAuthRefreshInternalTests(unittest.TestCase):
    def test_incomplete_composition_fails_closed(self):
        result = mount_optional_r1_oauth_refresh_internal(
            FastAPI(),
            factory_loader=lambda: (lambda: (_ for _ in ()).throw(RuntimeError()), lambda: None),
        )
        self.assertFalse(result.mounted)
        self.assertEqual(result.reason, "composition_failed")


if __name__ == "__main__":
    unittest.main()

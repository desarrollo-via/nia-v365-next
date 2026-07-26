import unittest

from bitrix_connector.worker_cli import build_parser


class WorkerCliTests(unittest.TestCase):
    def test_safe_non_secret_defaults(self):
        args = build_parser().parse_args([])

        self.assertIsNone(args.worker_id)
        self.assertEqual(args.poll_seconds, 1.0)
        self.assertEqual(args.lease_seconds, 60)
        self.assertEqual(args.retry_after_seconds, 30)
        self.assertEqual(args.http_timeout_seconds, 10.0)


if __name__ == "__main__":
    unittest.main()

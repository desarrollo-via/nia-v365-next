import unittest

from bitrix_connector.r1_oauth_refresh_invocation_contract import (
    build_r1_oauth_refresh_invocation_contracts,
    contract_is_inert,
)


class R1OAuthRefreshInvocationContractTests(unittest.TestCase):
    def test_two_distinct_inert_options_are_frozen(self):
        job, endpoint = build_r1_oauth_refresh_invocation_contracts()
        self.assertEqual((job.mode, endpoint.mode), ("WEBAPP_JOB", "INTERNAL_ENDPOINT"))
        self.assertNotEqual(job.invocation_path, endpoint.invocation_path)
        self.assertTrue(contract_is_inert(job))
        self.assertTrue(contract_is_inert(endpoint))

    def test_neither_option_creates_or_mounts_anything(self):
        for contract in build_r1_oauth_refresh_invocation_contracts():
            self.assertEqual(contract.deployment_calls, 0)
            self.assertEqual(contract.route_mounts, 0)
            self.assertEqual(contract.job_creations, 0)
            self.assertEqual(contract.retries, 0)
            self.assertEqual(contract.bitrix_rest_calls, 0)
            self.assertEqual(contract.messages, 0)


if __name__ == "__main__":
    unittest.main()

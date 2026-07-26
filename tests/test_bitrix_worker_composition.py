import unittest

from bitrix_connector.config import ConnectorMode
from bitrix_connector.mode_policy import ExternalCallPolicy
from bitrix_connector.worker import ConnectorWorkerRunStatus
from bitrix_connector.worker_composition import compose_workers


def enabled_review_policy():
    return ExternalCallPolicy(
        effective_mode=ConnectorMode.REVIEW,
        activation_locked=False,
        external_calls_enabled=True,
    )


class IdleStore:
    def __init__(self):
        self.claims = []

    async def claim_next(self, **kwargs):
        self.claims.append(("preflight", kwargs["lease_owner"]))
        return None

    async def claim_ready_for_nia(self, **kwargs):
        self.claims.append(("nia", kwargs["lease_owner"]))
        return None

    async def claim_ready_for_bitrix(self, **kwargs):
        self.claims.append(("bitrix", kwargs["lease_owner"]))
        return None


class ForbiddenNiaClient:
    async def send_approved_text(self, payload):
        raise AssertionError("NIA no debe invocarse sin un evento reclamado")


class ForbiddenBitrixClient:
    async def send_approved_message(self, payload):
        raise AssertionError("Bitrix no debe invocarse sin un evento reclamado")


class WorkerCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_composes_three_idle_stages_with_distinct_lease_owners(self):
        store = IdleStore()
        composition = compose_workers(
            store,
            ForbiddenNiaClient(),
            ForbiddenBitrixClient(),
            worker_id="worker-local",
            policy_provider=enabled_review_policy,
        )

        result = await composition.run_once()

        self.assertEqual(result.preflight.status, ConnectorWorkerRunStatus.IDLE)
        self.assertEqual(result.nia.status, ConnectorWorkerRunStatus.IDLE)
        self.assertEqual(result.bitrix.status, ConnectorWorkerRunStatus.IDLE)
        self.assertEqual(
            store.claims,
            [
                ("preflight", "worker-local:preflight"),
                ("nia", "worker-local:nia"),
                ("bitrix", "worker-local:bitrix"),
            ],
        )

    def test_rejects_ambiguous_worker_configuration(self):
        with self.assertRaisesRegex(ValueError, "worker_id"):
            compose_workers(
                IdleStore(),
                ForbiddenNiaClient(),
                ForbiddenBitrixClient(),
                worker_id=" ",
            )
        with self.assertRaisesRegex(ValueError, "lease_seconds"):
            compose_workers(
                IdleStore(),
                ForbiddenNiaClient(),
                ForbiddenBitrixClient(),
                worker_id="worker-local",
                lease_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()

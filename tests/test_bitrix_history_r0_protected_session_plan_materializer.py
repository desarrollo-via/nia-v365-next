import asyncio
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_armed_composition import (
    BitrixHistoryR0EphemeralInputs,
)
from bitrix_connector.bitrix_history_r0_protected_session_execution_gate import (
    PreparedProtectedHistorySessionExecutionGate,
)
from bitrix_connector.bitrix_history_r0_protected_session_plan_materializer import (
    MaterializedProtectedHistorySessionPlan,
    materialize_private_protected_history_session_plan_once,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResourcesFactory:
    async def build(self, *_args, **_kwargs):
        raise AssertionError("resources must not run")


def fictional_inputs():
    return BitrixHistoryR0EphemeralInputs(
        expected_text_sha256="e" * 64,
        window_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def materialize(**changes):
    values = {
        "dotenv_path": Path("fictional-m20.env"),
        "inputs": fictional_inputs(),
        "resources_factory": FakeResourcesFactory(),
        "preflight_client_builder": lambda **_kwargs: object(),
        "reader_client_builder": lambda **_kwargs: object(),
        "confirmation_reader": lambda: asyncio.sleep(0, result="fictional-m20"),
    }
    values.update(changes)
    return materialize_private_protected_history_session_plan_once(**values)


class ProtectedSessionPlanMaterializerTests(unittest.TestCase):
    def test_default_materialization_builds_plan_and_gate_without_external_calls(self):
        owner = materialize()
        snapshot = owner.snapshot()

        self.assertIsInstance(owner, MaterializedProtectedHistorySessionPlan)
        self.assertEqual(snapshot.state, "READY")
        self.assertEqual(snapshot.plan_calls, 1)
        self.assertEqual(snapshot.gate_calls, 1)
        self.assertEqual(snapshot.take_calls, 0)
        self.assertEqual(snapshot.external_calls, 0)
        self.assertTrue(snapshot.plan_retained)
        self.assertTrue(snapshot.gate_retained)
        self.assertEqual(repr(owner), "MaterializedProtectedHistorySessionPlan(<redacted>)")

    def test_injected_builders_run_once_but_dependencies_never_run(self):
        calls = {"plan": 0, "gate": 0, "client": 0, "confirmation": 0}
        from bitrix_connector.bitrix_history_r0_protected_session_coordinator import (
            ProtectedHistorySessionExecutionPlan,
        )
        from bitrix_connector.bitrix_history_r0_protected_session_execution_gate import (
            compose_protected_history_session_execution_gate,
        )

        def client(**_kwargs):
            calls["client"] += 1
            raise AssertionError("client must not run")

        async def confirmation():
            calls["confirmation"] += 1
            raise AssertionError("confirmation must not run")

        def plan_builder(**kwargs):
            calls["plan"] += 1
            return ProtectedHistorySessionExecutionPlan(**kwargs)

        def gate_composer(**kwargs):
            calls["gate"] += 1
            return compose_protected_history_session_execution_gate(**kwargs)

        owner = materialize(
            preflight_client_builder=client,
            reader_client_builder=client,
            confirmation_reader=confirmation,
            plan_builder=plan_builder,
            gate_composer=gate_composer,
        )

        self.assertEqual(calls, {"plan": 1, "gate": 1, "client": 0, "confirmation": 0})
        self.assertEqual(owner.snapshot().external_calls, 0)

    def test_gate_delivery_is_one_shot_and_clears_private_plan(self):
        owner = materialize()
        gate = owner.take_gate_once()

        self.assertIsInstance(gate, PreparedProtectedHistorySessionExecutionGate)
        self.assertEqual(owner.snapshot().state, "TAKEN")
        self.assertEqual(owner.snapshot().take_calls, 1)
        self.assertFalse(owner.snapshot().plan_retained)
        self.assertFalse(owner.snapshot().gate_retained)
        with self.assertRaisesRegex(RuntimeError, "plan_gate_unavailable"):
            owner.take_gate_once()

    def test_clear_discards_plan_and_gate_without_delivery(self):
        owner = materialize()
        owner.clear()

        self.assertEqual(owner.snapshot().state, "CLEARED")
        self.assertEqual(owner.snapshot().cleanup_calls, 1)
        self.assertFalse(owner.snapshot().plan_retained)
        self.assertFalse(owner.snapshot().gate_retained)

    def test_invalid_dependency_rejected_before_builders(self):
        with self.assertRaisesRegex(
            TypeError, "protected_history_session_plan_materializer_dependency_invalid"
        ):
            materialize(resources_factory=object())

    def test_builder_failure_is_redacted_and_retains_no_private_detail(self):
        private_detail = "fictional-m20-private-builder-detail"
        with self.assertRaisesRegex(
            RuntimeError, "protected_history_session_plan_materializer_failed_safe"
        ) as raised:
            materialize(
                plan_builder=lambda **_kwargs: (_ for _ in ()).throw(
                    RuntimeError(private_detail)
                )
            )
        self.assertNotIn(private_detail, str(raised.exception))

    def test_source_has_no_direct_external_or_interactive_surfaces(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_session_plan_materializer.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "open(",
            "read_text(",
            "os.environ",
            "load_dotenv",
            "get_access_token",
            "refresh_access_token",
            "get_dialog(",
            "get_session_history(",
            "httpx.AsyncClient(",
            "AsyncIOMotorClient(",
            "subprocess",
            "socket",
            "argparse",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

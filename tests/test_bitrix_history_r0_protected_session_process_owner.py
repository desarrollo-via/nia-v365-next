import asyncio
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_armed_composition import (
    BitrixHistoryR0EphemeralInputs,
)
from bitrix_connector.bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionCoordinatorSnapshot,
    ProtectedHistorySessionExecutionPlan,
)
from bitrix_connector.bitrix_history_r0_protected_session_process_owner import (
    compose_protected_history_session_process_owner,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResourcesFactory:
    async def build(self, *_args, **_kwargs):
        raise AssertionError("resources must remain fictional")


def plan():
    return ProtectedHistorySessionExecutionPlan(
        dotenv_path=Path("fictional-m37.env"),
        inputs=BitrixHistoryR0EphemeralInputs(
            expected_text_sha256="7" * 64,
            window_start=datetime(2026, 8, 3, tzinfo=timezone.utc),
        ),
        resources_factory=FakeResourcesFactory(),
        preflight_client_builder=lambda **_kwargs: object(),
        reader_client_builder=lambda **_kwargs: object(),
        confirmation_reader=lambda: asyncio.sleep(0, result="fictional-inner"),
        authorization_timeout_seconds=5,
        reader_timeout_seconds=5,
    )


def coordinator_result(state="RECEIVED", **changes):
    values = {
        "state": state,
        "reason": "fictional-m37-private-result",
        "execution_requested": True,
        "launcher_compositions": 1,
        "adapter_compositions": 1,
        "entrypoint_calls": 1,
        "owner_builder_calls": 1,
        "settings_capture_calls": 1,
        "confirmation_calls": 1,
        "reader_factory_calls": 1,
        "reader_calls": 1,
        "cleanup_calls": 1,
        "private_state_cleared": True,
    }
    values.update(changes)
    return ProtectedHistorySessionCoordinatorSnapshot(**values)


class ProtectedSessionProcessOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_is_prepared_without_coordinator_or_operational_calls(self):
        coordinator_calls = 0

        async def coordinator(**_kwargs):
            nonlocal coordinator_calls
            coordinator_calls += 1
            return coordinator_result()

        owner = compose_protected_history_session_process_owner(
            coordinator=coordinator
        )
        snapshot = await owner.execute_once()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertFalse(snapshot.execution_requested)
        self.assertFalse(snapshot.default_execution_enabled)
        self.assertFalse(snapshot.cli_available)
        self.assertTrue(snapshot.same_process_continuity_bound)
        self.assertEqual(snapshot.owner_attempts, 0)
        self.assertEqual(snapshot.coordinator_calls, 0)
        self.assertEqual(coordinator_calls, 0)

    async def test_explicit_fixture_execution_owns_single_coordinator_coroutine(self):
        calls = []
        selected_plan = plan()

        async def coordinator(**kwargs):
            calls.append(kwargs)
            return coordinator_result()

        owner = compose_protected_history_session_process_owner(
            coordinator=coordinator
        )
        snapshot = await owner.execute_once(execute=True, plan=selected_plan)

        self.assertEqual(snapshot.state, "RECEIVED")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["execute"])
        self.assertIs(calls[0]["plan"], selected_plan)
        self.assertEqual(snapshot.owner_attempts, 1)
        self.assertEqual(snapshot.coordinator_calls, 1)
        self.assertEqual(snapshot.launcher_compositions, 1)
        self.assertEqual(snapshot.adapter_compositions, 1)
        self.assertEqual(snapshot.entrypoint_calls, 1)
        self.assertEqual(snapshot.owner_builder_calls, 1)
        self.assertEqual(snapshot.confirmation_calls, 1)
        self.assertEqual(snapshot.reader_factory_calls, 1)
        self.assertEqual(snapshot.reader_calls, 1)
        self.assertEqual(snapshot.cleanup_calls, 1)
        self.assertTrue(snapshot.private_state_cleared)

    async def test_missing_plan_fails_before_coordinator(self):
        coordinator_calls = 0

        async def coordinator(**_kwargs):
            nonlocal coordinator_calls
            coordinator_calls += 1
            return coordinator_result()

        owner = compose_protected_history_session_process_owner(
            coordinator=coordinator
        )
        snapshot = await owner.execute_once(execute=True)

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.reason, "protected_history_session_process_owner_plan_invalid")
        self.assertEqual(coordinator_calls, 0)

    async def test_owner_is_one_shot(self):
        coordinator_calls = 0

        async def coordinator(**_kwargs):
            nonlocal coordinator_calls
            coordinator_calls += 1
            return coordinator_result()

        owner = compose_protected_history_session_process_owner(
            coordinator=coordinator
        )
        first = await owner.execute_once(execute=True, plan=plan())
        second = await owner.execute_once(execute=True, plan=plan())

        self.assertEqual(first.state, "RECEIVED")
        self.assertEqual(second.state, "NO-GO")
        self.assertEqual(second.reason, "protected_history_session_process_owner_already_used")
        self.assertEqual(coordinator_calls, 1)

    async def test_degraded_or_invalid_result_fails_closed_and_redacted(self):
        candidates = (
            object(),
            coordinator_result(bitrix_written=True),
            coordinator_result(private_state_cleared=False),
            coordinator_result(entrypoint_calls=0),
        )
        for candidate in candidates:
            with self.subTest(candidate=type(candidate).__name__):
                async def coordinator(**_kwargs):
                    return candidate

                owner = compose_protected_history_session_process_owner(
                    coordinator=coordinator
                )
                snapshot = await owner.execute_once(execute=True, plan=plan())
                self.assertEqual(snapshot.state, "NO-GO")
                self.assertTrue(snapshot.connector_locked_off)
                self.assertFalse(snapshot.persisted)
                self.assertFalse(snapshot.nia_called)
                self.assertFalse(snapshot.bitrix_written)
                self.assertNotIn("private-result", repr(asdict(snapshot)))

    async def test_allowlisted_coordinator_failure_category_is_propagated(self):
        async def coordinator(**_kwargs):
            return coordinator_result(
                state="NO-GO",
                failure_category="dialog_identity_mismatch",
                reader_calls=0,
            )

        owner = compose_protected_history_session_process_owner(
            coordinator=coordinator
        )
        snapshot = await owner.execute_once(execute=True, plan=plan())

        self.assertEqual(snapshot.state, "NO-GO")
        self.assertEqual(snapshot.failure_category, "dialog_identity_mismatch")

    async def test_history_shape_categories_reach_process_owner(self):
        categories = (
            "reader_history_envelope_invalid",
            "reader_history_collections_invalid",
            "reader_history_fields_invalid",
        )
        for category in categories:
            with self.subTest(category=category):
                async def coordinator(**_kwargs):
                    return coordinator_result(
                        state="NO-GO",
                        reason="fictional-m44-private-owner-reason",
                        failure_category=category,
                        reader_calls=1,
                    )

                owner = compose_protected_history_session_process_owner(
                    coordinator=coordinator
                )
                snapshot = await owner.execute_once(execute=True, plan=plan())

                self.assertEqual(snapshot.state, "NO-GO")
                self.assertEqual(snapshot.failure_category, category)
                self.assertNotIn("private-owner-reason", repr(asdict(snapshot)))

    async def test_cancellation_reraises_without_retry(self):
        calls = 0

        async def coordinator(**_kwargs):
            nonlocal calls
            calls += 1
            raise asyncio.CancelledError

        owner = compose_protected_history_session_process_owner(
            coordinator=coordinator
        )
        with self.assertRaises(asyncio.CancelledError):
            await owner.execute_once(execute=True, plan=plan())
        self.assertEqual(calls, 1)
        self.assertEqual(owner.snapshot().owner_attempts, 1)

    def test_repr_and_snapshot_do_not_expose_plan_or_inputs(self):
        owner = compose_protected_history_session_process_owner()
        serialized = repr(owner) + repr(asdict(owner.snapshot()))
        for private in ("fictional-m37.env", "7" * 64, "expected_text_sha256"):
            self.assertNotIn(private, serialized)

    def test_module_has_no_cli_or_direct_external_surfaces(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_session_process_owner.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "os.environ", "load_dotenv", "get_access_token",
            "refresh_access_token", "get_dialog(", "get_session_history(",
            "httpx", "pymongo", "subprocess", "socket", "argparse", "input(",
            "asyncio.run", "__main__",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

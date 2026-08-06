import asyncio
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_armed_composition import BitrixHistoryR0EphemeralInputs
from bitrix_connector.bitrix_history_r0_protected_session_cli import (
    PROTECTED_SESSION_FIXTURE_CONFIRMATION,
    PROTECTED_SESSION_FIXTURE_SOURCE,
    execute_fixture_protected_session_owner_once,
    main,
)
from bitrix_connector.bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionCoordinatorSnapshot,
)
from bitrix_connector.bitrix_history_r0_protected_session_execution_gate import (
    PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION,
    compose_protected_history_session_execution_gate,
)
from bitrix_connector.bitrix_history_r0_protected_session_plan_materializer import (
    materialize_private_protected_history_session_plan_once,
)
from bitrix_connector.bitrix_history_r0_protected_session_readiness_contract import (
    FUTURE_PROTECTED_SESSION_OWNER_COMMAND,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResourcesFactory:
    async def build(self, *_args, **_kwargs):
        raise AssertionError("M24 fixture must not build resources")


def materialized(coordinator):
    def gate_composer(*, plan):
        return compose_protected_history_session_execution_gate(
            plan=plan, coordinator=coordinator
        )

    return materialize_private_protected_history_session_plan_once(
        dotenv_path=Path("fictional-m24.env"),
        inputs=BitrixHistoryR0EphemeralInputs(
            expected_text_sha256="a" * 64,
            window_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ),
        resources_factory=FakeResourcesFactory(),
        preflight_client_builder=lambda **_kwargs: object(),
        reader_client_builder=lambda **_kwargs: object(),
        confirmation_reader=lambda: asyncio.sleep(0, result="fictional-inner"),
        gate_composer=gate_composer,
    )


def coordinator_result():
    return ProtectedHistorySessionCoordinatorSnapshot(
        state="RECEIVED",
        reason="fictional-m24-coordinator",
        execution_requested=True,
        launcher_compositions=1,
        adapter_compositions=1,
        entrypoint_calls=1,
        private_state_cleared=True,
    )


class ProtectedSessionCliTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_path_crosses_owner_once_and_cleans(self):
        calls = {"coordinator": 0, "confirmation": 0}

        async def coordinator(**_kwargs):
            calls["coordinator"] += 1
            return coordinator_result()

        async def confirmation():
            calls["confirmation"] += 1
            return PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION

        owner = materialized(coordinator)
        result = await execute_fixture_protected_session_owner_once(
            confirm_code=PROTECTED_SESSION_FIXTURE_CONFIRMATION,
            protected_source=PROTECTED_SESSION_FIXTURE_SOURCE,
            session_builder=lambda: owner,
            confirmation_reader=confirmation,
        )

        self.assertEqual(result.state, "RECEIVED")
        self.assertEqual(result.builder_calls, 1)
        self.assertEqual(result.owner_calls, 1)
        self.assertEqual(calls, {"coordinator": 1, "confirmation": 1})
        self.assertEqual(owner.snapshot().state, "CLEARED")

    async def test_wrong_fixture_contract_stops_before_builder(self):
        builder_calls = 0

        def builder():
            nonlocal builder_calls
            builder_calls += 1
            raise AssertionError("builder must not run")

        result = await execute_fixture_protected_session_owner_once(
            confirm_code="NO AUTORIZADO",
            protected_source=PROTECTED_SESSION_FIXTURE_SOURCE,
            session_builder=builder,
            confirmation_reader=lambda: asyncio.sleep(0, result="unused"),
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(builder_calls, 0)

    async def test_builder_failure_is_redacted_and_no_go(self):
        def builder():
            raise RuntimeError("fictional-m24-private-builder-detail")

        result = await execute_fixture_protected_session_owner_once(
            confirm_code=PROTECTED_SESSION_FIXTURE_CONFIRMATION,
            protected_source=PROTECTED_SESSION_FIXTURE_SOURCE,
            session_builder=builder,
            confirmation_reader=lambda: asyncio.sleep(0, result="unused"),
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertNotIn("private-builder", repr(result))

    async def test_cancellation_is_normalized_after_cleanup(self):
        owner = materialized(
            lambda **_kwargs: asyncio.sleep(0, result=coordinator_result())
        )

        async def confirmation():
            raise asyncio.CancelledError

        result = await execute_fixture_protected_session_owner_once(
            confirm_code=PROTECTED_SESSION_FIXTURE_CONFIRMATION,
            protected_source=PROTECTED_SESSION_FIXTURE_SOURCE,
            session_builder=lambda: owner,
            confirmation_reader=confirmation,
        )
        self.assertEqual(result.state, "CANCELLED")
        self.assertEqual(owner.snapshot().state, "CLEARED")

    def test_main_defaults_no_go_without_fixture_builder(self):
        emitted = []
        code = main(
            [
                "--confirm-code", PROTECTED_SESSION_FIXTURE_CONFIRMATION,
                "--protected-source", PROTECTED_SESSION_FIXTURE_SOURCE,
            ],
            emit=emitted.append,
        )
        self.assertEqual(code, 1)
        self.assertEqual(emitted[0].state, "NO-GO")

    def test_frozen_real_command_is_rejected_before_builder(self):
        builder_calls = 0

        def builder():
            nonlocal builder_calls
            builder_calls += 1
            return object()

        with self.assertRaises(SystemExit):
            main(
                [
                    "--confirm-code", "EJECUTAR SESION R0 PROTEGIDA UNA SOLA VEZ",
                    "--protected-source", "local-dotenv",
                ],
                session_builder=builder,
            )
        self.assertEqual(builder_calls, 0)
        self.assertIn(
            "bitrix_history_r0_protected_preflight_execution_owner",
            FUTURE_PROTECTED_SESSION_OWNER_COMMAND,
        )
        self.assertNotIn(
            "bitrix_history_r0_protected_session_cli",
            FUTURE_PROTECTED_SESSION_OWNER_COMMAND,
        )

    def test_source_has_no_real_source_or_external_surface(self):
        source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_protected_session_cli.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "AllowlistedDotenvSource", "load_dotenv", "os.environ", ".env",
            "get_access_token", "refresh_access_token", "get_dialog(",
            "get_session_history(", "httpx", "pymongo", "subprocess", "socket",
            "msvcrt", "input(", "Start-Process", "Invoke-RestMethod",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

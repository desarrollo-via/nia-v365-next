import asyncio
import signal
import unittest
from dataclasses import replace
from pathlib import Path

import httpx

from bitrix_connector.g0_deployment import (
    G0DeploymentConfigurationError,
    G0DeploymentRunner,
    G0RunnerStatus,
    compose_g0_deployment,
)


ORIGIN = "https://nia-bitrix-g0.example.com"


def safe_environ(**changes):
    values = {
        "NIA_BITRIX_G0_PUBLIC_ORIGIN": ORIGIN,
        "PORT": "8000",
        "NIA_BITRIX_MODE": "off",
        "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
        "NIA_BITRIX_MEMBER_ID": "member-123",
        "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
        "NIA_BITRIX_INSTALLATION_ENABLED": "false",
        "NIA_BITRIX_PILOT_ENABLED": "false",
        "NIA_BITRIX_PILOT_EMERGENCY_STOP": "true",
        "NIA_BITRIX_PILOT_RULES_JSON": "[]",
    }
    values.update(changes)
    return values


def bridge_environ(**changes):
    values = safe_environ(
        NIA_BITRIX_R0_BRIDGE_ENABLED="true",
        NIA_BITRIX_REVIEW_TOKEN="review-token-controlado-123456789",
        NIA_BITRIX_REVIEW_ACTOR="hugo",
        NIA_BITRIX_REVIEW_CREDENTIAL_ID="reviewer:hugo:r0",
    )
    values.update(changes)
    return values


class FakeConfig:
    def __init__(self, **values):
        self.values = values


class FakeServer:
    def __init__(self, config):
        self.config = config
        self.started = asyncio.Event()
        self.exit_requested = asyncio.Event()
        self.request_exit_calls = 0
        self.force_stop_calls = 0
        self.cancelled = False

    async def serve(self):
        self.started.set()
        try:
            await self.exit_requested.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    def request_exit(self):
        self.request_exit_calls += 1
        self.exit_requested.set()

    def force_stop(self):
        self.force_stop_calls += 1
        self.exit_requested.set()


class StubbornServer(FakeServer):
    async def serve(self):
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    def request_exit(self):
        self.request_exit_calls += 1

    def force_stop(self):
        self.force_stop_calls += 1


class ExitingServer(FakeServer):
    async def serve(self):
        self.started.set()


class FakeSignals:
    def __init__(self):
        self.handlers = {
            signal.SIGINT: "previous-int",
            signal.SIGTERM: "previous-term",
        }

    def get(self, number):
        return self.handlers[number]

    def set(self, number, handler):
        previous = self.handlers[number]
        self.handlers[number] = handler
        return previous

    def emit(self, number):
        self.handlers[number](number, None)


class G0DeploymentCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_composes_exact_single_worker_and_safe_app(self):
        deployment = compose_g0_deployment(
            safe_environ(),
            config_factory=FakeConfig,
            server_factory=FakeServer,
        )

        values = deployment.server.config.values
        self.assertEqual(values["host"], "0.0.0.0")
        self.assertEqual(values["port"], 8000)
        self.assertEqual(values["workers"], 1)
        self.assertFalse(values["reload"])
        self.assertFalse(values["access_log"])
        self.assertFalse(values["proxy_headers"])
        self.assertFalse(values["server_header"])
        self.assertFalse(values["date_header"])
        self.assertEqual(values["limit_concurrency"], 64)
        self.assertEqual(values["backlog"], 128)
        self.assertEqual(values["timeout_graceful_shutdown"], 10)
        self.assertIs(values["app"], deployment.app)
        self.assertFalse(deployment.stop_controller.stopped)
        self.assertFalse(deployment.server.started.is_set())

        transport = httpx.ASGITransport(app=deployment.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            health = await client.get("/healthz")

        self.assertEqual(health.status_code, 200)
        payload = health.json()
        self.assertEqual(payload["effective_mode"], "off")
        self.assertTrue(payload["activation_locked"])
        self.assertFalse(payload["external_calls_enabled"])
        self.assertFalse(payload["pilot_enabled"])
        self.assertTrue(payload["pilot_emergency_stop"])
        self.assertNotIn("application-secret", health.text)
        self.assertFalse(deployment.app.state.bitrix_g0_r0_bridge_enabled)
        self.assertFalse(
            deployment.app.state.bitrix_g0_optional_router_mounted
        )

    async def test_mounts_r0_bridge_only_with_independent_exact_switch(self):
        deployment = compose_g0_deployment(
            bridge_environ(),
            config_factory=FakeConfig,
            server_factory=FakeServer,
        )
        self.assertTrue(deployment.app.state.bitrix_g0_r0_bridge_enabled)
        self.assertTrue(
            deployment.app.state.bitrix_g0_optional_router_mounted
        )

        transport = httpx.ASGITransport(app=deployment.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ORIGIN,
        ) as client:
            unauthorized = await client.get(
                "/bitrix-connector/internal/r0-receipts/" + "a" * 64
            )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertNotIn("review-token-controlado", unauthorized.text)

    def test_requested_r0_bridge_fails_before_app_on_invalid_configuration(self):
        cases = (
            bridge_environ(NIA_BITRIX_REVIEW_TOKEN=""),
            bridge_environ(NIA_BITRIX_R0_BRIDGE_ENABLED="invalid"),
        )
        for environ in cases:
            with self.subTest(environ=environ), self.assertRaises(
                G0DeploymentConfigurationError
            ):
                compose_g0_deployment(
                    environ,
                    config_factory=FakeConfig,
                    server_factory=FakeServer,
                )

    def test_constructs_real_uvicorn_config_but_never_serves(self):
        deployment = compose_g0_deployment(
            safe_environ(),
            server_factory=FakeServer,
        )

        config = deployment.server.config
        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 8000)
        self.assertEqual(config.workers, 1)
        self.assertFalse(config.reload)
        self.assertFalse(config.access_log)
        self.assertFalse(config.proxy_headers)
        self.assertFalse(deployment.server.started.is_set())

    def test_owner_controlled_uvicorn_adapter_is_constructed_without_serving(self):
        deployment = compose_g0_deployment(safe_environ())
        server = deployment.server

        self.assertFalse(server._server.started)
        self.assertFalse(server._server.should_exit)
        server.request_exit()
        self.assertTrue(server._server.should_exit)
        server.force_stop()
        self.assertTrue(server._server.force_exit)

    def test_all_validation_finishes_before_any_factory_is_called(self):
        calls = []

        def forbidden(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("factory_must_not_run")

        with self.assertRaisesRegex(
            G0DeploymentConfigurationError,
            "g0_deployment_bitrix_identity_missing",
        ):
            compose_g0_deployment(
                safe_environ(NIA_BITRIX_APPLICATION_TOKEN=""),
                app_factory=forbidden,
                config_factory=forbidden,
                server_factory=forbidden,
            )
        self.assertEqual(calls, [])

    def test_rejects_unsafe_or_ambiguous_deployment_configuration(self):
        cases = (
            ({"NIA_BITRIX_G0_PUBLIC_ORIGIN": ""}, "public_origin_missing"),
            ({"NIA_BITRIX_G0_PUBLIC_ORIGIN": "http://g0.test"}, "public_origin_invalid"),
            ({"PORT": ""}, "port_missing"),
            ({"PORT": "invalid"}, "port_invalid"),
            ({"PORT": "70000"}, "port_invalid"),
            ({"WEB_CONCURRENCY": "2"}, "single_worker_required"),
            ({"NIA_BITRIX_G0_WORKERS": "0"}, "single_worker_required"),
            ({"NIA_BITRIX_MODE": "active"}, "safety_state_invalid"),
            ({"NIA_BITRIX_PILOT_ENABLED": "true"}, "pilot_state_invalid"),
            ({"NIA_BITRIX_PILOT_EMERGENCY_STOP": "false"}, "pilot_state_invalid"),
            ({"NIA_BITRIX_INSTALLATION_ENABLED": "true"}, "installation_state_invalid"),
            ({"NIA_BITRIX_DOMAIN": ""}, "bitrix_identity_missing"),
        )
        for changes, reason in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(
                G0DeploymentConfigurationError,
                f"g0_deployment_{reason}",
            ):
                compose_g0_deployment(
                    safe_environ(**changes),
                    config_factory=FakeConfig,
                    server_factory=FakeServer,
                )


class G0DeploymentRunnerTests(unittest.IsolatedAsyncioTestCase):
    def build(self, server_factory=FakeServer):
        return compose_g0_deployment(
            safe_environ(),
            config_factory=FakeConfig,
            server_factory=server_factory,
        )

    async def test_signal_stops_ingress_then_server_and_restores_handlers(self):
        deployment = self.build()
        signals = FakeSignals()
        runner = G0DeploymentRunner(
            signal_getter=signals.get,
            signal_setter=signals.set,
        )

        pending = asyncio.create_task(runner.run(deployment))
        await asyncio.wait_for(deployment.server.started.wait(), timeout=1)
        signals.emit(signal.SIGTERM)
        result = await asyncio.wait_for(pending, timeout=1)

        self.assertEqual(result.status, G0RunnerStatus.GRACEFUL_STOP)
        self.assertTrue(deployment.stop_controller.stopped)
        self.assertGreaterEqual(deployment.server.request_exit_calls, 1)
        self.assertEqual(deployment.server.force_stop_calls, 0)
        self.assertEqual(signals.handlers[signal.SIGINT], "previous-int")
        self.assertEqual(signals.handlers[signal.SIGTERM], "previous-term")

    async def test_shutdown_timeout_forces_and_cancels_server(self):
        deployment = self.build(StubbornServer)
        deployment = replace(
            deployment,
            config=replace(
                deployment.config,
                graceful_shutdown_timeout_seconds=0.01,
            ),
        )
        signals = FakeSignals()
        runner = G0DeploymentRunner(
            signal_getter=signals.get,
            signal_setter=signals.set,
        )

        pending = asyncio.create_task(runner.run(deployment))
        await asyncio.wait_for(deployment.server.started.wait(), timeout=1)
        signals.emit(signal.SIGINT)
        result = await asyncio.wait_for(pending, timeout=1)

        self.assertEqual(result.status, G0RunnerStatus.FORCED_STOP)
        self.assertEqual(result.reason, "g0_shutdown_timeout")
        self.assertEqual(deployment.server.force_stop_calls, 1)
        self.assertTrue(deployment.server.cancelled)
        self.assertEqual(signals.handlers[signal.SIGINT], "previous-int")
        self.assertEqual(signals.handlers[signal.SIGTERM], "previous-term")

    async def test_unexpected_server_exit_is_terminal_and_safe(self):
        deployment = self.build(ExitingServer)
        signals = FakeSignals()
        result = await G0DeploymentRunner(
            signal_getter=signals.get,
            signal_setter=signals.set,
        ).run(deployment)

        self.assertEqual(result.status, G0RunnerStatus.SERVER_EXITED)
        self.assertTrue(deployment.stop_controller.stopped)
        self.assertEqual(signals.handlers[signal.SIGINT], "previous-int")
        self.assertEqual(signals.handlers[signal.SIGTERM], "previous-term")

    async def test_runner_cancellation_cleans_server_and_signals(self):
        deployment = self.build(StubbornServer)
        signals = FakeSignals()
        pending = asyncio.create_task(
            G0DeploymentRunner(
                signal_getter=signals.get,
                signal_setter=signals.set,
            ).run(deployment)
        )
        await asyncio.wait_for(deployment.server.started.wait(), timeout=1)

        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending

        self.assertTrue(deployment.stop_controller.stopped)
        self.assertTrue(deployment.server.cancelled)
        self.assertEqual(signals.handlers[signal.SIGINT], "previous-int")
        self.assertEqual(signals.handlers[signal.SIGTERM], "previous-term")


class G0DeploymentIsolationTests(unittest.TestCase):
    def test_module_is_not_mounted_and_never_loads_dotenv(self):
        source = Path("bitrix_connector/g0_deployment.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("load_dotenv", source)
        self.assertNotIn("from main", source)
        self.assertNotIn("import main", source)
        for path in ("main.py", "bitrix_connector/router.py"):
            mounted = Path(path).read_text(encoding="utf-8")
            self.assertNotIn("g0_deployment", mounted)
            self.assertNotIn("compose_g0_deployment", mounted)
        example = Path(".env.example").read_text(encoding="utf-8")
        self.assertIn("NIA_BITRIX_G0_PUBLIC_ORIGIN=", example)


if __name__ == "__main__":
    unittest.main()

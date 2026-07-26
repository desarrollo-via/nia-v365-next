import shutil
import threading
import time
import unittest
from pathlib import Path
from uuid import uuid4

import httpx

from bitrix_connector.review_admin_local import (
    LOCAL_ADMIN_ORIGIN,
    LOCAL_BIND_HOST,
    LOCAL_BIND_PORT,
    RUNTIME_ROOT,
    build_local_fixture_runtime,
    local_off_state,
    run_local_fixture_server,
)


BOOTSTRAP_CODE = "bootstrap-local-controlado-0000000000000001"


def same_origin_headers():
    return {
        "Origin": LOCAL_ADMIN_ORIGIN,
        "Sec-Fetch-Site": "same-origin",
    }


class FakeConfig:
    def __init__(self, **values):
        self.values = values


class FakeServer:
    instances = []

    def __init__(self, config):
        self.config = config
        self.ran = False
        self.__class__.instances.append(self)

    def run(self):
        self.ran = True


class ControlledFakeServer(FakeServer):
    def __init__(self, config):
        super().__init__(config)
        self.started = False
        self.should_exit = False
        self.force_exit = False
        self.stopped_cleanly = False

    def run(self):
        self.ran = True
        self.started = True
        while not self.should_exit and not self.force_exit:
            time.sleep(0.01)
        self.stopped_cleanly = self.should_exit and not self.force_exit


class ReviewAdminLocalCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_runtime_logs_in_and_never_enables_decisions(self):
        runtime = build_local_fixture_runtime(
            bootstrap_code=BOOTSTRAP_CODE
        )
        transport = httpx.ASGITransport(app=runtime.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=LOCAL_ADMIN_ORIGIN,
        ) as client:
            state = await client.get("/state")
            login = await client.post(
                "/session",
                headers=same_origin_headers(),
                json={"credential": BOOTSTRAP_CODE},
            )
            reviews = await client.get("/reviews")
            event_key = reviews.json()["selected"]["event_key"]
            blocked = await client.post(
                f"/decisions/{event_key}/approve-input",
                headers={
                    **same_origin_headers(),
                    "X-CSRF-Token": login.json()["csrf_token"],
                    "Content-Type": "application/json",
                },
                json={},
            )

        self.assertEqual(state.status_code, 200)
        self.assertEqual(
            state.json(),
            {
                "effective_mode": "off",
                "activation_locked": True,
                "external_calls_enabled": False,
                "pilot_enabled": False,
                "pilot_emergency_stop": True,
                "decisions_allowed": False,
            },
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(reviews.status_code, 200)
        self.assertEqual(reviews.json()["source"], "fixture")
        self.assertTrue(reviews.json()["read_only"])
        self.assertFalse(reviews.json()["actions_enabled"])
        self.assertEqual(blocked.status_code, 503)
        self.assertEqual(
            blocked.json()["code"],
            "review_admin_decisions_locked",
        )
        self.assertEqual(runtime.decision_controller.calls, 0)
        self.assertNotIn(BOOTSTRAP_CODE, repr(runtime.__dict__))
        await runtime.close()
        self.assertTrue(runtime.sessions.closed)
        self.assertTrue(runtime.authenticator.closed)
        self.assertTrue(runtime.decision_controller.closed)

    async def test_local_state_is_permanently_off(self):
        state = local_off_state()
        self.assertEqual(state.effective_mode, "off")
        self.assertTrue(state.activation_locked)
        self.assertFalse(state.external_calls_enabled)
        self.assertFalse(state.decisions_allowed)


class ReviewAdminLocalRunnerTests(unittest.TestCase):
    def setUp(self):
        FakeServer.instances.clear()
        RUNTIME_ROOT.mkdir(exist_ok=True)
        self.run_directory = RUNTIME_ROOT / f"test-{uuid4().hex}"
        self.run_directory.mkdir()
        self.certificate = self.run_directory / "cert.pem"
        self.private_key = self.run_directory / "key.pem"
        self.ready_file = self.run_directory / "ready.signal"
        self.stop_file = self.run_directory / "stop.signal"
        self.bootstrap_file = self.run_directory / "bootstrap.secret"
        self.certificate.write_text("CERTIFICADO CONTROLADO", encoding="utf-8")
        self.private_key.write_text("CLAVE CONTROLADA", encoding="utf-8")

    def tearDown(self):
        if self.run_directory.exists():
            shutil.rmtree(self.run_directory)
        if RUNTIME_ROOT.exists() and not any(RUNTIME_ROOT.iterdir()):
            RUNTIME_ROOT.rmdir()

    def test_runner_fixes_loopback_tls_single_worker_and_prints_code_once(self):
        output = []

        result = run_local_fixture_server(
            cert_file=str(self.certificate),
            key_file=str(self.private_key),
            bootstrap_factory=lambda: BOOTSTRAP_CODE,
            output=output.append,
            config_factory=FakeConfig,
            server_factory=FakeServer,
        )

        self.assertEqual(result, 0)
        self.assertEqual(len(FakeServer.instances), 1)
        server = FakeServer.instances[0]
        self.assertTrue(server.ran)
        values = server.config.values
        self.assertEqual(values["host"], LOCAL_BIND_HOST)
        self.assertEqual(values["port"], LOCAL_BIND_PORT)
        self.assertEqual(values["workers"], 1)
        self.assertFalse(values["reload"])
        self.assertFalse(values["access_log"])
        self.assertEqual(values["ssl_certfile"], str(self.certificate.resolve()))
        self.assertEqual(values["ssl_keyfile"], str(self.private_key.resolve()))
        self.assertEqual("\n".join(output).count(BOOTSTRAP_CODE), 1)
        runtime = values["app"]
        self.assertTrue(runtime.state.review_admin_local_fixture)
        controller = runtime.state.review_admin_fixture_decision_controller
        self.assertEqual(controller.calls, 0)
        self.assertTrue(controller.closed)

    def test_real_uvicorn_config_is_constructed_but_server_remains_fake(self):
        result = run_local_fixture_server(
            cert_file=str(self.certificate),
            key_file=str(self.private_key),
            bootstrap_factory=lambda: BOOTSTRAP_CODE,
            output=lambda _message: None,
            server_factory=FakeServer,
        )

        self.assertEqual(result, 0)
        self.assertEqual(len(FakeServer.instances), 1)
        server = FakeServer.instances[0]
        self.assertTrue(server.ran)
        self.assertEqual(server.config.host, LOCAL_BIND_HOST)
        self.assertEqual(server.config.port, LOCAL_BIND_PORT)
        self.assertEqual(server.config.workers, 1)
        self.assertFalse(server.config.reload)
        self.assertFalse(server.config.access_log)
        self.assertEqual(
            server.config.ssl_certfile,
            str(self.certificate.resolve()),
        )
        self.assertEqual(
            server.config.ssl_keyfile,
            str(self.private_key.resolve()),
        )

    def test_control_files_mark_ready_then_stop_server_cleanly(self):
        output = []
        delivered_bootstrap = []

        def request_stop():
            deadline = time.monotonic() + 2.0
            while not self.ready_file.exists():
                if time.monotonic() >= deadline:
                    return
                time.sleep(0.01)
            delivered_bootstrap.append(
                self.bootstrap_file.read_text(encoding="utf-8")
            )
            self.bootstrap_file.unlink()
            self.stop_file.write_text("stop", encoding="ascii")

        stopper = threading.Thread(target=request_stop)
        stopper.start()
        result = run_local_fixture_server(
            cert_file=str(self.certificate),
            key_file=str(self.private_key),
            ready_file=str(self.ready_file),
            stop_file=str(self.stop_file),
            bootstrap_file=str(self.bootstrap_file),
            bootstrap_factory=lambda: BOOTSTRAP_CODE,
            output=output.append,
            config_factory=FakeConfig,
            server_factory=ControlledFakeServer,
        )
        stopper.join(2.0)

        self.assertEqual(result, 0)
        self.assertTrue(self.ready_file.exists())
        self.assertTrue(self.stop_file.exists())
        self.assertFalse(self.bootstrap_file.exists())
        self.assertEqual(delivered_bootstrap, [BOOTSTRAP_CODE])
        self.assertIn("HTTPS LISTO", "\n".join(output))
        self.assertNotIn(BOOTSTRAP_CODE, "\n".join(output))
        server = ControlledFakeServer.instances[-1]
        self.assertTrue(server.started)
        self.assertTrue(server.stopped_cleanly)
        self.assertFalse(server.force_exit)
        controller = (
            server.config.values["app"]
            .state.review_admin_fixture_decision_controller
        )
        self.assertTrue(controller.closed)

    def test_tls_files_must_be_pem_inside_exact_runtime_root(self):
        outside = Path(f"outside-review-admin-{uuid4().hex}.pem").resolve()
        outside.write_text("FUERA", encoding="utf-8")
        try:
            with self.assertRaisesRegex(
                ValueError,
                "review_admin_certificate_outside_runtime",
            ):
                run_local_fixture_server(
                    cert_file=str(outside),
                    key_file=str(self.private_key),
                    config_factory=FakeConfig,
                    server_factory=FakeServer,
                )
        finally:
            outside.unlink()

        invalid = self.run_directory / "cert.txt"
        invalid.write_text("INVALIDO", encoding="utf-8")
        with self.assertRaisesRegex(
            ValueError,
            "review_admin_certificate_invalid",
        ):
            run_local_fixture_server(
                cert_file=str(invalid),
                key_file=str(self.private_key),
                config_factory=FakeConfig,
                server_factory=FakeServer,
            )

    def test_module_and_launcher_are_fixed_fixture_only_contracts(self):
        module_source = Path(
            "bitrix_connector/review_admin_local.py"
        ).read_text(encoding="utf-8")
        launcher_source = Path(
            "scripts/lanzar_review_admin_https.ps1"
        ).read_text(encoding="utf-8")
        admin_source = Path(
            "bitrix_connector/review_admin.py"
        ).read_text(encoding="utf-8")

        for forbidden in (
            "main.py",
            "load_settings",
            "os.environ",
            "HttpReviewLabAdapter",
            "Mongo",
            "NiaClient",
            "BitrixClient",
        ):
            self.assertNotIn(forbidden, module_source)
        self.assertIn('LOCAL_BIND_HOST = "127.0.0.1"', module_source)
        self.assertIn("FixtureReviewLabAdapter()", module_source)
        self.assertIn("FixtureDecisionForbidden()", module_source)
        self.assertIn("[switch]$OpenBrowser", launcher_source)
        self.assertIn(
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            launcher_source,
        )
        self.assertIn('Name = \'chrome.exe\'', launcher_source)
        self.assertNotIn("msedge.exe", launcher_source)
        self.assertIn("--allow-insecure-localhost", launcher_source)
        self.assertNotIn("--ignore-certificate-errors", launcher_source)
        self.assertNotIn("New-SelfSignedCertificate", launcher_source)
        self.assertNotIn("Import-Certificate", launcher_source)
        self.assertNotIn(".env", launcher_source)
        self.assertIn("1.3.6.1.5.5.7.3.1", launcher_source)
        self.assertIn("GetCertHashString", launcher_source)
        self.assertIn('"ready.signal"', launcher_source)
        self.assertIn('"stop.signal"', launcher_source)
        self.assertIn('"bootstrap.secret"', launcher_source)
        self.assertIn('"--bootstrap-file"', launcher_source)
        self.assertIn("#nia-bootstrap=$encodedBootstrap", launcher_source)
        self.assertIn("Presiona ENTER para cerrar limpiamente", launcher_source)
        self.assertIn('setattr(server, "should_exit", True)', module_source)
        self.assertIn("window.location.hash", admin_source)
        self.assertIn("window.history.replaceState", admin_source)
        self.assertIn("parameters.get('nia-bootstrap')", admin_source)
        self.assertIn("fragmentBootstrap=''", admin_source)
        ready_wait = launcher_source.index(
            "while (-not (Test-Path -LiteralPath $readyPath"
        )
        bootstrap_read = launcher_source.index(
            "[System.IO.File]::ReadAllText($bootstrapPath)"
        )
        bootstrap_remove = launcher_source.index(
            "Remove-Item -LiteralPath $bootstrapPath"
        )
        chrome_start = launcher_source.index(
            "$chromeProcess = Start-Process"
        )
        self.assertLess(ready_wait, bootstrap_read)
        self.assertLess(bootstrap_read, bootstrap_remove)
        self.assertLess(bootstrap_remove, chrome_start)


if __name__ == "__main__":
    unittest.main()

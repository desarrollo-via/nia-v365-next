import argparse
import ast
import asyncio
import json
import signal
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, patch

from nia_process_launcher import (
    DEFAULT_WEB_COMMAND,
    build_config,
    build_parser,
    create_managed_process,
    install_stop_signal_handlers,
    run_from_args,
)
from nia_process_supervisor import ProcessRole, ProcessSpec


ROOT = Path(__file__).resolve().parents[1]


class FakeProcess:
    def __init__(self, *, exit_code: Optional[int] = None) -> None:
        self._returncode = exit_code
        self._done = asyncio.get_running_loop().create_future()
        if exit_code is not None:
            self._done.set_result(exit_code)
        self.terminate_calls = 0
        self.kill_calls = 0

    @property
    def returncode(self) -> Optional[int]:
        return self._returncode

    async def wait(self) -> int:
        return await asyncio.shield(self._done)

    def terminate(self) -> None:
        self.terminate_calls += 1
        self._returncode = -15
        if not self._done.done():
            self._done.set_result(-15)

    def kill(self) -> None:
        self.kill_calls += 1
        self._returncode = -9
        if not self._done.done():
            self._done.set_result(-9)


class RecordingFactory:
    def __init__(self, web: object, worker: Optional[object] = None) -> None:
        self.web = web
        self.worker = worker
        self.calls: list[ProcessSpec] = []

    async def __call__(self, spec: ProcessSpec) -> FakeProcess:
        self.calls.append(spec)
        selected = self.web if spec.role is ProcessRole.WEB else self.worker
        if isinstance(selected, Exception):
            raise selected
        if selected is None:
            raise AssertionError("unexpected_process")
        return selected  # type: ignore[return-value]


def immediate_stop_installer(request_stop: object):
    request_stop()  # type: ignore[operator]
    return lambda: None


class LauncherConfigurationTests(unittest.TestCase):
    def test_default_command_matches_observed_azure_startup(self) -> None:
        self.assertEqual(
            DEFAULT_WEB_COMMAND,
            (
                "gunicorn", "-w", "1", "-k",
                "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000",
                "main:app", "--timeout", "600", "--access-logfile", "-",
                "--error-logfile", "-",
            ),
        )

    def test_config_uses_strict_master_switch(self) -> None:
        args = build_parser().parse_args([])
        self.assertFalse(build_config(args, environ={}).worker_enabled)
        self.assertTrue(
            build_config(
                args,
                environ={"NIA_BITRIX_MODULE_ENABLED": " true "},
            ).worker_enabled
        )
        self.assertFalse(
            build_config(
                args,
                environ={"NIA_BITRIX_MODULE_ENABLED": "active"},
            ).worker_enabled
        )

    def test_invalid_limits_fail_before_any_process(self) -> None:
        args = argparse.Namespace(
            max_worker_restarts=-1,
            restart_backoff_seconds=1.0,
            shutdown_timeout_seconds=10.0,
        )
        with self.assertRaisesRegex(ValueError, "supervisor_worker_restarts_invalid"):
            build_config(args, environ={})

    def test_source_does_not_load_dotenv_or_use_a_shell(self) -> None:
        source = (ROOT / "nia_process_launcher.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        attributes = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        self.assertNotIn("create_subprocess_shell", attributes)
        self.assertNotIn("dotenv", source.lower())
        self.assertFalse(
            any(
                keyword.arg == "shell"
                for call in calls
                for keyword in call.keywords
            )
        )


class LauncherRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_signal_adapter_installs_and_removes_int_and_term(self) -> None:
        class FakeLoop:
            def __init__(self) -> None:
                self.added: list[tuple[signal.Signals, object]] = []
                self.removed: list[signal.Signals] = []

            def add_signal_handler(self, name: signal.Signals, callback: object) -> None:
                self.added.append((name, callback))

            def remove_signal_handler(self, name: signal.Signals) -> bool:
                self.removed.append(name)
                return True

        loop = FakeLoop()
        callback = lambda: None
        with patch("nia_process_launcher.asyncio.get_running_loop", return_value=loop):
            cleanup = install_stop_signal_handlers(callback)
            cleanup()
        self.assertEqual(
            [item[0] for item in loop.added],
            [signal.SIGINT, signal.SIGTERM],
        )
        self.assertTrue(all(item[1] is callback for item in loop.added))
        self.assertEqual(loop.removed, [signal.SIGINT, signal.SIGTERM])

    async def test_signal_adapter_cleans_partial_installation_on_failure(self) -> None:
        class FailingLoop:
            def __init__(self) -> None:
                self.removed: list[signal.Signals] = []

            def add_signal_handler(self, name: signal.Signals, _: object) -> None:
                if name is signal.SIGTERM:
                    raise RuntimeError("signal_install_failed")

            def remove_signal_handler(self, name: signal.Signals) -> bool:
                self.removed.append(name)
                return True

        loop = FailingLoop()
        with patch("nia_process_launcher.asyncio.get_running_loop", return_value=loop):
            with self.assertRaisesRegex(RuntimeError, "signal_install_failed"):
                install_stop_signal_handlers(lambda: None)
        self.assertEqual(loop.removed, [signal.SIGINT])

    async def test_process_adapter_uses_exec_with_exact_argv(self) -> None:
        expected = object()
        mocked = AsyncMock(return_value=expected)
        spec = ProcessSpec(ProcessRole.WEB, ("program", "arg with spaces"))
        with patch("nia_process_launcher.asyncio.create_subprocess_exec", mocked):
            actual = await create_managed_process(spec)
        self.assertIs(actual, expected)
        mocked.assert_awaited_once_with("program", "arg with spaces")

    async def test_off_starts_only_web_and_returns_cleanly_on_signal(self) -> None:
        web = FakeProcess()
        factory = RecordingFactory(web)
        output: list[str] = []
        code = await run_from_args(
            build_parser().parse_args([]),
            environ={},
            process_factory=factory,
            signal_installer=immediate_stop_installer,
            write_result=output.append,
        )
        self.assertEqual(code, 0)
        self.assertEqual([item.role for item in factory.calls], [ProcessRole.WEB])
        self.assertEqual(web.terminate_calls, 1)
        self.assertEqual(json.loads(output[0])["reason"], "stop_requested")

    async def test_enabled_starts_distinct_worker_without_shell(self) -> None:
        web = FakeProcess()
        worker = FakeProcess()
        factory = RecordingFactory(web, worker)
        installed: list[object] = []

        def capture_stop(request_stop: object):
            installed.append(request_stop)
            return lambda: None

        task = asyncio.create_task(
            run_from_args(
                build_parser().parse_args([]),
                environ={"NIA_BITRIX_MODULE_ENABLED": "true"},
                process_factory=factory,
                signal_installer=capture_stop,
                write_result=lambda _: None,
            )
        )
        while len(factory.calls) < 2:
            await asyncio.sleep(0)
        installed[0]()  # type: ignore[operator]
        code = await task
        self.assertEqual(code, 0)
        self.assertEqual(
            [item.role for item in factory.calls],
            [ProcessRole.WEB, ProcessRole.WORKER],
        )
        self.assertEqual(
            factory.calls[1].command,
            ("python", "-m", "bitrix_connector.worker_cli"),
        )

    async def test_web_exit_code_is_propagated(self) -> None:
        factory = RecordingFactory(FakeProcess(exit_code=7))
        output: list[str] = []
        code = await run_from_args(
            build_parser().parse_args([]),
            environ={},
            process_factory=factory,
            signal_installer=lambda _: (lambda: None),
            write_result=output.append,
        )
        self.assertEqual(code, 7)
        self.assertEqual(json.loads(output[0])["web_exit_code"], 7)

    async def test_web_start_failure_is_redacted_and_nonzero(self) -> None:
        output: list[str] = []
        cleanup_calls: list[bool] = []
        code = await run_from_args(
            build_parser().parse_args([]),
            environ={},
            process_factory=RecordingFactory(RuntimeError("secret-value")),
            signal_installer=lambda _: (lambda: cleanup_calls.append(True)),
            write_result=output.append,
        )
        self.assertEqual(code, 1)
        self.assertEqual(cleanup_calls, [True])
        self.assertNotIn("secret-value", output[0])
        self.assertEqual(
            json.loads(output[0])["reason"],
            "web_process_start_failed",
        )


if __name__ == "__main__":
    unittest.main()

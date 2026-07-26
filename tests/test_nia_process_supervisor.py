import ast
import asyncio
import unittest
from pathlib import Path
from typing import Optional

from nia_process_supervisor import (
    EmbeddedProcessSupervisor,
    EmbeddedSupervisorConfig,
    ProcessRole,
    ProcessSpec,
    SupervisorStartError,
)


ROOT = Path(__file__).resolve().parents[1]
WEB_COMMAND = ("nia-web", "--serve")


class FakeProcess:
    def __init__(self, *, terminate_completes: bool = True) -> None:
        self._returncode: Optional[int] = None
        self._done = asyncio.get_running_loop().create_future()
        self.terminate_completes = terminate_completes
        self.terminate_calls = 0
        self.kill_calls = 0

    @property
    def returncode(self) -> Optional[int]:
        return self._returncode

    async def wait(self) -> int:
        return await asyncio.shield(self._done)

    def exit(self, code: int) -> None:
        if self._done.done():
            return
        self._returncode = code
        self._done.set_result(code)

    def terminate(self) -> None:
        self.terminate_calls += 1
        if self.terminate_completes:
            self.exit(-15)

    def kill(self) -> None:
        self.kill_calls += 1
        self.exit(-9)


class FakeFactory:
    def __init__(self, web: object, workers: list[object]) -> None:
        self.web = web
        self.workers = list(workers)
        self.calls: list[ProcessSpec] = []

    async def __call__(self, spec: ProcessSpec) -> FakeProcess:
        self.calls.append(spec)
        item = self.web if spec.role is ProcessRole.WEB else self.workers.pop(0)
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[return-value]


async def wait_until(predicate: object, timeout: float = 0.25) -> None:
    async def poll() -> None:
        while not predicate():  # type: ignore[operator]
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), timeout=timeout)


async def no_delay(_: float) -> None:
    await asyncio.sleep(0)


class EmbeddedSupervisorTests(unittest.IsolatedAsyncioTestCase):
    def test_config_uses_master_switch_and_rejects_invalid_limits(self) -> None:
        off = EmbeddedSupervisorConfig.from_environ(
            web_command=WEB_COMMAND,
            environ={},
        )
        on = EmbeddedSupervisorConfig.from_environ(
            web_command=WEB_COMMAND,
            environ={"NIA_BITRIX_MODULE_ENABLED": "true"},
        )
        invalid = EmbeddedSupervisorConfig.from_environ(
            web_command=WEB_COMMAND,
            environ={"NIA_BITRIX_MODULE_ENABLED": "active"},
        )
        self.assertFalse(off.worker_enabled)
        self.assertTrue(on.worker_enabled)
        self.assertFalse(invalid.worker_enabled)
        with self.assertRaisesRegex(ValueError, "supervisor_worker_restarts_invalid"):
            EmbeddedSupervisorConfig(web_command=WEB_COMMAND, max_worker_restarts=-1)

    async def test_disabled_switch_starts_only_web(self) -> None:
        web = FakeProcess()
        factory = FakeFactory(web, [])
        stop = asyncio.Event()
        task = asyncio.create_task(
            EmbeddedProcessSupervisor(factory).run(
                EmbeddedSupervisorConfig(web_command=WEB_COMMAND),
                stop_event=stop,
            )
        )
        await wait_until(lambda: len(factory.calls) == 1)
        stop.set()
        result = await task

        self.assertEqual([call.role for call in factory.calls], [ProcessRole.WEB])
        self.assertEqual(result.reason, "stop_requested")
        self.assertEqual(result.worker_attempts, 0)
        self.assertEqual(web.terminate_calls, 1)

    async def test_enabled_switch_starts_web_then_worker_as_distinct_processes(self) -> None:
        web = FakeProcess()
        worker = FakeProcess()
        factory = FakeFactory(web, [worker])
        stop = asyncio.Event()
        task = asyncio.create_task(
            EmbeddedProcessSupervisor(factory).run(
                EmbeddedSupervisorConfig(
                    web_command=WEB_COMMAND,
                    worker_enabled=True,
                ),
                stop_event=stop,
            )
        )
        await wait_until(lambda: len(factory.calls) == 2)
        stop.set()
        result = await task

        self.assertEqual(
            [call.role for call in factory.calls],
            [ProcessRole.WEB, ProcessRole.WORKER],
        )
        self.assertEqual(result.reason, "stop_requested")
        self.assertEqual(worker.terminate_calls, 1)
        self.assertEqual(web.terminate_calls, 1)

    async def test_worker_start_failures_are_bounded_and_do_not_stop_web(self) -> None:
        web = FakeProcess()
        factory = FakeFactory(
            web,
            [RuntimeError("first"), RuntimeError("second")],
        )
        supervisor = EmbeddedProcessSupervisor(factory, sleep=no_delay)
        task = asyncio.create_task(
            supervisor.run(
                EmbeddedSupervisorConfig(
                    web_command=WEB_COMMAND,
                    worker_enabled=True,
                    max_worker_restarts=1,
                )
            )
        )
        await wait_until(lambda: len(factory.calls) == 3)
        self.assertIsNone(web.returncode)
        web.exit(0)
        result = await task

        self.assertEqual(result.reason, "web_exited")
        self.assertEqual(result.worker_attempts, 2)
        self.assertEqual(result.worker_restarts, 1)
        self.assertTrue(result.worker_exhausted)
        self.assertEqual(web.terminate_calls, 0)

    async def test_worker_exit_restarts_without_terminating_web(self) -> None:
        web = FakeProcess()
        first = FakeProcess()
        second = FakeProcess()
        factory = FakeFactory(web, [first, second])
        task = asyncio.create_task(
            EmbeddedProcessSupervisor(factory, sleep=no_delay).run(
                EmbeddedSupervisorConfig(
                    web_command=WEB_COMMAND,
                    worker_enabled=True,
                    max_worker_restarts=1,
                )
            )
        )
        await wait_until(lambda: len(factory.calls) == 2)
        first.exit(1)
        await wait_until(lambda: len(factory.calls) == 3)
        self.assertIsNone(web.returncode)
        second.exit(1)
        await asyncio.sleep(0)
        web.exit(0)
        result = await task

        self.assertEqual(result.worker_attempts, 2)
        self.assertEqual(result.worker_restarts, 1)
        self.assertTrue(result.worker_exhausted)
        self.assertEqual(web.terminate_calls, 0)

    async def test_web_exit_stops_live_worker(self) -> None:
        web = FakeProcess()
        worker = FakeProcess()
        factory = FakeFactory(web, [worker])
        task = asyncio.create_task(
            EmbeddedProcessSupervisor(factory).run(
                EmbeddedSupervisorConfig(
                    web_command=WEB_COMMAND,
                    worker_enabled=True,
                )
            )
        )
        await wait_until(lambda: len(factory.calls) == 2)
        web.exit(4)
        result = await task

        self.assertEqual(result.reason, "web_exited")
        self.assertEqual(result.web_exit_code, 4)
        self.assertEqual(worker.terminate_calls, 1)

    async def test_shutdown_forces_only_processes_that_exceed_timeout(self) -> None:
        web = FakeProcess(terminate_completes=False)
        worker = FakeProcess(terminate_completes=False)
        factory = FakeFactory(web, [worker])
        stop = asyncio.Event()
        task = asyncio.create_task(
            EmbeddedProcessSupervisor(factory).run(
                EmbeddedSupervisorConfig(
                    web_command=WEB_COMMAND,
                    worker_enabled=True,
                    shutdown_timeout_seconds=0.001,
                ),
                stop_event=stop,
            )
        )
        await wait_until(lambda: len(factory.calls) == 2)
        stop.set()
        result = await task

        self.assertEqual(result.forced_kills, 2)
        self.assertEqual(worker.kill_calls, 1)
        self.assertEqual(web.kill_calls, 1)

    async def test_web_start_failure_is_safe_and_supervisor_is_single_use(self) -> None:
        failed = EmbeddedProcessSupervisor(
            FakeFactory(RuntimeError("sensitive"), [])
        )
        with self.assertRaisesRegex(SupervisorStartError, "web_process_start_failed"):
            await failed.run(EmbeddedSupervisorConfig(web_command=WEB_COMMAND))
        with self.assertRaisesRegex(RuntimeError, "supervisor_single_use"):
            await failed.run(EmbeddedSupervisorConfig(web_command=WEB_COMMAND))

    def test_module_contains_no_real_process_factory_or_cli(self) -> None:
        source = (ROOT / "nia_process_supervisor.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        attributes = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        self.assertNotIn("subprocess", imported)
        self.assertNotIn("create_subprocess_exec", attributes)
        self.assertNotIn("create_subprocess_shell", attributes)
        self.assertNotIn("__main__", source)


if __name__ == "__main__":
    unittest.main()

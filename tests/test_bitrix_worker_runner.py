import asyncio
import unittest
from types import SimpleNamespace

from bitrix_connector.worker import ConnectorWorkerRunStatus
from bitrix_connector.worker_resources import WorkerResourceOptions
from bitrix_connector.worker_runner import (
    ConnectorWorkerRunner,
    WorkerRunnerStatus,
)


def cycle(status):
    stage = SimpleNamespace(status=status)
    return SimpleNamespace(preflight=stage, nia=stage, bitrix=stage)


class FakeResources:
    def __init__(self, composition, log):
        self.composition = composition
        self.log = log
        self.close_count = 0

    async def close(self):
        self.close_count += 1
        self.log.append("closed")


class FakeFactory:
    def __init__(self, resources):
        self.resources = resources
        self.calls = []

    async def build(self, settings, options):
        self.calls.append((settings, options))
        return self.resources


class WorkerRunnerTests(unittest.IsolatedAsyncioTestCase):
    def options(self):
        return WorkerResourceOptions(worker_id="worker-test")

    async def test_inert_factory_returns_without_polling(self):
        factory = FakeFactory(None)
        settings = object()
        runner = ConnectorWorkerRunner(
            factory,
            settings_provider=lambda: settings,
            poll_seconds=0.01,
        )

        result = await runner.run(self.options())

        self.assertEqual(result.status, WorkerRunnerStatus.INERT)
        self.assertEqual(result.cycles, 0)
        self.assertEqual(result.reason, "connector_safety_barrier_active")
        self.assertIs(factory.calls[0][0], settings)

    async def test_idle_cycle_wait_is_interruptible_and_resources_close(self):
        log = []
        stop = asyncio.Event()

        class IdleComposition:
            async def run_once(self):
                log.append("cycle")
                stop.set()
                return cycle(ConnectorWorkerRunStatus.IDLE)

        resources = FakeResources(IdleComposition(), log)
        runner = ConnectorWorkerRunner(
            FakeFactory(resources),
            settings_provider=object,
            poll_seconds=30,
        )

        result = await runner.run(self.options(), stop_event=stop)

        self.assertEqual(result.status, WorkerRunnerStatus.STOPPED)
        self.assertEqual(result.cycles, 1)
        self.assertEqual(log, ["cycle", "closed"])
        self.assertEqual(resources.close_count, 1)

    async def test_non_idle_cycle_yields_and_stops_without_poll_delay(self):
        log = []
        stop = asyncio.Event()

        class BusyComposition:
            async def run_once(self):
                log.append("cycle")
                stop.set()
                return cycle(ConnectorWorkerRunStatus.COMPLETED)

        resources = FakeResources(BusyComposition(), log)
        runner = ConnectorWorkerRunner(
            FakeFactory(resources),
            settings_provider=object,
            poll_seconds=30,
        )

        result = await asyncio.wait_for(
            runner.run(self.options(), stop_event=stop),
            timeout=0.5,
        )

        self.assertEqual(result.cycles, 1)
        self.assertEqual(log, ["cycle", "closed"])

    async def test_cycle_failure_still_closes_resources(self):
        log = []

        class BrokenComposition:
            async def run_once(self):
                raise RuntimeError("cycle failure")

        resources = FakeResources(BrokenComposition(), log)
        runner = ConnectorWorkerRunner(
            FakeFactory(resources),
            settings_provider=object,
            poll_seconds=0.01,
        )

        with self.assertRaisesRegex(RuntimeError, "cycle failure"):
            await runner.run(self.options())

        self.assertEqual(resources.close_count, 1)
        self.assertEqual(log, ["closed"])

    async def test_pre_stopped_runner_builds_then_closes_without_cycle(self):
        log = []
        stop = asyncio.Event()
        stop.set()

        class ForbiddenComposition:
            async def run_once(self):
                raise AssertionError("no debe ejecutar ciclos")

        resources = FakeResources(ForbiddenComposition(), log)
        runner = ConnectorWorkerRunner(
            FakeFactory(resources),
            settings_provider=object,
        )

        result = await runner.run(self.options(), stop_event=stop)

        self.assertEqual(result.status, WorkerRunnerStatus.STOPPED)
        self.assertEqual(result.cycles, 0)
        self.assertEqual(log, ["closed"])

    def test_rejects_non_positive_poll_interval(self):
        with self.assertRaisesRegex(ValueError, "poll_seconds"):
            ConnectorWorkerRunner(FakeFactory(None), poll_seconds=0)


if __name__ == "__main__":
    unittest.main()

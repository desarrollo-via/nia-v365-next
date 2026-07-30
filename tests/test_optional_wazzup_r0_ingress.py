import ast
import unittest
from dataclasses import dataclass
from pathlib import Path

from optional_wazzup_r0_ingress import (
    ExactPathASGIDispatchMiddleware,
    OptionalWazzupR0IngressStatus,
    mount_optional_wazzup_r0_ingress,
)


ROOT = Path(__file__).resolve().parents[1]
SWITCH = "NIA_WAZZUP_R0_ADAPTER_ENABLED"
PATH = "/bitrix-connector/internal/wazzup-r0"


class FakeApp:
    def __init__(self) -> None:
        self.middleware: list[tuple[object, dict[str, object]]] = []

    def add_middleware(self, middleware: object, **kwargs: object) -> None:
        self.middleware.append((middleware, kwargs))


class RecordingLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def warning(self, *args: object) -> None:
        self.calls.append(args)


@dataclass
class FakeIngressMount:
    enabled: bool
    reason: str
    app: object | None


def ready_loader(
    *,
    app: object | None = None,
    reason: str = "fixture_ready",
):
    ingress_app = object() if app is None else app

    def factory(environ, *, scope, header_verifier):
        if environ.get(SWITCH) != "true":
            raise AssertionError("switch contract changed")
        if scope != "synthetic-scope":
            raise AssertionError("scope was not injected")
        if not header_verifier({"x-fixture": "ok"}):
            raise AssertionError("verifier was not injected")
        return FakeIngressMount(True, reason, ingress_app)

    return lambda: (factory, PATH)


class OptionalWazzupR0IngressTests(unittest.TestCase):
    def test_absent_or_false_switch_does_not_load_or_mount(self) -> None:
        for environ in ({}, {SWITCH: "false"}):
            app = FakeApp()

            def forbidden_loader():
                raise AssertionError("ingress must not load")

            with self.subTest(environ=environ):
                result = mount_optional_wazzup_r0_ingress(
                    app,
                    environ=environ,
                    ingress_factory_loader=forbidden_loader,
                )
                self.assertEqual(result.status, OptionalWazzupR0IngressStatus.DISABLED)
                self.assertFalse(result.enabled)
                self.assertEqual(app.middleware, [])

    def test_invalid_switch_fails_closed_without_loading(self) -> None:
        app = FakeApp()

        def forbidden_loader():
            raise AssertionError("ingress must not load")

        result = mount_optional_wazzup_r0_ingress(
            app,
            environ={SWITCH: "yes"},
            ingress_factory_loader=forbidden_loader,
        )

        self.assertEqual(result.status, OptionalWazzupR0IngressStatus.UNAVAILABLE)
        self.assertEqual(result.reason, "wazzup_r0_ingress_switch_invalid")
        self.assertEqual(app.middleware, [])

    def test_true_without_real_dependencies_remains_unavailable(self) -> None:
        app = FakeApp()

        def forbidden_loader():
            raise AssertionError("ingress must not load")

        result = mount_optional_wazzup_r0_ingress(
            app,
            environ={SWITCH: "true"},
            ingress_factory_loader=forbidden_loader,
        )

        self.assertEqual(result.status, OptionalWazzupR0IngressStatus.UNAVAILABLE)
        self.assertEqual(result.reason, "wazzup_r0_ingress_dependencies_missing")
        self.assertEqual(app.middleware, [])

    def test_injected_ready_ingress_mounts_exact_dispatcher_once(self) -> None:
        app = FakeApp()
        verifier = lambda headers: headers.get("x-fixture") == "ok"
        kwargs = {
            "environ": {SWITCH: "true"},
            "scope": "synthetic-scope",
            "header_verifier": verifier,
            "ingress_factory_loader": ready_loader(),
        }

        first = mount_optional_wazzup_r0_ingress(app, **kwargs)
        second = mount_optional_wazzup_r0_ingress(app, **kwargs)

        self.assertEqual(first.status, OptionalWazzupR0IngressStatus.MOUNTED)
        self.assertEqual(second.status, OptionalWazzupR0IngressStatus.ALREADY_MOUNTED)
        self.assertEqual(len(app.middleware), 1)
        middleware, options = app.middleware[0]
        self.assertIs(middleware, ExactPathASGIDispatchMiddleware)
        self.assertEqual(options["path"], PATH)

    def test_not_ready_mount_has_fixed_safe_reason(self) -> None:
        app = FakeApp()

        def factory(environ, *, scope, header_verifier):
            return FakeIngressMount(False, "secret-or-internal-detail", None)

        result = mount_optional_wazzup_r0_ingress(
            app,
            environ={SWITCH: "true"},
            scope="synthetic-scope",
            header_verifier=lambda headers: True,
            ingress_factory_loader=lambda: (factory, PATH),
        )

        self.assertEqual(result.reason, "wazzup_r0_ingress_not_ready")
        self.assertNotIn("secret", result.reason)
        self.assertEqual(app.middleware, [])

    def test_composition_failure_logs_only_exception_type(self) -> None:
        app = FakeApp()
        logger = RecordingLogger()

        def unavailable_loader():
            raise RuntimeError("secret-or-internal-detail")

        result = mount_optional_wazzup_r0_ingress(
            app,
            environ={SWITCH: "true"},
            scope="synthetic-scope",
            header_verifier=lambda headers: True,
            ingress_factory_loader=unavailable_loader,
            logger=logger,  # type: ignore[arg-type]
        )

        self.assertEqual(result.reason, "wazzup_r0_ingress_composition_failed")
        rendered = repr(logger.calls)
        self.assertIn("RuntimeError", rendered)
        self.assertNotIn("secret-or-internal-detail", rendered)

    def test_bridge_does_not_load_dotenv_or_open_files(self) -> None:
        source = (ROOT / "optional_wazzup_r0_ingress.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("dotenv", imported)
        self.assertNotIn("open", called_names)

    def test_main_uses_bridge_without_direct_connector_import(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertFalse(
            any(name.startswith("bitrix_connector") for name in imported_modules)
        )
        self.assertIn("optional_wazzup_r0_ingress", imported_modules)
        self.assertEqual(
            list(called_names).count("mount_optional_wazzup_r0_ingress"),
            1,
        )
        self.assertNotIn(PATH, source)
        compile(source, str(ROOT / "main.py"), "exec")


class ExactPathASGIDispatchMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatches_only_exact_http_path_without_reading(self) -> None:
        calls: list[str] = []

        async def downstream(scope, receive, send):
            calls.append("downstream")

        async def ingress(scope, receive, send):
            calls.append("ingress")

        async def forbidden_receive():
            raise AssertionError("dispatcher must not read the body")

        async def ignored_send(message):
            return None

        middleware = ExactPathASGIDispatchMiddleware(
            downstream,
            ingress_app=ingress,
            path=PATH,
        )
        await middleware(
            {"type": "http", "path": PATH},
            forbidden_receive,
            ignored_send,
        )
        await middleware(
            {"type": "http", "path": PATH + "/extra"},
            forbidden_receive,
            ignored_send,
        )
        await middleware(
            {"type": "lifespan", "path": PATH},
            forbidden_receive,
            ignored_send,
        )

        self.assertEqual(calls, ["ingress", "downstream", "downstream"])

import ast
import unittest
from pathlib import Path

from optional_bitrix_connector import (
    OptionalModuleStatus,
    is_bitrix_connector_enabled,
    mount_optional_bitrix_connector,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeApp:
    def __init__(self) -> None:
        self.routes = ["nia-health", "nia-chat"]

    def include_router(self, router: object) -> None:
        self.routes.append(router)


class RecordingLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def warning(self, *args: object) -> None:
        self.calls.append(args)


class OptionalBitrixConnectorTests(unittest.TestCase):
    def test_switch_defaults_to_disabled_and_accepts_only_literal_true(self) -> None:
        self.assertFalse(is_bitrix_connector_enabled({}))
        self.assertFalse(is_bitrix_connector_enabled({"NIA_BITRIX_MODULE_ENABLED": "false"}))
        self.assertFalse(is_bitrix_connector_enabled({"NIA_BITRIX_MODULE_ENABLED": "1"}))
        self.assertFalse(is_bitrix_connector_enabled({"NIA_BITRIX_MODULE_ENABLED": "yes"}))
        self.assertTrue(is_bitrix_connector_enabled({"NIA_BITRIX_MODULE_ENABLED": " TRUE "}))

    def test_disabled_switch_preserves_existing_nia_routes_without_loading(self) -> None:
        app = FakeApp()

        def forbidden_loader() -> object:
            raise AssertionError("router loader must not run")

        result = mount_optional_bitrix_connector(
            app,
            environ={"NIA_BITRIX_MODULE_ENABLED": "false"},
            router_loader=forbidden_loader,
        )

        self.assertEqual(result.status, OptionalModuleStatus.DISABLED)
        self.assertEqual(result.reason, "module_disabled")
        self.assertEqual(app.routes, ["nia-health", "nia-chat"])

    def test_invalid_switch_fails_closed_without_loading(self) -> None:
        app = FakeApp()
        called = False

        def loader() -> object:
            nonlocal called
            called = True
            return object()

        result = mount_optional_bitrix_connector(
            app,
            environ={"NIA_BITRIX_MODULE_ENABLED": "active"},
            router_loader=loader,
        )

        self.assertFalse(called)
        self.assertEqual(result.status, OptionalModuleStatus.DISABLED)
        self.assertEqual(result.reason, "module_switch_invalid")
        self.assertEqual(app.routes, ["nia-health", "nia-chat"])

    def test_enabled_switch_mounts_router_exactly_once(self) -> None:
        app = FakeApp()
        router = object()
        calls = 0

        def loader() -> object:
            nonlocal calls
            calls += 1
            return router

        first = mount_optional_bitrix_connector(
            app,
            environ={"NIA_BITRIX_MODULE_ENABLED": "true"},
            router_loader=loader,
        )
        second = mount_optional_bitrix_connector(
            app,
            environ={"NIA_BITRIX_MODULE_ENABLED": "true"},
            router_loader=loader,
        )

        self.assertEqual(first.status, OptionalModuleStatus.MOUNTED)
        self.assertEqual(second.status, OptionalModuleStatus.ALREADY_MOUNTED)
        self.assertEqual(calls, 1)
        self.assertEqual(app.routes, ["nia-health", "nia-chat", router])

    def test_missing_connector_does_not_change_nia_or_expose_error_text(self) -> None:
        app = FakeApp()
        logger = RecordingLogger()

        def missing_loader() -> object:
            raise ModuleNotFoundError("secret-path-or-value")

        result = mount_optional_bitrix_connector(
            app,
            environ={"NIA_BITRIX_MODULE_ENABLED": "true"},
            router_loader=missing_loader,
            logger=logger,  # type: ignore[arg-type]
        )

        self.assertEqual(result.status, OptionalModuleStatus.UNAVAILABLE)
        self.assertEqual(result.reason, "router_import_failed")
        self.assertEqual(app.routes, ["nia-health", "nia-chat"])
        rendered_log = repr(logger.calls)
        self.assertIn("ModuleNotFoundError", rendered_log)
        self.assertNotIn("secret-path-or-value", rendered_log)

    def test_bridge_does_not_load_dotenv_or_open_files(self) -> None:
        source = (ROOT / "optional_bitrix_connector.py").read_text(encoding="utf-8")
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

    def test_main_uses_bridge_without_top_level_connector_import(self) -> None:
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
        self.assertIn("optional_bitrix_connector", imported_modules)
        self.assertIn("mount_optional_bitrix_connector", called_names)
        compile(source, str(ROOT / "main.py"), "exec")


if __name__ == "__main__":
    unittest.main()

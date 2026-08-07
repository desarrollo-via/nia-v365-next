import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_session_builder_composition import (
    PreparedDormantProtectedSessionBuilderComposition,
    compose_dormant_protected_session_builder,
    preview_dormant_protected_session_builder,
)
from bitrix_connector.bitrix_history_r0_protected_session_real_parser_adapter import (
    DormantProtectedSessionRealParserSnapshot,
)


ROOT = Path(__file__).resolve().parents[1]


def prepared_parser_contract():
    return DormantProtectedSessionRealParserSnapshot(
        state="PREPARED",
        reason="fictional-m28-parser-contract",
        activation_requested=True,
        exact_contract_valid=True,
        authorization_calls=1,
        authorization_verified=True,
        parser_contract_prepared=True,
    )


class ProtectedSessionBuilderCompositionTests(unittest.TestCase):
    def test_prepared_m27_contract_binds_builder_with_all_calls_zero(self):
        preview = preview_dormant_protected_session_builder(
            parser_contract=prepared_parser_contract()
        )
        self.assertEqual(preview.state, "PREPARED")
        self.assertTrue(preview.parser_contract_consumed)
        self.assertTrue(preview.path_builder_bound)
        self.assertTrue(preview.source_builder_bound)
        self.assertTrue(preview.private_builder_bound)
        for field in (
            "path_calls", "source_calls", "builder_calls",
            "materializer_calls", "external_calls",
        ):
            self.assertEqual(getattr(preview, field), 0, field)
        self.assertFalse(preview.parser_real_enabled)
        self.assertFalse(preview.command_available)
        self.assertFalse(preview.source_open_authorized)

    def test_injected_dependencies_are_bound_but_never_called(self):
        calls = {"path": 0, "source": 0, "builder": 0}

        def spy(name):
            def dependency(*_args, **_kwargs):
                calls[name] += 1
                raise AssertionError(f"{name} must not run")
            return dependency

        composition = compose_dormant_protected_session_builder(
            parser_contract=prepared_parser_contract(),
            path_builder=spy("path"),
            source_builder=spy("source"),
            private_builder=spy("builder"),
        )
        self.assertIsInstance(
            composition, PreparedDormantProtectedSessionBuilderComposition
        )
        self.assertEqual(calls, {"path": 0, "source": 0, "builder": 0})

    def test_dormant_default_parser_contract_is_rejected(self):
        preview = preview_dormant_protected_session_builder(
            parser_contract=DormantProtectedSessionRealParserSnapshot()
        )
        self.assertEqual(preview.state, "NO-GO")
        self.assertFalse(preview.parser_contract_consumed)

    def test_degraded_parser_contract_is_rejected(self):
        degraded = replace(prepared_parser_contract(), command_available=True)
        preview = preview_dormant_protected_session_builder(
            parser_contract=degraded
        )
        self.assertEqual(preview.state, "NO-GO")
        self.assertFalse(preview.source_open_authorized)

    def test_invalid_dependency_fails_closed(self):
        preview = preview_dormant_protected_session_builder(
            parser_contract=prepared_parser_contract(),
            compose_builder=lambda **kwargs: compose_dormant_protected_session_builder(
                **kwargs, source_builder=None
            ),
        )
        self.assertEqual(preview.state, "NO-GO")
        self.assertEqual(preview.external_calls, 0)

    def test_composed_object_is_redacted_and_not_invocable(self):
        composition = compose_dormant_protected_session_builder(
            parser_contract=prepared_parser_contract()
        )
        self.assertEqual(
            repr(composition),
            "PreparedDormantProtectedSessionBuilderComposition(<redacted>)",
        )
        self.assertFalse(callable(composition))
        self.assertFalse(hasattr(composition, "execute"))
        self.assertFalse(hasattr(composition, "parser_contract"))

    def test_source_has_no_path_creation_source_open_or_external_surface(self):
        source = (
            ROOT / "bitrix_connector" /
            "bitrix_history_r0_protected_session_builder_composition.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "Path(", "open(", ".env", "load_dotenv", "os.environ",
            "get_access_token", "refresh_access_token", "get_dialog(",
            "get_session_history(", "httpx", "pymongo", "subprocess", "socket",
            "argparse", "input(", "asyncio.run", "Invoke-RestMethod",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

import unittest

from bitrix_connector.bitrix_history_r0_m86_dormant_windows_environment_binding import (
    build_m86ae_dormant_windows_environment_source,
)
from bitrix_connector.bitrix_history_r0_m86_stage_specific_dormant_real_owner import (
    M86ATStageSpecificDormantRealOwner,
)


class M86ATStageSpecificDormantRealOwnerTests(unittest.TestCase):
    def test_preview_does_not_call_injected_factory(self):
        calls = []
        owner = M86ATStageSpecificDormantRealOwner(
            source_factory=lambda: calls.append("forbidden")
        )
        preview = owner.preview()
        self.assertEqual(calls, [])
        self.assertEqual(preview.state, "DORMANT-WAITING-AUTHORIZATION-DESIGN")
        self.assertTrue(preview.real_factory_bound)
        self.assertFalse(preview.real_factory_called)

    def test_default_factory_is_the_real_dormant_reference(self):
        owner = M86ATStageSpecificDormantRealOwner()
        self.assertIs(
            owner._source_factory,
            build_m86ae_dormant_windows_environment_source,
        )

    def test_owner_has_no_execution_or_cli_surface(self):
        owner = M86ATStageSpecificDormantRealOwner(source_factory=lambda: None)
        preview = owner.preview()
        self.assertFalse(hasattr(owner, "run_once"))
        self.assertFalse(hasattr(owner, "main"))
        self.assertFalse(preview.execution_surface_available)
        self.assertFalse(preview.execution_surface_has_cli)
        self.assertFalse(preview.authorization_literal_prepared)
        self.assertFalse(preview.authorization_received)

    def test_non_callable_factory_is_rejected(self):
        with self.assertRaisesRegex(TypeError, "source_factory_invalid"):
            M86ATStageSpecificDormantRealOwner(source_factory=None)


if __name__ == "__main__":
    unittest.main()

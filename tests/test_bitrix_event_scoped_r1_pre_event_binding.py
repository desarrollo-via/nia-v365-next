import unittest

from fastapi import FastAPI

from bitrix_connector.bitrix_event_scoped_r1_pre_event_binding import (
    PRE_EVENT_BINDING_INVALID_REASON,
    PRE_EVENT_BINDING_UNAVAILABLE_REASON,
    mount_optional_event_scoped_r1_with_pre_event_binding,
)
from bitrix_connector.config import load_settings


def enabled_settings(**overrides):
    values = {
        "NIA_BITRIX_MODE": "off",
        "NIA_BITRIX_EVENT_R1_ENABLED": "true",
        "NIA_BASE_URL": "https://nia.test",
        "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
        "NIA_BITRIX_MEMBER_ID": "member-controlled",
        "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
        "NIA_BITRIX_REVIEW_TOKEN": "review-token-fixture-1234567890",
        "NIA_BITRIX_REVIEW_ACTOR": "reviewer",
        "NIA_BITRIX_REVIEW_CREDENTIAL_ID": "credential-fixture",
    }
    values.update(overrides)
    return load_settings(values)


class LeaseFactoryBuilder:
    def __init__(self, *, error=None, result=None):
        self.error = error
        self.result = result if result is not None else (lambda: None)
        self.calls = []

    def __call__(self, *, safety):
        self.calls.append(safety)
        if self.error is not None:
            raise self.error
        return self.result


class PreEventBindingTests(unittest.TestCase):
    def test_default_posterior_mount_never_builds_protected_factory(self):
        builder = LeaseFactoryBuilder(
            error=AssertionError("must remain dormant")
        )
        app = FastAPI()

        mount = mount_optional_event_scoped_r1_with_pre_event_binding(
            app.router,
            enabled_settings(),
            lease_factory_builder=builder,
        )

        self.assertEqual(mount.state, "MOUNTED")
        self.assertEqual(mount.participant_strategy, "posterior")
        self.assertTrue(mount.participant_roundtrip_bound)
        self.assertFalse(mount.pre_event_lease_factory_bound)
        self.assertEqual(builder.calls, [])

    def test_explicit_pre_event_mount_builds_only_lazy_factory(self):
        builder = LeaseFactoryBuilder()
        app = FastAPI()

        mount = mount_optional_event_scoped_r1_with_pre_event_binding(
            app.router,
            enabled_settings(
                NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY="pre-event"
            ),
            lease_factory_builder=builder,
        )

        self.assertEqual(mount.state, "MOUNTED")
        self.assertEqual(mount.participant_strategy, "pre-event")
        self.assertTrue(mount.pre_event_lease_factory_bound)
        self.assertFalse(mount.participant_roundtrip_bound)
        self.assertEqual(len(builder.calls), 1)
        safety = builder.calls[0]
        self.assertEqual(safety.effective_mode, "off")
        self.assertTrue(safety.activation_locked)
        self.assertFalse(safety.external_calls_enabled)
        self.assertEqual(safety.runtime_state, "inert")
        self.assertFalse(safety.r0_mounted)
        self.assertTrue(safety.r1_active)

    def test_invalid_strategy_fails_closed_before_factory_build(self):
        builder = LeaseFactoryBuilder()
        app = FastAPI()

        mount = mount_optional_event_scoped_r1_with_pre_event_binding(
            app.router,
            enabled_settings(
                NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY="automatic"
            ),
            lease_factory_builder=builder,
        )

        self.assertEqual(mount.state, "UNAVAILABLE")
        self.assertEqual(mount.reason, PRE_EVENT_BINDING_INVALID_REASON)
        self.assertFalse(mount.enabled)
        self.assertIsNone(mount.observer)
        self.assertEqual(builder.calls, [])

    def test_pre_event_setting_is_dormant_while_r1_is_disabled(self):
        builder = LeaseFactoryBuilder(
            error=AssertionError("must remain dormant")
        )
        app = FastAPI()

        mount = mount_optional_event_scoped_r1_with_pre_event_binding(
            app.router,
            load_settings(
                {
                    "NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY": "pre-event"
                }
            ),
            lease_factory_builder=builder,
        )

        self.assertEqual(mount.state, "DORMANT")
        self.assertEqual(mount.participant_strategy, "none")
        self.assertEqual(builder.calls, [])

    def test_factory_construction_failure_is_isolated(self):
        builder = LeaseFactoryBuilder(error=RuntimeError("private detail"))
        app = FastAPI()

        mount = mount_optional_event_scoped_r1_with_pre_event_binding(
            app.router,
            enabled_settings(
                NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY="pre-event"
            ),
            lease_factory_builder=builder,
        )

        self.assertEqual(mount.state, "UNAVAILABLE")
        self.assertEqual(mount.reason, PRE_EVENT_BINDING_UNAVAILABLE_REASON)
        self.assertEqual(len(builder.calls), 1)
        self.assertNotIn("private detail", repr(mount))

    def test_router_uses_selection_without_direct_protected_builder_import(self):
        from pathlib import Path

        source = Path("bitrix_connector/router.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "mount_optional_event_scoped_r1_with_pre_event_binding",
            source,
        )
        self.assertNotIn(
            "build_dormant_real_pre_event_lease_factory",
            source,
        )
        self.assertNotIn("PilotDiscoveryOAuthFactory", source)
        self.assertNotIn("build_real_windows_credential_backend", source)


if __name__ == "__main__":
    unittest.main()

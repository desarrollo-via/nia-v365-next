"""Owner M86-V de dos confirmaciones, limitado a un almacén en memoria."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from .bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from .bitrix_history_r0_m86_credential_materialization_contract import (
    materialize_m84_blob_from_injected_buffers,
)


M86V_FIRST_CONFIRMATION_TEXT = (
    "PRIMERA CONFIRMACIÓN M86-V — PREPARACIÓN HERMÉTICA: Autorizo "
    "exclusivamente un preflight del target exacto "
    "nia-next/bitrix-r1/protected-settings/v1 sobre un doble ficticio en "
    "memoria, sin materializar valores ni aplicar cambios. No autorizo "
    "fuentes u operaciones reales: Credential Manager, secretos, red, "
    "servicios, escrituras, reemplazos, borrados o ejecución productiva."
)

M86V_SECOND_CONFIRMATION_TEXT = (
    "SEGUNDA CONFIRMACIÓN M86-V — EJECUCIÓN HERMÉTICA: Confirmo el preflight "
    "ficticio exacto y autorizo una sola materialización M84 con fixtures, "
    "verificación en memoria y rollback exacto al estado ficticio anterior. "
    "No autorizo fuentes u operaciones reales: Credential Manager, secretos, "
    "red, servicios, escrituras, reemplazos, borrados o ejecución productiva."
)


PriorFixtureState = Literal["absent", "present", "ambiguous"]


def _zeroize(value: object) -> None:
    if type(value) is bytearray:
        value[:] = b"\x00" * len(value)


class InMemoryCredentialFixture:
    """Doble sellado; su estado nunca sale del proceso ni representa secretos."""

    __slots__ = (
        "_closed",
        "_current",
        "_fail_rollback",
        "_prior_state",
        "apply_calls",
        "close_calls",
        "preflight_calls",
        "rollback_calls",
        "targets",
        "verify_calls",
    )

    def __init__(
        self,
        *,
        prior_state: PriorFixtureState,
        prior_blob: bytearray | None = None,
        fail_rollback: bool = False,
    ) -> None:
        if prior_state not in ("absent", "present", "ambiguous"):
            raise ValueError("m86v_fixture_prior_state_invalid")
        if prior_state == "present":
            if type(prior_blob) is not bytearray or not prior_blob:
                raise ValueError("m86v_fixture_prior_blob_invalid")
            current = bytearray(prior_blob)
        elif prior_blob is not None:
            raise ValueError("m86v_fixture_prior_blob_unexpected")
        else:
            current = None
        self._prior_state = prior_state
        self._current: bytearray | None = current
        self._fail_rollback = fail_rollback
        self._closed = False
        self.preflight_calls = 0
        self.apply_calls = 0
        self.verify_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0
        self.targets: list[str] = []

    def __repr__(self) -> str:
        return "InMemoryCredentialFixture(<redacted>)"

    def _assert_target(self, target_id: str) -> None:
        if self._closed or target_id != M80_CREDENTIAL_TARGET_ID:
            raise RuntimeError("m86v_fixture_target_or_state_invalid")
        self.targets.append(target_id)

    def _preflight_exact_once(self, target_id: str) -> tuple[PriorFixtureState, bytearray]:
        self._assert_target(target_id)
        if self.preflight_calls:
            raise RuntimeError("m86v_fixture_preflight_reused")
        self.preflight_calls = 1
        backup = bytearray(self._current) if self._current is not None else bytearray()
        return self._prior_state, backup

    def _apply_exact_once(self, target_id: str, blob: bytearray) -> None:
        self._assert_target(target_id)
        if self.apply_calls or type(blob) is not bytearray or not blob:
            raise RuntimeError("m86v_fixture_apply_invalid")
        self.apply_calls = 1
        _zeroize(self._current)
        self._current = bytearray(blob)

    def _verify_exact_once(self, target_id: str, expected: bytearray) -> bool:
        self._assert_target(target_id)
        if self.verify_calls or type(expected) is not bytearray:
            raise RuntimeError("m86v_fixture_verify_invalid")
        self.verify_calls = 1
        return self._current == expected

    def _rollback_exact_once(
        self,
        target_id: str,
        *,
        prior_state: PriorFixtureState,
        backup: bytearray,
    ) -> None:
        self._assert_target(target_id)
        if self.rollback_calls:
            raise RuntimeError("m86v_fixture_rollback_reused")
        self.rollback_calls = 1
        if self._fail_rollback:
            raise RuntimeError("m86v_fixture_rollback_failed")
        _zeroize(self._current)
        self._current = bytearray(backup) if prior_state == "present" else None

    def _is_restored(self, *, prior_state: PriorFixtureState, backup: bytearray) -> bool:
        if prior_state == "absent":
            return self._current is None
        if prior_state == "present":
            return self._current == backup
        return False

    def close(self) -> None:
        if not self._closed:
            self.close_calls += 1
            _zeroize(self._current)
            self._current = None
            self._closed = True


@dataclass(frozen=True)
class M86VFixtureProvisioningSnapshot:
    phase: Literal["M86-V"] = "M86-V"
    state: str = "INERT"
    prior_state: PriorFixtureState | Literal["unknown"] = "unknown"
    first_confirmation_exact: bool = False
    second_confirmation_exact: bool = False
    first_confirmation_consumed: bool = False
    second_confirmation_consumed: bool = False
    preflight_calls: int = 0
    fixture_apply_calls: int = 0
    fixture_verify_calls: int = 0
    fixture_rollback_calls: int = 0
    fixture_state_restored: bool = False
    resources_closed: bool = False
    real_source_bound: Literal[False] = False
    operating_system_calls: Literal[0] = 0
    external_calls: Literal[0] = 0
    real_execution_authorized: Literal[False] = False
    attention_required_now: Literal[False] = False
    human_message_required_now: Literal[False] = False
    connector_locked_off: Literal[True] = True
    persisted: Literal[False] = False
    nia_next_called: Literal[False] = False
    bitrix_written: Literal[False] = False


class M86VFixtureProvisioningOwner:
    """Secuencia one-shot separada; sólo admite el doble concreto sellado."""

    __slots__ = ("_backup", "_fixture", "_prepared", "_prior_state", "_used")

    def __init__(self) -> None:
        self._backup = bytearray()
        self._fixture: InMemoryCredentialFixture | None = None
        self._prepared = False
        self._prior_state: PriorFixtureState | Literal["unknown"] = "unknown"
        self._used = False

    def __repr__(self) -> str:
        return "M86VFixtureProvisioningOwner(<redacted>)"

    def _snapshot(
        self,
        *,
        state: str,
        first_exact: bool,
        second_exact: bool = False,
        second_consumed: bool = False,
        restored: bool = False,
        closed: bool = False,
    ) -> M86VFixtureProvisioningSnapshot:
        fixture = self._fixture
        return M86VFixtureProvisioningSnapshot(
            state=state,
            prior_state=self._prior_state,
            first_confirmation_exact=first_exact,
            second_confirmation_exact=second_exact,
            first_confirmation_consumed=True,
            second_confirmation_consumed=second_consumed,
            preflight_calls=fixture.preflight_calls if fixture is not None else 0,
            fixture_apply_calls=fixture.apply_calls if fixture is not None else 0,
            fixture_verify_calls=fixture.verify_calls if fixture is not None else 0,
            fixture_rollback_calls=fixture.rollback_calls if fixture is not None else 0,
            fixture_state_restored=restored,
            resources_closed=closed,
        )

    def _close(self) -> None:
        _zeroize(self._backup)
        self._backup = bytearray()
        fixture, self._fixture = self._fixture, None
        if fixture is not None:
            fixture.close()

    def close(self) -> None:
        """Permite abandonar la espera ficticia y limpiar el estado retenido."""

        self._prepared = False
        self._close()

    def prepare_once(
        self,
        *,
        first_confirmation: str,
        fixture: InMemoryCredentialFixture,
    ) -> M86VFixtureProvisioningSnapshot:
        if self._used or type(fixture) is not InMemoryCredentialFixture:
            self._used = True
            raise RuntimeError("m86v_owner_reuse_or_fixture_invalid")
        self._used = True
        self._fixture = fixture
        exact = (
            type(first_confirmation) is str
            and first_confirmation == M86V_FIRST_CONFIRMATION_TEXT
        )
        if not exact:
            snapshot = self._snapshot(state="NO-GO-FIRST-CONFIRMATION", first_exact=False)
            self._close()
            return replace(snapshot, resources_closed=True)
        try:
            prior_state, backup = fixture._preflight_exact_once(M80_CREDENTIAL_TARGET_ID)
            self._prior_state = prior_state
            self._backup = backup
            if prior_state == "ambiguous":
                snapshot = self._snapshot(state="NO-GO-AMBIGUOUS-PRIOR", first_exact=True)
                self._close()
                return replace(snapshot, resources_closed=True)
            self._prepared = True
            return self._snapshot(state="AWAITING-SECOND-CONFIRMATION", first_exact=True)
        except BaseException:
            self._close()
            raise

    def execute_fixture_once(
        self,
        *,
        second_confirmation: str,
        buffers: dict[str, bytearray],
    ) -> M86VFixtureProvisioningSnapshot:
        fixture = self._fixture
        if not self._prepared or fixture is None:
            raise RuntimeError("m86v_owner_not_prepared")
        self._prepared = False
        exact = (
            type(second_confirmation) is str
            and second_confirmation == M86V_SECOND_CONFIRMATION_TEXT
        )
        if not exact:
            snapshot = self._snapshot(
                state="NO-GO-SECOND-CONFIRMATION",
                first_exact=True,
                second_consumed=True,
            )
            self._close()
            return replace(snapshot, resources_closed=True)

        blob_owner = None
        blob = bytearray()
        applied = False
        restored = False
        state = "NO-GO-FIXTURE-LIFECYCLE"
        try:
            blob_owner = materialize_m84_blob_from_injected_buffers(buffers)
            blob = blob_owner.take_blob_once()
            fixture._apply_exact_once(M80_CREDENTIAL_TARGET_ID, blob)
            applied = True
            if not fixture._verify_exact_once(M80_CREDENTIAL_TARGET_ID, blob):
                raise RuntimeError("m86v_fixture_verification_failed")
            fixture._rollback_exact_once(
                M80_CREDENTIAL_TARGET_ID,
                prior_state=self._prior_state,
                backup=self._backup,
            )
            restored = fixture._is_restored(
                prior_state=self._prior_state,
                backup=self._backup,
            )
            state = "FIXTURE-ROLLED-BACK" if restored else state
        except BaseException:
            if applied and fixture.rollback_calls == 0:
                try:
                    fixture._rollback_exact_once(
                        M80_CREDENTIAL_TARGET_ID,
                        prior_state=self._prior_state,
                        backup=self._backup,
                    )
                    restored = fixture._is_restored(
                        prior_state=self._prior_state,
                        backup=self._backup,
                    )
                except BaseException:
                    restored = False
        finally:
            _zeroize(blob)
            if blob_owner is not None:
                blob_owner.close()
        snapshot = self._snapshot(
            state=state,
            first_exact=True,
            second_exact=True,
            second_consumed=True,
            restored=restored,
        )
        self._close()
        return replace(snapshot, resources_closed=True)


__all__ = [
    "InMemoryCredentialFixture",
    "M86VFixtureProvisioningOwner",
    "M86VFixtureProvisioningSnapshot",
    "M86V_FIRST_CONFIRMATION_TEXT",
    "M86V_SECOND_CONFIRMATION_TEXT",
]

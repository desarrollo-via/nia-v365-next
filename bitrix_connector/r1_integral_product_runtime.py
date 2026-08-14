"""Deferred real runtime for the v0.667 integral R1 product execution."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from pydantic import TypeAdapter, ValidationError

from .r1_integral_v2_review_session_factory import PUBLIC_ORIGIN
from .r1_key_vault_protected_probe_dotenv_source import (
    EXPECTED_DOTENV_PATH,
    ExactReviewTokenDotenvSource,
)
from .r1_key_vault_protected_probe_invocation_owner import REVIEW_TOKEN_NAME
from .r1_key_vault_recovery_resume import (
    ExactBearerSecretSink,
    RecoveryResumeResult,
    recover_and_resume_once,
)
from .r1_key_vault_linux_provisioning_real_binding import ExactDormantHealthReader
from .r1_pre_event_activation_preflight import (
    R1ActivationPreflight,
    R1ActivationPreflightEvidence,
    audit_r1_activation_preflight,
)
from .r1_remote_session_http_client import ExactR1RemoteSessionHttpClient
from .r1_result_eaor_product_real_binding import (
    R1ProductFactoryRuntime,
    R1ResultEaorProductRealBinding,
)


ACTIVATION_PREFLIGHT_ENDPOINT = (
    f"{PUBLIC_ORIGIN}/bitrix-connector/review/r1-activation-preflight"
)
MAX_PREFLIGHT_RESPONSE_BYTES = 4096
MAX_ACTIVATION_PREFLIGHT_ATTEMPTS = 3
ACTIVATION_PREFLIGHT_INITIAL_DELAY_SECONDS = 15
ACTIVATION_PREFLIGHT_RETRY_SECONDS = 30


class R1SharedReviewPreflightFailure(RuntimeError):
    __slots__ = ("attempts", "category", "retryable", "stage")

    def __init__(
        self, *, stage: str, category: str, retryable: bool, attempts: int
    ) -> None:
        super().__init__("r1_shared_review_preflight_unavailable")
        self.stage = stage
        self.category = category
        self.retryable = retryable
        self.attempts = attempts


class PersistentOneShotBearerSecretSink:
    """Reserves and consumes one PUT across process restarts."""

    __slots__ = ("_delegate", "_ledger_path", "_used")

    def __init__(self, *, ledger_path: Path, delegate=None) -> None:
        if not isinstance(ledger_path, Path):
            raise TypeError("r1_integral_write_ledger_path_invalid")
        self._ledger_path = ledger_path
        self._delegate = delegate or ExactBearerSecretSink()
        self._used = False

    def _read(self) -> dict[str, int]:
        initial = {
            "write_budget": 1,
            "write_reserved": 0,
            "write_succeeded": 0,
            "write_used": 0,
        }
        if not self._ledger_path.is_file():
            return initial
        payload = json.loads(self._ledger_path.read_text(encoding="utf-8"))
        if (
            set(payload) != set(initial)
            or any(type(value) is not int or value < 0 for value in payload.values())
            or payload["write_budget"] != 1
        ):
            raise RuntimeError("r1_integral_write_ledger_invalid")
        return payload

    def _write(self, payload: dict[str, int]) -> None:
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._ledger_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._ledger_path)

    async def set_exact_secret_once(self, payload: bytearray) -> str:
        if self._used:
            raise RuntimeError("r1_integral_write_sink_reused")
        self._used = True
        ledger = self._read()
        if ledger["write_reserved"] + ledger["write_used"] >= 1:
            raise RuntimeError("r1_integral_write_budget_exhausted")
        ledger["write_reserved"] += 1
        self._write(ledger)
        succeeded = False
        try:
            result = await self._delegate.set_exact_secret_once(payload)
            succeeded = True
            return result
        finally:
            ledger = self._read()
            ledger["write_reserved"] -= 1
            ledger["write_used"] += 1
            if succeeded:
                ledger["write_succeeded"] = 1
            self._write(ledger)

    def checkpoint_succeeded(self) -> bool:
        return self._read()["write_succeeded"] == 1

    async def close(self) -> None:
        delegate, self._delegate = self._delegate, None
        if delegate is not None:
            await delegate.close()


class _PreverifiedAbsenceProbe:
    async def exists_once(self) -> bool:
        raise RuntimeError("r1_preverified_absence_probe_must_not_run")

    async def close(self) -> None:
        return None


async def resume_preverified_absence_once(**kwargs):
    """Resumes from exact SecretNotFound evidence without another secret GET."""

    selected = dict(kwargs)
    selected.setdefault("probe", _PreverifiedAbsenceProbe())
    selected.setdefault("sink", ExactBearerSecretSink())
    sink = selected["sink"]
    presence_checkpoint = bool(
        callable(getattr(sink, "checkpoint_succeeded", None))
        and sink.checkpoint_succeeded()
    )
    selected.update({
        "secret_absence_preverified": not presence_checkpoint,
        "secret_presence_preverified": presence_checkpoint,
        "active_checkpoint_preverified": True,
        "skip_data_plane_readiness": True,
        "preserve_active_vault": True,
        "max_secret_probes": 1,
    })
    return await recover_and_resume_once(**selected)


async def resume_integral_checkpoint_once(**kwargs):
    """Uses the confirmed PUT checkpoint without repeating provisioning writes."""

    selected = dict(kwargs)
    sink = selected.get("sink")
    checkpoint = bool(
        callable(getattr(sink, "checkpoint_succeeded", None))
        and sink.checkpoint_succeeded()
    )
    if not checkpoint:
        return await resume_preverified_absence_once(**selected)

    health = selected.get("health") or ExactDormantHealthReader()
    resources_closed = True
    healthy = False
    try:
        healthy = bool(
            selected.get("local_state_guard", lambda: True)() is True
            and await health.read_exact_once() is True
        )
    finally:
        for resource in (health, sink):
            close = getattr(resource, "close", None)
            if callable(close):
                try:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
                except BaseException:
                    resources_closed = False
    return RecoveryResumeResult(
        state=(
            "RECOVERED-DORMANT-VERIFIED"
            if healthy and resources_closed
            else "NO-GO-REMAINDER"
        ),
        failure_stage="none" if healthy else "dormant_health",
        failure_category="none" if healthy else "drift",
        preflight_reads=0,
        recovery_calls=0,
        secret_probe_calls=0,
        protected_source_reads=0,
        secret_write_calls=0,
        app_setting_write_calls=0,
        rollback_calls=0,
        resources_closed=resources_closed,
        secret_existed=True,
    )


class ExactR1SharedReviewRuntime:
    """Reads the review token once and transfers it to the later session client."""

    __slots__ = (
        "_client_factory", "_dotenv_path", "_expected_sha", "_expected_tree",
        "_initial_delay", "_max_preflight_attempts", "_preflight_used",
        "_retry_delay", "_session_builder", "_session_used", "_sleeper",
        "_source_builder", "_token",
    )

    def __init__(
        self,
        *,
        dotenv_path: Path = EXPECTED_DOTENV_PATH,
        source_builder=ExactReviewTokenDotenvSource,
        client_factory=httpx.AsyncClient,
        session_builder=ExactR1RemoteSessionHttpClient,
        max_preflight_attempts: int = MAX_ACTIVATION_PREFLIGHT_ATTEMPTS,
        initial_delay_seconds: int = ACTIVATION_PREFLIGHT_INITIAL_DELAY_SECONDS,
        retry_delay_seconds: int = ACTIVATION_PREFLIGHT_RETRY_SECONDS,
        sleeper=asyncio.sleep,
        expected_deployed_sha: str,
        expected_deployed_tree: str,
    ) -> None:
        if (
            not isinstance(dotenv_path, Path)
            or type(max_preflight_attempts) is not int
            or not 1 <= max_preflight_attempts <= MAX_ACTIVATION_PREFLIGHT_ATTEMPTS
            or type(initial_delay_seconds) is not int
            or not 0 <= initial_delay_seconds <= 120
            or type(retry_delay_seconds) is not int
            or not 0 <= retry_delay_seconds <= 120
            or not all(callable(item) for item in (
                source_builder, client_factory, session_builder, sleeper,
            ))
        ):
            raise TypeError("r1_shared_review_runtime_dependency_invalid")
        if any(
            type(value) is not str
            or len(value) != 40
            or any(character not in "0123456789abcdef" for character in value)
            for value in (expected_deployed_sha, expected_deployed_tree)
        ):
            raise ValueError("r1_shared_review_deployment_identity_invalid")
        self._dotenv_path = dotenv_path
        self._expected_sha = expected_deployed_sha
        self._expected_tree = expected_deployed_tree
        self._source_builder = source_builder
        self._client_factory = client_factory
        self._session_builder = session_builder
        self._max_preflight_attempts = max_preflight_attempts
        self._initial_delay = initial_delay_seconds
        self._retry_delay = retry_delay_seconds
        self._sleeper = sleeper
        self._token = bytearray()
        self._preflight_used = False
        self._session_used = False

    async def activation_preflight_supplier(self) -> R1ActivationPreflight:
        if self._preflight_used or self._session_used:
            raise RuntimeError("r1_shared_review_preflight_reused")
        self._preflight_used = True
        source = self._source_builder(self._dotenv_path)
        client = None
        authorization = ""
        body = bytearray()
        try:
            await source.open()
            self._token = await source.read_exact(REVIEW_TOKEN_NAME)
            if type(self._token) is not bytearray or not self._token:
                raise RuntimeError("r1_shared_review_token_invalid")
            token_text = bytes(self._token).decode("utf-8")
            authorization = f"Bearer {token_text}"
            token_text = ""
            client = self._client_factory(
                timeout=30, follow_redirects=False, trust_env=False
            )
            if self._initial_delay:
                await self._sleeper(self._initial_delay)
            for attempt in range(1, self._max_preflight_attempts + 1):
                body[:] = b"\x00" * len(body)
                body.clear()
                try:
                    async with client.stream(
                        "GET",
                        ACTIVATION_PREFLIGHT_ENDPOINT,
                        headers={
                            "Authorization": authorization,
                            "Accept": "application/json",
                        },
                    ) as response:
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > MAX_PREFLIGHT_RESPONSE_BYTES:
                                raise RuntimeError(
                                    "r1_shared_review_preflight_oversized"
                                )
                            body.extend(chunk)
                        status_code = response.status_code
                except httpx.HTTPError:
                    if attempt < self._max_preflight_attempts:
                        if self._retry_delay:
                            await self._sleeper(self._retry_delay)
                        continue
                    raise R1SharedReviewPreflightFailure(
                        stage="transport", category="transport_unavailable",
                        retryable=False, attempts=attempt,
                    ) from None

                payload = json.loads(bytes(body).decode("utf-8"))
                if status_code == 200:
                    evidence = TypeAdapter(
                        R1ActivationPreflightEvidence
                    ).validate_python(payload)
                    result = audit_r1_activation_preflight(
                        evidence,
                        expected_deployed_sha=self._expected_sha,
                        expected_deployed_tree=self._expected_tree,
                    )
                    if result.state != "READY-FIRST-CONFIRMATION":
                        await self.close()
                    return result

                detail = payload.get("detail") if type(payload) is dict else None
                if status_code == 503 and type(detail) is dict:
                    stage = detail.get("stage")
                    category = detail.get("category")
                    retryable = detail.get("retryable") is True
                    if not (
                        type(stage) is str
                        and stage in {
                            "baseline", "switches", "protected_source", "oauth",
                            "participants", "deployment_identity",
                        }
                        and type(category) is str
                        and category in {
                            "material_drift", "protected_source_unavailable",
                            "oauth_unavailable", "participants_unavailable",
                            "baseline_review_token_missing",
                            "baseline_key_vault_url_missing",
                            "baseline_r0_bridge_enabled",
                            "baseline_event_r1_enabled",
                            "baseline_participant_strategy_drift",
                        }
                    ):
                        raise ValueError("r1_shared_review_failure_shape_invalid")
                    if retryable and attempt < self._max_preflight_attempts:
                        if self._retry_delay:
                            await self._sleeper(self._retry_delay)
                        continue
                    raise R1SharedReviewPreflightFailure(
                        stage=stage, category=category, retryable=False,
                        attempts=attempt,
                    )
                raise R1SharedReviewPreflightFailure(
                    stage="http", category=(
                        "collector_consumed" if status_code == 409
                        else "unexpected_status"
                    ), retryable=False, attempts=attempt,
                )
            raise RuntimeError("r1_shared_review_preflight_loop_invalid")
        except (UnicodeDecodeError, ValueError, ValidationError):
            await self.close()
            raise RuntimeError("r1_shared_review_preflight_invalid") from None
        except BaseException:
            await self.close()
            raise
        finally:
            authorization = ""
            body[:] = b"\x00" * len(body)
            body.clear()
            try:
                await source.close()
            except BaseException:
                await self.close()
                raise RuntimeError("r1_shared_review_source_close_failed") from None
            if client is not None:
                await client.aclose()

    async def remote_session_client_builder(self):
        if (
            not self._preflight_used
            or self._session_used
            or not self._token
        ):
            raise RuntimeError("r1_shared_review_session_unavailable")
        self._session_used = True
        token_text = ""
        try:
            token_text = bytes(self._token).decode("utf-8")
            return self._session_builder(
                public_origin=PUBLIC_ORIGIN,
                review_token=token_text,
            )
        finally:
            token_text = ""
            self._token[:] = b"\x00" * len(self._token)
            self._token.clear()

    async def close(self) -> None:
        self._token[:] = b"\x00" * len(self._token)
        self._token.clear()
        self._source_builder = None
        self._client_factory = None
        self._session_builder = None
        self._sleeper = None
        self._expected_sha = ""
        self._expected_tree = ""

    def __repr__(self) -> str:
        return "ExactR1SharedReviewRuntime(<redacted>)"


def build_integral_product_factory_binding(
    *,
    local_state_guard,
    shared_review_runtime: ExactR1SharedReviewRuntime,
    provisioning_sink=None,
    provisioning_operation=resume_integral_checkpoint_once,
    provisioning_runner=None,
    provisioning_health=None,
    provisioning_source_builder=None,
    activation_verifier_builder=None,
    activation_runner_factory=None,
) -> R1ResultEaorProductRealBinding:
    if type(shared_review_runtime) is not ExactR1SharedReviewRuntime:
        raise TypeError("r1_integral_shared_review_runtime_invalid")
    runtime_kwargs = dict(
            local_state_guard=local_state_guard,
            activation_preflight_supplier=(
                shared_review_runtime.activation_preflight_supplier
            ),
            remote_session_client_builder=(
                shared_review_runtime.remote_session_client_builder
            ),
            provisioning_operation=provisioning_operation,
            provisioning_runner=provisioning_runner,
            provisioning_health=provisioning_health,
            provisioning_source_builder=provisioning_source_builder,
            provisioning_sink=provisioning_sink,
            runtime_finalizer=shared_review_runtime.close,
    )
    if activation_verifier_builder is not None:
        runtime_kwargs["activation_verifier_builder"] = activation_verifier_builder
    if activation_runner_factory is not None:
        runtime_kwargs["activation_runner_factory"] = activation_runner_factory
    return R1ResultEaorProductRealBinding(
        runtime=R1ProductFactoryRuntime(**runtime_kwargs)
    )


__all__ = [
    "ACTIVATION_PREFLIGHT_ENDPOINT", "ExactR1SharedReviewRuntime",
    "R1SharedReviewPreflightFailure",
    "PersistentOneShotBearerSecretSink", "build_integral_product_factory_binding",
    "resume_integral_checkpoint_once", "resume_preverified_absence_once",
]

"""Process-bound, two-phase controller for the accepted R1 V3 EAOR."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Protocol

from .r1_result_eaor_coordinator import EAOR_ID, R1ResultEaorSnapshot


CHECKPOINT_SCHEMA = "nia-next-r1-v3-attention-receipt-v1"
_SAFE_FIELDS = frozenset({
    "state", "eaor_id", "acceptance_calls", "provisioning_calls",
    "activation_calls", "session_arm_calls", "observation_calls",
    "activation_restore_calls", "human_message_calls", "resources_closed",
    "human_message_required_now", "pre_event_lease_state", "external_retries",
    "failure_stage", "failure_category",
})


class _TwoPhaseRunner(Protocol):
    async def run_until_human_once(self) -> R1ResultEaorSnapshot: ...
    async def resume_after_human_once(self) -> R1ResultEaorSnapshot: ...
    async def close_waiting_once(self) -> R1ResultEaorSnapshot: ...


@dataclass(frozen=True)
class R1V3CheckpointReceipt:
    schema: str
    eaor_id: str
    state: str
    human_message_required_now: bool
    pre_event_lease_state: str
    snapshot_sha256: str


class R1V3SanitizedCheckpointStore:
    """Atomic narrow receipt store; rejects foreign or expanded payloads."""
    __slots__ = ("_path",)

    def __init__(self, *, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("r1_v3_checkpoint_path_invalid")
        self._path = path

    @staticmethod
    def _receipt(snapshot: R1ResultEaorSnapshot) -> dict:
        if type(snapshot) is not R1ResultEaorSnapshot:
            raise TypeError("r1_v3_checkpoint_snapshot_invalid")
        values = asdict(snapshot)
        payload = {name: values[name] for name in _SAFE_FIELDS}
        if set(payload) != _SAFE_FIELDS:
            raise RuntimeError("r1_v3_checkpoint_payload_invalid")
        return payload

    def write_attention_once(self, snapshot: R1ResultEaorSnapshot) -> R1V3CheckpointReceipt:
        payload = self._receipt(snapshot)
        if not (payload["state"] == "ATTENTION-REQUIRED" and payload["eaor_id"] == EAOR_ID
                and payload["human_message_required_now"] is True
                and payload["pre_event_lease_state"] == "AWAITING-EVENT"):
            raise RuntimeError("r1_v3_checkpoint_attention_invalid")
        serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        envelope = {"schema": CHECKPOINT_SCHEMA, "receipt": payload, "snapshot_sha256": digest}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(envelope, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self._path)
        return R1V3CheckpointReceipt(CHECKPOINT_SCHEMA, EAOR_ID, "ATTENTION-REQUIRED", True, "AWAITING-EVENT", digest)

    def read_attention_once(self) -> R1V3CheckpointReceipt:
        try:
            envelope = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RuntimeError("r1_v3_checkpoint_unavailable") from None
        if type(envelope) is not dict or set(envelope) != {"schema", "receipt", "snapshot_sha256"} or envelope["schema"] != CHECKPOINT_SCHEMA:
            raise RuntimeError("r1_v3_checkpoint_invalid")
        receipt, digest = envelope["receipt"], envelope["snapshot_sha256"]
        if type(receipt) is not dict or set(receipt) != _SAFE_FIELDS or type(digest) is not str:
            raise RuntimeError("r1_v3_checkpoint_invalid")
        serialized = json.dumps(receipt, separators=(",", ":"), sort_keys=True)
        if hashlib.sha256(serialized.encode("utf-8")).hexdigest() != digest:
            raise RuntimeError("r1_v3_checkpoint_tampered")
        return R1V3CheckpointReceipt(CHECKPOINT_SCHEMA, receipt["eaor_id"], receipt["state"], receipt["human_message_required_now"], receipt["pre_event_lease_state"], digest)


class R1V3TwoPhaseRunner:
    """Separates human checkpoint from the later explicit resumption."""
    __slots__ = ("_checkpoint", "_runner", "_waiting")

    def __init__(self, *, runner: _TwoPhaseRunner, checkpoint: R1V3SanitizedCheckpointStore) -> None:
        if type(checkpoint) is not R1V3SanitizedCheckpointStore or any(not callable(getattr(runner, name, None)) for name in ("run_until_human_once", "resume_after_human_once", "close_waiting_once")):
            raise TypeError("r1_v3_two_phase_dependency_invalid")
        self._runner, self._checkpoint, self._waiting = runner, checkpoint, False

    async def start_until_human_once(self) -> R1V3CheckpointReceipt:
        if self._waiting:
            raise RuntimeError("r1_v3_two_phase_reused")
        receipt = self._checkpoint.write_attention_once(await self._runner.run_until_human_once())
        self._waiting = True
        return receipt

    async def resume_after_human_once(self) -> R1ResultEaorSnapshot:
        if not self._waiting:
            raise RuntimeError("r1_v3_two_phase_process_checkpoint_required")
        receipt = self._checkpoint.read_attention_once()
        if not (receipt.eaor_id == EAOR_ID and receipt.state == "ATTENTION-REQUIRED" and receipt.human_message_required_now is True and receipt.pre_event_lease_state == "AWAITING-EVENT"):
            raise RuntimeError("r1_v3_two_phase_checkpoint_invalid")
        self._waiting = False
        return await self._runner.resume_after_human_once()

    async def close_waiting_once(self) -> R1ResultEaorSnapshot:
        if not self._waiting:
            raise RuntimeError("r1_v3_two_phase_process_checkpoint_required")
        self._waiting = False
        return await self._runner.close_waiting_once()


__all__ = ["CHECKPOINT_SCHEMA", "R1V3CheckpointReceipt", "R1V3SanitizedCheckpointStore", "R1V3TwoPhaseRunner"]

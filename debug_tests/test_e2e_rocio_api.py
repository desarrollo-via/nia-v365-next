import json
import urllib.request

BASE = "http://127.0.0.1:8000/nia/chat"
SESSION = "test_rocio_e2e_001"


def chat(msg: str) -> dict:
    body = json.dumps({"session_id": SESSION, "mensaje": msg}).encode()
    req = urllib.request.Request(
        BASE,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


r = chat("necesito medir el punto de rocio")
print(r.get("respuesta", ""))
assert "caudal" not in r.get("respuesta", "").lower()
assert any(
    w in r.get("respuesta", "").lower()
    for w in ("humedad", "rocío", "rocio")
)
print("E2E pregunta OK")

"""E2E vía API local: cemento → radar (no P241068)."""
import json
import urllib.request

BASE = "http://127.0.0.1:8000/nia/chat"
SESSION = "test_cemento_e2e_001"


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


def main():
    pasos = [
        "hola",
        "necesito medir nivel",
        "Tanques de almacenamiento",
        "otro",
        "cemento",
        "transmisor de nivel",
        "Hasta 2 metros",
        "4-20mA",
    ]
    for paso in pasos:
        r = chat(paso)
        print(f"\n>>> {paso}")
        print(r.get("respuesta", "")[:500])
        print("etapa:", r.get("etapa"), "opciones:", len(r.get("opciones") or []))

    texto = r.get("respuesta", "")
    assert "P241068" not in texto, f"Ultrasonico malo: {texto}"
    assert any(
        k in texto.lower()
        for k in ("radar", "guiad", "tdr", "onda guiada", "P245")
    ), f"No parece radar: {texto[:300]}"
    print("\nE2E OK")


if __name__ == "__main__":
    main()

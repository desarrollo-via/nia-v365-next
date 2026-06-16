"""Verifica que los libros Creus/Kuphaldt carguen en knowledge.py."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from knowledge import estado_conocimiento, contexto_para_agente, buscar_contexto


def main():
    estado = estado_conocimiento()
    print("Estado conocimiento:")
    for k, v in estado.items():
        print(f"  {k}: {v}")

    assert estado["chunks_cargados"] > 0, "No se cargaron chunks RAG"

    ctx = contexto_para_agente("necesito un transmisor de presion 0-10 bar 4-20mA")
    print("\nDominio detectado:", ctx["dominio"])
    print("Extractos:", len(ctx["extractos"]))
    print("Términos:", ctx["terminos"][:8])

    chunks = buscar_contexto("termometro RTD pt100 rango temperatura", top_k=3)
    print("\nTop chunks:")
    for c in chunks:
        print("-", c.get("source_id"), "|", c.get("domain"), "|", (c.get("title") or "")[:40])

    print("\nOK — libros conectados.")


if __name__ == "__main__":
    main()

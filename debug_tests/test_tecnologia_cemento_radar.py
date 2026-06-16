"""Regla técnica: cemento/polvo → radar, no ultrasonido."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from hybrid_discovery import (
    _contexto_material_nivel,
    _filtrar_niveles_por_tecnologia,
    _tecnologias_nivel_para_material,
    filtrar_productos_por_tecnologia_material,
)


def test_cemento_es_solido():
    resp = [
        {"campo": "aplicacion", "clave": "tanques", "valor": "Tanques"},
        {"campo": "fluido", "clave": "granel", "valor": "cemento"},
    ]
    ctx = _contexto_material_nivel(resp)
    assert ctx["es_solido_polvo"]
    prefer, excluir = _tecnologias_nivel_para_material(ctx)
    assert "radar" in prefer
    assert "ultrason" in excluir
    print("OK cemento = solido → radar")


def test_excluye_ultrasonico():
    resp = [
        {"campo": "aplicacion", "clave": "tanques", "valor": "Tanques"},
        {"campo": "fluido", "clave": "granel", "valor": "cemento"},
    ]
    productos = [
        {
            "codigo": "P1",
            "nombre": "Transmisor ultrasonico smart",
            "nivel_1": "transmisor-de-nivel-ultrasonico",
            "descripcion_corta": "ultrasonico",
        },
        {
            "codigo": "P2",
            "nombre": "Transmisor radar de nivel",
            "nivel_1": "transmisores-de-nivel-radar",
            "descripcion_corta": "radar FMCW tanque",
        },
    ]
    filtrados = filtrar_productos_por_tecnologia_material(productos, resp)
    codigos = [p["codigo"] for p in filtrados]
    assert "P2" in codigos
    assert "P1" not in codigos
    assert filtrados[0]["codigo"] == "P2"
    print("OK excluye ultrasonico, prioriza radar")


def test_niveles_radar_primero():
    resp = [{"campo": "fluido", "clave": "granel", "valor": "cemento"}]
    ctx = _contexto_material_nivel(resp)
    prefer, excluir = _tecnologias_nivel_para_material(ctx)
    niveles = [
        ("transmisor-de-nivel-ultrasonico", 10),
        ("transmisores-de-nivel-radar", 8),
        ("medidores-radar-de-nivel", 5),
    ]
    out = _filtrar_niveles_por_tecnologia(niveles, prefer, excluir)
    labels = [n[0] for n in out]
    assert "ultrasonico" not in labels[0]
    assert "radar" in labels[0]
    print("OK NIVEL_1 radar primero:", labels)


if __name__ == "__main__":
    test_cemento_es_solido()
    test_excluye_ultrasonico()
    test_niveles_radar_primero()
    print("TODOS OK")

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from product_discovery import (
    _clave_dedup_opcion,
    _combinar_opciones_catalogo_fallback,
    _construir_opciones,
    _deduplicar_opciones_valores,
)


def test_dedup_rangos_usuario():
    entrada = [
        "Checktemp -50.0 a 150.0°C",
        "-20-90°",
        "-10 a 300°C",
        "-10-300°",
    ]
    salida = _deduplicar_opciones_valores(entrada)
    assert len(salida) == 3, salida
    assert _clave_dedup_opcion("-10 a 300°C") == _clave_dedup_opcion("-10-300°")
    assert sum(1 for x in salida if "300" in x and "-10" in x) == 1
    assert "-50 a 150 °C" in salida
    assert "-20 a 90 °C" in salida
    assert "-10 a 300 °C" in salida


def test_combinar_catalogo_fallback_sin_repetir():
    catalogo = ["-10 a 300°C", "Checktemp -50.0 a 150.0°C"]
    fallback = ["-10-300°", "-20 a 80 °C", "-50 a 500 °C"]
    salida = _combinar_opciones_catalogo_fallback(catalogo, fallback)
    claves = [_clave_dedup_opcion(v) for v in salida]
    assert len(claves) == len(set(claves)), salida


def test_construir_opciones_chip_otro():
    opciones = _construir_opciones(
        [
            "Checktemp -50.0 a 150.0°C",
            "-20-90°",
            "-10 a 300°C",
            "-10-300°",
        ]
    )
    labels = [o["label"] for o in opciones if o["label"] != "Otro"]
    assert len(labels) == 3, labels
    assert opciones[-1]["label"] == "Otro"
    claves = [_clave_dedup_opcion(l) for l in labels]
    assert len(claves) == len(set(claves))


if __name__ == "__main__":
    test_dedup_rangos_usuario()
    test_combinar_catalogo_fallback_sin_repetir()
    test_construir_opciones_chip_otro()
    print("TODOS OK")

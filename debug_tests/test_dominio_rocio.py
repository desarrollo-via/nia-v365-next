"""Dominio correcto por variable de proceso (no mezclar caudal/nivel/humedad)."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from hybrid_discovery import (
    _inferir_dominio_tolerante,
    _detectar_dominio_hibrido,
    generar_pregunta_aplicacion,
    es_necesidad_hibrida_guiada,
)


def test_punto_rocio_es_humedad():
    texto = "necesito medir el punto de rocio"
    assert _inferir_dominio_tolerante(texto) == "humedad"
    assert _detectar_dominio_hibrido(texto) == "humedad"
    assert es_necesidad_hibrida_guiada(texto)
    pregunta = generar_pregunta_aplicacion("humedad")
    assert "humedad" in pregunta["texto"].lower() or "rocío" in pregunta["texto"].lower()
    assert "caudal" not in pregunta["texto"].lower()
    print("OK punto rocio -> humedad:", pregunta["texto"])


def test_nivel_sigue_nivel():
    assert _inferir_dominio_tolerante("necesito medir nivel") == "nivel"
    print("OK nivel -> nivel")


def test_presion_sigue_presion():
    assert _inferir_dominio_tolerante("necesito medir presion") == "presion"
    print("OK presion -> presion")


def test_caudal_explicito():
    assert _inferir_dominio_tolerante("necesito medir caudal") == "caudal"
    print("OK caudal -> caudal")


if __name__ == "__main__":
    test_punto_rocio_es_humedad()
    test_nivel_sigue_nivel()
    test_presion_sigue_presion()
    test_caudal_explicito()
    print("TODOS OK")

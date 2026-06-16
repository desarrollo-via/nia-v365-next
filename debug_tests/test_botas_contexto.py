import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from discovery_guards import (
    construir_texto_limpio_descubrimiento,
    es_producto_epi_seguridad,
    es_respuesta_desconocida,
    filtrar_terminos_libros,
    preguntas_refino_epi,
    respuestas_utiles,
)
from main import _construir_query_acumulado, _continuar_secuencia_preguntas


def test_epi_detecta_botas():
    assert es_producto_epi_seguridad("necesito unas botas para electricidad")
    assert es_producto_epi_seguridad("Botas dielectricas")


def test_no_se_no_contamina_query():
    ctx = {
        "texto_original": "necesito unas botas para electricidad",
        "respuestas_tecnicas": ["20000 V", "temperatura ambiente maximo 40oC", "no se"],
    }
    query = _construir_query_acumulado(ctx)
    assert "no se" not in query.lower()
    assert "20000" in query
    assert "botas" in query


def test_continuar_ignora_no_se():
    ctx = {
        "preguntas_pendientes": ["Q1", "Q2", "Q3"],
        "pregunta_indice": 2,
        "respuestas_tecnicas": ["20000 V", "40C"],
        "texto_original": "botas electricidad",
    }
    _, _, actualizado, buscar = _continuar_secuencia_preguntas(ctx, "no se", {})
    assert buscar is True
    assert len(actualizado["respuestas_tecnicas"]) == 2


def test_filtrar_terminos_instrumentacion_en_epi():
    ancla = "necesito botas para electricidad"
    terminos = ["Medidor Doppler", "RTD tipo K", "botas dielectricas"]
    filtrados = filtrar_terminos_libros(terminos, ancla)
    assert "Medidor Doppler" not in filtrados
    assert "RTD tipo K" not in filtrados


def test_preguntas_epi_no_mencionan_termopar():
    preguntas = preguntas_refino_epi("necesito botas para electricidad")
    texto = " ".join(
        (p.get("texto") if isinstance(p, dict) else str(p)) for p in preguntas
    ).lower()
    assert "termopar" not in texto
    assert "rtd" not in texto
    assert isinstance(preguntas[0], dict)
    assert preguntas[0].get("opciones")


def test_respuestas_utiles_filtra_desconocidas():
    assert respuestas_utiles(["20000 V", "no se", "dielectricas"]) == [
        "20000 V",
        "dielectricas",
    ]


if __name__ == "__main__":
    test_epi_detecta_botas()
    test_no_se_no_contamina_query()
    test_continuar_ignora_no_se()
    test_filtrar_terminos_instrumentacion_en_epi()
    test_preguntas_epi_no_mencionan_termopar()
    test_respuestas_utiles_filtra_desconocidas()
    print("OK: test_botas_contexto")

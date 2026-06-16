import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from main import _continuar_secuencia_preguntas


def test_otro_en_pregunta_tecnica_no_busca():
    cliente = {"nombre": "Andres"}
    ctx = {
        "fase_descubrimiento": "preguntas_tecnicas",
        "preguntas_pendientes": [
            {
                "texto": "¿Cuál es el material que necesitas?",
                "opciones": [
                    {"id": "1", "label": "Latón", "valor": "Latón"},
                    {"id": "2", "label": "Otro", "valor": "otro"},
                ],
            },
            {
                "texto": "¿Cuál es el tipo de conexión o montaje que necesitas?",
                "opciones": [
                    {"id": "1", "label": "1/2'' NPT", "valor": "1/2'' NPT"},
                    {"id": "2", "label": "Otro", "valor": "otro"},
                ],
            },
        ],
        "pregunta_indice": 1,
        "respuestas_tecnicas": ["Latón"],
    }

    respuesta, etapa, ctx_nuevo, accion = _continuar_secuencia_preguntas(
        ctx, "otro", cliente
    )

    assert accion == "esperar_otro", accion
    assert ctx_nuevo["fase_descubrimiento"] == "esperando_otro_tecnico"
    assert ctx_nuevo["respuestas_tecnicas"] == ["Latón"]
    assert "Descríbelo" in respuesta
    print("OK otro -> esperar descripcion")


def test_descripcion_tras_otro_dispara_busqueda():
    cliente = {"nombre": "Andres"}
    ctx = {
        "fase_descubrimiento": "preguntas_tecnicas",
        "preguntas_pendientes": [
            {"texto": "¿Material?", "opciones": []},
            {
                "texto": "¿Conexión?",
                "opciones": [
                    {"id": "1", "label": "1/2'' NPT", "valor": "1/2'' NPT"},
                    {"id": "2", "label": "Otro", "valor": "otro"},
                ],
            },
        ],
        "pregunta_indice": 1,
        "respuestas_tecnicas": ["Latón"],
    }

    _, _, ctx_nuevo, accion = _continuar_secuencia_preguntas(
        ctx,
        "4 pulgadas y 6 pulgadas",
        cliente,
        respuesta_forzada="4 pulgadas y 6 pulgadas",
    )

    assert accion == "buscar", accion
    assert "4 pulgadas" in ctx_nuevo["respuestas_tecnicas"][-1]
    assert "otro" not in [r.lower() for r in ctx_nuevo["respuestas_tecnicas"]]
    print("OK descripcion tras otro -> buscar con texto")


if __name__ == "__main__":
    test_otro_en_pregunta_tecnica_no_busca()
    test_descripcion_tras_otro_dispara_busqueda()
    print("TODOS OK")

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from learning_memory import (
    construir_contexto_aprendizaje_desde_necesidad,
    construir_evento_feedback,
    extraer_slice_historial,
    filtrar_productos_por_aprendizaje,
    resolver_clave_aprendizaje,
    _acumular_resumen,
    _vacio_memoria,
)


def test_resolver_clave_prioriza_phone():
    clave = resolver_clave_aprendizaje(
        phone_id="573001112233",
        cliente={"email": "a@b.com"},
        session_id="sess-1",
    )
    assert clave == "phone:573001112233"


def test_resolver_clave_email_sin_phone():
    clave = resolver_clave_aprendizaje(
        phone_id=None,
        cliente={"email": "Cliente@Example.com"},
        session_id="sess-1",
    )
    assert clave == "email:cliente@example.com"


def test_construir_evento_feedback_producto():
    evento = construir_evento_feedback(
        clave_aprendizaje="phone:1",
        tipo="no",
        categoria="producto",
        mensaje_usuario="no",
        session_id="sess-1",
        producto={"codigo": "P245613", "nombre": "Radar TDR", "nivel_1": "transmisor-de-nivel"},
        contexto={"dominio": "nivel", "texto_original": "medir cemento"},
        historial=[
            {"role": "user", "content": "necesito medir nivel", "ts": "2026-01-01"},
            {"role": "assistant", "content": "¿Este producto cubre lo que necesitas?", "ts": "2026-01-02"},
        ],
    )

    assert evento["tipo"] == "no"
    assert evento["producto"]["codigo"] == "P245613"
    assert evento["contexto"]["dominio"] == "nivel"
    assert len(evento["historial_slice"]) == 2


def test_filtrar_productos_rechazados():
    productos = [
        {"codigo": "P111"},
        {"codigo": "P222"},
        {"codigo": "P333"},
    ]
    memoria = {
        "productos_rechazados": ["P222"],
        "productos_aceptados": [],
    }

    filtrados = filtrar_productos_por_aprendizaje(productos, memoria)
    codigos = [p["codigo"] for p in filtrados]

    assert codigos == ["P111", "P333"]


def test_acumular_resumen_si_y_no():
    memoria = _vacio_memoria()

    memoria = _acumular_resumen(
        memoria,
        {
            "tipo": "si",
            "categoria": "producto",
            "producto": {"codigo": "P1", "nivel_1": "psicrometro"},
            "contexto": {"dominio": "humedad"},
        },
    )
    memoria = _acumular_resumen(
        memoria,
        {
            "tipo": "no",
            "categoria": "producto",
            "producto": {"codigo": "P2", "nivel_1": "medidor-caudal"},
            "contexto": {"dominio": "caudal"},
        },
    )

    assert memoria["productos_aceptados"] == ["P1"]
    assert memoria["productos_rechazados"] == ["P2"]
    assert "humedad" in memoria["dominios_aceptados"]
    assert "caudal" in memoria["dominios_rechazados"]


def test_contexto_desde_necesidad_ctx():
    ctx = construir_contexto_aprendizaje_desde_necesidad(
        {
            "texto_original": "punto de rocio",
            "dominio": "humedad",
            "nivel_1_seleccionado": "psicrometro",
            "respuestas_hibridas_previas": ["interior"],
            "respuestas_tecnicas": ["-40 a 60"],
        }
    )

    assert ctx["dominio"] == "humedad"
    assert ctx["nivel_1"] == "psicrometro"
    assert ctx["respuestas_hibridas"] == ["interior"]


def test_extraer_slice_historial_limita_turnos():
    historial = [
        {"role": "user", "content": f"mensaje {i}", "ts": str(i)}
        for i in range(50)
    ]

    slice_hist = extraer_slice_historial(historial)
    assert len(slice_hist) == 30
    assert slice_hist[0]["content"] == "mensaje 20"


if __name__ == "__main__":
    test_resolver_clave_prioriza_phone()
    test_resolver_clave_email_sin_phone()
    test_construir_evento_feedback_producto()
    test_filtrar_productos_rechazados()
    test_acumular_resumen_si_y_no()
    test_contexto_desde_necesidad_ctx()
    test_extraer_slice_historial_limita_turnos()
    print("OK: test_aprendizaje_feedback")

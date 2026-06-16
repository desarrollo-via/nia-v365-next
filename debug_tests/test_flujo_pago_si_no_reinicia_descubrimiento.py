import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from main import (
    _limpiar_ctx_para_cierre_comercial,
    _manejar_estado_comercial_prioritario,
)


def test_proforma_si_limpia_ctx_y_no_deja_botones():
    ctx_sucio = {
        "fase_descubrimiento": "preguntas_hibridas",
        "flujo_descubrimiento": "hibrida_libros",
        "dominio": "fluido",
        "opciones_actuales": [{"label": "Sí", "valor": "sí"}],
    }

    res = _manejar_estado_comercial_prioritario(
        etapa="proforma_enviada",
        mensaje="sí",
        cliente={"nombre": "Andres Valencia"},
        productos_acumulados=[{"producto": {"codigo": "P1"}}],
        necesidad_ctx=ctx_sucio,
    )

    assert res is not None
    assert res["etapa"] == "pago"
    assert res["necesidad_ctx"].get("comercial_listo_asesor") is True
    assert res["necesidad_ctx"].get("opciones_actuales") == []
    assert "fase_descubrimiento" not in res["necesidad_ctx"]
    assert "fluido" not in res["respuesta"].lower()


def test_pago_si_no_reinicia_descubrimiento():
    ctx_sucio = {
        "fase_descubrimiento": "preguntas_hibridas",
        "flujo_descubrimiento": "hibrida_libros",
        "dominio": "fluido",
        "opciones_actuales": [{"label": "Sí", "valor": "sí"}],
    }

    res = _manejar_estado_comercial_prioritario(
        etapa="pago",
        mensaje="sí",
        cliente={"nombre": "Andres Valencia"},
        productos_acumulados=[{"producto": {"codigo": "P1"}}],
        necesidad_ctx=ctx_sucio,
    )

    assert res is not None
    assert res["handled"] is True
    assert res["etapa"] == "pago_confirmado"
    assert "asesor" in res["respuesta"].lower()
    assert "fluido" not in res["respuesta"].lower()
    assert "material" not in res["respuesta"].lower()
    assert res["necesidad_ctx"].get("fase_descubrimiento") is None


def test_limpiar_ctx_para_cierre_comercial():
    ctx = _limpiar_ctx_para_cierre_comercial(
        {
            "fase_descubrimiento": "preguntas_hibridas",
            "cotizacion_aprobada_cliente": True,
            "opciones_actuales": [{"label": "Sí"}],
        }
    )

    assert ctx["comercial_listo_asesor"] is True
    assert ctx["opciones_actuales"] == []
    assert ctx.get("cotizacion_aprobada_cliente") is True
    assert "fase_descubrimiento" not in ctx


if __name__ == "__main__":
    test_proforma_si_limpia_ctx_y_no_deja_botones()
    test_pago_si_no_reinicia_descubrimiento()
    test_limpiar_ctx_para_cierre_comercial()
    print("OK: test_flujo_pago_si_no_reinicia_descubrimiento")

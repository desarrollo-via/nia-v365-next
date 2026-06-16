"""Prueba carrito: si agrega, cotizar cierra, límite 100."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import main


def _productos(n: int):
    return [
        {"producto": {"codigo": f"P{i}"}, "cantidad": 1, "ts": datetime.utcnow().isoformat()}
        for i in range(n)
    ]


def test_si_agrega_otro_producto():
    r = main._manejar_estado_comercial_prioritario(
        etapa="confirmando_cierre",
        mensaje="si",
        cliente={"nombre": "Andres"},
        productos_acumulados=_productos(1),
        necesidad_ctx={},
        historial=[],
    )
    assert r["handled"]
    assert r["etapa"] == "inicio"
    assert "agregar" in r["respuesta"].lower()
    print("OK si -> inicio")


def test_cotizar_cierra():
    r = main._manejar_estado_comercial_prioritario(
        etapa="confirmando_cierre",
        mensaje="cotizar con esto",
        cliente={"nombre": "Andres", "email": "a@test.com"},
        productos_acumulados=_productos(1),
        necesidad_ctx={},
        historial=[],
    )
    assert r["handled"]
    assert r["etapa"] in {"cotizacion", "calificacion", "cotizacion_lista"}
    print("OK cotizar -> cotizacion")


def test_boton_agregar_otro():
    r = main._manejar_estado_comercial_prioritario(
        etapa="confirmando_cierre",
        mensaje="agregar_otro",
        cliente={},
        productos_acumulados=_productos(2),
        necesidad_ctx={},
        historial=[],
    )
    assert r["etapa"] == "inicio"
    assert "2 productos" in r["respuesta"].lower()
    print("OK boton agregar_otro")


def test_limite_100():
    r = main._manejar_estado_comercial_prioritario(
        etapa="confirmando_cierre",
        mensaje="si",
        cliente={"nombre": "Andres", "email": "a@test.com"},
        productos_acumulados=_productos(100),
        necesidad_ctx={},
        historial=[],
    )
    assert r["handled"]
    assert "100" in r["respuesta"]
    assert r["etapa"] in {"cotizacion", "calificacion", "cotizacion_lista"}
    print("OK limite 100")


def test_timeout_30_min():
    hace_35 = (datetime.utcnow() - timedelta(minutes=35)).isoformat()
    historial = [
        {"role": "assistant", "content": "pregunta", "ts": hace_35},
    ]
    r = main._manejar_estado_comercial_prioritario(
        etapa="confirmando_cierre",
        mensaje="hola",
        cliente={"nombre": "Andres", "email": "a@test.com"},
        productos_acumulados=_productos(3),
        necesidad_ctx={},
        historial=historial,
    )
    assert r["handled"]
    assert "proceder a cotizar" in r["respuesta"].lower()
    print("OK timeout 30 min")


def test_esperando_cantidad_opciones():
    productos = [{"producto": {"codigo": "X"}, "cantidad": None}]
    r = main._manejar_estado_comercial_prioritario(
        etapa="esperando_cantidad",
        mensaje="3",
        cliente={},
        productos_acumulados=productos,
        necesidad_ctx={},
        historial=[],
    )
    assert r["etapa"] == "confirmando_cierre"
    assert r["necesidad_ctx"].get("opciones_actuales")
    assert productos[0]["cantidad"] == 3
    print("OK cantidad + opciones")


if __name__ == "__main__":
    test_si_agrega_otro_producto()
    test_cotizar_cierra()
    test_boton_agregar_otro()
    test_limite_100()
    test_timeout_30_min()
    test_esperando_cantidad_opciones()
    print("TODOS OK")

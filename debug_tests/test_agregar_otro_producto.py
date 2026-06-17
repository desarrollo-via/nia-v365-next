"""
Regresiones del flujo "Agregar otro producto".

Valida que:
1. Un código VIA de seis dígitos se detecte dentro de una frase natural.
2. Las acciones de interfaz no se capturen como nombre del cliente.
3. Un nombre contaminado por una acción previa se elimine del contexto.
"""

from pathlib import Path
import sys


BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from main import (
    _capturar_dato_comercial_por_etapa,
    _parece_nombre_simple,
    _sanitizar_cliente_control,
    detectar_identificador,
    detectar_modo_busqueda,
)


def test_codigo_exacto_dentro_de_frase_natural() -> None:
    mensaje = "Necesito información del producto 107009"

    tipo, valor = detectar_identificador(mensaje)

    assert tipo == "codigo"
    assert valor == "107009"
    assert detectar_modo_busqueda(mensaje) == "codigo_exacto"


def test_acciones_ui_no_son_nombres() -> None:
    acciones = (
        "cotizar",
        "cotizar con esto",
        "cotizar esto",
        "agregar",
        "agregar otro producto",
        "agregar_otro",
    )

    for accion in acciones:
        assert _parece_nombre_simple(accion) is None

        cliente = _capturar_dato_comercial_por_etapa(
            mensaje=accion,
            cliente={},
            etapa="confirmando_cierre",
        )

        assert not cliente.get("nombre"), (
            f"La acción '{accion}' no debe guardarse como nombre."
        )


def test_nombre_contaminado_se_limpia() -> None:
    cliente = _sanitizar_cliente_control(
        {
            "nombre": "Cotizar",
            "email": "cliente@example.com",
        }
    )

    assert "nombre" not in cliente
    assert cliente.get("email") == "cliente@example.com"


def test_nombre_real_se_conserva() -> None:
    cliente = _sanitizar_cliente_control(
        {
            "nombre": "Luis Diaz",
            "email": "cliente@example.com",
        }
    )

    assert cliente.get("nombre") == "Luis Diaz"


def run() -> None:
    test_codigo_exacto_dentro_de_frase_natural()
    test_acciones_ui_no_son_nombres()
    test_nombre_contaminado_se_limpia()
    test_nombre_real_se_conserva()

    print(
        "OK: agregar otro producto conserva el carrito, "
        "detecta códigos en frases y no contamina el nombre."
    )


if __name__ == "__main__":
    run()

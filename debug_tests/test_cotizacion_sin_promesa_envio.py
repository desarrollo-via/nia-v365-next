"""
Guardrail comercial de cotización.

La NIA experimental no debe afirmar que enviará una cotización
por correo mientras no exista una integración real que la genere
y la despache.
"""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAIN_FILE = BASE_DIR / "main.py"


def test_no_promete_envio_de_cotizacion() -> None:
    source = MAIN_FILE.read_text(encoding="utf-8-sig")

    forbidden = (
        "En breve recibirás la cotización en tu correo."
    )

    assert forbidden not in source, (
        "NIA no debe prometer un envío de cotización "
        "que no ha ocurrido."
    )


def test_informa_estado_real_de_la_solicitud() -> None:
    source = MAIN_FILE.read_text(encoding="utf-8-sig")

    expected = (
        "La cotización aún no ha sido emitida ni enviada."
    )

    assert expected in source, (
        "La respuesta debe informar que la cotización "
        "todavía requiere validación."
    )


def run() -> None:
    test_no_promete_envio_de_cotizacion()
    test_informa_estado_real_de_la_solicitud()

    print(
        "OK: la confirmación comercial no promete "
        "un envío inexistente."
    )


if __name__ == "__main__":
    run()

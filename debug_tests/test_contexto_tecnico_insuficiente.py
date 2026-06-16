"""
Regresión del descubrimiento técnico.

Una palabra contextual genérica como "industrial" no debe ser
suficiente para recomendar inmediatamente un SKU.

Una especificación estructurada como 4-20 mA sí debe permitir
la búsqueda técnica directa.
"""

from pathlib import Path
import sys


BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from main import _tiene_campos_tecnicos_mensaje


def test_contexto_generico_no_es_suficiente() -> None:
    mensaje = "Necesito un termómetro industrial"

    resultado = _tiene_campos_tecnicos_mensaje(mensaje)

    assert resultado is False, (
        "La palabra 'industrial' no debe bastar para recomendar "
        "un producto sin descubrimiento adicional."
    )


def test_especificacion_estructurada_si_es_suficiente() -> None:
    mensaje = (
        "Necesito un transmisor con entrada "
        "4-20 mA y salida de relé"
    )

    resultado = _tiene_campos_tecnicos_mensaje(mensaje)

    assert resultado is True, (
        "Una especificación estructurada 4-20 mA debe conservar "
        "la búsqueda técnica directa."
    )


def run() -> None:
    test_contexto_generico_no_es_suficiente()
    test_especificacion_estructurada_si_es_suficiente()

    print(
        "OK: contexto genérico requiere descubrimiento y "
        "la especificación estructurada permite búsqueda directa."
    )


if __name__ == "__main__":
    run()
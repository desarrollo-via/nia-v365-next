"""Pruebas del modo 3: búsqueda técnica/híbrida (sin MongoDB)."""
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

from catalog import extraer_campos_tecnicos
from hybrid_discovery import es_necesidad_hibrida_guiada
from main import detectar_modo_busqueda, _es_busqueda_hibrida, _debe_preguntar_antes_de_buscar


CASOS_HIBRIDA = [
    "necesito un termometro de -50 a 300°C con bulbo de 6 pulgadas",
    "transmisor de presion 0 a 10 bar salida 4-20 mA",
    "termometro industrial rango -40 a 200 C conexion 1/2 NPT",
]

CASOS_PRODUCTO = [
    "necesito un termometro",
    "busco una bomba centrifuga",
]

CASOS_CODIGO = [
    "referencia P1234567",
    "codigo 123456",
    "necesito la referencia P1A2B3C",
]


def main():
    print("=== Extracción de campos técnicos ===")
    texto = CASOS_HIBRIDA[0]
    campos = extraer_campos_tecnicos(texto)
    print(texto)
    print("campos:", campos)
    assert "rango" in campos
    assert campos["rango"].startswith("-50")
    assert "longitud_vastago" in campos

    print("\n=== Modo híbrida ===")
    for caso in CASOS_HIBRIDA:
        modo = detectar_modo_busqueda(caso)
        print(f"{modo:12} | {caso}")
        assert modo == "hibrida", f"Esperaba hibrida, obtuvo {modo} para: {caso}"
        assert not _debe_preguntar_antes_de_buscar(caso)

    print("\n=== Modo producto (sin specs) ===")
    for caso in CASOS_PRODUCTO:
        modo = detectar_modo_busqueda(caso)
        print(f"{modo:12} | {caso}")
        assert modo == "producto", f"Esperaba producto, obtuvo {modo} para: {caso}"
        assert _debe_preguntar_antes_de_buscar(caso)

    print("\n=== Modo código exacto ===")
    for caso in CASOS_CODIGO:
        modo = detectar_modo_busqueda(caso)
        print(f"{modo:12} | {caso}")
        assert modo == "codigo_exacto"

    print("\n=== Modo híbrida guiada (necesidad + libros) ===")
    for caso in [
        "quiero medir temperatura",
        "necesito controlar presion en una caldera",
    ]:
        modo = detectar_modo_busqueda(caso)
        print(f"{modo:16} | {caso}")
        assert modo == "hibrida_guiada", f"Esperaba hibrida_guiada para: {caso}"
        assert es_necesidad_hibrida_guiada(caso)

    print("\nOK — modos híbridos detectados correctamente.")


if __name__ == "__main__":
    main()

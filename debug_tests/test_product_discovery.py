import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from product_discovery import (
    obtener_tipos_nivel_1,
    generar_pregunta_seleccion_tipo,
    generar_preguntas_tecnicas_por_nivel_1,
    analizar_campos_discriminantes,
    obtener_descripciones_largas_por_nivel_1,
)


async def main():
    palabra = "termometro"
    tipos = await obtener_tipos_nivel_1(palabra, top=3)
    pregunta_data = generar_pregunta_seleccion_tipo(palabra, tipos)
    print("Q1:\n")
    print(pregunta_data["texto"])
    print("Opciones:", pregunta_data["opciones"])
    print("\n" + "=" * 80 + "\n")

    nivel = tipos[0]["nivel_1"]
    largas = await obtener_descripciones_largas_por_nivel_1(nivel)
    campos = analizar_campos_discriminantes(largas, top_n=2)
    print("NIVEL_1:", nivel)
    print("Campos discriminantes:", campos)
    print("\nQ2/Q3:")
    for q in await generar_preguntas_tecnicas_por_nivel_1(nivel):
        print("-", q["texto"])
        print("  opciones:", q["opciones"])


if __name__ == "__main__":
    asyncio.run(main())

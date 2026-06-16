import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
load_dotenv(BASE / ".env")

from product_discovery import obtener_tipos_nivel_1_por_texto


async def main():
    for texto in ["para alimentos", "alimentos", "sanitario", "carne"]:
        tipos = await obtener_tipos_nivel_1_por_texto("termometro", texto, top=3)
        print(texto, "->", tipos)


if __name__ == "__main__":
    asyncio.run(main())

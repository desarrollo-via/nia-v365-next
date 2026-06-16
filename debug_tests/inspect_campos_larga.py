import asyncio
import re
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from memory import get_db


def parse_campos(desc):
    campos = {}
    if not desc:
        return campos
    for sep in ["¦", "■", "|"]:
        if sep in desc:
            partes = desc.split(sep)
            break
    else:
        partes = [desc]
    for parte in partes:
        parte = parte.strip()
        if ":" in parte:
            k, v = parte.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            if k and v:
                campos[k] = v
    return campos


async def main():
    db = get_db()
    col = db["products_catalog"]
    tipo = "Termometros bimetalicos"

    cursor = col.find(
        {"DESCRIPCION_CORTA_PRE": tipo},
        {"DESCRIPCION_LARGA_PRE": 1, "_id": 0},
    ).limit(50)
    docs = await cursor.to_list(50)

    campo_valores = Counter()
    campo_distinct = {}

    for doc in docs:
        campos = parse_campos(doc.get("DESCRIPCION_LARGA_PRE", ""))
        for k, v in campos.items():
            campo_valores[k] += 1
            campo_distinct.setdefault(k, set()).add(v)

    print("Campos en", tipo, "n=", len(docs))
    for campo, count in campo_valores.most_common(15):
        distinct = len(campo_distinct.get(campo, set()))
        print(f"  {campo}: freq={count} distinct={distinct}")
        vals = list(campo_distinct[campo])[:5]
        print("    ej:", vals)


if __name__ == "__main__":
    asyncio.run(main())

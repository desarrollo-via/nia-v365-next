import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from memory import get_db


async def main():
    db = get_db()
    col = db["products_catalog"]
    keyword = "termometro"

    pipeline = [
        {"$match": {"DESCRIPCION_CORTA_PRE": {"$regex": keyword, "$options": "i"}}},
        {"$group": {"_id": "$DESCRIPCION_CORTA_PRE", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]
    results = await col.aggregate(pipeline).to_list(8)
    print("TOP TIPOS DESCRIPCION_CORTA_PRE para", keyword)
    for r in results:
        print(r["count"], "|", r["_id"])

    if results:
        tipo = results[0]["_id"]
        doc = await col.find_one(
            {"DESCRIPCION_CORTA_PRE": tipo},
            {"DESCRIPCION_LARGA_PRE": 1, "_id": 0},
        )
        print("\nSAMPLE DESCRIPCION_LARGA_PRE:")
        print((doc or {}).get("DESCRIPCION_LARGA_PRE", "")[:500])


if __name__ == "__main__":
    asyncio.run(main())

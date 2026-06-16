import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from dotenv import load_dotenv
load_dotenv(BASE / ".env")

from catalog import get_db, PRODUCTS_COLLECTION


async def main():
    col = get_db()[PRODUCTS_COLLECTION]
    for q in ["bota", "dielectric", "calzado", "seguridad", "epi"]:
        n = await col.count_documents({
            "$or": [
                {"nombre": {"$regex": q, "$options": "i"}},
                {"NIVEL_1": {"$regex": q, "$options": "i"}},
            ]
        })
        print(q, n)

    pipe = [
        {"$match": {"nombre": {"$regex": "bota", "$options": "i"}}},
        {"$group": {"_id": "$NIVEL_1", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]
    rows = await col.aggregate(pipe).to_list(8)
    print("nivel1 botas:", rows)


if __name__ == "__main__":
    asyncio.run(main())

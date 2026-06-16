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
    for q in ["dielectric", "calzado"]:
        pipe = [
            {"$match": {"nombre": {"$regex": q, "$options": "i"}}},
            {"$group": {"_id": "$NIVEL_1", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        rows = await col.aggregate(pipe).to_list(5)
        print(q, rows)

    doc = await col.find_one({"nombre": {"$regex": "dielectric", "$options": "i"}}, {"nombre": 1, "NIVEL_1": 1, "_id": 0})
    print("sample:", doc)


if __name__ == "__main__":
    asyncio.run(main())

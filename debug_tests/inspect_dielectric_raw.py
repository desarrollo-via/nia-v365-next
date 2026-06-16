import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from dotenv import load_dotenv
load_dotenv(BASE / ".env")
from memory import get_db

COL = "products_catalog"


async def main():
    col = get_db()[COL]
    for term in ["dielectric", "calzado", "bota", "electric"]:
        q = {
            "$or": [
                {"NOMBRE_PRODUCTO": {"$regex": term, "$options": "i"}},
                {"DESCRIPCION": {"$regex": term, "$options": "i"}},
                {"DESCRIPCION_CORTA": {"$regex": term, "$options": "i"}},
                {"NIVEL_1": {"$regex": term, "$options": "i"}},
            ]
        }
        n = await col.count_documents(q)
        print(term, n)
        if n:
            pipe = [
                {"$match": q},
                {"$group": {"_id": "$NIVEL_1", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 4},
            ]
            print(await col.aggregate(pipe).to_list(4))


if __name__ == "__main__":
    asyncio.run(main())

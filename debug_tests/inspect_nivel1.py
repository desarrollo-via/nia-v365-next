import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from memory import get_db


async def main():
    col = get_db()["products_catalog"]
    keyword = "termometro"
    pipeline = [
        {"$match": {"NIVEL_1": {"$regex": keyword, "$options": "i"}}},
        {"$group": {"_id": "$NIVEL_1", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]
    results = await col.aggregate(pipeline).to_list(8)
    print("TOP NIVEL_1 para", keyword)
    for r in results:
        print(r["count"], "|", r["_id"])


if __name__ == "__main__":
    asyncio.run(main())

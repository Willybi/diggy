"""Migration one-shot : ajoute la colonne deezer_id à la table catalog."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE catalog ADD COLUMN IF NOT EXISTS deezer_id VARCHAR(64)"))
    await engine.dispose()
    print("OK — colonne deezer_id ajoutée")

if __name__ == "__main__":
    asyncio.run(main())

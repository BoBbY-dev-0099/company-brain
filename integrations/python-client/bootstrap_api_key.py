"""Create a cb_live_ API key for a clean demo org (local / Docker bootstrap).

Seeds SAG demo skills + backfills embeddings into org `integrations-demo`
so W1–W3 are not polluted by leftover compiled skills in `default`.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.brain import store  # noqa: E402
from backend.core import compiler  # noqa: E402
from backend.demo import seed_data  # noqa: E402

ORG_ID = os.environ.get("BRAIN_BOOTSTRAP_ORG", "integrations-demo")


async def main() -> int:
    await store.init_db()
    seeded = await seed_data.seed_for_org(ORG_ID)
    patched = await seed_data.patch_sag_demo_skills(ORG_ID)
    try:
        filled = await compiler.backfill_seed_embeddings(org_id=ORG_ID)
    except Exception as exc:  # noqa: BLE001
        print(f"embedding backfill warning: {exc}", file=sys.stderr)
        filled = 0
    result = await store.create_api_key(
        org_id=ORG_ID,
        name="integrations-local",
        permissions="read:skills read:events write:events",
    )
    print(f"org_id={ORG_ID}")
    print(f"seed={seeded}")
    print(f"sag_patched={patched}")
    print(f"embeddings_backfilled={filled}")
    print(f"BRAIN_API_KEY={result['api_key']}")
    print("\nexport BRAIN_BASE_URL=http://127.0.0.1:8000")
    print(f"export BRAIN_API_KEY={result['api_key']}")
    await store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

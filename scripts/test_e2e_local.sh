#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_PYTEST=1
RUN_LLM_PHASE=0
BACKUP_DB=1

usage() {
  cat <<'EOF'
Usage: scripts/test_e2e_local.sh [options]

Local end-to-end smoke test:
1) Clean DB teardown + migrate
2) Optional pytest run
3) Seed deterministic indexed posts
4) Assert at least one proposed match exists
5) Optional LLM extraction phase (requires API keys)

Options:
  --skip-pytest    Skip running test suite
  --with-llm       Run additional extraction test via CLI submit --extract
  --no-backup      Skip backing up existing matchbot.db before teardown
  --help           Show this help text
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-pytest)
      RUN_PYTEST=0
      shift
      ;;
    --with-llm)
      RUN_LLM_PHASE=1
      shift
      ;;
    --no-backup)
      BACKUP_DB=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

echo "==> Sync dependencies"
uv sync --dev

if [[ -f "matchbot.db" && "$BACKUP_DB" -eq 1 ]]; then
  backup="matchbot.db.bak.$(date +%Y%m%d-%H%M%S)"
  echo "==> Backing up existing DB to $backup"
  cp matchbot.db "$backup"
fi

echo "==> Teardown: removing matchbot.db"
rm -f matchbot.db

echo "==> Running migrations"
uv run alembic upgrade head

if [[ "$RUN_PYTEST" -eq 1 ]]; then
  echo "==> Running pytest"
  uv run pytest -q
fi

echo "==> Baseline DB assertion (expect empty post/match tables)"
uv run python - <<'PY'
import sqlite3

conn = sqlite3.connect("matchbot.db")
cur = conn.cursor()
post_count = cur.execute("select count(*) from post").fetchone()[0]
match_count = cur.execute("select count(*) from 'match'").fetchone()[0]
conn.close()
print(f"post_count={post_count} match_count={match_count}")
if post_count != 0 or match_count != 0:
    raise SystemExit("Expected empty DB after teardown, but found existing rows.")
PY

echo "==> Seeding deterministic indexed posts and proposing matches"
uv run python - <<'PY'
import asyncio
import uuid

from matchbot.db.engine import get_session
from matchbot.db.models import Platform, Post, PostRole, PostStatus, PostType
from matchbot.matching.queue import propose_matches


async def main() -> None:
    async with get_session() as session:
        seeker = Post(
            platform=Platform.MANUAL,
            platform_post_id=f"e2e_seeker_{uuid.uuid4().hex[:8]}",
            platform_author_id="e2e_seeker_author",
            source_community="e2e-local",
            title="E2E seeker post",
            raw_text="Looking for camp, can help with kitchen and build.",
            status=PostStatus.INDEXED,
            post_type=PostType.MENTORSHIP,
            role=PostRole.SEEKER,
            vibes="community|art",
            contribution_types="kitchen|build",
            year=2026,
            extraction_confidence=1.0,
            extraction_method="e2e_fixture",
        )
        camp = Post(
            platform=Platform.MANUAL,
            platform_post_id=f"e2e_camp_{uuid.uuid4().hex[:8]}",
            platform_author_id="e2e_camp_author",
            source_community="e2e-local",
            title="E2E camp post",
            raw_text="Camp recruiting builders and kitchen support.",
            status=PostStatus.INDEXED,
            post_type=PostType.MENTORSHIP,
            role=PostRole.CAMP,
            vibes="community|art",
            contribution_types="kitchen|build",
            camp_name="Camp E2E",
            year=2026,
            extraction_confidence=1.0,
            extraction_method="e2e_fixture",
        )

        session.add(seeker)
        session.add(camp)
        await session.commit()
        await session.refresh(seeker)
        await session.refresh(camp)

        created = await propose_matches(session, camp)
        print(f"seeded seeker_id={seeker.id[:8]} camp_id={camp.id[:8]} created_matches={len(created)}")
        if not created:
            raise SystemExit("Expected at least one proposed match from seeded posts.")


asyncio.run(main())
PY

echo "==> Queue check"
uv run matchbot queue list --limit 10

if [[ "$RUN_LLM_PHASE" -eq 1 ]]; then
  echo "==> Optional LLM extraction phase (requires valid provider/API key in .env)"
  uv run matchbot submit text "I need a camp for 2026 and can help with kitchen + build." --platform manual --community e2e-llm --extract
  uv run matchbot submit text "Camp Sunforge is recruiting for 2026 and needs kitchen + build support." --platform manual --community e2e-llm --extract
  uv run matchbot posts list --platform manual --limit 10
  uv run matchbot posts list --status error --limit 10
fi

echo "==> E2E local smoke test completed"

"""
Analyze Facebook group data from production Neon database.
Shows actual LLM extraction yield (not regex patterns).

Run from project root: uv run python scripts/analyze_fb_groups_prod.py

Requires: DATABASE_BACKEND=neon and NEON_DATABASE_URL set in .env
"""
import asyncio
from datetime import UTC, datetime
from collections import defaultdict

from sqlalchemy import case, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.engine import get_engine
from matchbot.db.models import Post, PostStatus, Platform


async def analyze_facebook_groups():
    """Query prod DB and rank Facebook groups by extraction yield + freshness."""
    engine = get_engine()

    async with AsyncSession(engine) as session:
        # Query: GROUP BY source_community, count by status
        query = (
            select(
                Post.source_community,
                func.count(Post.id).label("total_posts"),
                func.sum(
                    case(
                        (Post.status.in_([PostStatus.INDEXED, PostStatus.EXTRACTED]), 1),
                        else_=0,
                    )
                ).label("indexed_count"),
                func.sum(
                    case(
                        (Post.status == PostStatus.SKIPPED, 1),
                        else_=0,
                    )
                ).label("skipped_count"),
                func.sum(
                    case(
                        (Post.status == PostStatus.ERROR, 1),
                        else_=0,
                    )
                ).label("error_count"),
                func.max(Post.source_created_at).label("newest_post"),
                func.min(Post.source_created_at).label("oldest_post"),
            )
            .where(Post.platform == Platform.FACEBOOK)
            .group_by(Post.source_community)
        )

        result = await session.exec(query)
        rows = result.all()

    # Process results
    results = []
    now = datetime.now(UTC).replace(tzinfo=None)

    for row in rows:
        source_community = row[0] or "(unlabelled)"
        total_posts = row[1] or 0
        indexed_count = row[2] or 0
        skipped_count = row[3] or 0
        error_count = row[4] or 0
        newest_post = row[5]
        oldest_post = row[6]

        # Calculate metrics
        yield_pct = (indexed_count / total_posts * 100) if total_posts > 0 else 0
        days_since_newest = (now - newest_post).days if newest_post else None

        # DISABLE RECENCY - I control how frequently we scrape, so this is a bad measure. Better to just look at yield % and total indexed volume, and then decide how often to scrape based on that.
        # Recency boost: score is 0 if >60 days old, otherwise (60 - days) / 60
        # if days_since_newest is None:
        #     recency_score = 0
        # else:
        #     recency_score = max(0, (60 - days_since_newest) / 60)

        # Composite score: useful_posts * (1 + recency_boost)
        # This prioritizes both volume and freshness
        composite_score = indexed_count # * (1 + recency_score)

        results.append({
            "source_community": source_community,
            "total_posts": total_posts,
            "indexed": indexed_count,
            "skipped": skipped_count,
            "error": error_count,
            "yield_pct": yield_pct,
            "newest_post": newest_post,
            "oldest_post": oldest_post,
            "days_since_newest": days_since_newest,
            "recency_score": recency_score,
            "composite_score": composite_score,
        })

    # Sort by composite score (useful posts + freshness)
    results.sort(key=lambda r: r["composite_score"], reverse=True)

    # Display results
    print("\n" + "=" * 140)
    print(f"{'GROUP':<50} {'TOTAL':>7} {'INDEXED':>8} {'YIELD%':>7} {'NEWEST':>12} {'DAYS OLD':>9} {'SCORE':>10}")
    print("=" * 140)

    for r in results:
        newest_str = r["newest_post"].strftime("%Y-%m-%d") if r["newest_post"] else "n/a"
        days_str = f"{r['days_since_newest']}d" if r["days_since_newest"] is not None else "n/a"

        print(
            f"{r['source_community']:<50} "
            f"{r['total_posts']:>7} "
            f"{r['indexed']:>8} "
            f"{r['yield_pct']:>6.1f}% "
            f"{newest_str:>12} "
            f"{days_str:>9} "
            f"{r['composite_score']:>10.1f}"
        )

    print("=" * 140)

    # Tier 1 recommendation: top 5 groups by composite score
    print("\n\n── TIER 1 — SCRAPE WEEKLY (Top 5 by freshness-weighted yield) ──")
    print(f"{'GROUP':<50} {'INDEXED':>8} {'NEWEST':>12} {'SCORE':>10}")
    print("-" * 80)
    for r in results[:5]:
        newest_str = r["newest_post"].strftime("%Y-%m-%d") if r["newest_post"] else "n/a"
        print(
            f"{r['source_community']:<50} "
            f"{r['indexed']:>8} "
            f"{newest_str:>12} "
            f"{r['composite_score']:>10.1f}"
        )

    # Tier 2: groups 6-15 by composite score
    print("\n\n── TIER 2 — SCRAPE MONTHLY (Groups 6-15) ──")
    print(f"{'GROUP':<50} {'INDEXED':>8} {'NEWEST':>12} {'SCORE':>10}")
    print("-" * 80)
    for r in results[5:15]:
        newest_str = r["newest_post"].strftime("%Y-%m-%d") if r["newest_post"] else "n/a"
        print(
            f"{r['source_community']:<50} "
            f"{r['indexed']:>8} "
            f"{newest_str:>12} "
            f"{r['composite_score']:>10.1f}"
        )

    # Stats on non-indexed posts
    print("\n\n── SKIPPED / ERROR BREAKDOWN ──")
    print(f"{'GROUP':<50} {'SKIPPED':>8} {'ERROR':>8} {'UNCLEAR':>8}")
    print("-" * 80)
    for r in results:
        unclear = r["total_posts"] - r["indexed"] - r["skipped"] - r["error"]
        print(
            f"{r['source_community']:<50} "
            f"{r['skipped']:>8} "
            f"{r['error']:>8} "
            f"{unclear:>8}"
        )

    print("\n[NOTE] 'UNCLEAR' = posts with status RAW, NEEDS_REVIEW, or CLOSED_STALE")
    print("[NOTE] Composite score = indexed_posts * (1 + recency_boost), where recency_boost")
    print("       is 0 for posts >60 days old, 1.0 for posts <1 day old.")


if __name__ == "__main__":
    asyncio.run(analyze_facebook_groups())

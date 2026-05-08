"""Content-based deduplication using SHA-256 and MinHash/LSH."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

import numpy as np
from datasketch import MinHash, MinHashLSH
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Post, PostStatus


def normalize_for_dedup(text: str) -> str:
    """Normalize text by lowercasing, removing non-alphanumeric, and collapsing whitespace."""
    if not text:
        return ""
    # Lowercase
    text = text.lower()
    # Remove non-alphanumeric (keep spaces)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    # Collapse whitespace
    text = " ".join(text.split())
    return text


def generate_content_hash(text: str) -> str:
    """Generate SHA-256 hash of normalized text."""
    normalized = normalize_for_dedup(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_minhash(text: str, num_perm: int = 128) -> MinHash:
    """Compute MinHash signature for the given text using character-level 5-grams."""
    normalized = normalize_for_dedup(text)
    m = MinHash(num_perm=num_perm)
    
    # Character-level 5-grams are more robust to small word changes than word-level 3-grams
    if len(normalized) < 5:
        shingles = [normalized]
    else:
        shingles = [normalized[i : i + 5] for i in range(len(normalized) - 4)]
    
    for s in shingles:
        m.update(s.encode("utf-8"))
    return m


def serialize_minhash(m: MinHash) -> str:
    """Serialize MinHash hashvalues to a comma-separated string of hex values."""
    return ",".join(hex(h) for h in m.hashvalues)


def deserialize_minhash(sig_str: str, num_perm: int = 128) -> MinHash:
    """Deserialize MinHash from comma-separated hex string."""
    m = MinHash(num_perm=num_perm)
    m.hashvalues = np.array([int(h, 16) for h in sig_str.split(",")], dtype=np.uint64)
    return m


async def find_canonical_post(
    session: AsyncSession,
    post: Post,
    threshold: float = 0.7,
    window_days: int = 14,
) -> Post | None:
    """
    Search for a canonical post that matches the new post (exact or fuzzy).
    
    Returns the oldest matching post (canonical) or None if unique.
    """
    if not post.raw_text:
        return None

    # 1. Exact Match via Hash
    if not post.content_hash:
        post.content_hash = generate_content_hash(post.raw_text)
    
    exact_q = select(Post).where(
        Post.content_hash == post.content_hash,
        Post.id != post.id,
        Post.parent_post_id.is_(None),  # Only match against canonicals
        Post.status != PostStatus.SKIPPED,
    ).order_by(Post.detected_at.asc())
    
    exact_match = (await session.exec(exact_q)).first()
    if exact_match:
        return exact_match

    # 2. Fuzzy Match via MinHash/LSH
    if not post.minhash_sigs:
        m_new = compute_minhash(post.raw_text)
        post.minhash_sigs = serialize_minhash(m_new)
    else:
        m_new = deserialize_minhash(post.minhash_sigs)

    # Load recent canonical posts
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=window_days)
    recent_q = select(Post).where(
        Post.detected_at >= since,
        Post.id != post.id,
        Post.parent_post_id.is_(None),
        Post.status != PostStatus.SKIPPED,
        Post.minhash_sigs.is_not(None),
    )
    candidates = (await session.exec(recent_q)).all()
    if not candidates:
        return None

    # Use LSH for efficient querying
    # We use a slightly lower threshold for LSH to ensure better recall, 
    # then we can verify with a strict check if needed.
    lsh = MinHashLSH(threshold=0.6, num_perm=128)
    for c in candidates:
        if c.minhash_sigs:
            m_c = deserialize_minhash(c.minhash_sigs)
            lsh.insert(c.id, m_c)
    
    # Query LSH
    matches = lsh.query(m_new)
    if not matches:
        return None
    
    # If we have matches, find the oldest one that meets the actual threshold
    oldest_match_q = select(Post).where(Post.id.in_(matches)).order_by(Post.detected_at.asc())
    possible_canonicals = (await session.exec(oldest_match_q)).all()
    
    for cand in possible_canonicals:
        if cand.minhash_sigs:
            m_cand = deserialize_minhash(cand.minhash_sigs)
            if m_new.jaccard(m_cand) >= threshold:
                return cand
                
    return None

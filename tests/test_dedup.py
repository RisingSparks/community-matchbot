import pytest
from sqlmodel import select
from matchbot.db.models import Post, PostStatus, Platform
from matchbot.extraction import process_post
from matchbot.extraction.dedup import generate_content_hash, compute_minhash
from matchbot.extraction.anthropic_extractor import AnthropicExtractor

from matchbot.extraction.schemas import ExtractedPost

@pytest.mark.asyncio
async def test_exact_deduplication(db_session, mocker):
    # Mock extractor to avoid API calls
    mock_extractor = mocker.Mock(spec=AnthropicExtractor)
    mock_extractor.provider_name.return_value = "mock"
    mock_extractor.extract = mocker.AsyncMock(return_value=ExtractedPost(
        confidence=1.0,
        role="seeker",
        post_type="mentorship",
        vibes=[],
        contribution_types=[]
    ))
    
    raw_text = "Looking for a theme camp to join! I love penguins and ice."
    
    # 1. First post (canonical)
    post1 = Post(
        platform=Platform.FACEBOOK,
        platform_post_id="p1",
        raw_text=raw_text,
        title="Post 1",
        status=PostStatus.RAW
    )
    db_session.add(post1)
    await db_session.commit()
    await db_session.refresh(post1)
    
    # Process first post
    await process_post(db_session, post1, mock_extractor)
    
    # Use text that WILL match keywords to ensure it hits the LLM path (if not deduped).
    raw_text_kw = "Looking for a theme camp to join! I can help with build and kitchen."
    
    post1.raw_text = raw_text_kw
    post1.content_hash = None # Reset to recompute
    db_session.add(post1)
    await db_session.commit()
    
    await process_post(db_session, post1, mock_extractor)
    assert post1.parent_post_id is None
    assert post1.content_hash == generate_content_hash(raw_text_kw)
    
    # 2. Second post (exact duplicate)
    post2 = Post(
        platform=Platform.FACEBOOK,
        platform_post_id="p2",
        raw_text=raw_text_kw,
        title="Post 2",
        status=PostStatus.RAW
    )
    db_session.add(post2)
    await db_session.commit()
    
    await process_post(db_session, post2, mock_extractor)
    
    assert post2.status == PostStatus.SKIPPED
    assert post2.parent_post_id == post1.id
    assert post2.extraction_method == "dedup"
    assert post2.extraction_method == "dedup"

@pytest.mark.asyncio
async def test_fuzzy_deduplication(db_session, mocker):
    mock_extractor = mocker.Mock(spec=AnthropicExtractor)
    mock_extractor.provider_name.return_value = "mock"
    mock_extractor.extract = mocker.AsyncMock(return_value=ExtractedPost(
        confidence=1.0,
        role="seeker",
        post_type="mentorship",
        vibes=[],
        contribution_types=[]
    ))
    
    text1 = "Looking for a theme camp to join! I am an artist and a builder. I have been to the burn 5 times."
    text2 = "Looking for a theme camp to join! I'm an artist and a builder. I've been to the burn 5 times." # Slightly different
    
    post1 = Post(
        platform=Platform.REDDIT,
        platform_post_id="r1",
        raw_text=text1,
        title="Art/Build seeker",
        status=PostStatus.RAW
    )
    db_session.add(post1)
    await db_session.commit()
    
    await process_post(db_session, post1, mock_extractor)
    
    post2 = Post(
        platform=Platform.DISCORD,
        platform_post_id="d1",
        raw_text=text2,
        title="Seeking Art Camp",
        status=PostStatus.RAW
    )
    db_session.add(post2)
    await db_session.commit()

    await process_post(db_session, post2, mock_extractor)

    # Text2 should be fuzzy matched to Text1 (Jaccard > 0.7)
    assert post2.status == PostStatus.SKIPPED, f"Similarity was {similarity}"
    assert post2.parent_post_id == post1.id
    assert post2.extraction_method == "dedup"

@pytest.mark.asyncio
async def test_not_deduplicated_if_different(db_session, mocker):
    mock_extractor = mocker.Mock(spec=AnthropicExtractor)
    mock_extractor.provider_name.return_value = "mock"
    mock_extractor.extract = mocker.AsyncMock(return_value=ExtractedPost(
        confidence=1.0,
        role="seeker",
        post_type="mentorship",
        vibes=[],
        contribution_types=[]
    ))
    
    text1 = "Looking for a theme camp to join! I love penguins."
    text2 = "Looking for a theme camp to join! I love sparkle ponies."
    
    post1 = Post(
        platform=Platform.REDDIT,
        platform_post_id="r1",
        raw_text=text1,
        status=PostStatus.RAW
    )
    db_session.add(post1)
    await db_session.commit()
    await process_post(db_session, post1, mock_extractor)
    
    post2 = Post(
        platform=Platform.REDDIT,
        platform_post_id="r2",
        raw_text=text2,
        status=PostStatus.RAW
    )
    db_session.add(post2)
    await db_session.commit()
    await process_post(db_session, post2, mock_extractor)
    
    assert post2.parent_post_id is None
    # If it was different enough, it shouldn't be deduped
    assert post2.extraction_method != "dedup"

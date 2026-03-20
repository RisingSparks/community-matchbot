# Plan: Seeker Sub-types (A vs A.2)

## Context

`PostRole.SEEKER` conflates two distinct use cases with different match criteria:
- **A — Camp membership seeker**: "I want to join a camp." Match on vibe culture fit + contribution fit.
- **A.2 — Skills/learning seeker**: "I want to learn to weld / build shade / do art." Match primarily on contribution_types overlap (does the camp teach what I want to learn?), vibe matters less.

Both currently get the same Jaccard weights (35% vibe, 40% contribution), the same match query, and the same intro template. The fix adds a `seeker_intent` field that flows through extraction → scoring → rendering without breaking the existing `seeker/camp` binary that the queue relies on.

---

## Approach

Add `seeker_intent: str | None` (values: `membership | skills_learning | unknown`) to `Post` and `Profile`. Pipe it through extraction, use it to select scorer weights, and dispatch to different intro templates.

No change to `Post.role` values or the `seeker → camp` matching direction. Skills seekers still match against camp posts — the camp just needs `teaching` in its `contribution_types` to score well.

---

## Files to Change

### 1. `src/matchbot/db/models.py`
- Add `class SeekerIntent` constant class: `MEMBERSHIP = "membership"`, `SKILLS_LEARNING = "skills_learning"`, `UNKNOWN = "unknown"`
- Add `seeker_intent: str | None = Field(default=None)` to `Post` (after `role`)
- Add `seeker_intent: str | None = Field(default=None)` to `Profile` (after `role`)

### 2. `src/matchbot/extraction/schemas.py`
- Add `seeker_intent: str | None = None` field to `ExtractedPost`
- Add `validate_seeker_intent` classmethod: allow `{"membership", "skills_learning", "unknown"}`, default to `None` (not `"unknown"`) so `None` means "not a seeker post at all" vs `"unknown"` meaning "seeker but unclear subtype"

### 3. `src/matchbot/extraction/prompts.py`
- Add `"seeker_intent": "membership" | "skills_learning" | "unknown" | null` to the output schema block
- Add guidance: set `"seeker_intent"` only when `role == "seeker"`. Use `"membership"` if they want to join a camp as a member; `"skills_learning"` if they want to learn a skill, find a mentor, or join a project; `null` for camp posts and infra posts.

### 4. `src/matchbot/extraction/__init__.py`
- In step 5 (Update Post fields), add: `post.seeker_intent = extracted.seeker_intent`
- Add `"seeker_intent": post.seeker_intent` to the `post_extracted` event payload

### 5. `src/matchbot/matching/scorer.py`
- Add `WEIGHTS_SKILLS` dict: `{"vibe_overlap": 0.15, "contribution_overlap": 0.60, "recency": 0.15, "year_match": 0.10}`
- Update `score_match(seeker, camp)` signature to `score_match(seeker, camp, seeker_intent: str | None = None)`
- Select `WEIGHTS` vs `WEIGHTS_SKILLS` based on `seeker_intent == "skills_learning"`
- Return the same `(float, dict)` tuple — breakdown keys stay identical

### 6. `src/matchbot/matching/queue.py`
- In `_propose_mentorship_matches`, update the scorer call:
  `score_match(seeker, camp, seeker_intent=seeker.seeker_intent)`

### 7. `src/matchbot/messaging/renderer.py`
- Add `_SKILLS_TEMPLATES` dict: `{"reddit": "intro_skills_reddit.md.j2", ...}`
- Add `_SKILLS_CAMP_TEMPLATES` dict: `{"reddit": "intro_skills_camp_reddit.md.j2", ...}`
- In `render_intro()`, before the `for_camp` branch, check `seeker.seeker_intent == SeekerIntent.SKILLS_LEARNING` and dispatch to `_render_skills_intro()` / `_render_skills_intro_camp()`
- Add `_render_skills_intro()` and `_render_skills_intro_camp()` functions — same context shape as existing mentorship renderers, so shared_contrib is already the right signal

### 8. `src/matchbot/config/templates/` — 6 new files
Seeker-facing (A.2 seeker gets this):
- `intro_skills_reddit.md.j2`
- `intro_skills_discord.md.j2`
- `intro_skills_facebook.md.j2`

Camp-facing (camp gets this when matched with an A.2 seeker):
- `intro_skills_camp_reddit.md.j2`
- `intro_skills_camp_discord.md.j2`
- `intro_skills_camp_facebook.md.j2`

Template context variables are the same as the existing mentorship templates (`seeker_username`, `camp_name`, `camp_contact`, `shared_vibes`, `shared_contrib`, `seeker_url`, `camp_url`, `moderator_name`). The copy differs: seeker-facing says "I found a camp with teaching/mentorship opportunities"; camp-facing says "this person is looking to learn [shared_contrib], not just join as a member."

### 9. `alembic/versions/<hash>_add_seeker_intent.py` — new migration
```python
op.add_column('post', sa.Column('seeker_intent', AutoString(), nullable=True))
op.add_column('profile', sa.Column('seeker_intent', AutoString(), nullable=True))
```
No index needed (low cardinality, not queried in WHERE clauses yet).

### 10. Tests
- `tests/conftest.py`: add `seeker_intent=None` param to `_make_post()` and both factory fixtures
- `tests/test_scoring.py`:
  - Add `TestScoreMatchSkills` class testing that skills weights are applied when `seeker_intent="skills_learning"`, breakdown keys unchanged
  - Add test: skills seeker with high contribution overlap but zero vibe overlap scores higher under skills weights than membership weights
- `tests/test_seeker_subtypes.py` (new):
  - `ExtractedPost` validator accepts `"membership"`, `"skills_learning"`, `"unknown"`, rejects invalid, passes `None` through
  - `propose_matches` uses skills weights for `seeker_intent="skills_learning"` posts (mock scorer, check call args)
  - `render_intro` dispatches to skills template for skills-learning seeker (check template name used)

---

## Verification

1. `pytest tests/` — all existing tests pass, new tests pass
2. Manual smoke: create a post with `seeker_intent="skills_learning"` in the DB; call `propose_matches`; confirm `score_breakdown` shows `contribution_overlap` weight of 0.60 via `match_method` field or breakdown inspection
3. Run `alembic upgrade head` against a test DB; confirm `seeker_intent` column present on both `post` and `profile`
4. Render check: call `render_intro(skills_seeker, camp, "reddit")` and confirm output contains skills-oriented copy (not membership copy)

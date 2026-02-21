# Plan: Phase 6 - Infrastructure Exchange

## Goal
Implement the "Bitch n Swap" functionality to facilitate equipment and logistics sharing between camps.

## Tasks

### 1. Taxonomy & Models
- [ ] Add `infrastructure_categories` to `config/taxonomy.yaml`.
- [ ] Update `src/matchbot/db/models.py`:
    - Add `PostType` (mentorship, infrastructure).
    - Add infrastructure-specific fields to `Post` if needed (quantity, condition).
- [ ] Update `src/matchbot/taxonomy.py` to load new categories.

### 2. Extraction Logic
- [ ] Update `src/matchbot/extraction/schemas.py` to include `infrastructure_categories`.
- [ ] Update `src/matchbot/extraction/prompts.py` (SYSTEM_PROMPT) to handle infrastructure classification and extraction.
- [ ] Add unit tests for infra extraction in `tests/test_extraction_infra.py`.

### 3. Matching Logic
- [ ] Implement or extend `src/matchbot/matching/scorer.py` to handle infrastructure overlap.
- [ ] Add unit tests for infra scoring in `tests/test_scoring_infra.py`.

### 4. Messaging & CLI
- [ ] Create infrastructure-specific Jinja2 templates in `config/templates/`.
- [ ] Update `src/matchbot/messaging/renderer.py` to use infra templates when appropriate.
- [ ] Update CLI (`cmd_queue.py`, `cmd_posts.py`) to support filtering by `PostType`.

### 5. Verification
- [ ] Verify infra posts are correctly identified and extracted.
- [ ] Verify matches are proposed based on infra categories.
- [ ] Verify intro messages for infra are correctly rendered.

## Success Criteria Verification
1. [ ] A post saying "Need 5kW generator for art project" is extracted as `PostType.INFRASTRUCTURE` with category `power`.
2. [ ] A post saying "Our camp has extra shade cloth to lend" matches the above if they both have `shade` (bad example, but you get it).
3. [ ] `matchbot queue list --type infrastructure` shows relevant matches.

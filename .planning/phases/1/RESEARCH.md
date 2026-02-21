# Research: Phase 1 - Foundation & Taxonomy

## Goal
Establish the project infrastructure and a shared language for camp/builder attributes.

## Findings

### 1. Project Infrastructure
- **Stack**: Python 3.12+ and `uv` are already configured in `pyproject.toml`.
- **Dev Tools**: `pytest`, `ruff`, `mypy` are available.
- **Action**: Need to initialize the package structure in `src/`.

### 2. Central Taxonomy
- **Requirements**: Needs to be "editable" and central.
- **Vibes**: Proposed initial list: `sober`, `party`, `chill`, `loud`, `active`, `wellness`, `art-focused`.
- **Skills/Roles**: Proposed initial list: `build`, `strike`, `kitchen`, `hosting`, `art`, `support`, `logistics`, `power`, `plumbing`.
- **Implementation**: A YAML or JSON file in `src/matchbot/config/taxonomy.yaml` allows easy editing without changing core logic. Pydantic models can be used to validate these at runtime.

### 3. Registry Database
- **Requirements**: Metadata-first storage, canonical links, support for "seeking" vs "offering".
- **Schema**:
    - `posts` table:
        - `id` (UUID)
        - `platform_id` (e.g., Reddit post ID)
        - `platform` (reddit, discord, telegram)
        - `canonical_url` (link to original post)
        - `post_type` (seeking, offering)
        - `role_type` (camp, seeker, art_project)
        - `raw_content` (original text)
        - `extracted_data` (JSON blob for taxonomy tags, etc.)
        - `status` (indexed, needs_review, etc.)
        - `created_at` (timestamp)
        - `updated_at` (timestamp)
- **Implementation**: SQLite for the pilot. SQLAlchemy or SQLModel for ORM.

## Proposed Strategy
1. Create package structure: `src/matchbot/`.
2. Define `taxonomy.yaml`.
3. Create a `Taxonomy` model to load and validate tags.
4. Set up database migrations/initialization using SQLAlchemy.
5. Create a `Registry` service to handle post storage.

## Verification Strategy
1. Test taxonomy loading and validation.
2. Test database initialization and basic CRUD for posts.
3. Verify `uv run` works for the new package.

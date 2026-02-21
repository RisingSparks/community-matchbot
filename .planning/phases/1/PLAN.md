# Plan: Phase 1 - Foundation & Taxonomy

## Goal
Establish the project infrastructure and a shared language for camp/builder attributes.

## Tasks

### 1. Package Initialization
- [ ] Create `src/matchbot/` directory structure.
- [ ] Create `src/matchbot/__init__.py`.
- [ ] Create `src/matchbot/__main__.py` as a placeholder entry point.

### 2. Taxonomy Implementation
- [ ] Create `src/matchbot/taxonomy.yaml` with initial Vibes and Skills.
- [ ] Implement `src/matchbot/models/taxonomy.py` using Pydantic to load and validate the taxonomy.
- [ ] Add `pyyaml` and `pydantic` to dependencies.

### 3. Registry Database Setup
- [ ] Add `sqlalchemy` or `sqlmodel` to dependencies.
- [ ] Implement `src/matchbot/models/database.py` with the `Post` schema.
- [ ] Implement `src/matchbot/services/registry.py` for database operations.
- [ ] Create a script/CLI command to initialize the database.

### 4. Verification & Testing
- [ ] Create `tests/test_taxonomy.py` to verify taxonomy loading.
- [ ] Create `tests/test_registry.py` to verify database operations.
- [ ] Run `pytest`, `ruff`, and `mypy`.

## Success Criteria Verification
1. [ ] Run `uv sync` and verify environment.
2. [ ] Verify `taxonomy.yaml` can be edited and re-loaded.
3. [ ] Verify a sample post can be saved to the database with a canonical link.

# Research: Phase 6 - Infrastructure Exchange (Bitch n Swap)

## Goal
Extend the Matchbot to handle infrastructure and equipment exchange ("Bitch n Swap") between camps and projects.

## Scope
- **Post Types**: Seeking vs. Offering.
- **Categories**: Tools, shade, power, kitchen, transport, setup/strike support, knowledge sharing.
- **Workflow**: Same passive-first ingestion + structured extraction + triage + intro model.

## Research Questions

### 1. Taxonomy Expansion
What are the core categories for infrastructure?
From Briefing Book:
- Tools
- Shade components
- Power gear (generators, solar, distribution)
- Kitchen infrastructure (stoves, gray water, storage)
- Transport help
- Setup/Strike support
- Logistics/Guidance (knowledge)

### 2. Post Identification
How to distinguish infra posts from camp-finding posts?
- Keywords: "borrow", "loan", "swap", "surplus", "selling" (maybe out of scope?), "need generator", "shade cloth".
- Existing `PostRole` (seeker/camp) might need to be refined or a new `PostType` field added (mentorship vs infra).

### 3. Extraction Requirements
What metadata is specific to infra?
- Condition (new/used/broken)
- Quantity
- Dates needed/available
- Location (Playa vs. Default world)
- Transport requirements

### 4. Matching Logic
How does infra matching differ?
- Proximity (if default world).
- Compatibility (e.g., 50A power vs 30A plug).
- Temporal overlap (dates).

## Proposed Implementation Path

### Phase 6a: Taxonomy & Schema
- Update `config/taxonomy.yaml` with `infrastructure_categories`.
- Update `PostRole` or add `PostType` to `src/matchbot/db/models.py`.

### Phase 6b: Extraction
- Update LLM prompts in `src/matchbot/extraction/prompts.py` to handle infra posts.
- Update `ExtractedPost` schema in `src/matchbot/extraction/schemas.py`.

### Phase 6c: Matching & CLI
- Implement `infra_scorer.py` or extend `scorer.py`.
- Update CLI to filter by mentorship vs infra.

### Phase 6d: Messaging
- Add `intro_infra_*.md.j2` templates.
- Update `renderer.py`.

## Next Steps
1. Define the exact taxonomy for infrastructure.
2. Draft the updated LLM prompt for multi-type extraction.
3. Create the implementation plan.

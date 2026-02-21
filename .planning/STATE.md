# Project State

## Project Reference
**Core Value:** Facilitating mentorship-driven matches between seekers and theme camps to strengthen the Burning Man builder pipeline.
**Current Focus:** Transitioning from mentorship matching to infrastructure exchange.

## Current Position
**Phase:** All 7 phases implemented
**Status:** 🟢 Code complete — pilot-ready with caveats
**Progress:** ~95% [███████████████████░]

## Performance Metrics
- **Total v1 Requirements:** 22
- **Requirements Implemented:** 22 (100%)
- **Stubs (not yet wired):** MATCH-03 (platform sending), MATCH-06 (feedback survey trigger)
- **Current Phase Health:** 🟢 Healthy

## Accumulated Context
### Decisions
- Initialized project with 7-phase roadmap derived from Briefing Book.
- Adopted "passive-first" ingestion strategy as a primary constraint.
- Prioritized taxonomy definition as a Phase 1 dependency for all matching logic.
- Implemented Reddit, Discord, and Facebook listeners with LLM-based extraction.
- Developed a deterministic Jaccard scorer for match proposals.
- Created a CLI for moderator triage and automated intro messaging.
- Established basic reporting for pilot metrics.
- Implemented "Bitch n Swap" infrastructure exchange (Phase 6) with separate infra_scorer.
- Added Jinja2 intro templates for all 3 platforms × 2 post types.
- Implemented APScheduler background jobs (stale expiry, feedback, data retention).
- Added WWW Guide enrichment, forms router, and full test suite (181 tests).

### Todos
- [ ] Wire platform senders (Reddit PRAW comment, Discord DM, Facebook Graph API)
- [ ] Add CLI command to trigger LLM triage on flagged matches
- [ ] Decide: change empty-set Jaccard 0.5 default or lower min_score threshold
- [ ] Configure canonical pilot channel (Discord vs Reddit vs hybrid)
- [ ] Define data retention consent language

### Blockers
- None.

## Session Continuity
**Last Action:** Full code review — all 7 phases implemented and 181 tests passing.
**Next Step:** Wire platform senders for pilot, or proceed to pilot operations.

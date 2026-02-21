# Requirements

## v1 Requirements

### Core Indexing (CORE)
- **CORE-01**: Monitor platforms (Reddit, Discord, etc.) for keywords like "seeking camp" or "needs builder".
- **CORE-02**: Extract key elements from posts using LLM into structured JSON (role, vibe, skills, etc.).
- **CORE-03**: Maintain a central registry of indexed posts and entities.
- **CORE-04**: Support a "Source allowlist" to ingest only from approved communities.
- **CORE-05**: Implement event-triggered capture to avoid broad crawling.
- **CORE-06**: Deduplicate repeat posts and expire stale entries in the registry.
- **CORE-07**: Store metadata-first (canonical links and summaries) rather than full content.

### Matching & Triage (MATCH)
- **MATCH-01**: Perform lightweight compatibility triage between seekers and projects.
- **MATCH-02**: Use deterministic parsing for clear cases, falling back to LLM for ambiguous matches.
- **MATCH-03**: Bot posts introduction notes on relevant community threads.
- **MATCH-04**: Send intro messages to both parties with an expectations checklist.
- **MATCH-05**: Track match lifecycle statuses (e.g., `intro_sent`, `conversation_started`, `onboarded`).
- **MATCH-06**: Trigger a simple feedback survey after the outcome window.

### Augmentation (ENH)
- **ENH-01**: Enrich camp data by joining against the What Where When (WWW) Guide data.
- **ENH-02**: Provide a lightweight form for optional data enrichment.
- **ENH-03**: Implement "Bitch n Swap" bot for infrastructure and equipment exchange.

### Operations (OPS)
- **OPS-01**: Maintain a central, editable taxonomy for "Vibes" and "Skills".
- **OPS-02**: Support exporting records for the pilot findings report.
- **OPS-03**: Generate a weekly dashboard (by channel, contribution type, etc.).

### Non-Functional (NFR)
- **NFR-02**: Optimize moderator workflow for <5 minutes per introduction.
- **NFR-03**: Build on Python 3.12+ with `uv` package management.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 2 | ✅ Complete |
| CORE-02 | Phase 2 | ✅ Complete |
| CORE-03 | Phase 1 | ✅ Complete |
| CORE-04 | Phase 2 | ✅ Complete |
| CORE-05 | Phase 2 | ✅ Complete |
| CORE-06 | Phase 2 | ✅ Complete |
| CORE-07 | Phase 1 | ✅ Complete |
| MATCH-01 | Phase 3 | ✅ Complete |
| MATCH-02 | Phase 3 | ✅ Complete |
| MATCH-03 | Phase 4 | ⚠️ Stub (render works; platform posting not wired) |
| MATCH-04 | Phase 4 | ✅ Complete |
| MATCH-05 | Phase 4 | ✅ Complete |
| MATCH-06 | Phase 4 | ⚠️ Partial (flagged in scheduler; no CLI trigger for surveys) |
| ENH-01 | Phase 3 | ✅ Complete |
| ENH-02 | Phase 7 | ✅ Complete |
| ENH-03 | Phase 6 | ✅ Complete |
| OPS-01 | Phase 1 | ✅ Complete |
| OPS-02 | Phase 5 | ✅ Complete |
| OPS-03 | Phase 5 | ✅ Complete |
| NFR-01 | Phase 5 | Removed from Reqs |
| NFR-02 | Phase 4 | ✅ Complete |
| NFR-03 | Phase 1 | ✅ Complete |

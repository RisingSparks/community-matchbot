# Project Roadmap

## Overview
This roadmap outlines the development of the "Matchbot" ecosystem, starting from foundational taxonomy and monitoring primitives to a full-featured matching and reporting system for the Burning Man builder pipeline.

---

## Phase 1: Foundation & Taxonomy
**Goal:** Establish the project infrastructure and a shared language for camp/builder attributes.

- **Dependencies:** None
- **Requirements:** CORE-03, CORE-07, OPS-01, NFR-03
- **Success Criteria:**
  1. System initialized with Python 3.12 and `uv`.
  2. Central taxonomy of "Vibes" and "Skills" is defined and editable.
  3. Registry database supports metadata-first storage with canonical links.

---

## Phase 2: Monitoring & Parsing
**Goal:** Ingest and structure community posts from target platforms.

- **Dependencies:** Phase 1
- **Requirements:** CORE-01, CORE-02, CORE-04, CORE-05, CORE-06
- **Success Criteria:**
  1. Bot detects "seeking" and "offering" posts on at least one pilot channel (e.g., Reddit).
  2. LLM extracts structured JSON (role, skills, vibe) with >80% accuracy in tests.
  3. Registry successfully deduplicates repeat posts and flags stale entries.

---

## Phase 3: Matchmaking Logic
**Goal:** Identify compatible connections between seekers and camps.

- **Dependencies:** Phase 2
- **Requirements:** MATCH-01, MATCH-02, ENH-01
- **Success Criteria:**
  1. Triage logic suggests matches based on taxonomy alignment.
  2. Camp profiles are enriched with WWW Guide data.
  3. Matches are surfaced for review with clear compatibility signals.

---

## Phase 4: Connection & Workflow
**Goal:** Facilitate introductions and track the match lifecycle.

- **Dependencies:** Phase 3
- **Requirements:** MATCH-03, MATCH-04, MATCH-05, MATCH-06, NFR-02
- **Success Criteria:**
  1. Bot can post intro notes or send messages to parties.
  2. Intro messages include the standardized expectations checklist.
  3. Status tracking persists the match state (intro → conversation → onboarded).

---

## Phase 5: Pilot Operations & Reporting
**Goal:** Measure success and manage pilot data.

- **Dependencies:** Phase 4
- **Requirements:** OPS-02, OPS-03
- **Success Criteria:**
  1. Weekly dashboard displays match volume and conversion metrics.
  2. One-click export of anonymized pilot findings report.
  3. Privacy-preserving data retention policy is automatically enforced.

---

## Phase 6: Infrastructure Exchange (Workstream B)
**Goal:** Apply the matchmaking model to gear and logistics.

- **Dependencies:** Phase 2
- **Requirements:** ENH-03
- **Success Criteria:**
  1. "Bitch n Swap" functionality indexes gear needs and surplus.
  2. Successful matches facilitated for infrastructure items (tools, power, etc.).

---

## Phase 7: Enrichment & Polish
**Goal:** Refine the system with optional enrichment and final polish.

- **Dependencies:** Phase 4
- **Requirements:** ENH-02
- **Success Criteria:**
  1. Optional form allows participants to provide deeper profile data.
  2. Refined UX for moderator workflow based on pilot feedback.

---

## Progress

| Phase | Status | Progress |
|-------|--------|----------|
| 1 - Foundation | ✅ Complete | 100% |
| 2 - Monitoring | ✅ Complete | 100% |
| 3 - Matchmaking | ✅ Complete | 100% |
| 4 - Connection | ✅ Complete | 100% |
| 5 - Pilot Ops | ✅ Complete | 100% |
| 6 - Infra Exchange | ✅ Complete | 100% |
| 7 - Polish | ✅ Complete | 100% |

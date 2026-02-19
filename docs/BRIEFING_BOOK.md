# Theme Camp Community Finder - Briefing Book and Product Doc

## Context

**The Challenge**: Burning Man has a builder-capacity risk:
- **The Builder Crisis**: Burning Man’s existential threat isn’t just an aging population; it’s a decline in the number of active **builders**—the people who create the art, build the infrastructure, and maintain the complex systems of Black Rock City.
- **Participation Gap**: While roughly 30% of participants are first-timers ("birgins"), under-30 participation has dropped from ~30% in 2014 to ~12% today.
- **Friction to Action**: New participants face high barriers to entry, not just socially, but in learning the **how-to** of Burning Man: how to build for the desert, how to manage logistics, and how to contribute to large-scale art.
- **Loss of Institutional Knowledge**: As experienced builders and TCOs face burnout, the tacit knowledge of *how to build the city* risks being lost.

## The Insight: Camps Are the Leverage Point

The high-level goal is to move beyond "recruitment" to **cultivating the next generation of builders**. We are not just trying to fill camp slots; we are helping people learn how to build.

**Theme camps** are the natural classrooms and connective tissue of Black Rock City. They are:

Theme camps are already:
- **Skill-Transfer Hubs**: High-trust environments where experienced builders can mentor newcomers in desert-specific engineering, logistics, and art production.
- **Financially enabling**: shared infrastructure (power, water, shade, food) dramatically lowers the cost barrier for newcomers. By lowering the financial and logistical barriers (shared food, water, shade), camps free up newcomers' energy to focus on **building and contributing** to the art or infrastructure projects.
- **Self-interested Mentors**: Camps need new builders to survive leadership burnout and ensure their projects continue into the future.
- **Acculturation incubators**: high-trust, high-accountability micro-communities where people *become* burners.

The project doesn't build new infrastructure—it strengthens the connective tissue that already works.

## Problem Statement: Solving the "Builder Pipeline"
1. **Newcomers/Seekers:** Want to contribute but don't know *how* or *where* their skills fit. They need mentorship to transition from "attendee" to "builder."
2. **Camps/TCOs/Art Leads:** Need reliable, motivated hands to execute complex projects but are often too busy to find and vet people outside their immediate circles.
3. **The Ecosystem:** Facing a "cold start" problem for new art and infrastructure as the pool of experienced builders shrinks.


## Project Summary

**Theme Camp Connection & Community Finder** is a lightweight matchmaking service that reduces friction for self-motivated newcomers to find theme camps and **art projects** that match their values, skills, and **desire to learn**.

Goals:
- **Discover Mentorship**: Help newcomers find projects where they can learn builder skills.
- **Support the Builders**: Connect art projects and camps with the hands they need to thrive.
- **Low Overhead**: Facilitate introductions without creating administrative debt for busy TCOs/Leads.

The product introduces people. Camps and projects own the vetting, intake, and mentorship relationship.

**Framing matters**: This is not "recruitment." It is **reducing friction for the interested builder.**
- *"This isn't 'recruitment.' This is 'reducing friction for the interested.'"*
- *"We're helping self-motivated people find their people and their projects."*
- *"We're creating more support for the builders—helping people learn how to build the city."*


## 4. Product Principles (Non-Negotiables)

1. **Participation-first:** Match for contribution, not consumption.
2. **Low burden on camps:** Workflows must save time for TCOs, not add process debt.
3. **Principle-aligned language:** Avoid “corporate recruiting” framing.
4. **Human-centered handoff:** Tool facilitates intros; people build trust.
5. **Decommodified + privacy-aware:** Opt-in only; minimal data capture.
6. **Use existing channels first:** Pilot on native community tools before building software.

## 5. Target Users and Jobs-To-Be-Done

### User Type A: Seekers (Birgins / New Participants)

Jobs to be done:

- Understand how camp participation works.
- Discover camps aligned with values, contribution style, and practical constraints.
- Make first contact with clear expectations.

Pain points:

- No social “in” to camp networks.
- Unclear norms (dues, shifts, accountability, contribution expectations).
- Fear of rejection or mismatch.

### User Type A.2: Seekers (Aspiring Builders)

Jobs to be done:
- Understand how to transition from a "tourist" to a "contributor/builder."
- Discover projects looking for specific skills (or a willingness to learn).
- Find mentors who can teach desert-hardened building/logistics.

Pain points:
- Don't know where to start or who to ask.
- Unsure if their "default world" skills translate to the playa.
- Fear of being a burden on an already stressed art team.

### User Type B: Camps / TCOs / Art Leads (The Mentors)

Jobs to be done:

- Find reliable, motivated hands to support build/strike/ops.
- Identify potential successors or leads for specific sub-projects.
- Reduce time spent on ad hoc pipeline building.

Pain points:

- Existing networks tapped out.
- Concern about seeker mismatch (tourist mindset vs contributor mindset).
- Burnout from "doing everything" because they don't have enough builders.
- Lack of a low-effort way to signal they are "open to mentoring new builders."

### User Type C: Ecosystem Stakeholders (Sparks, Placement, BMP teams)

Jobs to be done:

- Strengthen intergenerational continuity.
- Capture learnings for scalable policy/product integration.
- Capture data on what skills are in demand vs. what skills are available.
- Maintain culture and trust while improving access.

## 6. Scope by Phase

## Phase 1 (Pilot): Community-Led Discovery Layer

In scope:

- Launch moderated pilot on existing platform(s): Discord and/or Reddit.
- Co-design and publish structured templates:
  - Seeker Profile template
  - Camp Profile template
- Run pilot moderation and matching introductions.
- Collect structured feedback (survey + interview).
- Produce findings report with v2 requirements and go/no-go recommendation.

Out of scope:

- Custom standalone software platform.
- Replacing camp vetting/intake process.
- Ticketing, transport, or camp fee management.

## Phase 2 (Conditional on Phase 1 go decision): BMP Integration

Potential scope:

- Add “seeking members” fields to camp questionnaire flows.
- Add “seeking camp” fields to burner profile flows.
- Define lightweight opt-in connection pathways (API or export/import).
- Refine taxonomy for skills/interests/contribution styles.
- Produce governance recommendations for ethical operation.

## 7. Success Metrics

### Pilot adoption targets

- 10 participating camps.
- 100 seekers introduced/matched.
- 75% of participants report improved clarity on joining/contributing.

### Qualitative validation

- 3-5 documented mentorship/handoff stories.

### Strategic outcome (longer horizon)

- Contribute to stabilizing/reversing under-30 decline (tracked via BRC Census over time).

### Phase-gate readiness signal

- Evidence-backed v2 framework validated by pilot participants and stakeholders.

## 8. Risks and Mitigations

### Risk: Community backlash (“corporate,” “dating app,” impersonal)

Mitigation:

- Participatory design with advisory group.
- Community-native language (“Community Finder,” not recruitment platform).
- Co-owned messaging across Reddit/Facebook/Discord channels.

### Risk: Low camp adoption (feels like extra work)

Mitigation:

- Template-first workflows with minimal fields.
- Time-saving defaults and clear matching criteria.
- TCO co-design to keep burden low.

### Risk: Expectation mismatch (service-seeking vs contribution-seeking)

Mitigation:

- Explicit template fields for contribution style, ethos, dues/shifts, expectations.
- Intro guidance that sets accountability expectations early.

### Risk: Communication fragmentation across channels

Mitigation (recommended for product planning):

- Pick one canonical pilot home and treat others as intake funnels.
- Create weekly cross-post summary + standardized handoff form.
- Assign explicit moderation/ops owner for channel sync.

### Risk: Wrong primary diagnosis (recruitment issue vs retention issue)

Mitigation:

- Pair pilot outcomes with census/retention data analysis.
- Keep hypotheses explicit and update roadmap based on evidence.

## 9. Messaging Guardrails

Approved framing:

- “Reducing friction for the interested.”
- “Helping self-motivated people find their people.”
- “Strengthening theme camps by improving continuity pipelines.”

Avoid:

- “Recruiting funnel” language.
- Implicit promise of placement, acceptance, or service.
- Product positioning that bypasses camp autonomy.

## 10. Functional Requirements for v1 Workflow

1. Camp posts profile using structured template.
2. Seeker posts profile using structured template.
3. Moderator performs lightweight compatibility triage.
4. Intro message sent to both parties with expectations checklist.
5. Outcome tracked with simple statuses:
   - intro_sent
   - conversation_started
   - declined
   - accepted_pending
   - onboarded
6. Feedback survey triggered after outcome window.

Required template fields (minimum):

- Contribution style (build/strike/kitchen/hosting/art/support/etc).
- Values/ethos alignment statement.
- Time availability.
- Financial expectation transparency (dues range, major commitments).
- Communication preference.
- Non-negotiables / boundaries.

## 11. Non-Functional Requirements

- Fast to operate manually (moderator workflow <5 minutes per intro).
- Transparent expectations before first conversation.
- Privacy-aware data handling (minimal retention, opt-in sharing only).
- Channel-agnostic design (works on Discord/Reddit first).
- Exportable records for pilot findings report.

## 12. Data and Instrumentation (Pilot Level)

Track at minimum:

- Number of active camp profiles.
- Number of active seeker profiles.
- Match attempts per week.
- Intro-to-conversation conversion rate.
- Conversation-to-onboarding conversion rate.
- Top mismatch reasons.
- Participant sentiment (clarity, trust, usefulness).

Suggested weekly dashboard cuts:

- By channel (Discord/Reddit/etc).
- By contribution type.
- By first-time vs returning participants.

## 13. Operating Model for Pilot

Recommended roles:

- Product/Program owner: scope, success criteria, and phase-gate decision.
- Community ops lead: moderation, escalations, communication hygiene.
- Data/insights lead: instrumentation and findings report.
- Camp advisory circle: template and process validation.

Cadence:

- Weekly ops review.
- Biweekly stakeholder sync.
- End-of-pilot findings readout with go/no-go recommendation.

## 14. Implementation Guidance for Engineers and AI Contributors in This Repo

This repo (`burning-man-matchbot`) is the software implementation of the matchmaking layer described above. Key context:

- **Stack**: Python ≥ 3.12, managed with `uv`. Dev tools: `pytest`, `ruff`, `mypy`, `ipython`.
- **Phase 1 goal**: The bot/tooling should support the Discord or Reddit pilot—structured intake, profile storage, lightweight matching logic.
- **Design constraint**: The tool makes the *introduction only*. It must not replace human judgment or camp vetting. Any matching logic should surface candidates, not rank or endorse them.
- **Data principles**: Opt-in only, no commodification of participant data, privacy-preserving.
- **Tone**: Warm, community-native. Never feel like a corporate HR tool.

When implementing feature work related to this initiative, optimize for:

- **Configurability over hardcoding:** taxonomy, statuses, and templates should be editable.
- **Incremental delivery:** ship pilot-supporting primitives first (profiles, intros, status tracking, reporting).
- **Auditability:** preserve enough event history to generate credible pilot findings.
- **Principle-safe defaults:** contribution-first language in UX copy and prompt text.
- **Low ops overhead:** favor simple workflows moderators can execute quickly.

Do not optimize for:

- Fully automated matching as a black box.
- Complex ML/recommender systems in v1.
- Building a net-new platform before validating process fit.

## 15. Open Questions to Resolve Before Final Feature Spec

1. Canonical pilot channel: Discord, Reddit, or hybrid?
2. Single shared taxonomy source: where will it live and who owns updates?
3. Minimum moderation staffing and escalation policy?
4. Data retention period and consent language?
5. Exact phase-gate thresholds for Phase 2 go decision?


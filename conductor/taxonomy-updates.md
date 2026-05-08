# Taxonomy and Prompts Update Plan

## Objective
Tighten the LLM extraction prompts to reduce over-tagging of Burning Man posts, specifically addressing the over-use of "communal" and "logistics" tags. Replace the `logistics` and `admin` tags with a single `camp_admin` tag.

## Key Files & Context
- `src/matchbot/config/taxonomy.yaml`: Contains the list of allowed vibes and contribution types.
- `src/matchbot/extraction/prompts.py`: Contains the `SYSTEM_PROMPT` and `SYSTEM_PROMPT_VERBOSE` used by the LLMs for extraction.
- `src/matchbot/public/router.py`: References the `logistics` tag in community filters.
- `src/matchbot/forms/router.py`: References `logistics` in form labels.
- `tests/test_public_community.py`: Contains test assertions using the `logistics` tag.

## Implementation Steps
1. **Update Taxonomy (`src/matchbot/config/taxonomy.yaml`)**
   - Remove `- admin` and `- logistics` from the `contribution_types` list.
   - Add `- camp_admin` to the `contribution_types` list.

2. **Update Prompts (`src/matchbot/extraction/prompts.py`)**
   - Add the following constraints to both `SYSTEM_PROMPT` and `SYSTEM_PROMPT_VERBOSE`:
     - **Limit extractions**: Select a MAXIMUM of 3 `vibes` that are the primary focus of the camp.
     - **Limit extractions**: Select a MAXIMUM of 3 `contribution_types` that the camp is EXPLICITLY asking for (do not tag tasks they are simply describing or offering as a service).
     - **Tag Guidelines**:
       - `communal`: Use ONLY if the post emphasizes strict shared living, mandatory communal meals, or a high time commitment. Do NOT use just because it's a camp.
       - `camp_admin`: Use for supply chain, spreadsheets, inventory, or organizing. Do NOT use for physical labor (use `build`) or driving (use `transport`).

3. **Update References in Code**
   - **`src/matchbot/public/router.py`**: Update filter configurations and descriptions referencing `logistics` to use `camp_admin`.
   - **`src/matchbot/forms/router.py`**: Update form placeholder text referencing `logistics` to use `camp_admin`.
   - **`tests/test_public_community.py`**: Update assertions checking for `logistics` to check for `camp_admin`.

## Verification & Testing
- Run all tests `uv run pytest` to ensure no breakages due to taxonomy changes.
- Review recent posts manually with the updated prompt locally to confirm improved classification.
from pathlib import Path

import yaml

_TAXONOMY_PATH = Path(__file__).parent.parent.parent / "config" / "taxonomy.yaml"


def _load_taxonomy() -> dict:
    with open(_TAXONOMY_PATH) as f:
        return yaml.safe_load(f)


_taxonomy = _load_taxonomy()

VIBES: frozenset[str] = frozenset(_taxonomy.get("vibes", []))
CONTRIBUTION_TYPES: frozenset[str] = frozenset(_taxonomy.get("contribution_types", []))


def normalize_vibes(raw: list[str]) -> list[str]:
    """Return only taxonomy-valid vibe values, lowercased."""
    return [v.lower() for v in raw if v.lower() in VIBES]


def normalize_contribution_types(raw: list[str]) -> list[str]:
    """Return only taxonomy-valid contribution type values, lowercased."""
    return [v.lower() for v in raw if v.lower() in CONTRIBUTION_TYPES]

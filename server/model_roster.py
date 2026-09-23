"""User-controlled model roster: whitelist (participates in decisions) vs
blacklist (excluded).

The live decision candidate set is the roster whitelist intersected with the
models actually present in the Codex catalog. General coding models are ranked
for local failure escalation; specialized models may be chosen by Jev but never
used for generic one-rung bumps. Overrides persist as a small JSON file of
explicit overrides; defaults are derived so the file stays minimal.
"""
import json
import os

from routing_policy import (DEFAULT_ALLOW, GENERAL_ORDER, GENERAL_RANK,
                           SPECIAL_ORDER)

ROSTER_NAME = "model-roster.json"


def _path(state_dir):
    return os.path.join(state_dir, ROSTER_NAME)


def default_state(slug):
    """The default whitelist (GPT-6 family) is allowed; everything else denied."""
    return "allow" if slug in DEFAULT_ALLOW else "deny"


def load_overrides(state_dir):
    try:
        with open(_path(state_dir), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if v in ("allow", "deny")}


def load(state_dir):
    """Effective state for the default whitelist plus any explicit overrides."""
    overrides = load_overrides(state_dir)
    out = {m: overrides.get(m, "allow") for m in DEFAULT_ALLOW}
    for slug, state in overrides.items():
        out.setdefault(slug, state)
    return out


def state_for(slug, state_dir=None, roster=None):
    r = roster if roster is not None else load(state_dir)
    return r.get(slug, default_state(slug))


def is_allowed(slug, state_dir=None, roster=None):
    return state_for(slug, state_dir, roster) == "allow"


def candidate_sets(catalog_slugs, state_dir=None, roster=None):
    """Return (general, special) ordered candidate lists.

    A model participates only when whitelisted AND present in the catalog.
    """
    r = roster if roster is not None else load(state_dir)
    cats = set(catalog_slugs or [])

    def ok(model):
        return model in cats and r.get(model, default_state(model)) == "allow"

    general = [m for m in GENERAL_ORDER if ok(m)]
    special = [m for m in SPECIAL_ORDER if ok(m)]
    return general, special


def candidate_models(catalog_slugs, state_dir=None, roster=None):
    """All ordered candidates (general first, then special)."""
    general, special = candidate_sets(
        catalog_slugs, state_dir=state_dir, roster=roster)
    return general + special


def allowed_tiers(state_dir=None, roster=None, catalog_slugs=None):
    """Backwards-compatible accessor.

    With catalog slugs it returns the full ordered candidate set; without them
    it falls back to the default whitelist ordering.
    """
    r = roster if roster is not None else load(state_dir)
    if catalog_slugs is not None:
        return candidate_models(catalog_slugs, roster=r)
    return [m for m in DEFAULT_ALLOW if r.get(m, "allow") == "allow"]


def set_state(state_dir, slug, state):
    """Persist one override and return the effective roster."""
    if state not in ("allow", "deny"):
        raise ValueError("state must be allow or deny")
    if not isinstance(slug, str) or not slug or len(slug) > 128:
        raise ValueError("invalid slug")
    overrides = load_overrides(state_dir)
    if state == default_state(slug):
        overrides.pop(slug, None)
    else:
        overrides[slug] = state
    os.makedirs(state_dir, exist_ok=True)
    tmp = _path(state_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(overrides, ensure_ascii=False, indent=2, sort_keys=True))
    os.replace(tmp, _path(state_dir))
    try:
        os.chmod(_path(state_dir), 0o600)
    except OSError:
        pass
    return load(state_dir)


def _nearest_general(model, candidates):
    """Lowest general candidate at or above the model's rank, else nearest below."""
    general_cands = [c for c in candidates if c in GENERAL_RANK]
    if not general_cands:
        return candidates[0]
    rank = GENERAL_RANK.get(model)
    if rank is None:
        # A specialized/unknown model maps to the lowest general candidate.
        return general_cands[0]
    above = [c for c in general_cands if GENERAL_RANK[c] >= rank]
    if above:
        return above[0]
    return general_cands[-1]


def enforce(model, effort, candidates):
    """Map a chosen pair into the ordered candidate set.

    Returns (model, effort), or None when no model is a candidate. A candidate
    model is kept as-is. A denied/absent general model maps to the lowest
    candidate at or above its capability (preserving capacity); a specialized
    or unknown model maps to the lowest general candidate.
    """
    candidates = list(candidates)
    if model in candidates:
        return model, effort
    if not candidates:
        return None
    return _nearest_general(model, candidates), effort

"""User-controlled model roster: whitelist (can work) vs blacklist (disabled).

The decision layer can only lease a tier that is intrinsically routable AND
whitelisted. Overrides are persisted as a small JSON file of explicit
overrides; defaults are derived so the file stays minimal.
"""
import json
import os

from routing_policy import TIERS

ROSTER_NAME = "model-roster.json"


def _path(state_dir):
    return os.path.join(state_dir, ROSTER_NAME)


def default_state(slug):
    """The four selectable tiers default to allowed; everything else denied."""
    return "allow" if slug in TIERS else "deny"


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
    """Effective state for the tiers plus any explicit non-tier overrides."""
    overrides = load_overrides(state_dir)
    out = {t: overrides.get(t, "allow") for t in TIERS}
    for slug, state in overrides.items():
        out.setdefault(slug, state)
    return out


def state_for(slug, state_dir=None, roster=None):
    r = roster if roster is not None else load(state_dir)
    return r.get(slug, default_state(slug))


def is_allowed(slug, state_dir=None, roster=None):
    return state_for(slug, state_dir, roster) == "allow"


def allowed_tiers(state_dir=None, roster=None):
    r = roster if roster is not None else load(state_dir)
    return [t for t in TIERS if r.get(t, "allow") == "allow"]


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


def enforce(model, effort, state_dir=None, roster=None):
    """Map a chosen pair into the allowed tier set.

    Returns (model, effort), or None when no tier is allowed. When the chosen
    tier is denied, prefer the next higher allowed tier (preserve capability),
    then the nearest lower one.
    """
    r = roster if roster is not None else load(state_dir)
    if r.get(model, "allow") == "allow":
        return model, effort
    allowed = allowed_tiers(roster=r)
    if not allowed:
        return None
    order = list(TIERS)
    try:
        i = order.index(model)
    except ValueError:
        i = -1
    if i >= 0:
        higher = [t for t in order[i + 1:] if t in allowed]
        lower = [t for t in reversed(order[:i]) if t in allowed]
        target = (higher[0] if higher else lower[0])
    else:
        target = allowed[0]
    return target, effort

"""Build the rich catalog payload for the built-in control panel.

Pure read-only aggregation: execution models (grouped by tier), the decision
layer (judge + decision chain), tier/effort reference and key status. Nothing
here reads or returns secret values - only configured/missing booleans.
"""
from __future__ import annotations

import json
import os

from routing_policy import (ASTRA, DEPTH_PROFILES, EFFORTS, LUNA, MODEL_PROFILES,
                           SOL, TIERS, TERRA)

import model_roster

TIER_ORDER = [(LUNA, "luna"), (TERRA, "terra"), (SOL, "sol"), (ASTRA, "astra")]

KEY_KINDS = [
    {"kind": "typesafe", "env": "TYPESAFE_API_KEY", "layer": "decision"},
    {"kind": "opencode", "env": "OPENCODE_API_KEY", "layer": "provider"},
    {"kind": "opencode_go", "env": "OPENCODE_GO_API_KEY", "layer": "provider"},
    {"kind": "openrouter", "env": "OPENROUTER_API_KEY", "layer": "provider"},
]


def _tier_of(slug: str):
    s = (slug or "").lower()
    for model, key in TIER_ORDER:
        if key in s:
            return model
    return None


def _model_entry(raw: dict):
    levels = raw.get("supported_reasoning_levels") or []
    efforts = []
    for lvl in levels:
        effort = lvl.get("effort")
        if not effort:
            continue
        efforts.append({"effort": effort, "description": lvl.get("description") or
                        DEPTH_PROFILES.get(effort, "")})
    if not efforts:
        efforts = [{"effort": e, "description": DEPTH_PROFILES[e]} for e in EFFORTS]
    return {
        "slug": raw.get("slug"),
        "name": raw.get("display_name") or raw.get("slug"),
        "description": raw.get("description") or "",
        "default_effort": raw.get("default_reasoning_level"),
        "efforts": efforts,
        "visibility": raw.get("visibility") or "list",
        "in_api": bool(raw.get("supported_in_api")),
        "routable": raw.get("slug") in TIERS,
    }


def _execution_groups(merged_path: str):
    try:
        data = json.load(open(merged_path, encoding="utf-8"))
        raws = data.get("models") or []
    except (OSError, ValueError):
        raws = []
    buckets = {model: [] for model, _ in TIER_ORDER}
    other = []
    for raw in raws:
        entry = _model_entry(raw)
        tier = _tier_of(entry["slug"])
        if tier:
            buckets[tier].append(entry)
        else:
            other.append(entry)
    groups = []
    for model, key in TIER_ORDER:
        groups.append({
            "tier": model, "key": key,
            "profile": MODEL_PROFILES[model],
            "models": buckets[model],
        })
    if other:
        groups.append({"tier": "special", "key": "special", "profile": "", "models": other})
    return groups


def _key_status(decision_key: bool):
    out = []
    for spec in KEY_KINDS:
        configured = decision_key if spec["kind"] == "typesafe" else bool(
            os.environ.get(spec["env"], "").strip())
        out.append({
            "kind": spec["kind"], "env": spec["env"],
            "layer": spec["layer"], "configured": configured,
        })
    return out


def _annotated_groups(state_dir: str, merged_path: str):
    """Execution groups with each model's roster state and effective selectability."""
    roster = model_roster.load(state_dir)
    groups = _execution_groups(merged_path)
    for group in groups:
        for entry in group["models"]:
            entry["roster"] = model_roster.state_for(entry["slug"], roster=roster)
            entry["selectable"] = bool(entry["routable"]) and entry["roster"] == "allow"
    return groups


def build(state_dir: str, decision_key: bool):
    merged_path = os.path.join(state_dir, "merged-models.json")
    return {
        "decision": {
            "judge": {
                "id": "typesafe-system-one",
                "name": "TypeSafe System One",
                "key_configured": bool(decision_key),
            },
            "chain": [
                {"id": "typesafe", "name": "TypeSafe System One",
                 "available": bool(decision_key), "current": True},
                {"id": "opencode-free", "name": "opencode free (north-mini-code)",
                 "available": False, "current": False},
                {"id": "openrouter-free", "name": "OpenRouter free models",
                 "available": False, "current": False},
                {"id": "local-fallback", "name": "Local rule fallback",
                 "available": True, "current": False},
            ],
            "decides": ["model_tier", "reasoning_effort", "lease"],
        },
        "tiers": [
            {"id": model, "key": key, "rank": idx + 1,
             "profile": MODEL_PROFILES[model]}
            for idx, (model, key) in enumerate(TIER_ORDER)
        ],
        "efforts": [{"id": e, "profile": DEPTH_PROFILES[e]} for e in EFFORTS],
        "execution": _annotated_groups(state_dir, merged_path),
        "keys": _key_status(decision_key),
    }

"""Build the rich catalog payload for the built-in control panel.

Read-only aggregation: the live execution models (general coding family plus
specialized models), the decision layer (judge + decision chain), tier/effort
reference and key status. The roster whitelist determines which models
participate in decisions; the candidate set is the whitelist intersected with
the live Codex catalog. Nothing here reads or returns secret values.
"""
from __future__ import annotations

import json
import os

from routing_policy import (DEPTH_PROFILES, EFFORTS, GENERAL_ORDER, MASTER_ORDER,
                           MODEL_PROFILES, SPECIAL_ORDER)

import model_roster

KEY_KINDS = [
    {"kind": "typesafe", "env": "TYPESAFE_API_KEY", "layer": "decision"},
    {"kind": "opencode", "env": "OPENCODE_API_KEY", "layer": "provider"},
    {"kind": "opencode_go", "env": "OPENCODE_GO_API_KEY", "layer": "provider"},
    {"kind": "openrouter", "env": "OPENROUTER_API_KEY", "layer": "provider"},
]


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
    slug = raw.get("slug")
    return {
        "slug": slug,
        "name": raw.get("display_name") or slug,
        "description": raw.get("description") or "",
        "default_effort": raw.get("default_reasoning_level"),
        "efforts": efforts,
        "visibility": raw.get("visibility") or "list",
        "in_api": bool(raw.get("supported_in_api")),
        # A known, API-capable model can participate once whitelisted.
        "routable": bool(raw.get("supported_in_api")) and slug in MASTER_ORDER,
    }


def _read_entries(merged_path: str):
    try:
        data = json.load(open(merged_path, encoding="utf-8"))
        raws = data.get("models") or []
    except (OSError, ValueError):
        raws = []
    entries = {}
    for raw in raws:
        if not isinstance(raw, dict):
            continue
        entry = _model_entry(raw)
        if entry["slug"]:
            entries[entry["slug"]] = entry
    return entries


def _execution_groups(state_dir: str, merged_path: str):
    """All catalog models, ordered and annotated with live roster state."""
    roster = model_roster.load(state_dir)
    entries = _read_entries(merged_path)
    present = list(entries)

    general_present = [s for s in GENERAL_ORDER if s in entries]
    special_present = [s for s in SPECIAL_ORDER if s in entries]
    # Unknown models (not in the master registry) join the special bucket.
    known = set(MASTER_ORDER)
    unknown_present = [s for s in present if s not in known]

    gen_candidates, sp_candidates = model_roster.candidate_sets(
        present, roster=roster)
    selectable = set(gen_candidates + sp_candidates)

    def annotate(slug: str):
        entry = entries[slug]
        entry["roster"] = model_roster.state_for(slug, roster=roster)
        entry["selectable"] = slug in selectable
        return entry

    groups = []
    if general_present:
        groups.append({
            "tier": "general", "key": "general", "profile": "",
            "models": [annotate(s) for s in general_present],
        })
    special_all = special_present + unknown_present
    if special_all:
        groups.append({
            "tier": "special", "key": "special", "profile": "",
            "models": [annotate(s) for s in special_all],
        })
    # The active general ladder (whitelist ∩ catalog), for the tier cards.
    return groups, gen_candidates


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


def build(state_dir: str, decision_key: bool):
    merged_path = os.path.join(state_dir, "merged-models.json")
    groups, active_ladder = _execution_groups(state_dir, merged_path)
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
            {"id": model, "key": model, "rank": idx + 1,
             "profile": MODEL_PROFILES.get(model, "")}
            for idx, model in enumerate(active_ladder)
        ],
        "efforts": [{"id": e, "profile": DEPTH_PROFILES[e]} for e in EFFORTS],
        "execution": groups,
        "keys": _key_status(decision_key),
    }

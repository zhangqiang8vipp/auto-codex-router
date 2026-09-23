"""Shared Jev decision contract: one model/effort choice plus bounded context.

v4 (dynamic roster): the set of models that participate in a Jev decision is
not hardcoded. The user roster whitelist, intersected with the live Codex
catalog, defines the decision candidates; blacklisted models never appear.
A master capability order ranks known models so local failure escalation stays
monotonic. Specialized models may be whitelisted and chosen by Jev when their
domain fits, but generic one-rung escalation only moves between general models.
"""
import copy
import math

POLICY_VERSION = "joint-v4-dynamic-roster"
EFFORTS = ["low", "medium", "high", "xhigh", "max"]

# General coding models, ordered low -> high capability. Within a tier the
# newer generation ranks slightly higher. Failure escalation only moves inside
# this ordered family.
GENERAL_ORDER = (
    "gpt-5.6-luna",
    "gpt-6-luna",
    "gpt-5.6-terra",
    "gpt-5.4",
    "gpt-5.6-sol",
    "gpt-5.6-sol-1m",
    "gpt-6-sol",
    "gpt-5.5",
    "gpt-6-astra",
)
# Specialized/domain models. Whitelisting lets Jev pick them when appropriate;
# they never participate in generic one-rung escalation.
SPECIAL_ORDER = (
    "gpt-daybreak-blue-latest",
    "codex-auto-review",
    "gpt-daybreak-red-latest",
    "gpt-reserve",
)
MASTER_ORDER = GENERAL_ORDER + SPECIAL_ORDER
GENERAL_RANK = {name: i for i, name in enumerate(GENERAL_ORDER)}
MASTER_RANK = {name: i for i, name in enumerate(MASTER_ORDER)}

# Default whitelist: the GPT-6 family. Everything else defaults to blacklisted.
DEFAULT_ALLOW = ("gpt-6-luna", "gpt-6-sol", "gpt-6-astra")

# Backwards-compatible tier aliases (other modules and tests still import them).
LUNA = "gpt-6-luna"
SOL = "gpt-6-sol"
ASTRA = "gpt-6-astra"
TERRA = "gpt-5.6-terra"
# Default ordered ladder (the whitelist defaults), low -> high capability.
TIERS = tuple(m for m in GENERAL_ORDER if m in DEFAULT_ALLOW)

# Capability descriptions are priors, not benchmark-derived success rates.
# No task labels, keywords, target model shares, or confidence cutoffs select a route.
MODEL_PROFILES = {
    "gpt-5.6-luna": "Older cost-optimized model for clear, high-volume and mechanical work.",
    "gpt-6-luna": "Cheapest GPT-6 model for simple, fast and high-volume work.",
    "gpt-5.6-terra": "Older balanced model for everyday production coding and judgment.",
    "gpt-5.4": "Solid previous-generation model for everyday coding.",
    "gpt-5.6-sol": "Older higher-capacity model for complex professional work.",
    "gpt-5.6-sol-1m": "Older high-capacity model with a long 1M context window.",
    "gpt-6-sol": "GPT-6 workhorse for complex coding and agent workflows.",
    "gpt-5.5": "Previous-generation high-end coding model.",
    "gpt-6-astra": "Most capable model, for the hardest end-to-end reasoning work.",
    "gpt-daybreak-blue-latest": "Specialized defensive cybersecurity model (Trusted Access).",
    "codex-auto-review": "Specialized model for automated Codex approval review.",
    "gpt-daybreak-red-latest": "Specialized offensive cybersecurity variant for authorized research.",
    "gpt-reserve": "Reserve high-end fallback model.",
}
DEPTH_PROFILES = {
    "low": "A small reasoning budget.",
    "medium": "A moderate reasoning budget.",
    "high": "A substantial reasoning budget.",
    "xhigh": "An extended reasoning budget.",
    "max": "The largest supported reasoning budget.",
}


def is_known(slug):
    return slug in MASTER_RANK


def is_general(slug):
    return slug in GENERAL_RANK


def route_pairs_for(models):
    """Build the model:effort pair map for an ordered candidate model list."""
    return {f"{model}:{depth}": (model, depth)
            for model in models for depth in EFFORTS}


# Static default pairs (used when callers do not supply a dynamic set).
ROUTE_PAIRS = route_pairs_for(DEFAULT_ALLOW)

_QUESTION_TEMPLATE = {
    "route": {
        "type": "choice",
        "instructions": {
            "question": "Which model AND reasoning effort should be leased for the current execution phase?",
            "objective": (
                "Select the cheapest model/effort pair that is sufficiently capable for the "
                "current user turn or execution phase, not merely the next trivial tool call. "
                "The selected pair may stay leased across tool continuations until a real "
                "boundary or repeated failure, so include the likely reasoning needed to carry "
                "this phase forward correctly. Consider corrections, retries, and the cost of "
                "a wrong answer. Judge capability and effort jointly: more effort on a smaller "
                "model is not automatically equivalent to a stronger model."
            ),
            "evidence": (
                "Use the current request, recent assistant intent, available tool evidence, "
                "and bounded session/repository observations to determine what remains to be "
                "decided. Previous route, project identity, diff size, and failure streak are "
                "evidence, not difficulty labels. A tool result does not by itself make the "
                "next decision easy or difficult. Text length, an error keyword, repository "
                "size, and the general subject are not difficulty measurements."
            ),
            "continuity": (
                "For a short continuation such as continue/继续, interpret it in light of the "
                "previous assistant intent and session route instead of treating the short text "
                "as a new trivial task. Normal tool call/result loops are continuity-constrained "
                "and usually reuse an existing route without asking this question again. When "
                "this question is asked to recover a missing lease, choose a pair suitable for "
                "the remaining execution phase rather than only the immediate tool result."
            ),
            "neutrality": (
                "There is no target model distribution. Do not prefer a cheap model merely "
                "because it is inexpensive, a middle option when uncertain, or the strongest "
                "model merely because it is most capable. Prefer lower resource use only among "
                "pairs you judge adequate."
            ),
            "model_profiles": {},
            "effort_profiles": DEPTH_PROFILES,
            "speed": "Every option uses standard speed. Fast mode is unavailable.",
        },
        "criteria": {},
    },
}


def build_route_question(models):
    """Build a route question whose options are exactly the given candidate models."""
    question = copy.deepcopy(_QUESTION_TEMPLATE)
    instr = question["route"]["instructions"]
    instr["model_profiles"] = {
        m: MODEL_PROFILES[m] for m in models if m in MODEL_PROFILES
    }
    question["route"]["criteria"] = {
        key: {"model": model, "reasoning_effort": depth}
        for key, (model, depth) in route_pairs_for(models).items()
    }
    return question


# Default questions over the default whitelist (backwards-compatible export).
QUESTIONS = build_route_question(DEFAULT_ALLOW)


def route(tier, depth, conf=None, step=None):
    """Apply a valid pair verbatim; guardrails live outside this pure contract."""
    if tier not in MASTER_RANK or depth not in EFFORTS:
        raise ValueError("invalid model/effort pair")
    return tier, depth, "default", "apply"


def decision_from_answers(answers, pairs=None):
    """Validate the typed Jev answer without treating confidence as correctness."""
    pairs = ROUTE_PAIRS if pairs is None else pairs
    answer = answers.get("route") if isinstance(answers, dict) else None
    if not isinstance(answer, dict):
        raise ValueError("missing joint route decision")
    choice = answer.get("choice")
    if not isinstance(choice, str) or choice not in pairs:
        raise ValueError("unknown joint route choice")
    probabilities = answer.get("probabilities")
    if probabilities is not None:
        if not isinstance(probabilities, dict) or set(probabilities) != set(pairs):
            raise ValueError("incomplete route distribution")
        values = list(probabilities.values())
        if any(isinstance(p, bool) or not isinstance(p, (int, float))
               or not math.isfinite(p) or not 0 <= p <= 1 for p in values):
            raise ValueError("invalid route probabilities")
        if abs(sum(values) - 1) > 0.02 or probabilities[choice] < max(values) - 1e-6:
            raise ValueError("inconsistent route distribution")
    conf = answer.get("confidence")
    if (isinstance(conf, bool) or not isinstance(conf, (int, float))
            or not math.isfinite(conf) or not 0 <= conf <= 1):
        conf = None
    model, effort = pairs[choice]
    return {
        "model": model, "effort": effort, "speed": "default", "gate": "apply",
        "confidence": conf, "probabilities": probabilities,
        "chosen_probability": probabilities.get(choice) if probabilities else None,
        "policy_version": POLICY_VERSION,
    }

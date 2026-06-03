"""Compaction Susceptibility — texture-based inherent risk assessment.

USDA NRCS Soil Quality Indicators: susceptibility to compaction is primarily
driven by texture (clay > silt > sand). Organic matter and coarse fragments
act as modifiers.

This is a STATIC soil property — it describes POTENTIAL, not current state.
It does NOT diagnose active compaction. Field verification is always required.
"""

from __future__ import annotations

# Base susceptibility scores per USDA texture class (0-100)
# Source: USDA NRCS Soil Quality Indicators + FAO guidelines on compaction risk
TEXTURE_SUSCEPTIBILITY: dict[str, int] = {
    "sand":             10,
    "loamy-sand":       15,
    "sandy-loam":       25,
    "loam":             40,
    "silt-loam":        45,
    "silt":             50,
    "sandy-clay-loam":  60,
    "clay-loam":        65,
    "silty-clay-loam":  70,
    "sandy-clay":       75,
    "silty-clay":       80,
    "clay":             85,
}

# Classification thresholds: (max_score, class_label)
SUSCEPTIBILITY_CLASSES: list[tuple[float, str]] = [
    (25, "very_low"),
    (40, "low"),
    (55, "moderate"),
    (70, "high"),
    (float("inf"), "very_high"),
]


def compaction_susceptibility_score(
    usda_texture: str,
    organic_matter_pct: float | None = None,
    coarse_fragments_pct: float | None = None,
    bulk_density: float | None = None,
    bulk_density_ref: float | None = None,
) -> dict:
    """Calculate inherent compaction susceptibility for a soil horizon.

    Primary driver: USDA texture class.
    Modifiers: organic matter (±), coarse fragments (−).
    Flag: elevated bulk density vs. textural reference (indicative only).

    Returns:
        dict with keys:
            score (int): 0-100 susceptibility score
            class (str): very_low | low | moderate | high | very_high
            textural_score (int): base score before modifiers
            modifiers_applied (list[str]): human-readable modifier labels
            indicative_elevated_bd (bool): whether bulk density exceeds reference
    """
    base = TEXTURE_SUSCEPTIBILITY.get(usda_texture, 50)
    score = float(base)
    modifiers: list[str] = []

    # ── Organic matter modifier ──
    if organic_matter_pct is not None:
        if organic_matter_pct > 3.0:
            reduction = min(15.0, (organic_matter_pct - 3.0) * 5.0)
            score -= reduction
            modifiers.append(f"organic_matter_high_{reduction:.0f}")
        elif organic_matter_pct < 1.0:
            increase = min(10.0, (1.0 - organic_matter_pct) * 10.0)
            score += increase
            modifiers.append(f"organic_matter_low_{increase:.0f}")

    # ── Coarse fragments modifier ──
    if coarse_fragments_pct is not None and coarse_fragments_pct > 15.0:
        reduction = min(15.0, (coarse_fragments_pct - 15.0) * 0.5)
        score -= reduction
        modifiers.append(f"coarse_fragments_{reduction:.0f}")

    score = max(0.0, min(100.0, score))
    score_int = round(score)

    # ── Classification ──
    susceptibility_class = "very_high"
    for threshold, label in SUSCEPTIBILITY_CLASSES:
        if score < threshold:
            susceptibility_class = label
            break

    # ── Elevated bulk density flag (indicative — NOT diagnostic) ──
    elevated_bd = False
    if bulk_density is not None and bulk_density_ref is not None:
        if bulk_density > bulk_density_ref * 1.05:
            elevated_bd = True
            modifiers.append("indicative_elevated_bd")

    return {
        "score": score_int,
        "class": susceptibility_class,
        "textural_score": base,
        "modifiers_applied": modifiers,
        "indicative_elevated_bd": elevated_bd,
    }

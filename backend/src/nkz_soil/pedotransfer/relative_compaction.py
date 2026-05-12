REFERENCE_BULK_DENSITY = {
    "sand": 1.80, "loamy_sand": 1.75, "sandy_loam": 1.70,
    "loam": 1.60, "silt_loam": 1.55, "silt": 1.50,
    "sandy_clay_loam": 1.65, "clay_loam": 1.55, "silty_clay_loam": 1.50,
    "sandy_clay": 1.60, "silty_clay": 1.50, "clay": 1.45,
}
COMPACTION_CLASSIFICATION = [(85, "normal"), (90, "slight"), (95, "moderate"), (float("inf"), "severe")]


def textural_class(sand: float, silt: float, clay: float) -> str:
    """USDA textural classification from sand/silt/clay percentages."""
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 1.5 * clay >= 15 and silt + 2 * clay < 30:
        return "loamy_sand"
    if clay >= 7 and clay <= 20 and sand > 52 and silt + 2 * clay >= 30:
        return "sandy_loam"
    if (clay >= 7 and clay <= 27 and silt >= 28 and silt <= 50 and sand <= 52) or \
       (clay < 7 and silt < 50 and sand > 43):
        return "loam"
    if silt >= 50 and clay >= 12 and clay <= 27:
        return "silt_loam"
    if silt >= 50 and clay < 12:
        return "silt"
    if clay >= 20 and clay <= 35 and silt < 28 and sand > 45:
        return "sandy_clay_loam"
    if clay >= 27 and clay <= 40 and sand > 20 and sand <= 45:
        return "clay_loam"
    if clay >= 27 and clay <= 40 and silt > 40 and sand <= 20:
        return "silty_clay_loam"
    if clay > 35 and sand > 45:
        return "sandy_clay"
    if clay > 35 and silt > 40:
        return "silty_clay"
    if clay > 35 and sand <= 45 and silt <= 40:
        return "clay"
    return "loam"


def relative_compaction(bulk_density: float, sand: float, silt: float, clay: float) -> dict:
    """Calculate relative compaction vs. reference bulk density for textural class."""
    texture = textural_class(sand, silt, clay)
    ref_bd = REFERENCE_BULK_DENSITY.get(texture, 1.60)
    rc_pct = round((bulk_density / ref_bd) * 100, 1)

    classification = "normal"
    for threshold, label in sorted(COMPACTION_CLASSIFICATION):
        if rc_pct <= threshold:
            classification = label
            break

    return {"value": rc_pct, "classification": classification, "textural_class": texture}

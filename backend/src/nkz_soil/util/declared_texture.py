"""User-declared topsoil texture: storage name and read-time precedence.

The declaration lives on the parcel's AgriSoilExtended entity as its own
attribute. Ingest rewrites only the attributes it builds, so a re-ingest never
touches it. Precedence per topsoil horizon: measured > entered > estimated.
"""
from __future__ import annotations

ATTR = "declaredUsdaTextureClass"
# Orion may hand a term outside the platform @context back in prefixed or
# full-IRI form; accept all three.
_ATTR_FORMS = (ATTR, f"nkz:{ATTR}", f"https://nkz-os.org/ns/{ATTR}")
TOPSOIL_MAX_DEPTH_CM = 30


def declared_class(entity: dict) -> str | None:
    for key in _ATTR_FORMS:
        raw = entity.get(key)
        value = raw.get("value") if isinstance(raw, dict) else raw
        if isinstance(value, str) and value:
            return value
    return None


def _horizon_source(h: dict, data_source: str | None) -> str | None:
    src = h.get("usdaTextureSource")
    if src:
        return src
    if h.get("usdaTextureClass") is None:
        return None
    # Horizons stored before the source was recorded: a lab-led parcel is
    # treated as measured so a declaration never hides an analysis.
    return "measured" if data_source == "lab_analysis" else "estimated"


def apply_declared_texture(
    horizons: list[dict], declared: str | None, data_source: str | None
) -> list[dict]:
    """Horizons with usdaTextureSource set; topsoil ones carry the declared class
    unless a measured value exists."""
    out = []
    for h in horizons:
        h = dict(h)
        src = _horizon_source(h, data_source)
        depth_to = h.get("depthTo")
        topsoil = isinstance(depth_to, (int, float)) and depth_to <= TOPSOIL_MAX_DEPTH_CM
        if declared and topsoil and src != "measured":
            h["usdaTextureClass"] = declared
            src = "entered"
        h["usdaTextureSource"] = src
        out.append(h)
    return out


def topsoil_texture(horizons: list[dict], declared: str | None) -> dict:
    """{usdaTextureClass, source} of the shallowest topsoil horizon (after the
    overlay); the declaration alone when the parcel has no topsoil horizon."""
    top = [
        h for h in horizons
        if isinstance(h.get("depthTo"), (int, float)) and h["depthTo"] <= TOPSOIL_MAX_DEPTH_CM
    ]
    top.sort(key=lambda h: h.get("depthFrom", 0))
    for h in top:
        if h.get("usdaTextureClass") is not None:
            return {"usdaTextureClass": h["usdaTextureClass"], "source": h.get("usdaTextureSource")}
    if declared:
        return {"usdaTextureClass": declared, "source": "entered"}
    return {"usdaTextureClass": None, "source": None}

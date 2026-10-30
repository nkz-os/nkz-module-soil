from datetime import UTC, datetime, timedelta

from nkz_soil.models.domain import (
    DepthInterval,
    GeographicScope,
    Horizon,
    ProviderHealth,
    SoilDataResult,
    SoilProperty,
)
from nkz_soil.models.fertility import olsen_equivalent
from nkz_soil.providers.base import geometry_intersects_bbox
from nkz_soil.storage.orion import OrionClient, current_tenant
from nkz_soil.util.ngsi import horizons_of

# (Horizon attr, horizon dict key) for numeric values averaged as-is.
_PLAIN_FIELDS = (
    ("sand", "sand"),
    ("silt", "silt"),
    ("clay", "clay"),
    ("organic_carbon", "organicCarbon"),
    ("bulk_density", "bulkDensity"),
    ("ph", "ph"),
    ("cec", "cec"),
    ("coarse_fragments", "coarseFragments"),
    ("penetration_resistance", "penetrationResistance"),
    ("organic_matter", "organicMatter"),
    ("total_nitrogen", "totalNitrogen"),
    ("nitrate_n", "nitrateN"),
    ("ammonium_n", "ammoniumN"),
    ("carbonates", "carbonates"),
    ("active_lime", "activeLime"),
)


def _num(raw: object) -> float | None:
    if isinstance(raw, dict):
        raw = raw.get("value")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def _method_of(horizon: dict, key: str) -> str | None:
    raw = horizon.get(key)
    if isinstance(raw, dict):
        raw = raw.get("value")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip().lower()


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _average_group(depth_from: int, depth_to: int, horizons: list[dict]) -> Horizon:
    """One averaged Horizon for a depth interval.

    P is normalized to its Olsen equivalent before averaging (Villalobos et al.
    2020, Table 5): averaging raw values of different extractions mixes scales.
    K has no published conversion, so only the points of the most frequent
    method are averaged. Everything else is a plain mean of the non-null values.
    """
    averaged = Horizon(depth_from=depth_from, depth_to=depth_to)
    for attr, key in _PLAIN_FIELDS:
        vals = [v for h in horizons if (v := _num(h.get(key))) is not None]
        setattr(averaged, attr, _mean(vals))

    p_olsen: list[float] = []
    for h in horizons:
        value = _num(h.get("phosphorusAvailable"))
        method = _method_of(h, "phosphorusMethod")
        if value is None or method is None:
            continue
        try:
            p_olsen.append(olsen_equivalent(value, method))
        except ValueError:
            continue  # no published conversion: never averaged with the rest
    if p_olsen:
        averaged.phosphorus_available = _mean(p_olsen)
        averaged.phosphorus_method = "olsen"

    k_by_method: dict[str | None, list[float]] = {}
    for h in horizons:
        value = _num(h.get("potassiumExchangeable"))
        if value is None:
            continue
        k_by_method.setdefault(_method_of(h, "potassiumMethod"), []).append(value)
    if k_by_method:
        # Most frequent method wins; methoded points outrank unmethoded on a tie.
        method, vals = max(
            k_by_method.items(), key=lambda kv: (len(kv[1]), kv[0] is not None)
        )
        averaged.potassium_exchangeable = _mean(vals)
        averaged.potassium_method = method
    return averaged


class LabAnalysisProvider:
    name = "lab_analysis"
    priority = 100
    geographic_scope = GeographicScope(bbox=(-180, -90, 180, 90), countries=["*"])
    update_cadence = timedelta(days=1)

    def covers(self, geometry: dict) -> bool:
        return geometry_intersects_bbox(geometry, self.geographic_scope.bbox)

    async def fetch(
        self,
        geometry: dict,
        properties: list[SoilProperty],
        depths: list[DepthInterval],
    ) -> SoilDataResult:
        async with OrionClient(current_tenant()) as orion:
            points = await orion.query_entities(
                type="SoilSamplingPoint",
                geometry=geometry,
            )

        if not points:
            return SoilDataResult(
                provider=self.name, horizons=[], uncertainty=0.02, geometry=geometry
            )

        groups: dict[tuple[int, int], list[dict]] = {}
        for point in points:
            for h in horizons_of(point):
                try:
                    key = (int(h.get("depthFrom", 0)), int(h.get("depthTo", 100)))
                except (TypeError, ValueError):
                    continue
                groups.setdefault(key, []).append(h)

        all_horizons = [
            _average_group(df, dt, horizons)
            for (df, dt), horizons in sorted(groups.items())
        ]

        return SoilDataResult(
            provider=self.name,
            horizons=all_horizons,
            uncertainty=0.02,
            geometry=geometry,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            status="ok",
            latency_ms=0,
            last_success=datetime.now(tz=UTC),
            error_count=0,
            cache_hit_rate=0.0,
        )

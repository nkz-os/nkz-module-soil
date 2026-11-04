"""AgriSoilSample conversion: the soil API keeps answering in cm, %, ph and snake_case methods,
while the broker stores the SDM model (m, fractions, kg/m3, Pa, soilPh, camelCase methods)."""
from nkz_soil.models.agri_soil_sample import sample_id, to_analysis, to_entity

PARCEL = "urn:ngsi-ld:AgriParcel:demo-parcel-001"


def _row(**over):
    row = {"lat": 42.612345, "lon": -1.845678, "depth_from": 0, "depth_to": 30,
           "parcel_id": PARCEL, "sampling_date": "2026-09-01", "laboratory_reference": "LAB-1"}
    row.update(over)
    return row


def _v(entity, attr):
    return entity[attr]["value"]


def test_roundtrip_percent_fraction():
    e = to_entity("tenant-a", _row(sand=45, silt=30, clay=25, organic_matter=1.9, carbonates=12.5))
    assert (_v(e, "sand"), _v(e, "silt"), _v(e, "clay")) == (0.45, 0.3, 0.25)
    assert _v(e, "organicMatter") == 0.019 and _v(e, "carbonates") == 0.125
    (a,) = to_analysis([e])
    h = a["horizons"][0]
    assert (h["sand"], h["silt"], h["clay"], h["organicMatter"], h["carbonates"]) == (45, 30, 25, 1.9, 12.5)


def test_depth_cm_to_m_and_back():
    e = to_entity("tenant-a", _row(depth_from=30, depth_to=60, sand=40, silt=40, clay=20))
    assert (_v(e, "depthFrom"), _v(e, "depthTo")) == (0.3, 0.6)
    h = to_analysis([e])[0]["horizons"][0]
    assert (h["depthFrom"], h["depthTo"]) == (30, 60)
    assert isinstance(h["depthFrom"], int)


def test_si_units_bulk_density_and_penetration():
    e = to_entity("tenant-a", _row(bulk_density=1.35, penetration_resistance=2.5))
    assert _v(e, "bulkDensity") == 1350 and _v(e, "penetrationResistance") == 2_500_000
    h = to_analysis([e])[0]["horizons"][0]
    assert h["bulkDensity"] == 1.35 and h["penetrationResistance"] == 2.5


def test_methods_snake_to_camel_and_back():
    e = to_entity("tenant-a", _row(phosphorus_available=14.0, phosphorus_method="ammonium_acetate_edta",
                                   potassium_exchangeable=220.0, potassium_method="calcium_ammonium_lactate"))
    assert _v(e, "phosphorusMethod") == "ammoniumAcetateEdta"
    assert _v(e, "potassiumMethod") == "calciumAmmoniumLactate"
    h = to_analysis([e])[0]["horizons"][0]
    assert h["phosphorusMethod"] == "ammonium_acetate_edta"
    assert h["potassiumMethod"] == "calcium_ammonium_lactate"


def test_ph_to_soil_ph():
    e = to_entity("tenant-a", _row(ph=7.8))
    assert _v(e, "soilPh") == 7.8 and "ph" not in e
    assert to_analysis([e])[0]["horizons"][0]["ph"] == 7.8


def test_observed_at_is_sampling_date_noon():
    e = to_entity("tenant-a", _row(sand=40, silt=40, clay=20, nitrate_n=12.0))
    assert e["dateSampled"]["value"] == {"@type": "DateTime", "@value": "2026-09-01T12:00:00Z"}
    for attr in ("sand", "silt", "clay", "nitrateN"):
        assert e[attr]["observedAt"] == "2026-09-01T12:00:00Z"
    assert to_analysis([e])[0]["samplingDate"] == "2026-09-01"


def test_relationships_and_codes():
    zone = "urn:ngsi-ld:AgriManagementZone:tenant-a:p1:manual-1a2b3c4d-1"
    e = to_entity("tenant-a", _row(zone_id=zone, number_of_subsamples=15, operator="J. Doe"))
    assert e["type"] == "AgriSoilSample"
    assert e["hasAgriParcel"] == {"type": "Relationship", "object": PARCEL}
    assert e["hasAgriManagementZone"] == {"type": "Relationship", "object": zone}
    assert _v(e, "sampleCode") == "LAB-1" and _v(e, "numberOfSubsamples") == 15
    assert e["location"]["value"] == {"type": "Point", "coordinates": [-1.845678, 42.612345]}
    a = to_analysis([e])[0]
    assert a["laboratoryReference"] == "LAB-1" and a["operator"] == "J. Doe"
    assert a["location"] == {"lat": 42.612345, "lon": -1.845678}


def test_absent_values_are_omitted():
    e = to_entity("tenant-a", _row(parcel_id=None, laboratory_reference=None, sand=None))
    assert "hasAgriParcel" not in e and "sampleCode" not in e and "sand" not in e


def test_sample_id_is_deterministic():
    a = sample_id("tenant-a", _row())
    assert a == sample_id("tenant-a", _row())
    assert a.startswith("urn:ngsi-ld:AgriSoilSample:tenant-a:") and len(a.rsplit(":", 1)[1]) == 16
    assert a != sample_id("tenant-a", _row(depth_from=30, depth_to=60))
    assert a != sample_id("tenant-a", _row(sampling_date="2026-09-02"))
    assert to_entity("tenant-a", _row())["id"] == a


def test_depths_of_one_core_regroup_into_one_analysis():
    top = to_entity("tenant-a", _row(depth_from=0, depth_to=30, sand=40, silt=35, clay=25))
    sub = to_entity("tenant-a", _row(depth_from=30, depth_to=60, sand=30, silt=40, clay=30))
    other = to_entity("tenant-a", _row(sampling_date="2025-09-01", sand=50, silt=30, clay=20))
    analyses = to_analysis([sub, other, top])
    assert len(analyses) == 2
    core = next(a for a in analyses if a["samplingDate"] == "2026-09-01")
    assert [h["depthFrom"] for h in core["horizons"]] == [0, 30]
    assert core["id"] == top["id"]  # stable: the shallowest depth names the analysis


# Analysis shape FaST reads (copied from nkz-module-fast-navigator
# backend/tests/inputs/test_soil.py, `H` and `analysis()`): it must not change.
FAST_HORIZON = {"depthFrom": 0, "depthTo": 30, "sand": 40.0, "clay": 25.0, "ph": 7.8,
                "organicMatter": 1.9, "phosphorusAvailable": 14.0, "phosphorusMethod": "olsen",
                "potassiumExchangeable": 220.0, "potassiumMethod": "ammonium_acetate"}


def test_fast_contract_shape():
    e = to_entity("tenant-a", _row(sand=40.0, clay=25.0, ph=7.8, organic_matter=1.9,
                                   phosphorus_available=14.0, phosphorus_method="olsen",
                                   potassium_exchangeable=220.0, potassium_method="ammonium_acetate"))
    (a,) = to_analysis([e])
    assert a["horizons"] == [FAST_HORIZON]
    assert {"id", "samplingDate", "laboratoryReference", "dataSource", "horizons"} <= set(a)
    assert a["dataSource"] == "lab_analysis" and a["samplingDate"] == "2026-09-01"


def test_reads_attributes_as_orion_returns_them():
    """Orion returns DateTime values unwrapped or wrapped; both must read."""
    e = to_entity("tenant-a", _row(sand=40, silt=35, clay=25))
    e["dateSampled"] = {"type": "Property", "value": "2026-09-01T12:00:00Z"}
    assert to_analysis([e])[0]["samplingDate"] == "2026-09-01"


def test_every_p_and_k_method_round_trips():
    from nkz_soil.models.fertility import K_METHODS, P_METHODS
    for p in P_METHODS:
        h = to_analysis([to_entity("tenant-a", _row(phosphorus_available=10.0, phosphorus_method=p))])[0]["horizons"][0]
        assert h["phosphorusMethod"] == p
    for k in K_METHODS:
        h = to_analysis([to_entity("tenant-a", _row(potassium_exchangeable=100.0, potassium_method=k))])[0]["horizons"][0]
        assert h["potassiumMethod"] == k


def test_camel_methods_match_the_sdm_enums():
    from nkz_soil.models.agri_soil_sample import _camel
    from nkz_soil.models.fertility import K_METHODS, P_METHODS
    # enums of the SDM proposal (smart-data-models/incubated#283, AgriSoilSample schema)
    sdm_p = {"olsen", "bray1", "mehlich3", "ammoniumLactate", "ammoniumAcetateEdta", "calciumLactate",
             "calciumLactateAcetate", "water", "cacl2"}
    sdm_k = {"ammoniumAcetate", "mehlich3", "ammoniumLactate", "calciumAmmoniumLactate"}
    assert {_camel(m) for m in P_METHODS} == sdm_p
    assert {_camel(m) for m in K_METHODS} == sdm_k

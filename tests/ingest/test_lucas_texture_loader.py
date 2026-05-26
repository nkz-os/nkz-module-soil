from nkz_soil.ingest.lucas_texture_loader import _variable_for, _bbox_wkt


def test_variable_for_eu23_filenames():
    assert _variable_for("Clay_eu23.tif") == "CLAY"
    assert _variable_for("Sand_eu23.tif") == "SAND"
    assert _variable_for("Silt_eu23.tif") == "SILT"
    assert _variable_for("Bulk_density_eu23.tif") == "BULK_DENSITY"
    assert _variable_for("AWC_eu23.tif") == "AWC"
    assert _variable_for("Coarse_frag_eu23.tif") == "COARSE_FRAGMENTS"
    assert _variable_for("textureUSDA_eu23.tif") == "USDA_TEXTURE"
    assert _variable_for("Clay.tif") is None          # 'Extra' wide variant ignored


def test_bbox_wkt_is_closed_polygon():
    wkt = _bbox_wkt(-10, 34, 40, 70)
    assert wkt.startswith("POLYGON((") and wkt.endswith("))")
    assert wkt.count(",") == 4

"""Tests for compaction_susceptibility_score pedotransfer."""

from nkz_soil.pedotransfer.compaction_susceptibility import (
    compaction_susceptibility_score,
    TEXTURE_SUSCEPTIBILITY,
)


# ── Texture baseline tests (all 12 USDA classes) ──

def test_sand_is_very_low():
    result = compaction_susceptibility_score("sand")
    assert result["class"] == "very_low"
    assert result["score"] == 10
    assert result["textural_score"] == 10


def test_loamy_sand_is_very_low():
    result = compaction_susceptibility_score("loamy-sand")
    assert result["class"] == "very_low"
    assert result["score"] == 15


def test_sandy_loam_is_low():
    result = compaction_susceptibility_score("sandy-loam")
    assert result["class"] == "low"
    assert result["score"] == 25


def test_loam_is_moderate():
    result = compaction_susceptibility_score("loam")
    assert result["class"] == "moderate"
    assert result["score"] == 40


def test_silt_loam_is_moderate():
    result = compaction_susceptibility_score("silt-loam")
    assert result["class"] == "moderate"
    assert result["score"] == 45


def test_silt_is_moderate():
    result = compaction_susceptibility_score("silt")
    assert result["class"] == "moderate"
    assert result["score"] == 50


def test_sandy_clay_loam_is_high():
    result = compaction_susceptibility_score("sandy-clay-loam")
    assert result["class"] == "high"
    assert result["score"] == 60


def test_clay_loam_is_high():
    result = compaction_susceptibility_score("clay-loam")
    assert result["class"] == "high"
    assert result["score"] == 65


def test_silty_clay_loam_is_high():
    result = compaction_susceptibility_score("silty-clay-loam")
    assert result["class"] == "very_high"
    assert result["score"] == 70


def test_sandy_clay_is_very_high():
    result = compaction_susceptibility_score("sandy-clay")
    assert result["class"] == "very_high"
    assert result["score"] == 75


def test_silty_clay_is_very_high():
    result = compaction_susceptibility_score("silty-clay")
    assert result["class"] == "very_high"
    assert result["score"] == 80


def test_clay_is_very_high():
    result = compaction_susceptibility_score("clay")
    assert result["class"] == "very_high"
    assert result["score"] == 85


# ── Unknown texture falls back to moderate ──

def test_unknown_texture_defaults_to_50():
    result = compaction_susceptibility_score("gravel")
    assert result["score"] == 50
    assert result["textural_score"] == 50


# ── Organic matter modifier ──

def test_high_organic_matter_reduces_score():
    result = compaction_susceptibility_score("clay", organic_matter_pct=5.0)
    # base 85, reduction ~ (5-3)*5 = 10 → 75
    assert result["score"] < 85
    assert result["score"] >= 75
    assert any("organic_matter_high" in m for m in result["modifiers_applied"])


def test_low_organic_matter_increases_score():
    result = compaction_susceptibility_score("loam", organic_matter_pct=0.5)
    # base 40, increase ~ (1-0.5)*10 = 5 → 45
    assert result["score"] > 40
    assert result["score"] <= 50
    assert any("organic_matter_low" in m for m in result["modifiers_applied"])


def test_organic_matter_at_2_pct_no_effect():
    """OM of 2% is within the neutral range (1-3%)."""
    result = compaction_susceptibility_score("sandy-loam", organic_matter_pct=2.0)
    assert result["score"] == 25  # unchanged
    assert len(result["modifiers_applied"]) == 0


# ── Coarse fragments modifier ──

def test_coarse_fragments_reduce_score():
    result = compaction_susceptibility_score("clay-loam", coarse_fragments_pct=35.0)
    # base 65, reduction ~ (35-15)*0.5 = 10 → 55
    assert result["score"] < 65
    assert any("coarse_fragments" in m for m in result["modifiers_applied"])


def test_coarse_fragments_below_15_no_effect():
    result = compaction_susceptibility_score("clay-loam", coarse_fragments_pct=10.0)
    assert result["score"] == 65
    assert not any("coarse_fragments" in m for m in result["modifiers_applied"])


# ── Bulk density elevation flag ──

def test_elevated_bulk_density_flag():
    """BD 5% above reference triggers the indicative flag."""
    result = compaction_susceptibility_score(
        "clay", bulk_density=1.55, bulk_density_ref=1.45
    )
    # 1.55 > 1.45 * 1.05 = 1.5225 → elevated
    assert result["indicative_elevated_bd"] is True
    assert "indicative_elevated_bd" in result["modifiers_applied"]


def test_normal_bulk_density_no_flag():
    result = compaction_susceptibility_score(
        "clay", bulk_density=1.40, bulk_density_ref=1.45
    )
    assert result["indicative_elevated_bd"] is False


def test_bulk_density_without_ref_ignored():
    """If bulk_density is provided but no ref, don't crash."""
    result = compaction_susceptibility_score("clay", bulk_density=1.60)
    assert result["indicative_elevated_bd"] is False


# ── Score boundaries ──

def test_score_never_exceeds_100():
    """Even with worst modifiers, score must cap at 100."""
    result = compaction_susceptibility_score(
        "clay", organic_matter_pct=0.0, bulk_density=2.0, bulk_density_ref=1.45
    )
    assert result["score"] <= 100


def test_score_never_below_0():
    """Even with best modifiers, score must floor at 0."""
    result = compaction_susceptibility_score(
        "sand", organic_matter_pct=10.0, coarse_fragments_pct=80.0
    )
    assert result["score"] >= 0


# ── Classification thresholds ──

def test_threshold_boundary_low_to_moderate():
    """Score of 40 is 'low', score of 41 is 'moderate'."""
    # sand is 10 → very_low; sandy-loam is 25 → low
    # loam is 40 → moderate (threshold is 25 < x <= 40 for 'low')
    result = compaction_susceptibility_score("loam")
    assert result["class"] == "moderate"
    assert result["score"] == 40


# ── All returned keys present ──

def test_return_dict_has_all_keys():
    result = compaction_susceptibility_score("loam")
    for key in ("score", "class", "textural_score", "modifiers_applied", "indicative_elevated_bd"):
        assert key in result, f"Missing key: {key}"


# ── All 12 textures covered ──

def test_all_12_usda_classes_have_entries():
    expected = {
        "sand", "loamy-sand", "sandy-loam", "loam", "silt-loam", "silt",
        "sandy-clay-loam", "clay-loam", "silty-clay-loam",
        "sandy-clay", "silty-clay", "clay",
    }
    assert set(TEXTURE_SUSCEPTIBILITY.keys()) == expected

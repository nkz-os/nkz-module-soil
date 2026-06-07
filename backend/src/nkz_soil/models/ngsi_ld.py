"""NGSI-LD entity models for soil module.

All Properties use TaggedProperty which carries provenance sub-properties
(providedBy, license, observedAt, confidenceInterval, derivedBy).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel


CONTEXT_URLS = [
    "https://nkz-os.org/jsonld-contexts/v1/nkz-context.jsonld",
    "https://smartdatamodels.org/context.jsonld",
]


class GeoProperty(BaseModel):
    type: str = "GeoProperty"
    value: dict[str, Any]


class Relationship(BaseModel):
    type: str = "Relationship"
    object: str


class Property(BaseModel):
    """Legacy pydantic Property — kept for backwards-compat imports. Prefer TaggedProperty."""
    type: str = "Property"
    value: Any


@dataclass
class TaggedProperty:
    """NGSI-LD Property + provenance sub-properties."""
    value: Any
    unit_code: str | None = None
    provided_by: str | None = None
    license_id: str | None = None
    observed_at: str | None = None
    confidence_interval: tuple[float, float] | None = None
    derived_by: dict | None = None

    def to_ngsi(self) -> dict:
        out: dict = {"type": "Property", "value": self.value}
        if self.unit_code:
            out["unitCode"] = self.unit_code
        if self.provided_by:
            out["providedBy"] = {"type": "Property", "value": self.provided_by}
        if self.license_id:
            out["license"] = {"type": "Property", "value": self.license_id}
        if self.observed_at:
            out["observedAt"] = self.observed_at
        if self.confidence_interval is not None:
            out["confidenceInterval"] = {"type": "Property", "value": list(self.confidence_interval)}
        if self.derived_by:
            out["derivedBy"] = {"type": "Property", "value": self.derived_by}
        return out


@dataclass
class AgriSoilExtended:
    id: str
    location: GeoProperty
    hasAgriParcel: Relationship
    horizons: TaggedProperty
    hydrologicGroup: TaggedProperty | None = None
    parcelVersionId: TaggedProperty | None = None
    relativeCompaction: TaggedProperty | None = None
    type: str = "AgriSoilExtended"

    @property
    def context(self) -> list[str]:
        return CONTEXT_URLS

    def to_ngsi(self) -> dict:
        out: dict = {
            "id": self.id,
            "type": self.type,
            "location": self.location.model_dump(),
            "hasAgriParcel": self.hasAgriParcel.model_dump(),
            "horizons": self.horizons.to_ngsi(),
            "@context": self.context,
        }
        for attr in ("hydrologicGroup", "parcelVersionId", "relativeCompaction"):
            v: TaggedProperty | None = getattr(self, attr)
            if v is not None:
                out[attr] = v.to_ngsi()
        return out


# Legacy alias kept for one release of consumer compatibility.
AgriSoil = AgriSoilExtended


@dataclass
class SoilSamplingPoint:
    id: str
    location: GeoProperty
    samplingDate: TaggedProperty
    horizons: TaggedProperty
    laboratoryReference: TaggedProperty | None = None
    operator: TaggedProperty | None = None
    refSoilSurvey: Relationship | None = None
    type: str = "SoilSamplingPoint"


@dataclass
class SoilSurvey:
    id: str
    surveyType: TaggedProperty
    startDate: TaggedProperty
    tenant: TaggedProperty
    endDate: TaggedProperty | None = None
    hasAgriParcel: Relationship | None = None
    instrumentation: TaggedProperty | None = None
    pointCount: TaggedProperty | None = None
    type: str = "SoilSurvey"


@dataclass
class SoilDerivedRaster:
    id: str
    hasAgriParcel: Relationship
    soilProperty: TaggedProperty
    storageUri: TaggedProperty
    format: TaggedProperty
    crs: TaggedProperty
    resolution: TaggedProperty
    generatedAt: TaggedProperty
    depthFrom: TaggedProperty | None = None
    depthTo: TaggedProperty | None = None
    uncertainty: TaggedProperty | None = None
    type: str = "SoilDerivedRaster"

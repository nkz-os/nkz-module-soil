from pydantic import BaseModel
from typing import Any


class GeoProperty(BaseModel):
    type: str = "GeoProperty"
    value: dict[str, Any]


class Relationship(BaseModel):
    type: str = "Relationship"
    object: str


class Property(BaseModel):
    type: str = "Property"
    value: Any


class AgriSoil(BaseModel):
    id: str
    type: str = "AgriSoil"
    location: GeoProperty
    refAgriParcel: Relationship
    parcelVersionId: Property
    horizons: Property
    relativeCompaction: Property | None = None
    dataSource: Property
    uncertainty: Property
    lastUpdated: Property

    @property
    def context(self) -> list:
        return ["https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"]


class SoilSamplingPoint(BaseModel):
    id: str
    type: str = "SoilSamplingPoint"
    location: GeoProperty
    samplingDate: Property
    laboratoryReference: Property | None = None
    horizons: Property
    operator: Property | None = None
    refSoilSurvey: Relationship | None = None

    @property
    def context(self) -> list:
        return ["https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"]


class SoilSurvey(BaseModel):
    id: str
    type: str = "SoilSurvey"
    surveyType: Property
    refAgriParcel: Relationship | None = None
    startDate: Property
    endDate: Property | None = None
    instrumentation: Property | None = None
    pointCount: Property | None = None
    tenant: Property

    @property
    def context(self) -> list:
        return ["https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"]


class SoilDerivedRaster(BaseModel):
    id: str
    type: str = "SoilDerivedRaster"
    refAgriParcel: Relationship
    soilProperty: Property
    depthFrom: Property
    depthTo: Property
    storageUri: Property
    format: Property
    crs: Property
    resolution: Property
    generatedAt: Property
    uncertainty: Property
    parcelVersionId: Property

    @property
    def context(self) -> list:
        return ["https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"]

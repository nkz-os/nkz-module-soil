from enum import Enum
from dataclasses import dataclass
from datetime import datetime


class SoilProperty(str, Enum):
    SAND = "sand"
    SILT = "silt"
    CLAY = "clay"
    ORGANIC_CARBON = "organicCarbon"
    BULK_DENSITY = "bulkDensity"
    PH = "ph"
    CEC = "cec"
    COARSE_FRAGMENTS = "coarseFragments"
    KSAT_SATURATED = "ksatSaturated"
    AVAILABLE_WATER_CAPACITY = "availableWaterCapacity"
    HYDROLOGIC_GROUP = "hydrologicGroup"
    PENETRATION_RESISTANCE = "penetrationResistance"


class DataSource(str, Enum):
    LAB_ANALYSIS = "lab_analysis"
    EM_SURVEY = "em_survey"
    NIR = "nir"
    IOT_SENSOR = "iot_sensor"
    IDENA = "idena"
    IGME = "igme"
    BGS = "bgs"
    EU_SOIL_HYDRO = "eu_soil_hydro"
    LUCAS = "lucas"
    SOILGRIDS = "soilgrids"
    INTERPOLATED = "interpolated"


@dataclass
class Horizon:
    depth_from: int
    depth_to: int
    sand: float | None = None
    silt: float | None = None
    clay: float | None = None
    organic_carbon: float | None = None
    bulk_density: float | None = None
    ph: float | None = None
    cec: float | None = None
    coarse_fragments: float | None = None
    ksat_saturated: float | None = None
    available_water_capacity: float | None = None
    hydrologic_group: str | None = None
    penetration_resistance: float | None = None


@dataclass
class RelativeCompactionHorizon:
    depth_from: int
    depth_to: int
    value: float
    classification: str


@dataclass
class DepthInterval:
    depth_from: int
    depth_to: int


@dataclass
class SoilDataResult:
    provider: str
    horizons: list[Horizon]
    uncertainty: float
    geometry: dict


@dataclass
class ProviderHealth:
    name: str
    status: str
    latency_ms: float
    last_success: datetime | None
    error_count: int
    cache_hit_rate: float


@dataclass
class GeographicScope:
    bbox: tuple[float, float, float, float]
    countries: list[str]

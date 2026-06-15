import os
from contextlib import asynccontextmanager

from arq.connections import ArqRedis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nkz_soil.api.limiter import limiter
from nkz_soil.api.routes.capabilities import router as capabilities_router
from nkz_soil.api.routes.layers import router as layers_router
from nkz_soil.api.routes.metrics import router as metrics_router
from nkz_soil.api.routes.providers import router as providers_router, set_registry
from nkz_soil.api.routes.reading import router as reading_router
from nkz_soil.api.routes.subscriptions import router as subscriptions_router
from nkz_soil.api.routes.water_budget import router as water_budget_router
from nkz_soil.api.routes.writing import router as writing_router
from nkz_soil.config import REDIS_URL
from nkz_soil.providers.base import ProviderRegistry
from nkz_soil.providers.bgs import BgsProvider
from nkz_soil.providers.esdb_raster import EsdbRasterProvider
from nkz_soil.providers.eu_soil_hydro import EuSoilHydroGridsProvider
from nkz_soil.providers.idena import IdenaProvider
from nkz_soil.providers.igme import IgmeProvider
from nkz_soil.providers.iot_sensor import IotSensorProvider
from nkz_soil.providers.lab_analysis import LabAnalysisProvider
from nkz_soil.providers.lucas import LucasProvider
from nkz_soil.providers.lucas_texture_raster import LucasTextureRasterProvider
from nkz_soil.providers.soilgrids import SoilGridsProvider


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = ArqRedis.from_url(REDIS_URL)
    try:
        yield
    finally:
        await app.state.redis.close()


def create_app() -> FastAPI:
    registry = ProviderRegistry()
    registry.register(LabAnalysisProvider())
    registry.register(IotSensorProvider())
    registry.register(IdenaProvider())
    registry.register(IgmeProvider())
    registry.register(BgsProvider())
    registry.register(LucasProvider())
    registry.register(LucasTextureRasterProvider())
    registry.register(EsdbRasterProvider())
    registry.register(EuSoilHydroGridsProvider())
    registry.register(SoilGridsProvider())
    set_registry(registry)

    app = FastAPI(title="nkz-module-soil", version="0.1.0", lifespan=lifespan)

    allowed_origins = os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "https://nkz.robotika.cloud,https://nekazari.robotika.cloud",
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allowed_origins if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.limiter = limiter

    # Internal service-to-service routes — registered without JWT middleware
    from nkz_soil.api.routes.internal import router as internal_router

    app.include_router(internal_router, prefix="/v1/soil/internal")
    app.include_router(capabilities_router)
    app.include_router(reading_router, prefix="/v1/soil")
    app.include_router(writing_router, prefix="/v1/soil")
    app.include_router(layers_router, prefix="/v1/soil")
    app.include_router(providers_router, prefix="/v1/soil")
    app.include_router(subscriptions_router, prefix="/v1/soil")
    app.include_router(water_budget_router, prefix="/v1/soil")
    app.include_router(metrics_router, prefix="/v1/soil")

    @app.get("/health")
    @limiter.exempt
    async def health():
        return {"status": "ok"}

    return app


app = create_app()

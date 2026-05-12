from fastapi import FastAPI, Depends
from nkz_soil.api.routes.reading import router as reading_router
from nkz_soil.api.routes.writing import router as writing_router
from nkz_soil.api.routes.layers import router as layers_router
from nkz_soil.api.routes.providers import router as providers_router, set_registry
from nkz_soil.providers.base import ProviderRegistry
from nkz_soil.providers.soilgrids import SoilGridsProvider
from nkz_soil.providers.iot_sensor import IotSensorProvider
from nkz_soil.providers.lab_analysis import LabAnalysisProvider
from nkz_soil.providers.idena import IdenaProvider
from nkz_soil.providers.igme import IgmeProvider
from nkz_soil.providers.bgs import BgsProvider
from nkz_soil.providers.lucas import LucasPointsProvider
from nkz_soil.providers.eu_soil_hydro import EuSoilHydroGridsProvider


def create_app() -> FastAPI:
    registry = ProviderRegistry()
    registry.register(SoilGridsProvider())
    registry.register(IotSensorProvider())
    registry.register(LabAnalysisProvider())
    registry.register(IdenaProvider())
    registry.register(IgmeProvider())
    registry.register(BgsProvider())
    registry.register(LucasPointsProvider())
    registry.register(EuSoilHydroGridsProvider())
    set_registry(registry)

    app = FastAPI(title="nkz-module-soil", version="0.1.0")
    app.include_router(reading_router, prefix="/v1/soil")
    app.include_router(writing_router, prefix="/v1/soil")
    app.include_router(layers_router, prefix="/v1/soil")
    app.include_router(providers_router, prefix="/v1/soil")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()

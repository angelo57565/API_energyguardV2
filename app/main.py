import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (registra as tabelas)
from .anomaly import detector
from .config import get_settings
from .database import Base, engine, migrate
from .routers import alerts, analytics, appsettings, model, readings, validations
from .services import check_offline

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("energyguard")
settings = get_settings()


async def _watchdog() -> None:
    """A cada 30 s verifica se algum dispositivo parou de enviar."""
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(check_offline)
        except Exception:
            log.exception("Falha na verificação de dispositivos offline")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.api_key:
        log.warning("API_KEY vazia: qualquer pessoa com o endereço acessa a API. "
                    "Defina API_KEY antes de publicar na internet.")
    Base.metadata.create_all(bind=engine)
    migrate()
    if detector.load():
        log.info("Modelo carregado: %s", detector.meta)
    task = asyncio.create_task(_watchdog())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(
    title="EnergyGuard API",
    description="Recebe leituras do ESP32, guarda no banco, detecta anomalias e dispara alertas.",
    version="2.0.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (readings.router, model.router, alerts.router, analytics.router,
          appsettings.router, validations.router):
    app.include_router(r, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "model_ready": detector.ready}

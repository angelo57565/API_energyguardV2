import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from . import models  # noqa: F401  (registra as tabelas)
from .anomaly import detector
from .config import get_settings
from .database import Base, engine, migrate
from .routers import alerts, analytics, appsettings, model, readings, validations
from .services import check_offline, notify_events

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
        try:
            await asyncio.to_thread(notify_events)
        except Exception:
            log.exception("Falha ao processar entregas pendentes")


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


@app.get("/ready", responses={503: {"description": "Banco indisponível"}})
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível") from None
    return {"status": "ready"}

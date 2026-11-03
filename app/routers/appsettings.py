from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSetting
from ..security import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])

# chave -> (valor padrao, minimo, maximo)
ALLOWED = {
    "tariff": (0.90, 0.0, 100.0),               # R$/kWh
    "nominal_voltage": (127.0, 100.0, 300.0),   # V
    "monthly_goal_kwh": (0.0, 0.0, 100000.0),   # 0 = sem meta
    "send_interval_s": (5.0, 1.0, 3600.0),      # intervalo de envio do ESP32
}


def _read_all(db: Session) -> dict:
    stored = {s.key: s.value for s in db.scalars(select(AppSetting)).all()}
    out = {}
    for key, (default, _lo, _hi) in ALLOWED.items():
        try:
            out[key] = float(stored[key]) if key in stored else default
        except ValueError:
            out[key] = default
    return out


@router.get("/settings")
def get_settings_values(db: Session = Depends(get_db)):
    return _read_all(db)


@router.put("/settings")
def put_settings(body: dict[str, float], db: Session = Depends(get_db)):
    for key, value in body.items():
        if key not in ALLOWED:
            raise HTTPException(400, f"Configuração desconhecida: {key}")
        _default, lo, hi = ALLOWED[key]
        if not (lo <= value <= hi):
            raise HTTPException(400, f"{key} deve estar entre {lo:g} e {hi:g}")
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=str(value)))
        else:
            row.value = str(value)
    db.commit()
    return _read_all(db)

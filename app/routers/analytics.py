from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..database import engine, get_db
from ..models import Reading, utcnow
from ..security import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])

MIN_MAINS_V = 20.0  # abaixo disso consideramos "sem rede"


def _hour_bucket():
    if engine.dialect.name == "sqlite":
        return func.strftime("%Y-%m-%dT%H:00:00", Reading.created_at)
    return func.date_format(Reading.created_at, "%Y-%m-%dT%H:00:00")


@router.get("/consumption/hourly")
def consumption_hourly(
    device_id: str | None = None,
    hours: int = Query(168, ge=1, le=24 * 31),
    db: Session = Depends(get_db),
):
    """kWh consumidos por hora (horas em UTC; o dashboard converte para o fuso local)."""
    since = utcnow() - timedelta(hours=hours)
    bucket = _hour_bucket()
    q = select(bucket, func.min(Reading.energy), func.max(Reading.energy)).where(Reading.created_at >= since)
    if device_id:
        q = q.where(Reading.device_id == device_id)
    rows = db.execute(q.group_by(bucket).order_by(bucket)).all()

    out = []
    prev_max = None
    for period, e_min, e_max in rows:
        # o que foi consumido entre a ultima leitura da hora anterior e a 1a desta conta aqui
        start = prev_max if (prev_max is not None and prev_max <= e_min) else e_min
        out.append({"period": period + "Z", "kwh": round(max(e_max - start, 0.0), 5)})
        prev_max = e_max
    return out


@router.get("/quality")
def quality(
    device_id: str | None = None,
    hours: int = Query(24, ge=1, le=24 * 30),
    vmin: float = 117.0,
    vmax: float = 133.0,
    fmin: float = 59.5,
    fmax: float = 60.5,
    db: Session = Depends(get_db),
):
    """Qualidade da energia: quanto tempo a tensão/frequência ficaram fora da faixa."""
    since = utcnow() - timedelta(hours=hours)
    base = [Reading.created_at >= since]
    if device_id:
        base.append(Reading.device_id == device_id)

    total = db.scalar(select(func.count(Reading.id)).where(*base)) or 0

    mains = [*base, Reading.voltage >= MIN_MAINS_V]
    freq_ok = Reading.frequency > 0

    def count_if(cond):
        return func.sum(case((cond, 1), else_=0))

    q = select(
        func.count(Reading.id),
        count_if(Reading.voltage < vmin),
        count_if(Reading.voltage > vmax),
        func.min(Reading.voltage),
        func.avg(Reading.voltage),
        func.max(Reading.voltage),
        func.min(case((freq_ok, Reading.frequency))),
        func.avg(case((freq_ok, Reading.frequency))),
        func.max(case((freq_ok, Reading.frequency))),
        count_if(and_(freq_ok, or_(Reading.frequency < fmin, Reading.frequency > fmax))),
    ).where(*mains)
    n, low, high, v_min, v_avg, v_max, f_min, f_avg, f_max, f_out = db.execute(q).one()
    n = int(n or 0)

    def r(x, nd=2):
        return round(float(x), nd) if x is not None else None

    def pct(x):
        return round(100.0 * float(x or 0) / n, 2) if n else None

    return {
        "hours": hours,
        "readings_total": int(total),
        "readings_with_mains": n,
        "voltage": {"min": r(v_min), "avg": r(v_avg), "max": r(v_max), "range": [vmin, vmax],
                    "low_pct": pct(low), "high_pct": pct(high)},
        "frequency": {"min": r(f_min), "avg": r(f_avg), "max": r(f_max), "range": [fmin, fmax],
                      "out_pct": pct(f_out)},
    }

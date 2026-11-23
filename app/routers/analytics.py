from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..consumption import energy_deltas
from ..database import get_db
from ..models import Reading, utcnow
from ..security import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])

MIN_MAINS_V = 20.0  # abaixo disso consideramos "sem rede"


@router.get("/consumption/hourly")
def consumption_hourly(
    device_id: str | None = None,
    hours: int = Query(168, ge=1, le=24 * 31),
    db: Session = Depends(get_db),
):
    """kWh consumidos por hora (horas em UTC; o dashboard converte para o fuso local)."""
    since = utcnow() - timedelta(hours=hours)
    by_hour = {}
    for measured_at, delta in energy_deltas(db, since, device_id):
        hour = measured_at.replace(minute=0, second=0, microsecond=0)
        by_hour[hour] = by_hour.get(hour, 0.0) + delta
    return [
        {"period": hour.isoformat(timespec="seconds") + "Z", "kwh": round(by_hour[hour], 5)}
        for hour in sorted(by_hour)
    ]


@router.get("/quality")
def quality(
    device_id: str | None = None,
    hours: int = Query(24, ge=1, le=24 * 30),
    vmin: float = Query(117.0, ge=0, le=500),
    vmax: float = Query(133.0, ge=0, le=500),
    fmin: float = Query(59.5, ge=0, le=100),
    fmax: float = Query(60.5, ge=0, le=100),
    db: Session = Depends(get_db),
):
    """Percentual de amostras válidas fora da faixa, entre leituras com rede."""
    if vmin > vmax or fmin > fmax:
        raise HTTPException(422, "O limite mínimo deve ser menor ou igual ao máximo.")
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
        count_if(freq_ok),
        count_if(and_(freq_ok, or_(Reading.frequency < fmin, Reading.frequency > fmax))),
    ).where(*mains)
    n, low, high, v_min, v_avg, v_max, f_min, f_avg, f_max, n_freq, f_out = db.execute(q).one()
    n = int(n or 0)

    def r(x, nd=2):
        return round(float(x), nd) if x is not None else None

    def pct(x, count):
        return round(100.0 * float(x or 0) / count, 2) if count else None

    return {
        "hours": hours,
        "readings_total": int(total),
        "readings_with_mains": n,
        "voltage": {"min": r(v_min), "avg": r(v_avg), "max": r(v_max), "range": [vmin, vmax],
                    "low_pct": pct(low, n), "high_pct": pct(high, n)},
        "frequency": {"min": r(f_min), "avg": r(f_avg), "max": r(f_max), "range": [fmin, fmax],
                      "valid_readings": int(n_freq or 0), "out_pct": pct(f_out, n_freq)},
    }

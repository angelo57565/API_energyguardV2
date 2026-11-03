import logging
import math
import threading

import numpy as np
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .anomaly import FEATURES, detector
from .config import get_settings
from .database import SessionLocal
from .anomaly_types import TYPES
from .models import AlertEvent, AlertRule, AppSetting, Reading, utcnow
from .notify import notify

log = logging.getLogger("energyguard")
_train_lock = threading.Lock()

METRIC_INFO = {
    "voltage": ("Tensão", "V"),
    "current": ("Corrente", "A"),
    "power": ("Potência", "W"),
    "power_factor": ("Fator de potência", ""),
    "frequency": ("Frequência", "Hz"),
    "apparent_power": ("Potência aparente", "VA"),
    "reactive_power": ("Potência reativa", "var"),
}


def metric_value(r: Reading, metric: str) -> float:
    if metric == "apparent_power":
        return r.voltage * r.current
    if metric == "reactive_power":
        s = r.voltage * r.current
        return math.sqrt(max(s * s - r.power * r.power, 0.0))
    return float(getattr(r, metric))


def feature_stats() -> dict | None:
    meta = detector.meta
    if not meta.get("feature_mean"):
        return None
    return {
        name: (mean, max(std, 1e-6))
        for name, mean, std in zip(FEATURES, meta["feature_mean"], meta["feature_std"])
    }


def nominal_voltage(db: Session) -> float:
    row = db.get(AppSetting, "nominal_voltage")
    try:
        return float(row.value) if row else 127.0
    except ValueError:
        return 127.0


# ----------------------------- modelo -----------------------------
def train_model(db: Session) -> dict:
    """Treina o Isolation Forest com as leituras mais recentes.

    Leituras que voce marcou como anomalia real ficam de fora do treino.
    """
    s = get_settings()
    cols = [getattr(Reading, f) for f in FEATURES]
    q = (
        select(*cols)
        .where(or_(Reading.feedback.is_(None), Reading.feedback != "real"))
        .order_by(Reading.id.desc())
        .limit(s.train_window)
    )
    rows = db.execute(q).all()
    if len(rows) < s.min_train_samples:
        raise ValueError(
            f"Leituras insuficientes para treinar: {len(rows)} (mínimo {s.min_train_samples})."
        )
    X = np.array([tuple(r) for r in rows], dtype=float)
    return detector.train(X)


def maybe_train() -> None:
    """Treina sozinho: na 1ª vez que houver amostras suficientes e depois a cada N leituras."""
    if not _train_lock.acquire(blocking=False):
        return
    try:
        s = get_settings()
        with SessionLocal() as db:
            total = db.scalar(select(func.count(Reading.id))) or 0
            if total < s.min_train_samples:
                return
            if detector.ready and total % s.retrain_every != 0:
                return
            meta = train_model(db)
            log.info("Modelo treinado com %s leituras", meta["n_samples"])
    except Exception:
        log.exception("Falha ao treinar o modelo")
    finally:
        _train_lock.release()


# ----------------------------- alertas -----------------------------
def _in_cooldown(db: Session, now, device_id: str, kind: str, rule_id: int | None, cooldown_s: int) -> bool:
    q = select(func.max(AlertEvent.created_at)).where(
        AlertEvent.device_id == device_id, AlertEvent.kind == kind
    )
    if rule_id is not None:
        q = q.where(AlertEvent.rule_id == rule_id)
    last = db.scalar(q)
    return last is not None and (now - last).total_seconds() < cooldown_s


def evaluate_alerts(db: Session, reading: Reading) -> list[int]:
    """Cria eventos de alerta para a leitura recem-gravada. Retorna os ids criados."""
    s = get_settings()
    now = utcnow()
    created: list[AlertEvent] = []

    rules = db.scalars(select(AlertRule).where(AlertRule.enabled.is_(True))).all()
    for rule in rules:
        if rule.device_id and rule.device_id != reading.device_id:
            continue
        value = metric_value(reading, rule.metric)
        hit = value > rule.threshold if rule.operator == ">" else value < rule.threshold
        if not hit:
            continue
        if _in_cooldown(db, now, reading.device_id, "rule", rule.id, rule.cooldown_s):
            continue
        label, unit = METRIC_INFO[rule.metric]
        created.append(
            AlertEvent(
                kind="rule", rule_id=rule.id, device_id=reading.device_id, metric=rule.metric,
                value=value, threshold=rule.threshold,
                message=f"ALERTA - {rule.name}: {label} = {value:.2f} {unit} (limite {rule.operator} {rule.threshold:g} {unit})".strip(),
            )
        )

    if s.notify_on_anomaly and reading.is_anomaly:
        if not _in_cooldown(db, now, reading.device_id, "anomaly", None, s.anomaly_alert_cooldown_s):
            codes = (reading.anomaly_types or "").split(",")
            label = TYPES[codes[0]][0] if codes and codes[0] in TYPES else "tipo não classificado"
            created.append(
                AlertEvent(
                    kind="anomaly", device_id=reading.device_id,
                    value=reading.anomaly_score,
                    message=(f"ANOMALIA ({label}) em {reading.device_id}: {reading.voltage:.1f} V, "
                             f"{reading.current:.2f} A, {reading.power:.0f} W, FP {reading.power_factor:.2f}"),
                )
            )

    if not created:
        return []
    db.add_all(created)
    db.commit()
    return [e.id for e in created]


def notify_events(event_ids: list[int]) -> None:
    """Envia os eventos por Telegram/e-mail e marca como notificados."""
    with SessionLocal() as db:
        for eid in event_ids:
            ev = db.get(AlertEvent, eid)
            if ev is None:
                continue
            ev.notified = notify(ev.message)
        db.commit()


def check_offline() -> None:
    """Gera um alerta quando um dispositivo para de enviar (uma vez por queda)."""
    s = get_settings()
    now = utcnow()
    new_ids: list[int] = []
    with SessionLocal() as db:
        rows = db.execute(
            select(Reading.device_id, func.max(Reading.created_at)).group_by(Reading.device_id)
        ).all()
        for device, last in rows:
            silent = (now - last).total_seconds()
            if silent < s.offline_after_s:
                continue
            last_alert = db.scalar(
                select(func.max(AlertEvent.created_at)).where(
                    AlertEvent.device_id == device, AlertEvent.kind == "offline"
                )
            )
            if last_alert is not None and last_alert > last:
                continue  # ja avisamos desta queda
            ev = AlertEvent(
                kind="offline", device_id=device,
                message=f"OFFLINE - {device} está sem enviar dados há {int(silent // 60)} min",
            )
            db.add(ev)
            db.commit()
            new_ids.append(ev.id)
    if new_ids:
        notify_events(new_ids)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from ..anomaly import detector
from ..database import get_db
from ..models import Reading
from ..security import require_api_key
from ..services import train_model

router = APIRouter(prefix="/model", dependencies=[Depends(require_api_key)])


@router.get("/status")
def model_status():
    return {"ready": detector.ready, **detector.meta}


@router.post("/train")
def train(db: Session = Depends(get_db)):
    """Treina (ou retreina) o Isolation Forest agora, com as leituras mais recentes."""
    try:
        meta = train_model(db)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ready": True, **meta}


@router.get("/evaluation")
def evaluation(device_id: str | None = None, db: Session = Depends(get_db)):
    """Matriz de confusão com base nos rótulos que você deu (real / falso alarme).

    - TP: o modelo marcou e você confirmou   - FP: o modelo marcou e era falso alarme
    - FN: o modelo não marcou, mas era anomalia - TN: o modelo não marcou e era normal
    O recall só é confiável se você também rotular leituras que o modelo deixou passar.
    """
    q = select(*_confusion_counts()).where(*_evaluated_readings())
    if device_id:
        q = q.where(Reading.device_id == device_id)

    return _metrics(*db.execute(q).one())


@router.get("/evaluation/devices")
def evaluation_by_device(db: Session = Depends(get_db)):
    """Compara os medidores com previsões rotuladas."""
    q = (
        select(Reading.device_id, *_confusion_counts())
        .where(*_evaluated_readings())
        .group_by(Reading.device_id)
        .order_by(Reading.device_id)
    )
    return [{"device_id": device_id, **_metrics(*counts)} for device_id, *counts in db.execute(q)]


def _evaluated_readings():
    return Reading.anomaly_score.is_not(None), Reading.feedback.in_(("real", "false"))


def _confusion_counts():
    return [
        func.count(case((and_(Reading.is_anomaly.is_(flagged), Reading.feedback == label), 1)))
        for flagged, label in ((True, "real"), (True, "false"), (False, "real"), (False, "false"))
    ]

def _metrics(tp: int, fp: int, fn: int, tn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1_denominator = 2 * tp + fp + fn
    f1 = 2 * tp / f1_denominator if f1_denominator else None
    return {
        "labeled": tp + fp + fn + tn,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
    }

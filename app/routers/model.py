from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
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
    q = (
        select(Reading.is_anomaly, Reading.feedback, func.count(Reading.id))
        .where(Reading.feedback.is_not(None))
        .group_by(Reading.is_anomaly, Reading.feedback)
    )
    if device_id:
        q = q.where(Reading.device_id == device_id)

    tp = fp = fn = tn = 0
    for flagged, label, n in db.execute(q).all():
        if flagged and label == "real":
            tp += n
        elif flagged and label == "false":
            fp += n
        elif not flagged and label == "real":
            fn += n
        else:
            tn += n

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else None
    return {
        "labeled": tp + fp + fn + tn,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
    }

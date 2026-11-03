from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Reading, Validation
from ..schemas import ValidationIn, ValidationOut
from ..security import require_api_key

router = APIRouter(prefix="/validations", dependencies=[Depends(require_api_key)])

AVG_LAST_N = 6  # media das ultimas leituras (~30 s a cada 5 s) para reduzir ruido


@router.post("", response_model=ValidationOut, status_code=201)
def create_validation(body: ValidationIn, db: Session = Depends(get_db)):
    """Registra o valor do instrumento e guarda o que o ESP32 estava medindo agora."""
    rows = db.scalars(
        select(Reading).where(Reading.device_id == body.device_id).order_by(Reading.id.desc()).limit(AVG_LAST_N)
    ).all()
    if not rows:
        raise HTTPException(404, "Nenhuma leitura desse dispositivo ainda")
    measured = sum(getattr(r, body.quantity) for r in rows) / len(rows)
    item = Validation(
        device_id=body.device_id, quantity=body.quantity,
        reference=body.reference, measured=round(measured, 4), note=body.note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[ValidationOut])
def list_validations(
    device_id: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    q = select(Validation)
    if device_id:
        q = q.where(Validation.device_id == device_id)
    return db.scalars(q.order_by(Validation.id.desc()).limit(limit)).all()


@router.delete("/{validation_id}", status_code=204)
def delete_validation(validation_id: int, db: Session = Depends(get_db)):
    item = db.get(Validation, validation_id)
    if item is None:
        raise HTTPException(404, "Registro não encontrado")
    db.delete(item)
    db.commit()
    return Response(status_code=204)

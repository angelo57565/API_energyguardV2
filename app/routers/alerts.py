from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AlertEvent, AlertRule
from ..notify import email_configured, notify, telegram_configured
from ..schemas import AlertEventOut, AlertRuleIn, AlertRuleOut
from ..security import require_api_key

router = APIRouter(prefix="/alerts", dependencies=[Depends(require_api_key)])


@router.get("/rules", response_model=list[AlertRuleOut])
def list_rules(db: Session = Depends(get_db)):
    return db.scalars(select(AlertRule).order_by(AlertRule.id)).all()


@router.post("/rules", response_model=AlertRuleOut, status_code=201)
def create_rule(body: AlertRuleIn, db: Session = Depends(get_db)):
    rule = AlertRule(**body.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/rules/{rule_id}", response_model=AlertRuleOut)
def update_rule(rule_id: int, body: AlertRuleIn, db: Session = Depends(get_db)):
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Regra não encontrada")
    for key, value in body.model_dump().items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Regra não encontrada")
    db.delete(rule)
    db.commit()
    return Response(status_code=204)


@router.get("/events", response_model=list[AlertEventOut])
def list_events(
    device_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(AlertEvent)
    if device_id:
        q = q.where(AlertEvent.device_id == device_id)
    return db.scalars(q.order_by(AlertEvent.id.desc()).limit(limit)).all()


@router.get("/channels")
def channels():
    return {"telegram": telegram_configured(), "email": email_configured()}


@router.post("/test")
def send_test():
    ok = notify("EnergyGuard: mensagem de teste.")
    return {"sent": ok, "telegram": telegram_configured(), "email": email_configured()}

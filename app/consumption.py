from datetime import datetime
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Reading


def energy_deltas(
    db: Session, since: datetime, device_id: str | None,
) -> Iterator[tuple[datetime, float]]:
    """Diferenças entre medições consecutivas de cada medidor dentro da janela."""
    q = select(Reading.device_id, Reading.created_at, Reading.energy).where(Reading.created_at >= since)
    if device_id:
        q = q.where(Reading.device_id == device_id)
    q = q.order_by(Reading.device_id, Reading.created_at, Reading.id)

    previous_device = None
    previous_energy = 0.0
    with db.execute(q.execution_options(yield_per=1000)) as rows:
        for device, measured_at, energy in rows:
            delta = 0.0
            if device == previous_device:
                # Após um reset para zero, só sabemos quanto o novo contador acumulou.
                delta = energy - previous_energy if energy >= previous_energy else energy
            yield measured_at, delta
            previous_device, previous_energy = device, energy

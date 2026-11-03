from datetime import datetime, timedelta, timezone

MIN_VALID_EPOCH = 1_700_000_000
MAX_FUTURE = timedelta(minutes=5)
MAX_AGE = timedelta(days=7)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def created_at_from_epoch(epoch: int | None, now: datetime | None = None) -> tuple[datetime, bool]:
    now = now or utcnow()
    if epoch is None or epoch < MIN_VALID_EPOCH:
        return now, False
    moment = datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None)
    if moment > now + MAX_FUTURE or moment < now - MAX_AGE:
        return now, False
    return moment, True

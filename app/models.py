from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    """UTC sem tzinfo (formato que o MySQL/SQLite guardam)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Reading(Base):
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64))
    voltage: Mapped[float] = mapped_column(Float)
    current: Mapped[float] = mapped_column(Float)
    power: Mapped[float] = mapped_column(Float)
    energy: Mapped[float] = mapped_column(Float)
    frequency: Mapped[float] = mapped_column(Float)
    power_factor: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # saude do ESP32 (opcionais)
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uptime_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    send_failures: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # explicacao da anomalia (JSON) e rotulo dado pelo usuario ("real" | "false")
    reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(String(16), nullable=True)
    anomaly_types: Mapped[str | None] = mapped_column(String(120), nullable=True)

    __table_args__ = (Index("ix_readings_device_created", "device_id", "created_at"),)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    metric: Mapped[str] = mapped_column(String(32))
    operator: Mapped[str] = mapped_column(String(2))  # ">" ou "<"
    threshold: Mapped[float] = mapped_column(Float)
    cooldown_s: Mapped[int] = mapped_column(Integer, default=300)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # rule | anomaly | offline
    rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_id: Mapped[str] = mapped_column(String(64))
    metric: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(String(255))
    notified: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


class Validation(Base):
    """Comparacao de uma leitura do ESP32 com um instrumento de referencia."""

    __tablename__ = "validations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    device_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[str] = mapped_column(String(16))  # voltage | current | power
    reference: Mapped[float] = mapped_column(Float)
    measured: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

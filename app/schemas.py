import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

MetricName = Literal[
    "voltage", "current", "power", "power_factor", "frequency", "apparent_power", "reactive_power"
]


def _z(value: datetime) -> str:
    # guardado em UTC; o "Z" deixa isso explicito para o dashboard
    return value.isoformat(timespec="seconds") + "Z"


class ReadingIn(BaseModel):
    """Payload enviado pelo ESP32 em POST /api/readings."""

    device_id: str = Field(min_length=1, max_length=64)
    voltage: float = Field(ge=0, le=500, description="Tensão RMS (V)")
    current: float = Field(ge=0, le=500, description="Corrente RMS (A)")
    power: float = Field(ge=0, le=200000, description="Potência ativa (W)")
    energy: float = Field(ge=0, description="Energia acumulada (kWh)")
    frequency: float = Field(ge=0, le=100, description="Frequência (Hz)")
    power_factor: float = Field(ge=0, le=1, description="Fator de potência")
    # saude do ESP32 (opcionais, firmwares antigos nao enviam)
    rssi: int | None = Field(default=None, ge=-127, le=0, description="Sinal Wi-Fi (dBm)")
    uptime_s: int | None = Field(default=None, ge=0, description="Tempo ligado (s)")
    send_failures: int | None = Field(default=None, ge=0, description="Falhas de envio desde o boot")


class ReadingUpload(ReadingIn):
    measured_ts: int | None = Field(default=None, ge=0, description="Horário da medição (epoch UTC, em segundos)")


class ReadingBatch(BaseModel):
    readings: list[ReadingUpload] = Field(min_length=1, max_length=100)


class ReadingOut(ReadingIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    is_anomaly: bool
    anomaly_score: float | None = None
    feedback: str | None = None
    reasons: list[dict] | None = None
    anomaly_types: list[str] | None = None

    @field_validator("anomaly_types", mode="before")
    @classmethod
    def _split_types(cls, v):
        if isinstance(v, str):
            return [t for t in v.split(",") if t]
        return v

    @field_validator("reasons", mode="before")
    @classmethod
    def _parse_reasons(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                return None
        return v

    @field_serializer("created_at")
    def _ser_created(self, value: datetime) -> str:
        return _z(value)


class FeedbackIn(BaseModel):
    label: Literal["real", "false"] | None = Field(
        description="'real' = é anomalia de verdade; 'false' = não é anomalia; null remove o rótulo"
    )


class AlertRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    metric: MetricName
    operator: Literal[">", "<"]
    threshold: float
    cooldown_s: int = Field(default=300, ge=0, le=86400)
    enabled: bool = True
    device_id: str | None = None


class AlertRuleOut(AlertRuleIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AlertEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    kind: str
    rule_id: int | None = None
    device_id: str
    metric: str | None = None
    value: float | None = None
    threshold: float | None = None
    message: str
    notified: bool

    @field_serializer("created_at")
    def _ser_created(self, value: datetime) -> str:
        return _z(value)


class ValidationIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    quantity: Literal["voltage", "current", "power"]
    reference: float = Field(gt=0, description="Valor medido no multímetro/alicate")
    note: str | None = Field(default=None, max_length=255)


class ValidationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    device_id: str
    quantity: str
    reference: float
    measured: float
    note: str | None = None

    @field_serializer("created_at")
    def _ser_created(self, value: datetime) -> str:
        return _z(value)

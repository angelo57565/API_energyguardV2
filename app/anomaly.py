import threading
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import get_settings

# Ordem das colunas usadas no treino e na predicao
FEATURES = ["voltage", "current", "power", "power_factor", "frequency"]


class AnomalyDetector:
    """Isolation Forest (com StandardScaler) guardado em disco com joblib."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model = None
        self._meta: dict = {}

    @property
    def ready(self) -> bool:
        return self._model is not None

    @property
    def meta(self) -> dict:
        return dict(self._meta)

    def load(self) -> bool:
        path = Path(get_settings().model_path)
        if not path.exists():
            return False
        bundle = joblib.load(path)
        with self._lock:
            self._model = bundle["model"]
            self._meta = bundle["meta"]
        return True

    def train(self, X: np.ndarray) -> dict:
        s = get_settings()
        model = make_pipeline(
            StandardScaler(),
            IsolationForest(
                n_estimators=s.n_estimators,
                contamination=s.contamination,
                random_state=42,
                n_jobs=1,
            ),
        )
        model.fit(X)
        meta = {
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_samples": int(X.shape[0]),
            "features": FEATURES,
            "contamination": s.contamination,
            "n_estimators": s.n_estimators,
            # usados para explicar anomalias (quanto cada variavel fugiu do normal)
            "feature_mean": [float(x) for x in X.mean(axis=0)],
            "feature_std": [float(x) for x in X.std(axis=0)],
        }
        path = Path(s.model_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": model, "meta": meta}, path)
        with self._lock:
            self._model = model
            self._meta = meta
        return meta

    def predict(self, features: list[float]) -> tuple[bool, float] | None:
        """Retorna (is_anomaly, score). Score menor (negativo) = mais anomalo."""
        with self._lock:
            model = self._model
        if model is None:
            return None
        x = np.asarray([features], dtype=float)
        label = int(model.predict(x)[0])
        score = float(model.decision_function(x)[0])
        return label == -1, score


    def explain(self, features: list[float], top: int = 3) -> list[dict] | None:
        """Variaveis que mais se afastaram da media do treino (em desvios-padrao).

        E uma explicacao aproximada: o Isolation Forest nao da motivos sozinho,
        entao mostramos o que estava mais longe do comportamento normal.
        """
        meta = self._meta
        if not meta.get("feature_mean"):
            return None
        out = []
        for name, value, mean, std in zip(FEATURES, features, meta["feature_mean"], meta["feature_std"]):
            std = max(std, 1e-6)
            out.append({
                "feature": name,
                "value": round(float(value), 4),
                "mean": round(mean, 4),
                "std": round(std, 4),
                "z": round((float(value) - mean) / std, 2),
            })
        out.sort(key=lambda r: abs(r["z"]), reverse=True)
        return out[:top]


detector = AnomalyDetector()

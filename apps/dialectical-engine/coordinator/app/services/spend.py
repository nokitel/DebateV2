from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import RUNTIME_SETTINGS_KEY, load_settings
from app.models.entities import Generation, Setting, now_utc

GROK_MODEL_ID = "grok-4"
GROK_INPUT_USD_PER_MILLION_TOKENS = 1.25
GROK_OUTPUT_USD_PER_MILLION_TOKENS = 2.50
MODEL_PRICING_USD_PER_MILLION_TOKENS = {
    GROK_MODEL_ID: {
        "input": GROK_INPUT_USD_PER_MILLION_TOKENS,
        "output": GROK_OUTPUT_USD_PER_MILLION_TOKENS,
    }
}


def current_month_start(now: datetime | None = None) -> datetime:
    now = now or now_utc()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def grok_monthly_cap_usd(db: Session) -> float:
    return model_monthly_caps_usd(db).get(GROK_MODEL_ID, load_settings().grok_monthly_cap_usd)


def model_monthly_caps_usd(db: Session) -> dict[str, float]:
    defaults = load_settings()
    setting = db.get(Setting, RUNTIME_SETTINGS_KEY)
    if not setting:
        return {GROK_MODEL_ID: defaults.grok_monthly_cap_usd}
    value = setting.value if isinstance(setting.value, dict) else {}
    caps = clean_model_monthly_caps(value.get("model_monthly_caps_usd"))
    if GROK_MODEL_ID not in caps:
        caps[GROK_MODEL_ID] = clean_grok_monthly_cap(
            value.get("grok_monthly_cap_usd"),
            defaults.grok_monthly_cap_usd,
        )
    return caps


def clean_monthly_cap(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        cap = float(value)
    except (TypeError, ValueError):
        return None
    if cap != cap or cap in {float("inf"), float("-inf")}:
        return None
    return max(0.0, cap)


def clean_model_monthly_caps(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    caps: dict[str, float] = {}
    for model_id, cap in value.items():
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        cleaned = clean_monthly_cap(cap)
        if cleaned is not None:
            caps[model_id.strip()] = cleaned
    return caps


def clean_grok_monthly_cap(value: object, default: float) -> float:
    cleaned = clean_monthly_cap(value)
    return default if cleaned is None else cleaned


def grok_monthly_spend_usd(db: Session, now: datetime | None = None) -> float:
    return model_monthly_spend_usd(db, GROK_MODEL_ID, now=now)


def model_monthly_spend_usd(db: Session, model_id: str, now: datetime | None = None) -> float:
    pricing = MODEL_PRICING_USD_PER_MILLION_TOKENS.get(model_id)
    if not pricing:
        return 0.0
    tokens_in, tokens_out = db.execute(
        select(
            func.coalesce(func.sum(Generation.tokens_in), 0),
            func.coalesce(func.sum(Generation.tokens_out), 0),
        ).where(
            Generation.model_id == model_id,
            Generation.created_at >= current_month_start(now),
        )
    ).one()
    cost = (
        (int(tokens_in or 0) / 1_000_000) * float(pricing["input"])
        + (int(tokens_out or 0) / 1_000_000) * float(pricing["output"])
    )
    return round(cost, 6)


def model_monthly_spend_usd_by_model(db: Session, model_ids: list[str], now: datetime | None = None) -> dict[str, float]:
    return {model_id: model_monthly_spend_usd(db, model_id, now=now) for model_id in model_ids}


def grok_cap_reached(db: Session) -> bool:
    return model_cap_reached(db, GROK_MODEL_ID)


def model_cap_reached(db: Session, model_id: str) -> bool:
    caps = model_monthly_caps_usd(db)
    if model_id not in caps:
        return False
    cap = caps[model_id]
    return cap <= 0 or model_monthly_spend_usd(db, model_id) >= cap


def capped_model_ids(db: Session, model_ids: set[str]) -> set[str]:
    return {model_id for model_id in model_ids if model_cap_reached(db, model_id)}

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, require_user_token
from app.core.config import DEFAULT_ROUTING, RUNTIME_SETTINGS_KEY, load_settings
from app.core.db import get_db
from app.core.write_lock import commit_write
from app.models.entities import Setting
from app.services.routing import routing_engine
from app.services.spend import (
    GROK_INPUT_USD_PER_MILLION_TOKENS,
    GROK_MODEL_ID,
    GROK_OUTPUT_USD_PER_MILLION_TOKENS,
    grok_monthly_cap_usd,
    grok_monthly_spend_usd,
    MODEL_PRICING_USD_PER_MILLION_TOKENS,
    clean_model_monthly_caps,
    model_monthly_caps_usd,
    model_monthly_spend_usd_by_model,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])
POOL_STRATEGIES = {"round_robin"}
ROLE_CONSTRAINTS = {"not_same_as_claim_author"}


class SettingsUpdate(BaseModel):
    routing: Optional[dict[str, Any]] = None
    enabled_models: Optional[list[str]] = None
    grok_monthly_cap_usd: Optional[float] = Field(default=None, ge=0)
    model_monthly_caps_usd: Optional[dict[str, Any]] = None


def clean_model_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def clean_choice(value: Any, field_name: str, allowed: set[str]) -> str:
    cleaned = clean_model_id(value, field_name)
    if cleaned not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"{field_name} must be one of: {allowed_values}")
    return cleaned


def clean_model_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return [clean_model_id(model, field_name) for model in value]


def unique_model_list(models: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for model in models:
        if model in seen:
            continue
        unique.append(model)
        seen.add(model)
    return unique


def clean_enabled_models(value: Any, routing: dict[str, Any]) -> list[str]:
    models = unique_model_list(clean_model_list(value, "enabled_models"))
    configured = set(configured_model_ids(routing))
    unknown = sorted(model for model in models if model not in configured)
    if unknown:
        raise ValueError(f"enabled_models contains models not present in routing: {', '.join(unknown)}")
    return models


def clean_cap_value(value: Any, field_name: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative number")
    try:
        cap = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a non-negative number") from None
    if cap != cap or cap in {float("inf"), float("-inf")} or cap < 0:
        raise ValueError(f"{field_name} must be a non-negative number")
    return cap


def clean_model_caps(value: Any, routing: dict[str, Any]) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("model_monthly_caps_usd must be an object")
    caps: dict[str, float] = {}
    for model_id, cap in value.items():
        model = clean_model_id(model_id, "model_monthly_caps_usd model")
        caps[model] = clean_cap_value(cap, f"model_monthly_caps_usd.{model}")
    configured = set(configured_model_ids(routing))
    unknown = sorted(model for model in caps if model not in configured)
    if unknown:
        raise ValueError(f"model_monthly_caps_usd contains models not present in routing: {', '.join(unknown)}")
    return caps


def clean_persisted_model_caps(value: Any, routing: dict[str, Any]) -> dict[str, float]:
    configured = set(configured_model_ids(routing))
    return {model: cap for model, cap in clean_model_monthly_caps(value).items() if model in configured}


def clean_persisted_model_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return unique_model_list([model.strip() for model in value if isinstance(model, str) and model.strip()])


def clean_persisted_enabled_models(value: Any, routing: dict[str, Any]) -> list[str]:
    configured = set(configured_model_ids(routing))
    return [model for model in clean_persisted_model_list(value) if model in configured]


def validate_routing(routing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not routing:
        raise ValueError("routing must define at least one role")

    cleaned: dict[str, dict[str, Any]] = {}
    for role, role_config in routing.items():
        if not isinstance(role, str) or not role.strip():
            raise ValueError("routing role names must be non-empty strings")
        if not isinstance(role_config, dict):
            raise ValueError(f"routing.{role} must be an object")

        role_value = dict(role_config)
        if "pool" in role_value:
            pool = unique_model_list(clean_model_list(role_value.get("pool"), f"routing.{role}.pool"))
            if not pool:
                raise ValueError(f"routing.{role}.pool must contain at least one model")
            role_value["pool"] = pool
            strategy = role_value.get("strategy")
            if strategy is not None:
                role_value["strategy"] = clean_choice(strategy, f"routing.{role}.strategy", POOL_STRATEGIES)
            constraint = role_value.get("constraint")
            if constraint is not None:
                role_value["constraint"] = clean_choice(constraint, f"routing.{role}.constraint", ROLE_CONSTRAINTS)
        else:
            primary = role_value.get("primary")
            fallback = role_value.get("fallback", [])
            if primary is not None:
                role_value["primary"] = clean_model_id(primary, f"routing.{role}.primary")
            role_value["fallback"] = unique_model_list(clean_model_list(fallback, f"routing.{role}.fallback"))
            if not role_value.get("primary") and not role_value["fallback"]:
                raise ValueError(f"routing.{role} must define primary, fallback, or pool")
        cleaned[role.strip()] = role_value
    return cleaned


def clean_persisted_routing(value: Any) -> dict[str, dict[str, Any]] | None:
    if not isinstance(value, dict):
        return None
    try:
        return validate_routing(value)
    except ValueError:
        return None


def configured_model_ids(routing: dict[str, Any]) -> list[str]:
    models: set[str] = set()
    for role_config in routing.values():
        if not isinstance(role_config, dict):
            continue
        primary = role_config.get("primary")
        if primary:
            models.add(str(primary))
        models.update(str(model) for model in role_config.get("fallback", []) if model)
        models.update(str(model) for model in role_config.get("pool", []) if model)
    return sorted(models)


def current_settings(db: Session) -> dict[str, Any]:
    persisted = db.get(Setting, RUNTIME_SETTINGS_KEY)
    value = persisted.value if persisted and isinstance(persisted.value, dict) else {}
    routing = clean_persisted_routing(value.get("routing")) or routing_engine.as_dict() or DEFAULT_ROUTING
    models = configured_model_ids(routing)
    caps = clean_persisted_model_caps(model_monthly_caps_usd(db), routing)
    if GROK_MODEL_ID in models and GROK_MODEL_ID not in caps:
        caps[GROK_MODEL_ID] = grok_monthly_cap_usd(db)
    return {
        "routing": routing,
        "configured_models": models,
        "enabled_models": clean_persisted_enabled_models(value.get("enabled_models", []), routing),
        "grok_monthly_cap_usd": grok_monthly_cap_usd(db),
        "grok_monthly_spend_usd": grok_monthly_spend_usd(db),
        "grok_pricing_usd_per_million_tokens": {
            "input": GROK_INPUT_USD_PER_MILLION_TOKENS,
            "output": GROK_OUTPUT_USD_PER_MILLION_TOKENS,
        },
        "model_monthly_caps_usd": caps,
        "model_monthly_spend_usd": model_monthly_spend_usd_by_model(db, models),
        "model_pricing_usd_per_million_tokens": MODEL_PRICING_USD_PER_MILLION_TOKENS,
    }


def apply_persisted_runtime_settings(db: Session) -> None:
    setting = db.get(Setting, RUNTIME_SETTINGS_KEY)
    value = setting.value if setting and isinstance(setting.value, dict) else {}
    routing = clean_persisted_routing(value.get("routing"))
    if routing is None:
        return
    routing_engine.roles = routing
    routing_engine.counters.clear()


@router.get("")
def get_settings(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthContext, Depends(require_user_token)],
) -> dict[str, Any]:
    return current_settings(db)


@router.put("")
def put_settings(
    payload: SettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthContext, Depends(require_user_token)],
) -> dict[str, Any]:
    current = current_settings(db)
    update: dict[str, Any] = {}
    if payload.routing is not None:
        try:
            update["routing"] = validate_routing(payload.routing)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    target_routing = update.get("routing", current["routing"])
    if payload.enabled_models is not None:
        try:
            update["enabled_models"] = clean_enabled_models(payload.enabled_models, target_routing)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    model_caps = clean_persisted_model_caps(current.get("model_monthly_caps_usd", {}), target_routing)
    if payload.model_monthly_caps_usd is not None:
        try:
            model_caps = clean_model_caps(payload.model_monthly_caps_usd, target_routing)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.grok_monthly_cap_usd is not None:
        model_caps[GROK_MODEL_ID] = payload.grok_monthly_cap_usd
    value = {
        "routing": current["routing"],
        "enabled_models": clean_persisted_enabled_models(current["enabled_models"], target_routing),
        "grok_monthly_cap_usd": model_caps.get(GROK_MODEL_ID, current["grok_monthly_cap_usd"]),
        "model_monthly_caps_usd": model_caps,
    }
    value.update(update)
    setting = db.get(Setting, RUNTIME_SETTINGS_KEY)
    if setting:
        setting.value = value
    else:
        db.add(Setting(key=RUNTIME_SETTINGS_KEY, value=value))
    if payload.routing is not None:
        routing_engine.roles = update["routing"]
        routing_engine.counters.clear()
    commit_write(db)
    return current_settings(db)

"""
Referee Config Resolver — per-project overrides > global defaults

Usage:
    config = get_referee_config(project_id)
    model = config["primary_model"]
"""
from typing import Optional
from app.config import settings


def get_referee_config(project_id: Optional[str] = None) -> dict:
    """Resolve referee config: per-project domain_config.referee > global settings."""
    defaults = {
        "primary_model": settings.referee_primary_model,
        "backup_model": settings.referee_backup_model,
        "triage_model": settings.referee_triage_model,
        "auto_decide_threshold": settings.referee_auto_decide_threshold,
        "human_confirm_threshold": settings.referee_human_confirm_threshold,
        "enable_dual_model": settings.referee_enable_dual_model,
        "enable_triple_model": settings.referee_enable_triple_model,
        "voting_temperature": settings.referee_voting_temperature,
        "consistency_samples": settings.referee_consistency_samples,
    }
    if not project_id:
        return defaults

    from app.db import crud
    project = crud.get_project(project_id)
    if not project:
        return defaults

    overrides = (project.get("domain_config") or {}).get("referee", {})
    return {**defaults, **overrides}

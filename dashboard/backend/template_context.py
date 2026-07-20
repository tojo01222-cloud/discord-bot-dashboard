"""
Ein Jinja2 "Context Processor": eine Funktion, die bei JEDEM Template-Rendern
automatisch mit ausgeführt wird und ihre Rückgabewerte in den Kontext
mischt. Damit müssen operator_username/operator_invite (für den
"Discord beitreten"-Link im Footer, siehe base.html) nicht in jeder
einzelnen Route manuell mitgegeben werden.
"""
from starlette.requests import Request

from dashboard.backend.config import dashboard_config as cfg


def global_template_context(request: Request) -> dict:
    return {
        "operator_username": cfg.OPERATOR_DISCORD_USERNAME,
        "operator_invite": cfg.OPERATOR_DISCORD_INVITE,
    }

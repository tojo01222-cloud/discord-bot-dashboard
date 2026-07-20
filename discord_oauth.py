"""
Einheitliches Embed-Design, damit alle Panels (Tickets, Warteraum,
Ankündigungen, Strafen usw.) gleich aussehen. Später im Dashboard
(Phase 8) pro Server anpassbar (Farben, Logo).
"""
import datetime as dt

import discord

COLOR_SUCCESS = discord.Color.green()
COLOR_ERROR = discord.Color.red()
COLOR_INFO = discord.Color.blurple()
COLOR_WARNING = discord.Color.orange()


def base_embed(title: str, description: str = "", color: discord.Color = COLOR_INFO) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color, timestamp=dt.datetime.utcnow())
    return embed


def success_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(f"✅ {title}", description, COLOR_SUCCESS)


def error_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(f"❌ {title}", description, COLOR_ERROR)


def warning_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(f"⚠️ {title}", description, COLOR_WARNING)

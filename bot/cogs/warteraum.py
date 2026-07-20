"""
Warteraum-System.

- /warteraum set <voice-kanal> <text-kanal>   -- legt Warteraum + Melde-Kanal fest (SERVER_ADMIN)
- /warteraum clear                             -- hebt die Einrichtung auf (SERVER_ADMIN)
- /warteraum status                            -- zeigt die aktuelle Einrichtung

Sobald jemand dem konfigurierten Sprachkanal (Warteraum) beitritt, sendet der
Bot automatisch eine Nachricht in den festgelegten Textkanal, dass diese
Person Hilfe braucht -- wie ursprünglich gewünscht. Ein Team-Mitglied kann
sich über den Button "Ich kümmere mich darum" als zuständig markieren, damit
nicht mehrere gleichzeitig antworten.

Bug-Fix: vorher löste JEDER Beitritt sofort eine Meldung aus -- wer schnell
den Kanal verlässt und wieder betritt (oder zwischen zwei Warteräumen hin-
und herwechselt), erzeugte Spam im Melde-Kanal. Jetzt gibt es einen kurzen
Cooldown pro User.
"""
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel, get_member_permission_level
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import get_guild_language, get_or_create_guild_settings, get_guild_settings_snapshot
from bot.database.db import get_session

NOTIFY_COOLDOWN_SECONDS = 30

# In-Memory-Cache (guild_id, user_id) -> Zeitstempel der letzten Meldung.
# Verhindert Spam im Melde-Kanal bei schnellem Verlassen/erneutem Beitreten.
_last_notify_time: dict[tuple[int, int], float] = {}


class WaitingRoomAckView(discord.ui.View):
    """Nicht-persistenter View (bewusst kein bot.add_view() nötig -- eine
    Warteraum-Meldung ist von Natur aus kurzlebig; nach einem Bot-Neustart
    ist der Button einfach nicht mehr klickbar, was für diesen Anwendungsfall
    unkritisch ist)."""

    def __init__(self, lang: str):
        super().__init__(timeout=1800)  # 30 Minuten, danach automatisch deaktiviert
        self.lang = lang
        self.claimed_by: int | None = None

    @discord.ui.button(label="Ich kümmere mich darum", emoji="🙋", style=discord.ButtonStyle.primary)
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if get_member_permission_level(interaction.user) < PermissionLevel.TEAM:
            await interaction.response.send_message(embed=error_embed(t("no_permission", self.lang)), ephemeral=True)
            return
        if self.claimed_by:
            await interaction.response.send_message(
                embed=error_embed(t("warteraum.already_claimed", self.lang, user=f"<@{self.claimed_by}>")),
                ephemeral=True)
            return

        self.claimed_by = interaction.user.id
        button.disabled = True
        button.label = t("warteraum.claimed_button", self.lang, user=interaction.user.display_name)
        await interaction.response.edit_message(view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


class Warteraum(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="warteraum", description="Warteraum-System verwalten.")
    @commands.guild_only()
    async def warteraum(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @warteraum.command(name="set", description="Legt den Warteraum-Sprachkanal und den Melde-Textkanal fest.")
    @app_commands.describe(voice="Der Sprachkanal, der als Warteraum dient",
                            text="Der Textkanal, in dem Meldungen erscheinen")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def warteraum_set(self, ctx: commands.Context, voice: discord.VoiceChannel, text: discord.TextChannel):
        lang = await get_guild_language(ctx.guild.id)
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, ctx.guild.id)
            settings.waiting_room_voice_channel_id = voice.id
            settings.waiting_room_notify_channel_id = text.id
            await session.commit()

        await ctx.send(embed=success_embed(t("warteraum.set", lang, voice=voice.mention, text=text.mention)))

    @warteraum.command(name="clear", description="Hebt die Warteraum-Einrichtung auf.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def warteraum_clear(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, ctx.guild.id)
            settings.waiting_room_voice_channel_id = 0
            settings.waiting_room_notify_channel_id = 0
            await session.commit()

        await ctx.send(embed=success_embed(t("warteraum.cleared", lang)))

    @warteraum.command(name="status", description="Zeigt die aktuelle Warteraum-Einrichtung.")
    async def warteraum_status(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        snapshot = await get_guild_settings_snapshot(ctx.guild.id)
        voice_id = snapshot["waiting_room_voice_channel_id"]
        text_id = snapshot["waiting_room_notify_channel_id"]

        if not voice_id or not text_id:
            await ctx.send(embed=error_embed(t("warteraum.not_configured", lang)))
            return

        voice = ctx.guild.get_channel(voice_id)
        text = ctx.guild.get_channel(text_id)
        embed = base_embed("🙋 Warteraum-Status" if lang == "de" else "🙋 Waiting room status")
        embed.add_field(name="Sprachkanal" if lang == "de" else "Voice channel",
                         value=voice.mention if voice else "⚠️ (gelöscht)", inline=True)
        embed.add_field(name="Melde-Kanal" if lang == "de" else "Notify channel",
                         value=text.mention if text else "⚠️ (gelöscht)", inline=True)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                     after: discord.VoiceState):
        if member.bot:
            return
        # Nur reagieren, wenn der Kanal NEU betreten wurde (nicht bei Stumm/Deaf-Änderungen
        # im selben Kanal, und nicht wenn jemand den Kanal nur verlässt).
        if after.channel is None or before.channel == after.channel:
            return

        guild = after.channel.guild
        snapshot = await get_guild_settings_snapshot(guild.id)
        waiting_room_id = snapshot["waiting_room_voice_channel_id"]
        notify_channel_id = snapshot["waiting_room_notify_channel_id"]
        lang = snapshot["language"]

        if not waiting_room_id or after.channel.id != waiting_room_id:
            return
        if not notify_channel_id:
            return

        # Bug-Fix: Spam-Schutz -- schnelles Verlassen/erneutes Beitreten löste
        # vorher jedes Mal eine neue Meldung aus.
        key = (guild.id, member.id)
        now = time.monotonic()
        last = _last_notify_time.get(key, 0)
        if now - last < NOTIFY_COOLDOWN_SECONDS:
            return
        _last_notify_time[key] = now

        notify_channel = guild.get_channel(notify_channel_id)
        if not notify_channel:
            return

        embed = base_embed("🙋 Warteraum" if lang == "de" else "🙋 Waiting room")
        custom_message = snapshot.get("waiting_room_message", "")
        if custom_message:
            embed.description = custom_message.replace("{user}", member.mention).replace(
                "{channel}", after.channel.mention)
        else:
            embed.description = t("warteraum.notify", lang, user=member.mention, channel=after.channel.mention)
        try:
            await notify_channel.send(embed=embed, view=WaitingRoomAckView(lang))
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Warteraum(bot))

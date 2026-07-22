"""
Willkommen/Abschied, Zeit-Autorole, Verifizierung.

- /willkommen kanal/nachricht        -- Begrüßungsnachricht einrichten (SERVER_ADMIN)
- /abschied kanal/nachricht           -- Abschiedsnachricht einrichten (SERVER_ADMIN)
- /zeitautorole add/liste/entfernen    -- Rolle nach X Tagen im Server automatisch vergeben
- /verifizierung on/off/kanal/rolle     -- Beitritts-Verifizierung per Button einrichten

Platzhalter in Willkommens-/Abschiedsnachricht: {user}, {server}, {membercount}.
Bleibt der Text leer, wird automatisch ein Standardtext mit Mitgliederzahl verwendet
(vorher wurde in diesem Fall fälschlich gar nichts gesendet).

Diese Systeme laufen unabhängig vom normalen Autorole-Cog (bot/cogs/autorole.py) --
das hier ergänzt, ersetzt nichts.
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed
from bot.utils.db_helpers import (
    get_guild_language,
    get_welcome_config,
    set_welcome_config,
    add_timed_autorole,
    get_timed_autoroles,
    get_all_timed_autoroles,
    remove_timed_autorole,
    get_verification_config,
    set_verification_config,
)

VERIFY_CUSTOM_ID = "verify_button"


class VerifyView(discord.ui.View):
    """Persistent View (timeout=None), damit der Button auch nach einem
    Bot-Neustart weiterhin funktioniert -- siehe cog_load()."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, custom_id=VERIFY_CUSTOM_ID)
    async def verify(self, interaction: discord.Interaction, _button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user
        lang = await get_guild_language(guild.id)
        cfg = await get_verification_config(guild.id)

        if not cfg.verified_role_id:
            await interaction.response.send_message(
                embed=error_embed("Keine Verifizierungs-Rolle eingerichtet." if lang == "de"
                                   else "No verification role configured."), ephemeral=True)
            return

        role = guild.get_role(cfg.verified_role_id)
        if not role:
            await interaction.response.send_message(
                embed=error_embed("Die Verifizierungs-Rolle existiert nicht mehr." if lang == "de"
                                   else "The verification role no longer exists."), ephemeral=True)
            return

        if role in member.roles:
            await interaction.response.send_message(
                embed=success_embed("Du bist bereits verifiziert." if lang == "de" else "You're already verified."),
                ephemeral=True)
            return

        try:
            await member.add_roles(role, reason="Verifizierung bestanden")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Ich kann dir die Rolle nicht geben (Berechtigung/Hierarchie)." if lang == "de"
                                   else "I can't give you the role (permission/hierarchy)."), ephemeral=True)
            return

        await interaction.response.send_message(
            embed=success_embed("✅ Verifiziert! Willkommen." if lang == "de" else "✅ Verified! Welcome."),
            ephemeral=True)


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(VerifyView())
        self._timed_autorole_loop.start()

    def cog_unload(self) -> None:
        self._timed_autorole_loop.cancel()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        lang = await get_guild_language(guild.id)
        cfg = await get_welcome_config(guild.id)

        # Bug behoben: vorher wurde NICHTS gesendet, wenn kein eigener Text
        # eingetragen war -- jetzt reicht ein ausgewählter Kanal, ein
        # sinnvoller Standardtext (inkl. Mitgliederzahl) springt sonst ein.
        if cfg.welcome_channel_id:
            channel = guild.get_channel(cfg.welcome_channel_id)
            if channel:
                if cfg.welcome_message:
                    text = (cfg.welcome_message
                            .replace("{user}", member.mention)
                            .replace("{server}", guild.name)
                            .replace("{membercount}", str(guild.member_count)))
                else:
                    text = (f"👋 Willkommen auf **{guild.name}**, {member.mention}! "
                            f"Wir haben jetzt **{guild.member_count}** Mitglieder." if lang == "de" else
                            f"👋 Welcome to **{guild.name}**, {member.mention}! "
                            f"We now have **{guild.member_count}** members.")
                embed = discord.Embed(description=text, color=discord.Color.green())
                embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

        verify_cfg = await get_verification_config(guild.id)
        if verify_cfg.enabled and verify_cfg.channel_id:
            channel = guild.get_channel(verify_cfg.channel_id)
            if channel:
                embed = success_embed(
                    "Willkommen! Bitte verifizieren" if lang == "de" else "Welcome! Please verify",
                    (f"{member.mention}, klick auf den Button, um Zugriff auf den Server zu bekommen."
                     if lang == "de" else
                     f"{member.mention}, click the button to get access to the server."),
                )
                try:
                    await channel.send(embed=embed, view=VerifyView())
                except discord.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        lang = await get_guild_language(guild.id)
        cfg = await get_welcome_config(guild.id)
        if cfg.leave_channel_id:
            channel = guild.get_channel(cfg.leave_channel_id)
            if channel:
                if cfg.leave_message:
                    text = (cfg.leave_message
                            .replace("{user}", str(member))
                            .replace("{server}", guild.name)
                            .replace("{membercount}", str(guild.member_count)))
                else:
                    text = (f"👋 **{member}** hat den Server verlassen. Wir sind jetzt **{guild.member_count}** Mitglieder."
                            if lang == "de" else
                            f"👋 **{member}** left the server. We're now **{guild.member_count}** members.")
                embed = discord.Embed(description=text, color=discord.Color.red())
                embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    @tasks.loop(hours=1)
    async def _timed_autorole_loop(self) -> None:
        """Prüft stündlich alle Zeit-Autorole-Einträge gegen die tatsächliche
        Mitgliedschaftsdauer (member.joined_at) und vergibt die Rolle, falls
        die Wartezeit erreicht ist und die Person sie noch nicht hat."""
        import datetime as dt
        entries = await get_all_timed_autoroles()
        by_guild: dict[int, list] = {}
        for e in entries:
            by_guild.setdefault(e.guild_id, []).append(e)

        for guild_id, guild_entries in by_guild.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            now = dt.datetime.now(dt.timezone.utc)
            for member in guild.members:
                if member.bot or not member.joined_at:
                    continue
                days_in_guild = (now - member.joined_at).days
                for entry in guild_entries:
                    if days_in_guild < entry.days_required:
                        continue
                    role = guild.get_role(entry.role_id)
                    if not role or role in member.roles:
                        continue
                    try:
                        await member.add_roles(role, reason=f"Zeit-Autorole ({entry.days_required} Tage erreicht)")
                    except discord.Forbidden:
                        pass

    @_timed_autorole_loop.before_loop
    async def _before_timed_autorole(self) -> None:
        await self.bot.wait_until_ready()

    # ---------- Befehle ----------

    @commands.hybrid_group(name="willkommen", description="Begrüßungsnachricht verwalten.")
    @commands.guild_only()
    async def willkommen(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @willkommen.command(name="kanal", description="Legt den Kanal für Begrüßungsnachrichten fest.")
    @app_commands.describe(kanal="Der Zielkanal")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def willkommen_kanal(self, ctx: commands.Context, kanal: discord.TextChannel):
        await set_welcome_config(ctx.guild.id, welcome_channel_id=kanal.id)
        await ctx.send(embed=success_embed(f"Willkommens-Kanal auf {kanal.mention} gesetzt."))

    @willkommen.command(name="nachricht", description="Legt den Begrüßungstext fest ({user}, {server}, {membercount} als Platzhalter).")
    @app_commands.describe(text="Der Begrüßungstext")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def willkommen_nachricht(self, ctx: commands.Context, *, text: str):
        await set_welcome_config(ctx.guild.id, welcome_message=text)
        await ctx.send(embed=success_embed("Begrüßungstext gespeichert."))

    @commands.hybrid_group(name="abschied", description="Abschiedsnachricht verwalten.")
    @commands.guild_only()
    async def abschied(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @abschied.command(name="kanal", description="Legt den Kanal für Abschiedsnachrichten fest.")
    @app_commands.describe(kanal="Der Zielkanal")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def abschied_kanal(self, ctx: commands.Context, kanal: discord.TextChannel):
        await set_welcome_config(ctx.guild.id, leave_channel_id=kanal.id)
        await ctx.send(embed=success_embed(f"Abschieds-Kanal auf {kanal.mention} gesetzt."))

    @abschied.command(name="nachricht", description="Legt den Abschiedstext fest ({user}, {server}, {membercount} als Platzhalter).")
    @app_commands.describe(text="Der Abschiedstext")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def abschied_nachricht(self, ctx: commands.Context, *, text: str):
        await set_welcome_config(ctx.guild.id, leave_message=text)
        await ctx.send(embed=success_embed("Abschiedstext gespeichert."))

    @commands.hybrid_group(name="zeitautorole", description="Rolle nach X Tagen Mitgliedschaft automatisch vergeben.")
    @commands.guild_only()
    async def zeitautorole(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @zeitautorole.command(name="add", description="Fügt eine Zeit-Autorole hinzu.")
    @app_commands.describe(rolle="Die Rolle", tage="Nach wie vielen Tagen im Server")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def zeitautorole_add(self, ctx: commands.Context, rolle: discord.Role, tage: int):
        if tage < 1:
            await ctx.send(embed=error_embed("Die Anzahl Tage muss mindestens 1 sein."))
            return
        await add_timed_autorole(ctx.guild.id, rolle.id, tage)
        await ctx.send(embed=success_embed(f"{rolle.mention} wird nach {tage} Tagen automatisch vergeben."))

    @zeitautorole.command(name="liste", description="Zeigt alle eingerichteten Zeit-Autoroles.")
    async def zeitautorole_liste(self, ctx: commands.Context):
        entries = await get_timed_autoroles(ctx.guild.id)
        if not entries:
            await ctx.send(embed=error_embed("Keine Zeit-Autoroles eingerichtet."))
            return
        lines = [f"#{e.id} — <@&{e.role_id}> nach {e.days_required} Tagen" for e in entries]
        await ctx.send(embed=success_embed("⏳ Zeit-Autoroles", "\n".join(lines)))

    @zeitautorole.command(name="entfernen", description="Entfernt eine Zeit-Autorole.")
    @app_commands.describe(entry_id="Die ID aus /zeitautorole liste")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def zeitautorole_entfernen(self, ctx: commands.Context, entry_id: int):
        ok = await remove_timed_autorole(entry_id)
        await ctx.send(embed=success_embed("Entfernt.") if ok else error_embed("ID nicht gefunden."))

    @commands.hybrid_group(name="verifizierung", description="Beitritts-Verifizierung verwalten.")
    @commands.guild_only()
    async def verifizierung(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @verifizierung.command(name="on", description="Aktiviert die Verifizierung.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def verifizierung_on(self, ctx: commands.Context):
        await set_verification_config(ctx.guild.id, enabled=True)
        await ctx.send(embed=success_embed("✅ Verifizierung aktiviert."))

    @verifizierung.command(name="off", description="Deaktiviert die Verifizierung.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def verifizierung_off(self, ctx: commands.Context):
        await set_verification_config(ctx.guild.id, enabled=False)
        await ctx.send(embed=success_embed("Verifizierung deaktiviert."))

    @verifizierung.command(name="kanal", description="Legt den Kanal für den Verifizierungs-Button fest.")
    @app_commands.describe(kanal="Der Zielkanal")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def verifizierung_kanal(self, ctx: commands.Context, kanal: discord.TextChannel):
        await set_verification_config(ctx.guild.id, channel_id=kanal.id)
        await ctx.send(embed=success_embed(f"Verifizierungs-Kanal auf {kanal.mention} gesetzt."))

    @verifizierung.command(name="rolle", description="Legt die Rolle fest, die nach Verifizierung vergeben wird.")
    @app_commands.describe(rolle="Die Rolle")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def verifizierung_rolle(self, ctx: commands.Context, rolle: discord.Role):
        await set_verification_config(ctx.guild.id, verified_role_id=rolle.id)
        await ctx.send(embed=success_embed(f"Verifizierungs-Rolle auf {rolle.mention} gesetzt."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))

"""
Utility- und Moderations-Werkzeuge.

- /slowmode <sekunden>            -- setzt Slowmode für den aktuellen Kanal (0 = aus)
- /lock                            -- sperrt den aktuellen Kanal für @everyone (keine Nachrichten)
- /unlock                          -- hebt die Sperre wieder auf
- /nickname <member> [name]        -- ändert den Spitznamen eines Mitglieds (leer = zurücksetzen)
- /afk [grund]                     -- markiert dich als abwesend; wird automatisch entfernt, sobald
                                       du wieder schreibst, und andere werden informiert, wenn sie
                                       dich währenddessen erwähnen

AFK-Status ist bewusst NUR im Arbeitsspeicher (kein Datenbank-Zugriff bei
jeder Nachricht nötig -- siehe Lektion aus dem Anti-Spam-Bug: reine
Dictionary-Lookups sind hier völlig ausreichend und praktisch kostenlos).
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed
from bot.utils.db_helpers import get_guild_language

# (guild_id, user_id) -> Grund. Rein im Arbeitsspeicher, siehe Docstring oben.
_afk_users: dict[tuple[int, int], str] = {}

MAX_SLOWMODE_SECONDS = 21600  # Discords eigenes Maximum (6 Stunden)


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="slowmode", description="Setzt das Slowmode-Intervall für diesen Kanal (0 = aus).")
    @app_commands.describe(sekunden="Sekunden zwischen Nachrichten pro User (0-21600, 0 = aus)")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def slowmode(self, ctx: commands.Context, sekunden: int):
        lang = await get_guild_language(ctx.guild.id)
        if sekunden < 0 or sekunden > MAX_SLOWMODE_SECONDS:
            await ctx.send(embed=error_embed(
                f"Wert muss zwischen 0 und {MAX_SLOWMODE_SECONDS} liegen." if lang == "de"
                else f"Value must be between 0 and {MAX_SLOWMODE_SECONDS}."))
            return

        try:
            await ctx.channel.edit(slowmode_delay=sekunden)
        except discord.Forbidden:
            await ctx.send(embed=error_embed(
                "Mir fehlt die Berechtigung 'Kanäle verwalten'." if lang == "de"
                else "I'm missing the 'Manage Channels' permission."))
            return

        if sekunden == 0:
            text = "Slowmode deaktiviert." if lang == "de" else "Slowmode disabled."
        else:
            text = (f"Slowmode auf {sekunden}s gesetzt." if lang == "de"
                    else f"Slowmode set to {sekunden}s.")
        await ctx.send(embed=success_embed(text))

    @commands.hybrid_command(name="lock", description="Sperrt den aktuellen Kanal für @everyone.")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def lock(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite,
                                               reason=f"/lock von {ctx.author}")
        except discord.Forbidden:
            await ctx.send(embed=error_embed(
                "Mir fehlt die Berechtigung 'Kanäle verwalten'." if lang == "de"
                else "I'm missing the 'Manage Channels' permission."))
            return
        await ctx.send(embed=success_embed(
            "🔒 Kanal gesperrt." if lang == "de" else "🔒 Channel locked."))

    @commands.hybrid_command(name="unlock", description="Hebt die Sperre des aktuellen Kanals wieder auf.")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def unlock(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None  # zurück auf Server-Standard, statt explizit zu erlauben
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite,
                                               reason=f"/unlock von {ctx.author}")
        except discord.Forbidden:
            await ctx.send(embed=error_embed(
                "Mir fehlt die Berechtigung 'Kanäle verwalten'." if lang == "de"
                else "I'm missing the 'Manage Channels' permission."))
            return
        await ctx.send(embed=success_embed(
            "🔓 Kanal entsperrt." if lang == "de" else "🔓 Channel unlocked."))

    @commands.hybrid_command(name="nickname", description="Ändert den Spitznamen eines Mitglieds.")
    @app_commands.describe(member="Das Mitglied", name="Neuer Spitzname (leer lassen zum Zurücksetzen)")
    @commands.guild_only()
    @require_level(PermissionLevel.MODERATOR)
    async def nickname(self, ctx: commands.Context, member: discord.Member, *, name: str = None):
        lang = await get_guild_language(ctx.guild.id)
        try:
            await member.edit(nick=name, reason=f"/nickname von {ctx.author}")
        except discord.Forbidden:
            await ctx.send(embed=error_embed(
                "Ich kann den Spitznamen dieses Mitglieds nicht ändern (höhere Rolle oder fehlende "
                "Berechtigung)." if lang == "de" else
                "I can't change this member's nickname (higher role or missing permission)."))
            return

        if name:
            text = (f"Spitzname von {member.mention} auf **{name}** gesetzt." if lang == "de"
                    else f"{member.mention}'s nickname set to **{name}**.")
        else:
            text = (f"Spitzname von {member.mention} zurückgesetzt." if lang == "de"
                    else f"{member.mention}'s nickname reset.")
        await ctx.send(embed=success_embed(text))

    @commands.hybrid_command(name="afk", description="Markiert dich als abwesend (AFK).")
    @app_commands.describe(grund="Optional: Grund für deine Abwesenheit")
    @commands.guild_only()
    async def afk(self, ctx: commands.Context, *, grund: str = "AFK"):
        lang = await get_guild_language(ctx.guild.id)
        _afk_users[(ctx.guild.id, ctx.author.id)] = grund
        await ctx.send(embed=success_embed(
            f"Du bist jetzt als abwesend markiert: {grund}" if lang == "de"
            else f"You're now marked as AFK: {grund}"))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Eigener AFK-Status wird durch die nächste eigene Nachricht automatisch entfernt.
        own_key = (message.guild.id, message.author.id)
        if own_key in _afk_users:
            del _afk_users[own_key]
            try:
                await message.channel.send(
                    f"👋 Willkommen zurück, {message.author.mention}! Dein AFK-Status wurde entfernt.",
                    delete_after=6,
                )
            except discord.Forbidden:
                pass

        # Wird ein AFK-User erwähnt, kurz darauf hinweisen.
        for mentioned in message.mentions:
            key = (message.guild.id, mentioned.id)
            if key in _afk_users:
                try:
                    await message.channel.send(
                        f"💤 {mentioned.display_name} ist gerade AFK: {_afk_users[key]}",
                        delete_after=8,
                    )
                except discord.Forbidden:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))

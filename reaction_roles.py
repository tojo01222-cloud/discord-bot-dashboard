"""
Ticket-System (neu, vereinfacht).

- /ticketpanel setup <name> <beschreibung> <farbe> [kategorie]  -- legt ein neues
                                             Ticket-Panel an (SERVER_ADMIN). Farbe:
                                             Standard, Premium, VIP oder Schwarz.
- /ticketpanel senden <panel_id> <kanal>    -- sendet ein angelegtes Panel in einen
                                             Kanal (SERVER_ADMIN)
- /ticketpanel entfernen <panel_id>          -- löscht ein Panel wieder (SERVER_ADMIN)
- /ticketpanel liste                          -- zeigt alle Panels dieses Servers
- /ticketclose                                -- schließt das aktuelle Ticket (TEAM, oder der Ersteller)
- /ticketclaim                                -- ein Team-Mitglied übernimmt das Ticket sichtbar (TEAM)

Jedes Panel hat genau EINEN "Ticket erstellen"-Button (kein Auswahlmenü mehr) --
dafür lassen sich beliebig viele verschiedene Panels anlegen und in
unterschiedliche Kanäle senden. Die Buttons sind persistent (überleben einen
Bot-Neustart) über einen generischen on_interaction-Dispatcher, der anhand des
custom_id-Präfixes (TICKET_PANEL_PREFIX + panel_id) erkennt, für welches Panel
geklickt wurde -- funktioniert auch für neu angelegte Panels ohne Bot-Neustart.
"""
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel, get_member_permission_level
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import (
    get_guild_language,
    get_or_create_guild_settings,
    get_open_ticket_for_user,
    create_ticket,
    get_ticket_by_channel,
    close_ticket,
    claim_ticket,
    get_team_ranks,
    create_ticket_panel,
    get_ticket_panels,
    get_ticket_panel,
    delete_ticket_panel,
)
from bot.database.db import get_session
from bot.database.models import TicketPanel

TICKET_CLOSE_CUSTOM_ID = "ticket_close_button"
TICKET_DELETE_CUSTOM_ID = "ticket_delete_button"
TICKET_PANEL_PREFIX = "ticket_panel_create_"  # + panel_id, siehe on_interaction-Dispatcher

# Feste Farb-Vorlagen, wie gewünscht: Standard, Premium, VIP, Schwarz.
COLOR_CHOICES = {
    "standard": {"color": discord.Color.blurple(), "emoji": "🎫", "label": "Standard"},
    "premium": {"color": discord.Color.gold(), "emoji": "⭐", "label": "Premium"},
    "vip": {"color": discord.Color.purple(), "emoji": "💎", "label": "VIP"},
    "schwarz": {"color": discord.Color.from_rgb(20, 20, 24), "emoji": "🖤", "label": "Schwarz"},
}


def _build_panel_embed(panel: TicketPanel, lang: str) -> discord.Embed:
    style = COLOR_CHOICES.get(panel.color, COLOR_CHOICES["standard"])
    embed = discord.Embed(
        title=f"{style['emoji']} {panel.name}",
        description=panel.description or t("ticket.panel_desc", lang),
        color=style["color"],
    )
    embed.set_footer(text="Support-Team" if lang == "de" else "Support Team")
    return embed


class TicketCloseView(discord.ui.View):
    """Persistenter View für den 'Ticket schließen'-Button innerhalb eines Ticket-Kanals."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket schließen", emoji="🔒", style=discord.ButtonStyle.danger,
                        custom_id=TICKET_CLOSE_CUSTOM_ID)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_close_ticket(interaction)


class TicketClosedView(discord.ui.View):
    """Persistenter View mit dem 'Ticket löschen'-Button, der nach dem Schließen
    angezeigt wird (nur Team-Mitglieder, siehe _handle_delete_ticket)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket löschen", emoji="🗑️", style=discord.ButtonStyle.danger,
                        custom_id=TICKET_DELETE_CUSTOM_ID)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_delete_ticket(interaction)


async def _handle_create_ticket(interaction: discord.Interaction, panel: TicketPanel) -> None:
    guild = interaction.guild
    member = interaction.user
    lang = await get_guild_language(guild.id)

    existing = await get_open_ticket_for_user(guild.id, member.id)
    if existing:
        channel = guild.get_channel(existing.channel_id)
        if channel:
            await interaction.response.send_message(
                embed=error_embed(t("ticket.already_open", lang, channel=channel.mention)),
                ephemeral=True,
            )
            return

    await interaction.response.defer(ephemeral=True)

    discord_category = guild.get_channel(panel.category_id) if panel.category_id else None
    if discord_category and not isinstance(discord_category, discord.CategoryChannel):
        discord_category = None
    if not discord_category:
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, guild.id)
        discord_category = guild.get_channel(settings.ticket_category_id) if settings.ticket_category_id else None
        if discord_category and not isinstance(discord_category, discord.CategoryChannel):
            discord_category = None

    ranks = await get_team_ranks(guild.id)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    for rank in ranks:
        role = guild.get_role(rank.role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    # Kanalnamen von Discord-unzulässigen/verwirrenden Zeichen befreien, statt
    # blind zu vertrauen, dass jeder Anzeigename schon kanaltauglich ist.
    safe_username = "".join(c for c in member.name.lower() if c.isalnum() or c in "-_") or "user"
    safe_prefix = "".join(c for c in panel.name.lower().replace(" ", "-") if c.isalnum() or c == "-") or "ticket"
    channel_name = f"{safe_prefix}-{safe_username}"[:90]

    try:
        ticket_channel = await guild.create_text_channel(
            name=channel_name, category=discord_category, overwrites=overwrites,
            reason=f"Ticket erstellt von {member} (Panel: {panel.name})",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            embed=error_embed("Mir fehlt die Berechtigung, einen Kanal zu erstellen." if lang == "de"
                               else "I'm missing permission to create a channel."),
            ephemeral=True,
        )
        return

    await create_ticket(guild.id, ticket_channel.id, member.id, design=panel.color, category_id=panel.id)

    style = COLOR_CHOICES.get(panel.color, COLOR_CHOICES["standard"])
    desc = f"**{panel.name}**: {panel.description}\n\n{t('ticket.welcome_desc', lang)}" if panel.description \
        else t("ticket.welcome_desc", lang)
    welcome = discord.Embed(
        title=f"{style['emoji']} {t('ticket.welcome_title', lang, user=member.display_name)}",
        description=desc,
        color=style["color"],
    )

    await ticket_channel.send(content=member.mention, embed=welcome, view=TicketCloseView())
    await interaction.followup.send(
        embed=success_embed(t("ticket.created", lang, channel=ticket_channel.mention)),
        ephemeral=True,
    )


async def _lock_ticket_channel(guild: discord.Guild, channel: discord.TextChannel, creator_id: int) -> None:
    """Sperrt den Kanal für den Ersteller (weiter sichtbar, aber nicht mehr
    beschreibbar) und benennt ihn um. Gemeinsame Logik für BEIDE Schließ-Wege
    (Button und /ticketclose) -- vorher wich der Slash-Befehl hiervon ab und
    ließ den Ersteller in einem 'geschlossenen' Ticket weiterschreiben."""
    try:
        creator = guild.get_member(creator_id)
        if creator and creator in channel.overwrites:
            await channel.set_permissions(creator, view_channel=True, send_messages=False)
        if not channel.name.startswith("closed-"):
            await channel.edit(name=f"closed-{channel.name}"[:90])
    except discord.Forbidden:
        pass


async def _handle_close_ticket(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel = interaction.channel
    lang = await get_guild_language(guild.id)

    ticket = await get_ticket_by_channel(channel.id)
    if not ticket:
        await interaction.response.send_message(embed=error_embed(t("ticket.not_a_ticket", lang)), ephemeral=True)
        return
    if ticket.status == "closed":
        await interaction.response.send_message(embed=error_embed(t("ticket.reopen_not_allowed", lang)), ephemeral=True)
        return

    await interaction.response.send_message(
        embed=success_embed(t("ticket.closed", lang, user=interaction.user.mention)),
        view=TicketClosedView(),
    )
    await close_ticket(channel.id, claimed_by=interaction.user.id)
    await _lock_ticket_channel(guild, channel, ticket.creator_id)


async def _handle_delete_ticket(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel = interaction.channel
    lang = await get_guild_language(guild.id)

    level = get_member_permission_level(interaction.user) if isinstance(interaction.user, discord.Member) \
        else PermissionLevel.EVERYONE
    if level < PermissionLevel.TEAM:
        await interaction.response.send_message(embed=error_embed(t("no_permission", lang)), ephemeral=True)
        return

    ticket = await get_ticket_by_channel(channel.id)
    if not ticket:
        await interaction.response.send_message(embed=error_embed(t("ticket.not_a_ticket", lang)), ephemeral=True)
        return

    await interaction.response.send_message(embed=base_embed(t("ticket.deleted", lang)))
    await asyncio.sleep(5)
    try:
        await channel.delete(reason=f"Ticket gelöscht von {interaction.user}")
    except discord.Forbidden:
        pass


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        # Persistente Views für Schließen/Löschen registrieren, damit sie nach
        # einem Bot-Neustart weiter funktionieren. Die Panel-"Ticket erstellen"-
        # Buttons brauchen KEINE registrierte View-Instanz -- sie werden über
        # den generischen on_interaction-Dispatcher unten behandelt, der anhand
        # des custom_id-Präfixes (TICKET_PANEL_PREFIX + panel_id) erkennt, für
        # welches Panel geklickt wurde. Das funktioniert auch für neu erstellte
        # Panels, ohne dass der Bot bei jedem neuen Panel neu gestartet werden müsste.
        self.bot.add_view(TicketCloseView())
        self.bot.add_view(TicketClosedView())

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith(TICKET_PANEL_PREFIX):
            return
        try:
            panel_id = int(custom_id[len(TICKET_PANEL_PREFIX):])
        except ValueError:
            return
        panel = await get_ticket_panel(panel_id)
        if panel is None:
            lang = await get_guild_language(interaction.guild.id)
            await interaction.response.send_message(
                embed=error_embed("Dieses Panel existiert nicht mehr." if lang == "de"
                                   else "This panel no longer exists."), ephemeral=True)
            return
        await _handle_create_ticket(interaction, panel)

    # ---------- Ticket-Panel (neu, vereinfacht: 4 Befehle) ----------
    @commands.hybrid_group(name="ticketpanel", description="Ticket-Panels verwalten.")
    @commands.guild_only()
    async def ticketpanel(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ticketpanel.command(name="setup", description="Legt ein neues Ticket-Panel an.")
    @app_commands.describe(
        name="Name des Panels (erscheint als Titel)", beschreibung="Kurze Beschreibung",
        farbe="Standard, Premium, VIP oder Schwarz", kategorie="Discord-Kanalkategorie für neue Ticket-Kanäle",
    )
    @app_commands.choices(farbe=[
        app_commands.Choice(name="Standard", value="standard"),
        app_commands.Choice(name="Premium", value="premium"),
        app_commands.Choice(name="VIP", value="vip"),
        app_commands.Choice(name="Schwarz", value="schwarz"),
    ])
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def ticketpanel_setup(self, ctx: commands.Context, name: str, beschreibung: str,
                                 farbe: str, kategorie: discord.CategoryChannel = None):
        lang = await get_guild_language(ctx.guild.id)
        panel = await create_ticket_panel(
            ctx.guild.id, name, beschreibung, farbe, kategorie.id if kategorie else 0, ctx.author.id,
        )
        await ctx.send(embed=success_embed(
            f"✅ Panel #{panel.id} „{name}“ angelegt." if lang == "de" else f"✅ Panel #{panel.id} \"{name}\" created."))

    @ticketpanel.command(name="senden", description="Sendet ein Ticket-Panel in einen Kanal.")
    @app_commands.describe(panel_id="Die Panel-ID aus /ticketpanel liste", kanal="Zielkanal")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def ticketpanel_senden(self, ctx: commands.Context, panel_id: int, kanal: discord.TextChannel):
        lang = await get_guild_language(ctx.guild.id)
        panel = await get_ticket_panel(panel_id)
        if panel is None or panel.guild_id != ctx.guild.id:
            await ctx.send(embed=error_embed("Panel nicht gefunden." if lang == "de" else "Panel not found."))
            return

        style = COLOR_CHOICES.get(panel.color, COLOR_CHOICES["standard"])
        embed = _build_panel_embed(panel, lang)
        view = discord.ui.View(timeout=None)
        button = discord.ui.Button(
            label="Ticket erstellen" if lang == "de" else "Create ticket", emoji=style["emoji"],
            style=discord.ButtonStyle.primary, custom_id=f"{TICKET_PANEL_PREFIX}{panel.id}",
        )
        view.add_item(button)
        try:
            await kanal.send(embed=embed, view=view)
        except discord.Forbidden:
            await ctx.send(embed=error_embed("Ich kann in diesem Kanal nicht senden." if lang == "de"
                                              else "I can't send in that channel."))
            return
        await ctx.send(embed=success_embed(f"📨 Panel in {kanal.mention} gesendet."))

    @ticketpanel.command(name="entfernen", description="Löscht ein Ticket-Panel (bestehende Tickets bleiben unberührt).")
    @app_commands.describe(panel_id="Die Panel-ID aus /ticketpanel liste")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def ticketpanel_entfernen(self, ctx: commands.Context, panel_id: int):
        lang = await get_guild_language(ctx.guild.id)
        ok = await delete_ticket_panel(panel_id)
        await ctx.send(embed=success_embed("Panel gelöscht." if lang == "de" else "Panel deleted.") if ok
                        else error_embed("Panel nicht gefunden." if lang == "de" else "Panel not found."))

    @ticketpanel.command(name="liste", description="Zeigt alle Ticket-Panels dieses Servers.")
    async def ticketpanel_liste(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        panels = await get_ticket_panels(ctx.guild.id)
        if not panels:
            await ctx.send(embed=error_embed("Noch keine Panels angelegt." if lang == "de" else "No panels yet."))
            return
        lines = []
        for p in panels:
            style = COLOR_CHOICES.get(p.color, COLOR_CHOICES["standard"])
            lines.append(f"#{p.id} {style['emoji']} **{p.name}** ({style['label']})")
        await ctx.send(embed=base_embed("🎫 Ticket-Panels", "\n".join(lines)))

    @commands.hybrid_command(name="ticketclose", description="Schließt das aktuelle Ticket.")
    @commands.guild_only()
    async def ticketclose(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        ticket = await get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            await ctx.send(embed=error_embed(t("ticket.not_a_ticket", lang)))
            return
        if ticket.status == "closed":
            await ctx.send(embed=error_embed(t("ticket.reopen_not_allowed", lang)))
            return

        # Nur der Ersteller oder Team-Mitglieder dürfen schließen.
        level = get_member_permission_level(ctx.author)
        if ctx.author.id != ticket.creator_id and level < PermissionLevel.TEAM:
            await ctx.send(embed=error_embed(t("no_permission", lang)))
            return

        await close_ticket(ctx.channel.id, claimed_by=ctx.author.id)
        await ctx.send(embed=success_embed(t("ticket.closed", lang, user=ctx.author.mention)),
                        view=TicketClosedView())
        # Vorher wich dieser Befehl vom Button-Weg ab und sperrte den Kanal für
        # den Ersteller NICHT -- jetzt identisches Verhalten über die gemeinsame
        # Hilfsfunktion (siehe _lock_ticket_channel Docstring).
        await _lock_ticket_channel(ctx.guild, ctx.channel, ticket.creator_id)

    @commands.hybrid_command(name="ticketclaim", description="Beansprucht das aktuelle Ticket für dich als Bearbeiter.")
    @commands.guild_only()
    @require_level(PermissionLevel.TEAM)
    async def ticketclaim(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        ticket = await get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            await ctx.send(embed=error_embed(t("ticket.not_a_ticket", lang)))
            return
        if ticket.claimed_by:
            await ctx.send(embed=error_embed(t("ticket.already_claimed", lang, user=f"<@{ticket.claimed_by}>")))
            return

        await claim_ticket(ctx.channel.id, ctx.author.id)
        await ctx.send(embed=success_embed(t("ticket.claimed", lang, user=ctx.author.mention)))
        try:
            await ctx.channel.edit(topic=t("ticket.claimed_topic", lang, user=str(ctx.author)))
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))

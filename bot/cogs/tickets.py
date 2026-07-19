"""
Ticket-System.

- /ticketpanel send <kanal> [design]   -- sendet ein Ticket-Panel mit Button (SERVER_ADMIN)
- /ticketkategorie set <kategorie>      -- legt fest, in welcher Kategorie neue Ticket-Kanäle
                                            entstehen (SERVER_ADMIN)
- /ticketclose                          -- schließt das aktuelle Ticket (TEAM, oder der Ersteller)

Buttons sind "persistent" (überleben einen Bot-Neustart) -- dafür registriert
cog_load() diese Views einmal über bot.add_view(...).

Drei Designs für das Panel (visuell unterschiedlich, gleiche Funktion):
  standard -> Blurple, klassisch
  minimal  -> schlicht, ohne Extra-Felder
  premium  -> Gold, mit zusätzlichem "Was du erwarten kannst"-Feld
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel, get_member_permission_level
from bot.utils.embeds import success_embed, error_embed
from bot.utils.i18n import t
from bot.utils.db_helpers import (
    get_guild_language,
    get_or_create_guild_settings,
    get_open_ticket_for_user,
    create_ticket,
    get_ticket_by_channel,
    close_ticket,
    get_team_ranks,
)
from bot.database.db import get_session

TICKET_CREATE_CUSTOM_ID = "ticket_create_button"
TICKET_CLOSE_CUSTOM_ID = "ticket_close_button"

DESIGNS = {
    "standard": {"color": discord.Color.blurple(), "emoji": "🎫"},
    "minimal": {"color": discord.Color.light_grey(), "emoji": "✉️"},
    "premium": {"color": discord.Color.gold(), "emoji": "⭐"},
}


def _build_panel_embed(lang: str, design: str) -> discord.Embed:
    style = DESIGNS.get(design, DESIGNS["standard"])
    embed = discord.Embed(
        title=f"{style['emoji']} {t('ticket.panel_title', lang)}",
        description=t("ticket.panel_desc", lang),
        color=style["color"],
    )
    if design == "premium":
        embed.add_field(
            name="Was dich erwartet" if lang == "de" else "What to expect",
            value="Ein privater Kanal nur für dich und unser Team." if lang == "de"
            else "A private channel just for you and our team.",
            inline=False,
        )
    return embed


class TicketPanelView(discord.ui.View):
    """Persistenter View für den 'Ticket erstellen'-Button im Panel."""

    def __init__(self, design: str = "standard"):
        super().__init__(timeout=None)
        self.design = design

    @discord.ui.button(label="Ticket erstellen", emoji="🎫", style=discord.ButtonStyle.primary,
                        custom_id=TICKET_CREATE_CUSTOM_ID)
    async def create_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_create_ticket(interaction, self.design)


class TicketCloseView(discord.ui.View):
    """Persistenter View für den 'Ticket schließen'-Button innerhalb eines Ticket-Kanals."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket schließen", emoji="🔒", style=discord.ButtonStyle.danger,
                        custom_id=TICKET_CLOSE_CUSTOM_ID)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_close_ticket(interaction)


async def _handle_create_ticket(interaction: discord.Interaction, design: str = "standard") -> None:
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

    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild.id)
        category_id = settings.ticket_category_id

    category = guild.get_channel(category_id) if category_id else None
    if category and not isinstance(category, discord.CategoryChannel):
        category = None

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

    channel_name = f"ticket-{member.name}"[:90]
    try:
        ticket_channel = await guild.create_text_channel(
            name=channel_name, category=category, overwrites=overwrites,
            reason=f"Ticket erstellt von {member}",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            embed=error_embed("Mir fehlt die Berechtigung, einen Kanal zu erstellen." if lang == "de"
                               else "I'm missing permission to create a channel."),
            ephemeral=True,
        )
        return

    await create_ticket(guild.id, ticket_channel.id, member.id, design=design)

    welcome = discord.Embed(
        title=t("ticket.welcome_title", lang, user=member.display_name),
        description=t("ticket.welcome_desc", lang),
        color=DESIGNS.get(design, DESIGNS["standard"])["color"],
    )
    await ticket_channel.send(content=member.mention, embed=welcome, view=TicketCloseView())
    await interaction.followup.send(
        embed=success_embed(t("ticket.created", lang, channel=ticket_channel.mention)),
        ephemeral=True,
    )


async def _handle_close_ticket(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel = interaction.channel
    lang = await get_guild_language(guild.id)

    ticket = await get_ticket_by_channel(channel.id)
    if not ticket:
        await interaction.response.send_message(embed=error_embed(t("ticket.not_a_ticket", lang)), ephemeral=True)
        return

    await interaction.response.send_message(embed=success_embed(t("ticket.closed", lang, user=interaction.user.mention)))
    await close_ticket(channel.id, claimed_by=interaction.user.id)

    # Kanal für den Ersteller sperren, aber fürs Team sichtbar/archiviert lassen
    # (bewusst NICHT sofort löschen -- Nachvollziehbarkeit für das Team).
    try:
        overwrites = channel.overwrites
        creator = guild.get_member(ticket.creator_id)
        if creator and creator in overwrites:
            await channel.set_permissions(creator, view_channel=True, send_messages=False)
        await channel.edit(name=f"closed-{channel.name}"[:90])
    except discord.Forbidden:
        pass


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        # Persistente Views registrieren, damit die Buttons nach einem
        # Bot-Neustart weiter funktionieren.
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketCloseView())

    @commands.hybrid_group(name="ticketpanel", description="Ticket-Panel verwalten.")
    @commands.guild_only()
    async def ticketpanel(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ticketpanel.command(name="send", description="Sendet ein Ticket-Panel in einen Kanal.")
    @app_commands.describe(channel="Zielkanal für das Panel", design="standard, minimal oder premium")
    @app_commands.choices(design=[
        app_commands.Choice(name=d, value=d) for d in DESIGNS.keys()
    ])
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def ticketpanel_send(self, ctx: commands.Context, channel: discord.TextChannel, design: str = "standard"):
        lang = await get_guild_language(ctx.guild.id)
        embed = _build_panel_embed(lang, design)
        await channel.send(embed=embed, view=TicketPanelView(design=design))
        await ctx.send(embed=success_embed(
            "Panel gesendet" if lang == "de" else "Panel sent",
            f"In {channel.mention} ({design})",
        ))

    @commands.hybrid_group(name="ticketkategorie", description="Kategorie für neue Ticket-Kanäle verwalten.")
    @commands.guild_only()
    async def ticketkategorie(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ticketkategorie.command(name="set", description="Legt fest, in welcher Kategorie neue Tickets entstehen.")
    @app_commands.describe(category="Die Kategorie für Ticket-Kanäle")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def ticketkategorie_set(self, ctx: commands.Context, category: discord.CategoryChannel):
        lang = await get_guild_language(ctx.guild.id)
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, ctx.guild.id)
            settings.ticket_category_id = category.id
            await session.commit()
        await ctx.send(embed=success_embed(t("ticket.category_set", lang, category=category.name)))

    @commands.hybrid_command(name="ticketclose", description="Schließt das aktuelle Ticket.")
    @commands.guild_only()
    async def ticketclose(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        ticket = await get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            await ctx.send(embed=error_embed(t("ticket.not_a_ticket", lang)))
            return

        # Nur der Ersteller oder Team-Mitglieder dürfen schließen.
        level = get_member_permission_level(ctx.author)
        if ctx.author.id != ticket.creator_id and level < PermissionLevel.TEAM:
            await ctx.send(embed=error_embed(t("no_permission", lang)))
            return

        await close_ticket(ctx.channel.id, claimed_by=ctx.author.id)
        await ctx.send(embed=success_embed(t("ticket.closed", lang, user=ctx.author.mention)))
        try:
            await ctx.channel.edit(name=f"closed-{ctx.channel.name}"[:90])
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))

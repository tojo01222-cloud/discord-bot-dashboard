"""
Ticket-System.

- /ticketpanel send <kanal> [design]     -- sendet ein Ticket-Panel in einen Kanal (SERVER_ADMIN).
                                             Zeigt automatisch ein Auswahlmenü mit allen per
                                             /ticketart erstellen angelegten Ticket-Arten -- oder,
                                             falls keine Ticket-Art existiert, den klassischen
                                             einzelnen "Ticket erstellen"-Button (abwärtskompatibel).
- /ticketart erstellen|liste|entfernen|bearbeiten  -- verschiedene Ticket-ARTEN (Kategorien zur
                                             Auswahl, z.B. Support/Bug-Report/Beschwerde) verwalten
                                             (SERVER_ADMIN). Jede Ticket-Art kann eine eigene
                                             Discord-Kanalkategorie und Farbe haben.
- /ticketart standardkategorie <kategorie> -- legt die STANDARD-Discord-Kanalkategorie fest, in der
                                             neue Ticket-Kanäle entstehen, wenn eine Ticket-Art
                                             keine eigene hinterlegt hat (SERVER_ADMIN). War früher
                                             ein eigener Befehl (/ticketkategorie set) -- jetzt hier
                                             gebündelt, um die Befehlsliste nicht unnötig aufzublähen.
- /ticketclose                            -- schließt das aktuelle Ticket (TEAM, oder der Ersteller)
- /ticketclaim                            -- ein Team-Mitglied übernimmt das Ticket sichtbar (TEAM)

Buttons/Auswahlmenüs sind "persistent" (überleben einen Bot-Neustart) -- dafür
registriert cog_load() diese Views einmal über bot.add_view(...). Für das
Auswahlmenü wird dabei bewusst ein generischer "Dispatcher" mit Platzhalter-
Option registriert: Discord matcht eingehende Interaktionen ausschließlich
über die custom_id, die tatsächlich im Server angezeigten Optionen kommen
weiterhin aus der Nachricht selbst, die /ticketpanel send ursprünglich mit
den echten, damals aktuellen Ticket-Arten gesendet hat.

Drei Designs für das Panel (visuell unterschiedlich, gleiche Funktion):
  standard -> Blurple, klassisch
  minimal  -> schlicht, ohne Extra-Felder
  premium  -> Gold, mit zusätzlichem "Was du erwarten kannst"-Feld
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
    get_ticket_categories,
    get_ticket_category,
    get_ticket_category_by_name,
    create_ticket_category,
    update_ticket_category,
    delete_ticket_category,
)
from bot.database.db import get_session
from bot.database.models import TicketCategory

TICKET_CREATE_CUSTOM_ID = "ticket_create_button"
TICKET_CLOSE_CUSTOM_ID = "ticket_close_button"
TICKET_DELETE_CUSTOM_ID = "ticket_delete_button"
TICKET_SELECT_CUSTOM_ID = "ticket_type_select"

DESIGNS = {
    "standard": {"color": discord.Color.blurple(), "emoji": "🎫"},
    "minimal": {"color": discord.Color.light_grey(), "emoji": "✉️"},
    "premium": {"color": discord.Color.gold(), "emoji": "⭐"},
    "dark": {"color": discord.Color.from_rgb(30, 30, 40), "emoji": "🌑"},
}


def _parse_color_hex(value: str) -> str:
    """Validiert einen Hex-Farbcode (z.B. '#5865F2' oder '5865F2') und gibt ihn
    normalisiert mit führendem '#' zurück. Wirft ValueError bei ungültiger Eingabe."""
    candidate = value if value.startswith("#") else f"#{value}"
    discord.Color.from_str(candidate)  # wirft ValueError bei ungültigem Format
    return candidate


def _build_panel_embed(lang: str, design: str, categories: list[TicketCategory]) -> discord.Embed:
    style = DESIGNS.get(design, DESIGNS["standard"])
    embed = discord.Embed(
        title=f"{style['emoji']} {t('ticket.panel_title', lang)}",
        description=f"{t('ticket.panel_desc', lang)}\n" + ("─" * 28),
        color=style["color"],
    )
    if categories:
        lines = [f"{c.emoji} **{c.name}**" + (f"\n> {c.description}" if c.description else "")
                  for c in categories[:25]]
        embed.add_field(
            name="📂 " + ("Verfügbare Ticket-Arten" if lang == "de" else "Available ticket types"),
            value="\n".join(lines),
            inline=False,
        )
    if design == "premium":
        embed.add_field(
            name="✨ " + ("Was dich erwartet" if lang == "de" else "What to expect"),
            value="Ein privater Kanal nur für dich und unser Team." if lang == "de"
            else "A private channel just for you and our team.",
            inline=False,
        )
    embed.set_footer(text="Support-Team" if lang == "de" else "Support Team")
    return embed


class TicketPanelView(discord.ui.View):
    """Persistenter View für den klassischen einzelnen 'Ticket erstellen'-Button
    (wird nur benutzt, wenn KEINE Ticket-Arten für den Server angelegt sind)."""

    def __init__(self, design: str = "standard"):
        super().__init__(timeout=None)
        self.design = design

    @discord.ui.button(label="Ticket erstellen", emoji="🎫", style=discord.ButtonStyle.primary,
                        custom_id=TICKET_CREATE_CUSTOM_ID)
    async def create_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_create_ticket(interaction, design=self.design)


class TicketTypeSelect(discord.ui.Select):
    """Auswahlmenü mit den echten Ticket-Arten eines Servers -- wird beim
    tatsächlichen Versand des Panels (/ticketpanel send) mit den dann aktuellen
    Ticket-Arten gebaut. Läuft ein Server auf mehr als 25 Ticket-Arten (Discords
    Limit für Auswahlmenüs), werden nur die ersten 25 angezeigt."""

    def __init__(self, categories: list[TicketCategory], design: str = "standard"):
        options = [
            discord.SelectOption(
                label=c.name[:100],
                value=str(c.id),
                description=(c.description or "")[:100] or None,
                emoji=c.emoji or None,
            )
            for c in categories[:25]
        ]
        super().__init__(
            placeholder="…", min_values=1, max_values=1, options=options,
            custom_id=TICKET_SELECT_CUSTOM_ID,
        )
        self.design = design

    async def callback(self, interaction: discord.Interaction):
        try:
            category_id = int(self.values[0])
        except (ValueError, IndexError):
            return
        await _handle_create_ticket(interaction, design=self.design, category_id=category_id)


class TicketPanelSelectView(discord.ui.View):
    """View mit dem Ticket-Arten-Auswahlmenü fürs Panel."""

    def __init__(self, categories: list[TicketCategory], design: str = "standard"):
        super().__init__(timeout=None)
        if categories:
            self.add_item(TicketTypeSelect(categories, design))


def _dispatcher_select_view() -> discord.ui.View:
    """Generischer, bei cog_load() registrierter Dispatcher für das
    Auswahlmenü-Panel (siehe Modul-Docstring: nur die custom_id zählt für die
    Zuordnung eingehender Interaktionen nach einem Bot-Neustart)."""
    view = discord.ui.View(timeout=None)
    select = discord.ui.Select(
        custom_id=TICKET_SELECT_CUSTOM_ID,
        placeholder="…",
        options=[discord.SelectOption(label="…", value="0")],
    )

    async def _callback(interaction: discord.Interaction):
        try:
            category_id = int(select.values[0])
        except (ValueError, IndexError):
            return
        await _handle_create_ticket(interaction, design="standard", category_id=category_id)

    select.callback = _callback
    view.add_item(select)
    return view


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


async def _handle_create_ticket(interaction: discord.Interaction, design: str = "standard",
                                 category_id: int = 0) -> None:
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

    category = await get_ticket_category(category_id) if category_id else None

    async with get_session() as session:
        settings = await get_or_create_guild_settings(session, guild.id)
        default_category_id = settings.ticket_category_id

    discord_category_id = (category.channel_category_id if category and category.channel_category_id
                            else default_category_id)
    discord_category = guild.get_channel(discord_category_id) if discord_category_id else None
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

    name_prefix = f"{category.name}" if category else "ticket"
    # Kanalnamen von Discord-unzulässigen/verwirrenden Zeichen befreien, statt
    # blind zu vertrauen, dass jeder Anzeigename schon kanaltauglich ist.
    safe_username = "".join(c for c in member.name.lower() if c.isalnum() or c in "-_") or "user"
    safe_prefix = "".join(c for c in name_prefix.lower().replace(" ", "-") if c.isalnum() or c == "-") or "ticket"
    channel_name = f"{safe_prefix}-{safe_username}"[:90]

    try:
        ticket_channel = await guild.create_text_channel(
            name=channel_name, category=discord_category, overwrites=overwrites,
            reason=f"Ticket erstellt von {member}" + (f" (Art: {category.name})" if category else ""),
        )
    except discord.Forbidden:
        await interaction.followup.send(
            embed=error_embed("Mir fehlt die Berechtigung, einen Kanal zu erstellen." if lang == "de"
                               else "I'm missing permission to create a channel."),
            ephemeral=True,
        )
        return

    await create_ticket(guild.id, ticket_channel.id, member.id, design=design,
                         category_id=category.id if category else 0)

    if category:
        color = discord.Color.blurple()
        if category.color_hex:
            try:
                color = discord.Color.from_str(category.color_hex)
            except ValueError:
                pass
        title_emoji = category.emoji or "🎫"
        desc = t("ticket.welcome_desc", lang)
        if category.description:
            desc = f"**{category.name}**: {category.description}\n\n{desc}"
    else:
        color = DESIGNS.get(design, DESIGNS["standard"])["color"]
        title_emoji = "🎫"
        desc = t("ticket.welcome_desc", lang)

    welcome = discord.Embed(
        title=f"{title_emoji} {t('ticket.welcome_title', lang, user=member.display_name)}",
        description=desc,
        color=color,
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
        # Persistente Views registrieren, damit die Buttons/Auswahlmenüs nach
        # einem Bot-Neustart weiter funktionieren.
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketCloseView())
        self.bot.add_view(TicketClosedView())
        self.bot.add_view(_dispatcher_select_view())

    # ---------- Ticket-Panel ----------
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
        categories = await get_ticket_categories(ctx.guild.id)
        embed = _build_panel_embed(lang, design, categories)

        if categories:
            view = TicketPanelSelectView(categories, design=design)
            extra = (f"\n\n{len(categories)} Ticket-Arten im Auswahlmenü."
                     if lang == "de" else f"\n\n{len(categories)} ticket types in the dropdown.")
        else:
            view = TicketPanelView(design=design)
            extra = ("\n\nKeine Ticket-Arten eingerichtet -- einzelner Button wird verwendet. "
                     "Nutze `/ticketart erstellen`, um mehrere Ticket-Kategorien anzubieten." if lang == "de" else
                     "\n\nNo ticket types configured -- using a single button. "
                     "Use `/ticketart erstellen` to offer multiple ticket categories.")

        await channel.send(embed=embed, view=view)
        await ctx.send(embed=success_embed(
            "Panel gesendet" if lang == "de" else "Panel sent",
            f"In {channel.mention} ({design}).{extra}",
        ))

    # ---------- Ticket-Arten (verschiedene Kategorien zur Auswahl) ----------
    @commands.hybrid_group(name="ticketart", description="Verschiedene Ticket-Arten (Kategorien) verwalten.")
    @commands.guild_only()
    async def ticketart(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ticketart.command(name="erstellen", description="Erstellt eine neue Ticket-Art (z.B. Support, Bug-Report).")
    @app_commands.describe(
        name="Name der Ticket-Art (wird im Auswahlmenü angezeigt)",
        emoji="Emoji für die Ticket-Art (Standard: 🎫)",
        beschreibung="Kurze Beschreibung, im Auswahlmenü sichtbar",
        farbe="Hex-Farbcode für die Willkommens-Nachricht, z.B. #5865F2",
        kanal_kategorie="Eigene Discord-Kanalkategorie für diese Ticket-Art (optional)",
    )
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def ticketart_erstellen(
        self, ctx: commands.Context, name: str, emoji: str = "🎫", beschreibung: str = "",
        farbe: str = "", kanal_kategorie: discord.CategoryChannel = None,
    ):
        lang = await get_guild_language(ctx.guild.id)

        if await get_ticket_category_by_name(ctx.guild.id, name):
            await ctx.send(embed=error_embed(t("ticket.type_exists", lang)))
            return

        color_hex = ""
        if farbe:
            try:
                color_hex = _parse_color_hex(farbe)
            except ValueError:
                await ctx.send(embed=error_embed(
                    "Ungültiger Hex-Farbcode, z.B. #5865F2." if lang == "de"
                    else "Invalid hex color code, e.g. #5865F2."))
                return

        existing_count = len(await get_ticket_categories(ctx.guild.id))
        category = await create_ticket_category(
            ctx.guild.id, name=name, emoji=emoji, description=beschreibung,
            color_hex=color_hex, channel_category_id=kanal_kategorie.id if kanal_kategorie else 0,
        )

        note = ""
        if existing_count >= 25:
            note = ("\n\n⚠️ Discord erlaubt maximal 25 Optionen pro Auswahlmenü -- diese Ticket-Art "
                    "wird im Panel nicht angezeigt, solange mehr als 25 Ticket-Arten existieren."
                    if lang == "de" else
                    "\n\n⚠️ Discord allows a maximum of 25 options per select menu -- this ticket type "
                    "won't show in the panel while more than 25 ticket types exist.")

        await ctx.send(embed=success_embed(t("ticket.type_created", lang, name=category.name) + note))

    @ticketart.command(name="liste", description="Zeigt alle Ticket-Arten dieses Servers.")
    async def ticketart_liste(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        categories = await get_ticket_categories(ctx.guild.id)
        if not categories:
            await ctx.send(embed=error_embed(t("ticket.type_list_empty", lang)))
            return

        embed = base_embed(t("ticket.type_list_title", lang))
        lines = []
        for c in categories:
            target = (ctx.guild.get_channel(c.channel_category_id).name
                      if c.channel_category_id and ctx.guild.get_channel(c.channel_category_id)
                      else ("Standard-Kategorie" if lang == "de" else "default category"))
            desc = f" — {c.description}" if c.description else ""
            lines.append(f"{c.emoji} **{c.name}**{desc}\n　↳ {target}")
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @ticketart.command(name="entfernen", description="Entfernt eine Ticket-Art.")
    @app_commands.describe(name="Name der zu entfernenden Ticket-Art")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def ticketart_entfernen(self, ctx: commands.Context, name: str):
        lang = await get_guild_language(ctx.guild.id)
        category = await get_ticket_category_by_name(ctx.guild.id, name)
        if not category:
            await ctx.send(embed=error_embed(t("ticket.type_not_found", lang)))
            return
        await delete_ticket_category(category.id)
        await ctx.send(embed=success_embed(t("ticket.type_removed", lang, name=category.name)))

    @ticketart.command(name="bearbeiten", description="Bearbeitet eine bestehende Ticket-Art.")
    @app_commands.describe(
        name="Name der zu bearbeitenden Ticket-Art",
        emoji="Neues Emoji (optional)",
        beschreibung="Neue Beschreibung (optional)",
        farbe="Neuer Hex-Farbcode, z.B. #5865F2 (optional)",
        kanal_kategorie="Neue Discord-Kanalkategorie (optional)",
    )
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def ticketart_bearbeiten(
        self, ctx: commands.Context, name: str, emoji: str = None, beschreibung: str = None,
        farbe: str = None, kanal_kategorie: discord.CategoryChannel = None,
    ):
        lang = await get_guild_language(ctx.guild.id)
        category = await get_ticket_category_by_name(ctx.guild.id, name)
        if not category:
            await ctx.send(embed=error_embed(t("ticket.type_not_found", lang)))
            return

        color_hex = None
        if farbe:
            try:
                color_hex = _parse_color_hex(farbe)
            except ValueError:
                await ctx.send(embed=error_embed(
                    "Ungültiger Hex-Farbcode, z.B. #5865F2." if lang == "de"
                    else "Invalid hex color code, e.g. #5865F2."))
                return

        await update_ticket_category(
            category.id, emoji=emoji, description=beschreibung, color_hex=color_hex,
            channel_category_id=kanal_kategorie.id if kanal_kategorie else None,
        )
        await ctx.send(embed=success_embed(t("ticket.type_updated", lang, name=category.name)))

    # ---------- Standard-Kanalkategorie (Discord-Kategorie-Kanal) ----------
    # Bewusst KEIN eigener Top-Level-Befehl mehr (war vorher /ticketkategorie set)
    # -- das führte zu Verwirrung zwischen "Kategorie" (Discord-Kanalkategorie)
    # und "Art" (Ticket-Typ zur Auswahl). Jetzt als Unterbefehl von /ticketart
    # gebündelt, ein Befehl weniger im "/"-Menü, gleiche Funktion.
    @ticketart.command(name="standardkategorie",
                        description="Legt die Standard-Discord-Kanalkategorie für neue Ticket-Kanäle fest.")
    @app_commands.describe(kategorie="Die Discord-Kanalkategorie für Ticket-Kanäle ohne eigene Kategorie")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def ticketart_standardkategorie(self, ctx: commands.Context, kategorie: discord.CategoryChannel):
        lang = await get_guild_language(ctx.guild.id)
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, ctx.guild.id)
            settings.ticket_category_id = kategorie.id
            await session.commit()
        await ctx.send(embed=success_embed(t("ticket.category_set", lang, category=kategorie.name)))

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

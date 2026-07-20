"""
Economy-System.

- /balance [user]                      -- zeigt den Kontostand
- /daily                                -- holt die tägliche Belohnung ab (24h Cooldown)
- /pay <user> <betrag>                   -- überweist Coins an einen anderen User
- /leaderboard_economy                    -- Top 10 nach Kontostand
- /shop liste                              -- zeigt kaufbare Items
- /shop kaufen <item_id>                    -- kauft ein Item (vergibt ggf. automatisch eine Rolle)
- /shop add <name> <preis> [rolle]           -- fügt ein Item hinzu (SERVER_ADMIN)
- /shop remove <item_id>                      -- entfernt ein Item (SERVER_ADMIN)

Bewusst komplett unabhängig vom Level-/XP-System (bot/cogs/level.py) --
zwei getrennte "Währungen", damit Server sich aussuchen können, welches
System sie nutzen wollen, ohne dass beide sich gegenseitig beeinflussen.
"""
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import (
    get_guild_language,
    get_balance,
    add_balance,
    claim_daily,
    get_economy_leaderboard,
    add_shop_item,
    get_shop_items,
    get_shop_item,
    remove_shop_item,
)

DAILY_AMOUNT = 100


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="balance", description="Zeigt deinen Kontostand (oder den eines anderen Users).")
    @app_commands.describe(member="Optional: ein anderer User")
    @commands.guild_only()
    async def balance(self, ctx: commands.Context, member: discord.Member = None):
        lang = await get_guild_language(ctx.guild.id)
        target = member or ctx.author
        entry = await get_balance(ctx.guild.id, target.id)
        embed = base_embed(f"💰 {target.display_name}", f"**{entry.balance}** Coins" if lang == "de"
                            else f"**{entry.balance}** coins")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="daily", description="Holt deine tägliche Belohnung ab.")
    @commands.guild_only()
    async def daily(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        new_balance = await claim_daily(ctx.guild.id, ctx.author.id, DAILY_AMOUNT)
        if new_balance is None:
            await ctx.send(embed=error_embed(
                "Du hast deine tägliche Belohnung schon abgeholt -- versuch's morgen wieder." if lang == "de"
                else "You've already claimed your daily reward -- try again tomorrow."), ephemeral=True)
            return

        await ctx.send(embed=success_embed(
            f"+{DAILY_AMOUNT} Coins! Neuer Kontostand: {new_balance}." if lang == "de"
            else f"+{DAILY_AMOUNT} coins! New balance: {new_balance}."))

    @commands.hybrid_command(name="pay", description="Überweist Coins an einen anderen User.")
    @app_commands.describe(member="Empfänger", betrag="Wie viele Coins")
    @commands.guild_only()
    async def pay(self, ctx: commands.Context, member: discord.Member, betrag: int):
        lang = await get_guild_language(ctx.guild.id)
        if member.id == ctx.author.id:
            await ctx.send(embed=error_embed(
                "Du kannst dir nicht selbst Coins schicken." if lang == "de"
                else "You can't send coins to yourself."), ephemeral=True)
            return
        if betrag <= 0:
            await ctx.send(embed=error_embed(
                "Der Betrag muss größer als 0 sein." if lang == "de" else "The amount must be greater than 0."),
                ephemeral=True)
            return

        sender_entry = await get_balance(ctx.guild.id, ctx.author.id)
        if sender_entry.balance < betrag:
            await ctx.send(embed=error_embed(
                "Du hast nicht genug Coins." if lang == "de" else "You don't have enough coins."), ephemeral=True)
            return

        await add_balance(ctx.guild.id, ctx.author.id, -betrag)
        await add_balance(ctx.guild.id, member.id, betrag)
        await ctx.send(embed=success_embed(
            f"{betrag} Coins an {member.mention} überwiesen." if lang == "de"
            else f"Sent {betrag} coins to {member.mention}."))

    @commands.hybrid_command(name="leaderboard_economy", description="Zeigt die Top 10 nach Kontostand.")
    @commands.guild_only()
    async def leaderboard_economy(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        top = await get_economy_leaderboard(ctx.guild.id)
        if not top:
            await ctx.send(embed=error_embed("Noch keine Daten." if lang == "de" else "No data yet."))
            return

        embed = base_embed("💰 Economy-Leaderboard" if lang == "de" else "💰 Economy leaderboard")
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"{medals[i] if i < 3 else f'{i+1}.'} <@{e.user_id}> — {e.balance} Coins"
                 for i, e in enumerate(top)]
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="shop", description="Shop verwalten/nutzen.")
    @commands.guild_only()
    async def shop(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @shop.command(name="liste", description="Zeigt alle kaufbaren Items.")
    async def shop_liste(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        items = await get_shop_items(ctx.guild.id)
        if not items:
            await ctx.send(embed=error_embed("Der Shop ist leer." if lang == "de" else "The shop is empty."))
            return

        embed = base_embed("🛒 Shop")
        lines = [f"#{i.id} — **{i.name}** — {i.price} Coins" + (f" (Rolle: <@&{i.role_id}>)" if i.role_id else "")
                 for i in items[:25]]
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @shop.command(name="kaufen", description="Kauft ein Item aus dem Shop.")
    @app_commands.describe(item_id="Die ID aus /shop liste")
    @commands.guild_only()
    async def shop_kaufen(self, ctx: commands.Context, item_id: int):
        lang = await get_guild_language(ctx.guild.id)
        item = await get_shop_item(item_id)
        if item is None or item.guild_id != ctx.guild.id:
            await ctx.send(embed=error_embed("Item nicht gefunden." if lang == "de" else "Item not found."),
                            ephemeral=True)
            return

        entry = await get_balance(ctx.guild.id, ctx.author.id)
        if entry.balance < item.price:
            await ctx.send(embed=error_embed(
                "Du hast nicht genug Coins für dieses Item." if lang == "de"
                else "You don't have enough coins for this item."), ephemeral=True)
            return

        await add_balance(ctx.guild.id, ctx.author.id, -item.price)

        if item.role_id:
            role = ctx.guild.get_role(item.role_id)
            if role:
                try:
                    await ctx.author.add_roles(role, reason=f"Shop-Kauf: {item.name}")
                except discord.Forbidden:
                    pass

        await ctx.send(embed=success_embed(
            f"**{item.name}** gekauft!" if lang == "de" else f"Bought **{item.name}**!"))

    @shop.command(name="add", description="Fügt ein Item zum Shop hinzu.")
    @app_commands.describe(name="Name des Items", preis="Preis in Coins", rolle="Optional: Rolle, die beim Kauf vergeben wird")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def shop_add(self, ctx: commands.Context, name: str, preis: int, rolle: discord.Role = None):
        lang = await get_guild_language(ctx.guild.id)
        if preis <= 0:
            await ctx.send(embed=error_embed(
                "Der Preis muss größer als 0 sein." if lang == "de" else "The price must be greater than 0."))
            return
        item = await add_shop_item(ctx.guild.id, name, preis, rolle.id if rolle else 0)
        await ctx.send(embed=success_embed(
            f"Item **{item.name}** für {preis} Coins hinzugefügt." if lang == "de"
            else f"Item **{item.name}** added for {preis} coins."))

    @shop.command(name="remove", description="Entfernt ein Item aus dem Shop.")
    @app_commands.describe(item_id="Die ID aus /shop liste")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def shop_remove(self, ctx: commands.Context, item_id: int):
        lang = await get_guild_language(ctx.guild.id)
        ok = await remove_shop_item(item_id)
        if ok:
            await ctx.send(embed=success_embed("Entfernt." if lang == "de" else "Removed."))
        else:
            await ctx.send(embed=error_embed("ID nicht gefunden." if lang == "de" else "ID not found."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))

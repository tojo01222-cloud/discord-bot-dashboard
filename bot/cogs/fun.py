"""
Spaß-Befehle. 20 Stück, alle ohne externe Abhängigkeiten außer /katze und
/hund (nutzen kostenlose, schlüssellose öffentliche APIs).
"""
import random

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.embeds import base_embed, error_embed

EIGHT_BALL_ANSWERS_DE = [
    "Ja, definitiv.", "Auf jeden Fall.", "Sieht gut aus.", "Wahrscheinlich.",
    "Frag später nochmal.", "Kann ich jetzt nicht sagen.", "Konzentrier dich und frag nochmal.",
    "Verlass dich nicht darauf.", "Meine Antwort ist nein.", "Sieht nicht gut aus.", "Sehr zweifelhaft.",
]

JOKES_DE = [
    "Warum können Geister so schlecht lügen? Weil man durch sie hindurchsieht.",
    "Treffen sich zwei Magnete. Sagt der eine: 'Ich finde dich anziehend.'",
    "Was ist grün und steht vor der Tür? Ein Klopfsalat.",
    "Warum weinen Bäume im Frühling? Weil sie Blätter lassen müssen.",
    "Kommt ein Pferd in die Bar. Fragt der Barkeeper: 'Warum so ein langes Gesicht?'",
    "Was macht ein Keks unterm Baum? Krümel.",
]

QUOTES_DE = [
    "„Der Weg ist das Ziel.“",
    "„Wer kämpft, kann verlieren. Wer nicht kämpft, hat schon verloren.“",
    "„Man sieht nur mit dem Herzen gut.“",
    "„Es ist nie zu spät, das zu werden, was man hätte sein können.“",
]

COMPLIMENTS_DE = [
    "hat heute richtig gute Laune verbreitet!",
    "ist einfach eine tolle Person.",
    "bringt jeden zum Lachen.",
    "ist unterschätzt gut in dem, was er/sie tut.",
]


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ping", description="Zeigt die Antwortzeit des Bots.")
    async def ping(self, ctx: commands.Context):
        await ctx.send(embed=base_embed("🏓 Pong!", f"{round(self.bot.latency * 1000)}ms"))

    @commands.hybrid_command(name="muenzwurf", description="Wirft eine Münze.")
    async def muenzwurf(self, ctx: commands.Context):
        result = random.choice(["Kopf", "Zahl"])
        await ctx.send(embed=base_embed("🪙 Münzwurf", f"**{result}**"))

    @commands.hybrid_command(name="wuerfel", description="Würfelt (Standard: 6 Seiten).")
    @app_commands.describe(seiten="Anzahl der Seiten (Standard 6)")
    async def wuerfel(self, ctx: commands.Context, seiten: int = 6):
        if seiten < 2 or seiten > 1000:
            await ctx.send(embed=error_embed("Seitenzahl muss zwischen 2 und 1000 liegen."))
            return
        result = random.randint(1, seiten)
        await ctx.send(embed=base_embed("🎲 Würfelwurf", f"**{result}** (von 1-{seiten})"))

    @commands.hybrid_command(name="8ball", description="Stell die magische 8-Kugel eine Frage.")
    @app_commands.describe(frage="Deine Ja/Nein-Frage")
    async def eight_ball(self, ctx: commands.Context, *, frage: str):
        embed = base_embed("🎱 Magische 8-Kugel")
        embed.add_field(name="Frage", value=frage, inline=False)
        embed.add_field(name="Antwort", value=random.choice(EIGHT_BALL_ANSWERS_DE), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="avatar", description="Zeigt das Profilbild eines Users.")
    @app_commands.describe(member="Optional: ein anderer User")
    async def avatar(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        embed = base_embed(f"🖼️ Avatar von {target.display_name}")
        embed.set_image(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="banner", description="Zeigt das Profil-Banner eines Users (falls vorhanden).")
    @app_commands.describe(member="Optional: ein anderer User")
    async def banner(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        user = await self.bot.fetch_user(target.id)  # Banner ist nur über einen frischen API-Call verfügbar
        if not user.banner:
            await ctx.send(embed=error_embed(f"{target.display_name} hat kein Banner gesetzt."))
            return
        embed = base_embed(f"🖼️ Banner von {target.display_name}")
        embed.set_image(url=user.banner.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="userinfo", description="Zeigt Informationen über einen User.")
    @app_commands.describe(member="Optional: ein anderer User")
    @commands.guild_only()
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        embed = base_embed(f"👤 {target.display_name}")
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Beigetreten am", value=discord.utils.format_dt(target.joined_at, style="D")
                         if target.joined_at else "—", inline=True)
        embed.add_field(name="Account erstellt", value=discord.utils.format_dt(target.created_at, style="D"), inline=True)
        embed.add_field(name="Rollen", value=str(len(target.roles) - 1), inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="witz", description="Erzählt einen zufälligen Witz.")
    async def witz(self, ctx: commands.Context):
        await ctx.send(embed=base_embed("😂 Witz", random.choice(JOKES_DE)))

    @commands.hybrid_command(name="zitat", description="Zeigt ein zufälliges Zitat.")
    async def zitat(self, ctx: commands.Context):
        await ctx.send(embed=base_embed("💬 Zitat", random.choice(QUOTES_DE)))

    @commands.hybrid_command(name="umfrage", description="Erstellt eine Umfrage mit Ja/Nein-Reaktionen.")
    @app_commands.describe(frage="Die Frage der Umfrage")
    async def umfrage(self, ctx: commands.Context, *, frage: str):
        embed = base_embed("📊 Umfrage", frage)
        embed.set_footer(text=f"Gestartet von {ctx.author.display_name}")
        message = await ctx.send(embed=embed)
        await message.add_reaction("👍")
        await message.add_reaction("👎")
        await message.add_reaction("🤷")

    @commands.hybrid_command(name="ssp", description="Schere, Stein, Papier gegen den Bot.")
    @app_commands.describe(wahl="schere, stein oder papier")
    @app_commands.choices(wahl=[
        app_commands.Choice(name="Schere", value="schere"),
        app_commands.Choice(name="Stein", value="stein"),
        app_commands.Choice(name="Papier", value="papier"),
    ])
    async def ssp(self, ctx: commands.Context, wahl: str):
        options = ["schere", "stein", "papier"]
        bot_choice = random.choice(options)
        beats = {"schere": "papier", "stein": "schere", "papier": "stein"}

        if wahl == bot_choice:
            result = "Unentschieden!"
        elif beats[wahl] == bot_choice:
            result = "Du gewinnst! 🎉"
        else:
            result = "Der Bot gewinnt!"

        embed = base_embed("✂️ Schere, Stein, Papier")
        embed.add_field(name="Du", value=wahl.capitalize(), inline=True)
        embed.add_field(name="Bot", value=bot_choice.capitalize(), inline=True)
        embed.add_field(name="Ergebnis", value=result, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="reverse", description="Dreht einen Text um.")
    @app_commands.describe(text="Der Text zum Umdrehen")
    async def reverse(self, ctx: commands.Context, *, text: str):
        await ctx.send(embed=base_embed("🔄 Umgedreht", text[::-1]))

    @commands.hybrid_command(name="katze", description="Zeigt ein zufälliges Katzenbild.")
    async def katze(self, ctx: commands.Context):
        url = await self._fetch_random_image("https://api.thecatapi.com/v1/images/search", "url")
        if not url:
            await ctx.send(embed=error_embed("Konnte gerade kein Katzenbild laden, versuch's nochmal."))
            return
        embed = base_embed("🐱 Miau!")
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="hund", description="Zeigt ein zufälliges Hundebild.")
    async def hund(self, ctx: commands.Context):
        try:
            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://dog.ceo/api/breeds/image/random") as resp:
                    data = await resp.json()
                    url = data.get("message")
        except Exception:
            url = None

        if not url:
            await ctx.send(embed=error_embed("Konnte gerade kein Hundebild laden, versuch's nochmal."))
            return
        embed = base_embed("🐶 Wuff!")
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @staticmethod
    async def _fetch_random_image(api_url: str, json_key: str) -> str | None:
        try:
            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url) as resp:
                    data = await resp.json()
                    if isinstance(data, list) and data:
                        return data[0].get(json_key)
        except Exception:
            return None
        return None

    @commands.hybrid_command(name="liebescalc", description="Berechnet die 'Liebe' zwischen zwei Usern (nur Spaß!).")
    @app_commands.describe(user1="Erste Person", user2="Optional: zweite Person (sonst du selbst)")
    async def liebescalc(self, ctx: commands.Context, user1: discord.Member, user2: discord.Member = None):
        target2 = user2 or ctx.author
        seed = user1.id + target2.id
        percent = seed % 101
        embed = base_embed("💞 Liebes-Rechner", f"{user1.mention} + {target2.mention} = **{percent}%**")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="zufallszahl", description="Gibt eine Zufallszahl in einem Bereich zurück.")
    @app_commands.describe(minimum="Kleinster Wert", maximum="Größter Wert")
    async def zufallszahl(self, ctx: commands.Context, minimum: int, maximum: int):
        if minimum >= maximum:
            await ctx.send(embed=error_embed("Minimum muss kleiner als Maximum sein."))
            return
        await ctx.send(embed=base_embed("🔢 Zufallszahl", str(random.randint(minimum, maximum))))

    @commands.hybrid_command(name="waehle", description="Wählt zufällig eine Option aus einer Liste (Komma-getrennt).")
    @app_commands.describe(optionen="Optionen, durch Komma getrennt")
    async def waehle(self, ctx: commands.Context, *, optionen: str):
        choices = [o.strip() for o in optionen.split(",") if o.strip()]
        if len(choices) < 2:
            await ctx.send(embed=error_embed("Bitte mindestens 2 Optionen durch Komma getrennt angeben."))
            return
        await ctx.send(embed=base_embed("🎯 Auswahl", f"Ich wähle: **{random.choice(choices)}**"))

    @commands.hybrid_command(name="slap", description="Klatscht spielerisch einen anderen User.")
    @app_commands.describe(member="Wen du 'schlagen' willst")
    async def slap(self, ctx: commands.Context, member: discord.Member):
        await ctx.send(f"👋 {ctx.author.mention} klatscht {member.mention} spielerisch!")

    @commands.hybrid_command(name="hug", description="Umarmt einen anderen User.")
    @app_commands.describe(member="Wen du umarmen willst")
    async def hug(self, ctx: commands.Context, member: discord.Member):
        await ctx.send(f"🤗 {ctx.author.mention} umarmt {member.mention}!")

    @commands.hybrid_command(name="kompliment", description="Macht jemandem ein zufälliges Kompliment.")
    @app_commands.describe(member="Optional: wem das Kompliment gilt")
    async def kompliment(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        await ctx.send(f"✨ {target.mention} {random.choice(COMPLIMENTS_DE)}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))

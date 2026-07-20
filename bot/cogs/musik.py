"""
Musiksystem.

- /musikkanal set <voice-channel>   -- bindet den Bot dauerhaft an einen Sprachkanal (SERVER_ADMIN)
- /play <song oder URL>             -- spielt einen Track ab (SERVER_ADMIN, wie gewünscht)
- /skip                              -- überspringt den aktuellen Track
- /stop                              -- stoppt Wiedergabe, leert Warteschlange
- /queue                             -- zeigt die aktuelle Warteschlange
- /radio <genre>                     -- Live-Radiosender passend zum Genre (electro, techno,
                                         hiphop, pop, chill) oder direkt per Sendername (energy, kronehit)
- /lautstaerke <prozent>             -- passt die Lautstärke an (1-250%, Standard 100%)

Auto-Rejoin + Radio-Fortsetzung: wird der Bot aus dem gebundenen Sprachkanal
entfernt (gekickt, Verbindung verloren oder per /stop weiter im Kanal), tritt
er beim nächsten Beitritt automatisch wieder bei UND setzt den zuletzt
gehörten Radiosender direkt fort -- ganz ohne erneutes /radio. Das gilt auch
nach einem kompletten Bot-Neustart, da der zuletzt gehörte Sender pro Server
in der Datenbank gespeichert wird (GuildSettings.music_last_genre).
"""
import asyncio
import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.utils.permissions import require_level, PermissionLevel
from bot.utils.embeds import success_embed, error_embed, base_embed
from bot.utils.db_helpers import (
    get_guild_language, get_or_create_guild_settings, set_music_last_genre, get_music_last_genre,
)
from bot.utils.i18n import t
from bot.utils.music_player import get_player, MusicPlayer, RADIO_STREAMS, MIN_VOLUME, MAX_VOLUME
from bot.database.db import get_session

log = logging.getLogger("bot.cogs.musik")


class Musik(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self._music_channel_poll_loop.start()

    def cog_unload(self) -> None:
        self._music_channel_poll_loop.cancel()

    @tasks.loop(seconds=30)
    async def _music_channel_poll_loop(self) -> None:
        """WICHTIGER FIX: der gebundene Musik-Kanal wurde bisher NUR beim
        Bot-Start (on_ready) übernommen. Änderte man ihn übers Dashboard,
        während der Bot schon lief, passierte gar nichts -- der Bot blieb
        im alten Kanal (oder trat gar keinem bei), bis zum nächsten Neustart.
        Diese Schleife prüft alle 30s aktiv auf Änderungen und reagiert sofort:
        neuer Kanal -> beitreten/wechseln, Kanal entfernt -> Bot verlässt ihn."""
        from bot.database.models import GuildSettings
        from sqlalchemy import select

        try:
            async with get_session() as session:
                result = await session.execute(select(GuildSettings))
                all_settings = result.scalars().all()
        except Exception:
            log.exception("Konnte GuildSettings für Musik-Kanal-Abgleich nicht laden")
            return

        for settings in all_settings:
            guild = self.bot.get_guild(settings.guild_id)
            if not guild:
                continue

            player = get_player(guild.id)
            target_channel_id = settings.music_bound_voice_channel_id

            if target_channel_id == player.bound_channel_id:
                continue  # keine Änderung seit der letzten Prüfung

            player.bound_channel_id = target_channel_id

            if not target_channel_id:
                # Kanal wurde übers Dashboard entfernt -> Bot verlässt ihn
                if player.voice_client and player.voice_client.is_connected():
                    await player.voice_client.disconnect()
                    player.voice_client = None
                    log.info("Musik-Kanal-Bindung entfernt (Guild %s) -- Bot hat den Kanal verlassen.", guild.id)
                continue

            channel = guild.get_channel(target_channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                continue

            try:
                if player.voice_client and player.voice_client.is_connected():
                    if player.voice_client.channel.id == target_channel_id:
                        continue  # bereits im richtigen Kanal
                    await player.voice_client.move_to(channel)
                    log.info("Musik-Kanal übers Dashboard gewechselt (Guild %s) -> %s", guild.id, channel.id)
                else:
                    player.voice_client = await channel.connect()
                    log.info("Musik-Kanal übers Dashboard neu gesetzt (Guild %s) -> %s", guild.id, channel.id)
                    await self._resume_last_radio_if_idle(guild.id, player)
            except Exception:
                log.exception("Konnte auf Dashboard-Musik-Kanal-Änderung nicht reagieren (Guild %s)", guild.id)

    async def _after_track(self, player: MusicPlayer, _track) -> None:
        """Wird nach jedem Track aufgerufen -- spielt automatisch den nächsten
        (oder holt bei aktivem Radio-Modus neue Musik nach)."""
        await player.play_next(lambda t: self._after_track(player, t))

    async def _resume_last_radio_if_idle(self, guild_id: int, player: MusicPlayer) -> None:
        """Setzt beim (Wieder-)Beitritt zum gebundenen Musikkanal automatisch den
        zuletzt gehörten Radiosender fort, sofern gerade nichts läuft und nichts
        in der Warteschlange wartet -- damit /radio nach einem Kick, /stop oder
        einem Bot-Neustart nicht erneut manuell aufgerufen werden muss."""
        if player.queue:
            return  # eine manuelle /play-Warteschlange hat Vorrang
        if player.voice_client and (player.voice_client.is_playing() or player.voice_client.is_paused()):
            return  # es läuft bereits etwas (z.B. Radio lief schon durch)

        genre = player.last_radio_genre
        if not genre:
            genre = await get_music_last_genre(guild_id)  # z.B. nach Bot-Neustart aus der DB
        if not genre or genre not in RADIO_STREAMS:
            return

        started = await player.play_radio_stream(genre)
        if started:
            log.info("Radiosender '%s' nach (Wieder-)Beitritt automatisch fortgesetzt (Guild %s).", genre, guild_id)

    # ---------- Kanal-Bindung ----------
    @commands.hybrid_group(name="musikkanal", description="Sprachkanal für die Musik-Bindung verwalten.")
    @commands.guild_only()
    async def musikkanal(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @musikkanal.command(name="set", description="Bindet den Bot dauerhaft an diesen Sprachkanal.")
    @app_commands.describe(channel="Der Sprachkanal, in dem der Bot immer bleiben soll")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def musikkanal_set(self, ctx: commands.Context, channel: discord.VoiceChannel):
        await ctx.defer()  # Verbindungsaufbau kann >3s dauern -> Discord vorab "Bescheid geben"
        lang = await get_guild_language(ctx.guild.id)
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, ctx.guild.id)
            settings.music_bound_voice_channel_id = channel.id
            await session.commit()

        player = get_player(ctx.guild.id)
        player.bound_channel_id = channel.id
        player.text_channel_id = ctx.channel.id

        if not player.voice_client or not player.voice_client.is_connected():
            try:
                player.voice_client = await asyncio.wait_for(channel.connect(), timeout=15)
            except asyncio.TimeoutError:
                await ctx.send(embed=error_embed(
                    "Verbindung zum Sprachkanal fehlgeschlagen (Timeout). Das kann daran liegen, dass "
                    "dein Hoster keine Voice-Verbindungen (UDP) erlaubt — bitte beim Support nachfragen."
                    if lang == "de" else
                    "Voice connection timed out. This can happen if your host blocks voice (UDP) "
                    "connections — please check with your hosting support."
                ))
                return
            except discord.ClientException as e:
                await ctx.send(embed=error_embed(f"Verbindungsfehler: {e}" if lang == "de" else f"Connection error: {e}"))
                return
            await self._resume_last_radio_if_idle(ctx.guild.id, player)

        await ctx.send(embed=success_embed(
            "Musik-Kanal gesetzt" if lang == "de" else "Music channel set",
            f"Ich bleibe jetzt dauerhaft in {channel.mention}." if lang == "de"
            else f"I'll stay in {channel.mention} from now on.",
        ))

    @musikkanal.command(name="clear", description="Hebt die Sprachkanal-Bindung auf.")
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def musikkanal_clear(self, ctx: commands.Context):
        await ctx.defer()
        lang = await get_guild_language(ctx.guild.id)
        async with get_session() as session:
            settings = await get_or_create_guild_settings(session, ctx.guild.id)
            settings.music_bound_voice_channel_id = 0
            await session.commit()

        player = get_player(ctx.guild.id)
        player.bound_channel_id = 0
        if player.voice_client and player.voice_client.is_connected():
            await player.voice_client.disconnect()

        await ctx.send(embed=success_embed("Bindung aufgehoben" if lang == "de" else "Binding removed"))

    # ---------- Wiedergabe ----------
    @commands.hybrid_command(name="play", description="Spielt einen Song ab (YouTube-Suche oder URL).")
    @app_commands.describe(song="Songname oder YouTube-URL")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def play(self, ctx: commands.Context, *, song: str):
        await ctx.defer()  # WICHTIG: vor jeder potenziell langsamen Aktion (Verbindung, Suche)
        lang = await get_guild_language(ctx.guild.id)
        player = get_player(ctx.guild.id)

        if not player.voice_client or not player.voice_client.is_connected():
            if not ctx.author.voice or not ctx.author.voice.channel:
                await ctx.send(embed=error_embed(
                    "Du musst in einem Sprachkanal sein." if lang == "de"
                    else "You need to be in a voice channel."))
                return
            try:
                player.voice_client = await asyncio.wait_for(ctx.author.voice.channel.connect(), timeout=15)
            except asyncio.TimeoutError:
                await ctx.send(embed=error_embed(
                    "Verbindung zum Sprachkanal fehlgeschlagen (Timeout)." if lang == "de"
                    else "Voice connection timed out."))
                return
            player.text_channel_id = ctx.channel.id

        query = song if song.startswith("http") else f"ytsearch1:{song}"
        try:
            track = await asyncio.wait_for(player.extract_track(query, requested_by=ctx.author.id), timeout=25)
        except asyncio.TimeoutError:
            await ctx.send(embed=error_embed(
                "Die Suche hat zu lange gedauert (Timeout). Bitte nochmal versuchen." if lang == "de"
                else "The search took too long (timeout). Please try again."))
            return

        if track is None:
            await ctx.send(embed=error_embed(
                "Konnte nichts dazu finden." if lang == "de" else "Couldn't find anything for that."))
            return

        await player.add_and_maybe_play(track, lambda t: self._after_track(player, t))
        await ctx.send(embed=success_embed(
            "Zur Warteschlange hinzugefügt" if lang == "de" else "Added to queue",
            f"🎵 [{track.title}]({track.url})",
        ))

    @commands.hybrid_command(name="skip", description="Überspringt den aktuellen Track.")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def skip(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        player = get_player(ctx.guild.id)
        if player.skip():
            await ctx.send(embed=success_embed("Übersprungen" if lang == "de" else "Skipped"))
        else:
            await ctx.send(embed=error_embed(
                "Gerade läuft nichts." if lang == "de" else "Nothing is playing right now."))

    @commands.hybrid_command(name="stop", description="Stoppt die Musik und leert die Warteschlange.")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def stop(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        player = get_player(ctx.guild.id)
        player.stop_and_clear()
        await ctx.send(embed=success_embed("Gestoppt" if lang == "de" else "Stopped"))

    @commands.hybrid_command(name="lautstaerke", description="Passt die Wiedergabelautstärke an (1-250%).")
    @app_commands.describe(prozent="Lautstärke in Prozent, z.B. 100 für normale Lautstärke")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def lautstaerke(self, ctx: commands.Context, prozent: int):
        lang = await get_guild_language(ctx.guild.id)
        min_pct, max_pct = int(MIN_VOLUME * 100), int(MAX_VOLUME * 100)
        if prozent < min_pct or prozent > max_pct:
            await ctx.send(embed=error_embed(
                f"Die Lautstärke muss zwischen {min_pct}% und {max_pct}% liegen." if lang == "de"
                else f"Volume must be between {min_pct}% and {max_pct}%."))
            return

        player = get_player(ctx.guild.id)
        applied = player.set_volume(prozent / 100)
        await ctx.send(embed=success_embed(
            "🔊 Lautstärke geändert" if lang == "de" else "🔊 Volume changed",
            f"Jetzt bei **{round(applied * 100)}%**.",
        ))

    @commands.hybrid_command(name="queue", description="Zeigt die aktuelle Warteschlange.")
    @commands.guild_only()
    async def queue_cmd(self, ctx: commands.Context):
        lang = await get_guild_language(ctx.guild.id)
        player = get_player(ctx.guild.id)

        if not player.queue:
            await ctx.send(embed=error_embed("Warteschlange ist leer." if lang == "de" else "Queue is empty."))
            return

        embed = base_embed("🎵 Warteschlange" if lang == "de" else "🎵 Queue")
        lines = [f"{i+1}. [{tr.title}]({tr.url})" for i, tr in enumerate(player.queue[:15])]
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="radio", description="Startet einen Radiosender-Stream (electro/techno/hiphop/pop/chill/energy/kronehit).")
    @app_commands.describe(genre="electro, techno, hiphop, pop, chill, energy oder kronehit")
    @app_commands.choices(genre=[
        app_commands.Choice(name=g, value=g) for g in RADIO_STREAMS.keys()
    ])
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def radio(self, ctx: commands.Context, genre: str):
        await ctx.defer()  # Verbindung kann >3s dauern
        lang = await get_guild_language(ctx.guild.id)
        player = get_player(ctx.guild.id)

        if not player.voice_client or not player.voice_client.is_connected():
            if not ctx.author.voice or not ctx.author.voice.channel:
                await ctx.send(embed=error_embed(
                    "Du musst in einem Sprachkanal sein." if lang == "de"
                    else "You need to be in a voice channel."))
                return
            try:
                player.voice_client = await asyncio.wait_for(ctx.author.voice.channel.connect(), timeout=15)
            except asyncio.TimeoutError:
                await ctx.send(embed=error_embed(
                    "Verbindung zum Sprachkanal fehlgeschlagen (Timeout)." if lang == "de"
                    else "Voice connection timed out."))
                return
            player.text_channel_id = ctx.channel.id

        started = await player.play_radio_stream(genre)
        if not started:
            await ctx.send(embed=error_embed(
                "Für dieses Genre ist gerade kein Sender hinterlegt." if lang == "de"
                else "No station is configured for that genre right now."))
            return

        # Sofort persistieren (nicht erst nach der 25s-Stabilitätsprüfung unten):
        # so weiß der Bot auch dann, welcher Sender zuletzt gewünscht war, wenn
        # er zwischen jetzt und dem Ende der Prüfung neu startet oder gekickt wird.
        await set_music_last_genre(ctx.guild.id, genre)

        # Kurz warten und prüfen, ob der Sender tatsächlich stabil läuft, statt
        # sofort "Erfolg" zu melden. Bei 3 Versuchen à 8 Sekunden (siehe
        # music_player.py) kann es bis zu ~24s dauern, bis der Bot wirklich
        # aufgibt -- 25s deckt das sicher ab, statt eine verfrühte
        # "Erfolg"-Meldung zu riskieren, während im Hintergrund noch
        # weitere Versuche laufen.
        await ctx.send(embed=base_embed(
            "⏳ Prüfe Verbindung..." if lang == "de" else "⏳ Checking connection...",
            "Das kann bis zu 25 Sekunden dauern." if lang == "de"
            else "This can take up to 25 seconds.",
        ))
        await asyncio.sleep(25)
        if player.radio_genre != genre:
            # Radio-Modus wurde inzwischen komplett beendet (z.B. durch /stop
            # oder einen anderen /radio-Aufruf) -- echter Fehlerfall.
            await ctx.send(embed=error_embed(
                "Sender-Fehler" if lang == "de" else "Station error",
                player.last_stream_error or (
                    "Der Sender konnte nicht abgespielt werden." if lang == "de"
                    else "The station could not be played."),
            ))
            return

        if player._is_fallback:
            await ctx.send(embed=error_embed(
                "Sender nicht erreichbar" if lang == "de" else "Station unreachable",
                (f"„{genre}“ war nach mehreren Versuchen nicht erreichbar — ich spiele stattdessen "
                 f"FM4, damit trotzdem Musik läuft.") if lang == "de" else
                (f"\"{genre}\" was unreachable after several attempts — playing FM4 instead so there's "
                 f"still music."),
            ))
            return

        await ctx.send(embed=success_embed(
            f"📻 Radio-Modus: {genre}",
            "Ich spiele jetzt einen Live-Radiosender passend zum Genre, bis `/stop` oder `/radio` "
            "mit einem anderen Genre aufgerufen wird." if lang == "de"
            else "I'm now playing a live radio station for that genre until `/stop` or a new `/radio` genre.",
        ))

    @commands.hybrid_command(name="musikdiag", description="Prüft, ob Internetverbindungen zu den Radiosendern überhaupt möglich sind.")
    @commands.guild_only()
    @require_level(PermissionLevel.SERVER_ADMIN)
    async def musikdiag(self, ctx: commands.Context):
        await ctx.defer()
        lang = await get_guild_language(ctx.guild.id)

        results = []

        # Test 1: generelle Internetverbindung (unabhängig von Radiosendern) --
        # zeigt, ob der Server grundsätzlich beliebige externe Seiten erreichen
        # kann, oder ob der Hoster das blockiert (nur Discord selbst erlaubt).
        general_ok, general_detail = await self._check_url("https://www.google.com")
        results.append(("🌐 Allgemeine Internetverbindung (google.com)", general_ok, general_detail))

        for genre, url in RADIO_STREAMS.items():
            ok, detail = await self._check_url(url)
            results.append((f"📻 {genre}", ok, detail))

        embed = base_embed("🔧 Musik-Diagnose" if lang == "de" else "🔧 Music diagnostics")
        lines = []
        for name, ok, detail in results:
            icon = "✅" if ok else "❌"
            lines.append(f"{icon} **{name}** — {detail}")
        embed.description = "\n".join(lines)

        if not general_ok:
            embed.add_field(
                name="Vermutliche Ursache" if lang == "de" else "Likely cause",
                value=(
                    "Die allgemeine Verbindung schlägt schon fehl — das deutet stark darauf hin, "
                    "dass dein Hoster ausgehende Verbindungen zu fremden Servern grundsätzlich "
                    "blockiert (nur Discord selbst wäre dann erlaubt). Das müsste dann beim "
                    "Hoster-Support geklärt werden — an den Sender-URLs liegt es in dem Fall nicht."
                    if lang == "de" else
                    "The general connectivity check already fails — this strongly suggests your "
                    "host blocks outbound connections to external servers entirely (only Discord "
                    "itself allowed). That would need to be clarified with hosting support — it "
                    "would not be about the station URLs in that case."
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @staticmethod
    async def _check_url(url: str) -> tuple[bool, str]:
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status < 400:
                        return True, f"HTTP {resp.status}"
                    return False, f"HTTP {resp.status}"
        except asyncio.TimeoutError:
            return False, "Timeout (keine Antwort)"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    # ---------- Auto-Rejoin ----------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                     after: discord.VoiceState):
        # Nur reagieren, wenn es sich um DIESEN Bot handelt und er den Kanal verlassen hat/musste
        if member.id != self.bot.user.id:
            return
        if before.channel is None or after.channel is not None:
            return  # kein "Kanal verlassen"-Ereignis für den Bot

        guild_id = before.channel.guild.id
        player = get_player(guild_id)
        if not player.bound_channel_id or player.bound_channel_id != before.channel.id:
            return  # kein gebundener Kanal -> kein automatisches Rejoin gewünscht

        # Kurze Pause, dann erneut verbinden (verhindert Sofort-Loop bei absichtlichem /musikkanal clear)
        await asyncio.sleep(3)
        settings_channel_id = player.bound_channel_id
        if settings_channel_id != before.channel.id:
            return

        try:
            channel = before.channel
            player.voice_client = await channel.connect()
            log.info("Auto-Rejoin in Guild %s, Kanal %s", guild_id, channel.id)
            if player.queue and not player.voice_client.is_playing():
                await player.play_next(lambda t: self._after_track(player, t))
            else:
                # Kein wartender Track -- den zuletzt gehörten Radiosender fortsetzen
                # (funktioniert auch, wenn zwischendurch /stop aufgerufen wurde).
                await self._resume_last_radio_if_idle(guild_id, player)
        except Exception:
            log.exception("Auto-Rejoin fehlgeschlagen in Guild %s", guild_id)

    @commands.Cog.listener()
    async def on_ready(self):
        # Bei Bot-Start: falls Server einen gebundenen Musik-Kanal haben, direkt beitreten.
        from bot.database.models import GuildSettings
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(
                select(GuildSettings).where(GuildSettings.music_bound_voice_channel_id != 0)
            )
            all_settings = result.scalars().all()

        for settings in all_settings:
            guild = self.bot.get_guild(settings.guild_id)
            if not guild:
                continue
            channel = guild.get_channel(settings.music_bound_voice_channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                continue
            player = get_player(guild.id)
            player.bound_channel_id = channel.id

            # on_ready kann mehrfach feuern (z.B. nach kurzem Verbindungsabbruch zu
            # Discord) -- ohne diese Prüfung würde hier versucht, sich erneut mit
            # einem bereits verbundenen Kanal zu verbinden (Fehler "Already connected").
            if player.voice_client and player.voice_client.is_connected():
                continue

            try:
                player.voice_client = await channel.connect()
                log.info("Beim Start Musik-Kanal beigetreten: Guild %s, Kanal %s", guild.id, channel.id)
                await self._resume_last_radio_if_idle(guild.id, player)
            except Exception:
                log.exception("Konnte Musik-Kanal beim Start nicht beitreten (Guild %s)", guild.id)


async def setup(bot: commands.Bot):
    import shutil
    if shutil.which("ffmpeg") is None:
        log.warning(
            "FFmpeg wurde auf diesem Server nicht gefunden! Musik-Wiedergabe wird NICHT "
            "funktionieren, bis FFmpeg installiert ist. Bitte beim Hoster prüfen, ob FFmpeg "
            "verfügbar ist oder installiert werden kann (siehe README, Abschnitt Phase 5)."
        )
    try:
        import davey  # noqa: F401
    except ImportError:
        log.warning(
            "Das Paket 'davey' fehlt! Sprachverbindungen werden NICHT funktionieren "
            "(RuntimeError: davey library needed in order to use voice). Bitte 'davey' in "
            "requirements.txt sicherstellen und neu installieren (pip install -r requirements.txt)."
        )
    await bot.add_cog(Musik(bot))

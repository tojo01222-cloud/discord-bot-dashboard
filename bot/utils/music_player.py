"""
Kernlogik des Musiksystems. Ein MusicPlayer pro Server (Guild), verwaltet
Warteschlange, aktuellen Voice-Client und den Radio-Modus (spielt einen
echten Live-Radiosender-Stream direkt ab, siehe RADIO_STREAMS unten).

/play nutzt yt-dlp, das den rohen Audio-Stream direkt von der Quelle lädt --
nicht die normale YouTube-Player-Seite mit eingeblendeter Werbung. Ein
zusätzlicher Werbefilter ist technisch daher nicht nötig; als zusätzliche
Absicherung werden Titel mit offensichtlichen Werbe-Schlagwörtern trotzdem
übersprungen.

Werbe-Erkennung im Radio-Modus (/radio) ist EXPERIMENTELL und NICHT
garantiert zuverlässig -- siehe Docstring von _ad_watch_loop() weiter unten.

WICHTIGE ERKENNTNIS aus echten Tests: Manche Sender-Streams hängen sich bei
FFmpeg intern in einer endlosen Reconnect-Schleife auf (FFmpeg meldet
"Stream ends prematurely" und versucht ewig weiter, OHNE den Prozess zu
beenden) -- ein einfacher "nach dem Prozessende zählen"-Ansatz erkennt das
NICHT, weil der Prozess ja nie endet. Deshalb gibt es jetzt einen echten
Bytes-Wächter (siehe _MonitoredSource/_start_stream): läuft ein Stream 8
Sekunden, ohne auch nur ein einziges Byte Audio zu liefern, wird er als
gescheitert gewertet und aktiv abgebrochen.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field

import aiohttp
import discord
import yt_dlp

log = logging.getLogger("bot.music")

YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extract_flat": False,
}

FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# Lautstärke-Verstärkung (1.0 = normal, 2.0 = doppelt so laut). Bei sehr
# lauten Passagen kann es dadurch zu leichten Verzerrungen kommen -- das ist
# eine unvermeidbare Nebenwirkung von digitaler Verstärkung über den
# ursprünglichen Pegel hinaus.
VOLUME_MULTIPLIER = 2.0

# Wie lange (Sekunden) ein neu gestarteter Stream Zeit hat, mindestens EIN
# Byte Audiodaten zu liefern, bevor er als gescheitert gilt.
STARTUP_WATCHDOG_SECONDS = 8

# Nach wie vielen gescheiterten Versuchen IN FOLGE der Radio-Modus für ein
# Genre komplett aufgibt (statt endlos weiterzuversuchen).
MAX_CONSECUTIVE_FAILURES = 3

# Schlagwörter, bei denen ein YouTube-Suchergebnis übersprungen wird
# (Sicherheitsnetz, siehe Modul-Docstring oben).
AD_KEYWORDS = ("sponsored", "werbung", "advertisement", "promo code")

# Schlagwörter für die EXPERIMENTELLE Werbe-Erkennung im Radio-Modus, siehe
# _ad_watch_loop(). Mehrsprachig, da sowohl österreichische als auch
# italienische Sender dabei sind.
AD_TITLE_KEYWORDS = (
    "werbung", "spot", "advertisement", "commercial", "sponsor", "anzeige",
    "pubblicità", "pubblicita", "publicidad",
)

# Echte Radiosender-Streams statt YouTube-Suche für den Radio-Modus.
#
# WICHTIG: Diese Adressen wurden aus aktuellen Sender-Listen im Web
# übernommen, aber NICHT live von hier aus getestet (keine
# Internetverbindung in dieser Umgebung möglich). electro/techno/hiphop/
# pop/chill nutzen FM4 bzw. Ö3 (ORF, offizielle Quelle -- höheres
# Vertrauen). Die restlichen sind Bonus-Sender aus sekundären Quellen.
# .m3u/.pls-Adressen werden jetzt automatisch aufgelöst (siehe
# _resolve_stream_url), das behebt das Energy-Problem strukturell.
RADIO_STREAMS = {
    "electro": "https://orf-live.ors-shoutcast.at/fm4-q2a",
    "techno": "https://orf-live.ors-shoutcast.at/fm4-q2a",
    "hiphop": "https://orf-live.ors-shoutcast.at/fm4-q2a",
    "pop": "https://orf-live.ors-shoutcast.at/oe3-q2a",
    "chill": "https://orf-live.ors-shoutcast.at/fm4-q2a",
    "energy": "http://stream1.energy.at:8000/vie.m3u",
    "kronehit": "http://onair.krone.at/kronehit.mp3",
    "886": "http://radio886.at/streams/radio_88.6/mp3",
    "arabella": "https://edge05.streams.arabella.at/arabella-wien",
    "italopop": "http://mp3.kataweb.it:8000/RadioDeejay",
    "italohiphop": "http://shoutcast.unitedradio.it:1113/listen.pls",
}

_ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)


@dataclass
class Track:
    title: str
    url: str
    stream_url: str
    requested_by: int


class _MonitoredSource(discord.FFmpegPCMAudio):
    """FFmpegPCMAudio, das mitzählt, ob und wie viele Audio-Bytes tatsächlich
    ankommen. Damit lässt sich ein Stream erkennen, der intern (in FFmpeg
    selbst) endlos hängt, ohne dass der FFmpeg-Prozess je beendet wird --
    genau das Verhalten, das beim echten Test beobachtet wurde."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_bytes = 0

    def read(self) -> bytes:
        data = super().read()
        if data:
            self.total_bytes += len(data)
        return data


async def _resolve_stream_url(url: str) -> str:
    """Löst .m3u/.m3u8/.pls-Playlist-Zeiger-Dateien zur tatsächlichen
    Stream-Adresse auf. Viele ältere Icecast/Shoutcast-Sender (z.B. Energy)
    geben nur einen Zeiger auf die echte Adresse heraus, den FFmpeg nicht
    zuverlässig automatisch auflöst."""
    lower = url.lower()
    if not (lower.endswith(".m3u") or lower.endswith(".m3u8") or lower.endswith(".pls")):
        return url

    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                text = await resp.text(errors="ignore")
    except Exception:
        log.warning("Konnte Playlist-Datei nicht auflösen, nutze Original-URL: %s", url)
        return url

    if lower.endswith(".pls"):
        # Format: File1=http://... (INI-artig)
        match = re.search(r"File\d*=(\S+)", text)
        if match:
            return match.group(1).strip()
    else:
        # .m3u/.m3u8: erste Zeile, die mit http beginnt und kein Kommentar ist
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("http"):
                return line

    log.warning("Playlist-Datei enthielt keine erkennbare Stream-URL, nutze Original: %s", url)
    return url


def _pick_backup_stream(current_genre: str) -> str | None:
    """Wählt einen anderen Sender als vorübergehenden Ersatz (siehe _ad_watch_loop)."""
    current_url = RADIO_STREAMS.get(current_genre)
    for genre, url in RADIO_STREAMS.items():
        if url != current_url:
            return url
    return None


async def _fetch_icy_stream_title(url: str) -> str | None:
    """Fragt einmalig die ICY-Metadaten (aktueller Songtitel) eines
    Radio-Streams ab. Gibt None zurück, wenn der Sender keine ICY-Metadaten
    unterstützt oder die Abfrage fehlschlägt (kein Fehler, einfach 'unbekannt')."""
    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {"Icy-MetaData": "1", "User-Agent": "Mozilla/5.0"}
            async with session.get(url, headers=headers) as resp:
                metaint = resp.headers.get("icy-metaint")
                if not metaint:
                    return None
                metaint = int(metaint)
                await resp.content.readexactly(metaint)
                length_byte = await resp.content.readexactly(1)
                meta_length = length_byte[0] * 16
                if meta_length == 0:
                    return None
                meta_data = await resp.content.readexactly(meta_length)
                text = meta_data.decode("utf-8", errors="ignore")
                match = re.search(r"StreamTitle='([^']*)'", text)
                return match.group(1) if match else None
    except Exception:
        return None


@dataclass
class MusicPlayer:
    guild_id: int
    bound_channel_id: int = 0
    voice_client: discord.VoiceClient | None = None
    queue: list[Track] = field(default_factory=list)
    radio_genre: str | None = None
    text_channel_id: int = 0  # wohin "Jetzt spielt"-Nachrichten gehen
    _active_stream_url: str | None = field(default=None, repr=False)
    _ad_watch_task: asyncio.Task | None = field(default=None, repr=False)
    _play_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _consecutive_failures: int = field(default=0, repr=False)
    last_stream_error: str | None = field(default=None, repr=False)

    async def extract_track(self, query: str, requested_by: int) -> Track | None:
        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(None, lambda: _ytdl.extract_info(query, download=False))
        except Exception:
            log.exception("yt-dlp Fehler bei Query: %s", query)
            return None

        if data is None:
            return None
        if "entries" in data:  # Suchergebnis-Liste
            entries = [e for e in data["entries"] if e]
            if not entries:
                return None
            data = entries[0]

        title = data.get("title", "Unbekannter Titel")
        if any(kw in title.lower() for kw in AD_KEYWORDS):
            return None

        stream_url = data.get("url")
        webpage_url = data.get("webpage_url", query)
        if not stream_url:
            return None

        return Track(title=title, url=webpage_url, stream_url=stream_url, requested_by=requested_by)

    async def add_and_maybe_play(self, track: Track, after_play_callback) -> None:
        self.radio_genre = None  # ein manueller /play-Befehl unterbricht den Radio-Modus
        self._cancel_ad_watch()
        self.queue.append(track)
        if self.voice_client and not self.voice_client.is_playing() and not self.voice_client.is_paused():
            await self.play_next(after_play_callback)

    async def play_next(self, after_play_callback) -> None:
        if not self.queue:
            return

        track = self.queue.pop(0)
        if not self.voice_client or not self.voice_client.is_connected():
            return

        monitored = _MonitoredSource(track.stream_url, **FFMPEG_OPTS)
        source = discord.PCMVolumeTransformer(monitored, volume=VOLUME_MULTIPLIER)

        loop = asyncio.get_running_loop()

        def _after(error):
            if error:
                log.error("Fehler nach Wiedergabe: %s", error)
            asyncio.run_coroutine_threadsafe(after_play_callback(track), loop)

        self.voice_client.play(source, after=_after)
        asyncio.create_task(self._startup_watchdog(monitored, self.voice_client))

    async def play_radio_stream(self, genre: str) -> bool:
        """Spielt einen echten Radiosender-Stream direkt ab (siehe RADIO_STREAMS)
        und startet die experimentelle Werbe-Erkennung dafür (siehe _ad_watch_loop)."""
        if genre not in RADIO_STREAMS or not self.voice_client or not self.voice_client.is_connected():
            return False

        self.queue.clear()  # Radio-Modus ersetzt eine eventuell laufende Warteschlange
        self.radio_genre = genre
        self._consecutive_failures = 0
        self.last_stream_error = None
        self._cancel_ad_watch()
        await self._start_stream(RADIO_STREAMS[genre])
        self._ad_watch_task = asyncio.create_task(self._ad_watch_loop(genre))
        return True

    async def _start_stream(self, raw_url: str) -> None:
        """Löst die URL auf (falls .m3u/.pls), spielt sie ab, überwacht per
        Bytes-Wächter, ob überhaupt Audio ankommt, und gibt nach
        MAX_CONSECUTIVE_FAILURES gescheiterten Versuchen sauber auf, statt
        endlos weiterzuversuchen."""
        async with self._play_lock:
            if not self.voice_client or not self.voice_client.is_connected():
                return

            stream_url = await _resolve_stream_url(raw_url)
            self._active_stream_url = raw_url  # der "logische" (unaufgelöste) Sender-Schlüssel
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()

            monitored = _MonitoredSource(stream_url, **FFMPEG_OPTS)
            source = discord.PCMVolumeTransformer(monitored, volume=VOLUME_MULTIPLIER)
            loop = asyncio.get_running_loop()

            def _after(error):
                if error:
                    log.error("Radio-Stream-Fehler: %s", error)
                if self.radio_genre and self.voice_client and self.voice_client.is_connected():
                    asyncio.run_coroutine_threadsafe(self._start_stream(raw_url), loop)

            self.voice_client.play(source, after=_after)
            asyncio.create_task(self._radio_startup_watchdog(monitored, raw_url))

    async def _startup_watchdog(self, source: _MonitoredSource, voice_client: discord.VoiceClient) -> None:
        """Für /play (einzelne Tracks): bricht ab, wenn nach STARTUP_WATCHDOG_SECONDS
        kein einziges Byte Audio angekommen ist."""
        await asyncio.sleep(STARTUP_WATCHDOG_SECONDS)
        if source.total_bytes == 0 and voice_client.is_playing():
            log.warning("Track liefert nach %ss keine Audiodaten -- breche ab.", STARTUP_WATCHDOG_SECONDS)
            voice_client.stop()

    async def _radio_startup_watchdog(self, source: _MonitoredSource, raw_url: str) -> None:
        """Für /radio: derselbe Bytes-Check, zählt aber zusätzlich Fehlschläge
        und gibt nach MAX_CONSECUTIVE_FAILURES komplett auf."""
        await asyncio.sleep(STARTUP_WATCHDOG_SECONDS)
        if self._active_stream_url != raw_url:
            return  # inzwischen ein anderer Sender/Genre aktiv -> dieser Check ist überholt
        if source.total_bytes > 0:
            self._consecutive_failures = 0  # lief erfolgreich an
            return

        self._consecutive_failures += 1
        log.warning(
            "Radiosender %s liefert nach %ss keine Audiodaten (Versuch %d/%d).",
            raw_url, STARTUP_WATCHDOG_SECONDS, self._consecutive_failures, MAX_CONSECUTIVE_FAILURES,
        )

        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            self.last_stream_error = f"Sender nicht erreichbar (nach {MAX_CONSECUTIVE_FAILURES} Versuchen): {raw_url}"
            log.error("Radio-Modus wird beendet: %s", self.last_stream_error)
            self.radio_genre = None
            self._cancel_ad_watch()

        if self.voice_client and self.voice_client.is_connected():
            self.voice_client.stop()  # bricht den hängenden FFmpeg-Prozess aktiv ab

    def _cancel_ad_watch(self) -> None:
        if self._ad_watch_task and not self._ad_watch_task.done():
            self._ad_watch_task.cancel()
        self._ad_watch_task = None

    async def _ad_watch_loop(self, genre: str) -> None:
        """EXPERIMENTELL, KEINE GARANTIE: fragt alle 20 Sekunden die
        ICY-Metadaten (Songtitel) des aktuellen Radio-Streams ab. Enthält der
        Titel ein typisches Werbe-Schlagwort, wird für ca. 75 Sekunden auf
        einen anderen Sender gewechselt, danach automatisch zurück.
        Grenzen: funktioniert nur bei Sendern mit aussagekräftigen
        ICY-Metadaten, keine Erkennungsgarantie."""
        try:
            while self.radio_genre == genre and self.voice_client and self.voice_client.is_connected():
                await asyncio.sleep(20)
                if self.radio_genre != genre:
                    return
                title = await _fetch_icy_stream_title(await _resolve_stream_url(self._active_stream_url or ""))
                if title and any(kw in title.lower() for kw in AD_TITLE_KEYWORDS):
                    backup_url = _pick_backup_stream(genre)
                    if backup_url and backup_url != self._active_stream_url:
                        log.info("Mögliche Werbung erkannt (Titel: %r) -- wechsle Sender temporär.", title)
                        await self._start_stream(backup_url)
                        await asyncio.sleep(75)
                        if self.radio_genre == genre:
                            await self._start_stream(RADIO_STREAMS[genre])
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Fehler in der Werbe-Erkennung (Radio-Modus)")

    def skip(self) -> bool:
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()
            return True
        return False

    def stop_and_clear(self) -> None:
        self.queue.clear()
        self.radio_genre = None
        self._cancel_ad_watch()
        if self.voice_client:
            self.voice_client.stop()


_players: dict[int, MusicPlayer] = {}


def get_player(guild_id: int) -> MusicPlayer:
    if guild_id not in _players:
        _players[guild_id] = MusicPlayer(guild_id=guild_id)
    return _players[guild_id]

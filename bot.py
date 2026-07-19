"""
Einstiegspunkt für Pterodactyl/racehost.eu.

Das Bot-Hosting-Egg führt immer eine Datei namens 'bot.py' im Hauptverzeichnis
aus (siehe Variable "APP PY FILE" im Startup-Tab). Der eigentliche Bot-Code
liegt aber strukturiert im Paket bot/ (bot/main.py, bot/cogs/, ...), da er
aus mehreren zusammenhängenden Dateien besteht.

Diese Datei ist nur eine dünne Weiterleitung: sie ruft bot/main.py auf,
ohne den Code zu duplizieren. Nicht verändern nötig.
"""
import asyncio

from bot.main import main

if __name__ == "__main__":
    asyncio.run(main())

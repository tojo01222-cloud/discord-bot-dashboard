"""
Einfaches DE/EN Sprachsystem. Jeder Server hat eine eigene Sprache
(gespeichert in GuildSettings.language), der Bot-Owner setzt beim
Hinzufügen des Bots einen Standardwert über DEFAULT_LANGUAGE in .env.

Benutzung in einem Cog:
    text = t("moderation.kick_success", lang, user=member.display_name)
"""

TRANSLATIONS: dict[str, dict[str, str]] = {
    "de": {
        "no_permission": "❌ Du hast keine Berechtigung für diesen Befehl.",
        "moderation.kick_success": "✅ {user} wurde gekickt.",
        "moderation.ban_success": "✅ {user} wurde gebannt.",
        "moderation.unban_success": "✅ {user_id} wurde entbannt.",
        "moderation.timeout_success": "✅ {user} wurde für {duration} in Timeout gesetzt.",
        "moderation.warn_added": "✅ {user} hat eine Verwarnung erhalten. (Grund: {reason})",
        "moderation.warn_removed": "✅ Verwarnung #{id} wurde entfernt.",
        "moderation.warn_none": "ℹ️ {user} hat keine aktiven Verwarnungen.",
        "moderation.warn_list_title": "⚠️ Verwarnungen von {user}",
        "moderation.cannot_moderate_self": "❌ Du kannst diesen Befehl nicht gegen dich selbst ausführen.",
        "moderation.cannot_moderate_higher": "❌ Diese Person hat eine höhere oder gleiche Rolle wie du.",
        "team.rank_added": "✅ Team-Rang {role} auf Position {position} hinzugefügt.",
        "team.rank_removed": "✅ Team-Rang entfernt.",
        "team.rank_list_title": "👥 Team-Ränge (niedrig → hoch)",
        "team.rank_none": "ℹ️ Für diesen Server sind noch keine Team-Ränge eingerichtet. Nutze `/teamrank add`.",
        "team.uprank_success": "⬆️ {user} wurde befördert zu **{rank}**.",
        "team.downrank_success": "⬇️ {user} wurde zurückgestuft zu **{rank}**.",
        "team.uprank_already_top": "❌ {user} hat bereits den höchsten Rang.",
        "team.downrank_already_bottom": "❌ {user} hat bereits den niedrigsten Rang / ist nicht im Team.",
        "team.not_in_team": "❌ {user} ist kein Teammitglied.",
        "team.teamkick_success": "✅ {user} wurde aus dem Team entfernt. (Grund: {reason})",
        "team.teamliste_title": "👥 Teamliste",
        "team.teamliste_empty": "ℹ️ Das Team ist aktuell leer.",
        "security.antinuke_enabled": "🛡️ Anti-Nuke ist jetzt **aktiviert**.",
        "security.antinuke_disabled": "🛡️ Anti-Nuke ist jetzt **deaktiviert**.",
        "security.antispam_enabled": "🛡️ Anti-Spam ist jetzt **aktiviert**.",
        "security.antispam_disabled": "🛡️ Anti-Spam ist jetzt **deaktiviert**.",
        "security.status_title": "🛡️ Sicherheitsstatus",
        "security.trusted_added": "✅ {user} wurde zur Anti-Nuke-Whitelist hinzugefügt.",
        "security.trusted_already": "ℹ️ {user} ist bereits auf der Whitelist.",
        "security.trusted_removed": "✅ {user} wurde von der Anti-Nuke-Whitelist entfernt.",
        "security.trusted_not_found": "❌ {user} war nicht auf der Whitelist.",
        "security.trusted_list_title": "🛡️ Anti-Nuke-Whitelist",
        "security.trusted_list_empty": "ℹ️ Die Whitelist ist leer.",
        "security.nuke_alert_title": "🚨 Anti-Nuke ausgelöst",
        "security.nuke_alert_desc": "{user} hat verdächtig viele destruktive Aktionen ausgeführt ({action}) und wurde automatisch eingeschränkt (alle Rollen entfernt).",
        "security.spam_alert_desc": "{user} wurde wegen Spam automatisch in Timeout gesetzt.",
        "help.title": "📖 Befehlsübersicht",
        "serverinfo.title": "ℹ️ Server-Info",
    },
    "en": {
        "no_permission": "❌ You don't have permission to use this command.",
        "moderation.kick_success": "✅ {user} was kicked.",
        "moderation.ban_success": "✅ {user} was banned.",
        "moderation.unban_success": "✅ {user_id} was unbanned.",
        "moderation.timeout_success": "✅ {user} was timed out for {duration}.",
        "moderation.warn_added": "✅ {user} received a warning. (Reason: {reason})",
        "moderation.warn_removed": "✅ Warning #{id} was removed.",
        "moderation.warn_none": "ℹ️ {user} has no active warnings.",
        "moderation.warn_list_title": "⚠️ Warnings for {user}",
        "moderation.cannot_moderate_self": "❌ You can't use this command on yourself.",
        "moderation.cannot_moderate_higher": "❌ That person has an equal or higher role than you.",
        "team.rank_added": "✅ Team rank {role} added at position {position}.",
        "team.rank_removed": "✅ Team rank removed.",
        "team.rank_list_title": "👥 Team ranks (low → high)",
        "team.rank_none": "ℹ️ No team ranks set up yet for this server. Use `/teamrank add`.",
        "team.uprank_success": "⬆️ {user} was promoted to **{rank}**.",
        "team.downrank_success": "⬇️ {user} was demoted to **{rank}**.",
        "team.uprank_already_top": "❌ {user} already has the highest rank.",
        "team.downrank_already_bottom": "❌ {user} already has the lowest rank / isn't on the team.",
        "team.not_in_team": "❌ {user} is not a team member.",
        "team.teamkick_success": "✅ {user} was removed from the team. (Reason: {reason})",
        "team.teamliste_title": "👥 Team list",
        "team.teamliste_empty": "ℹ️ The team is currently empty.",
        "security.antinuke_enabled": "🛡️ Anti-Nuke is now **enabled**.",
        "security.antinuke_disabled": "🛡️ Anti-Nuke is now **disabled**.",
        "security.antispam_enabled": "🛡️ Anti-Spam is now **enabled**.",
        "security.antispam_disabled": "🛡️ Anti-Spam is now **disabled**.",
        "security.status_title": "🛡️ Security status",
        "security.trusted_added": "✅ {user} was added to the anti-nuke whitelist.",
        "security.trusted_already": "ℹ️ {user} is already on the whitelist.",
        "security.trusted_removed": "✅ {user} was removed from the anti-nuke whitelist.",
        "security.trusted_not_found": "❌ {user} was not on the whitelist.",
        "security.trusted_list_title": "🛡️ Anti-nuke whitelist",
        "security.trusted_list_empty": "ℹ️ The whitelist is empty.",
        "security.nuke_alert_title": "🚨 Anti-nuke triggered",
        "security.nuke_alert_desc": "{user} performed a suspicious number of destructive actions ({action}) and was automatically restricted (all roles removed).",
        "security.spam_alert_desc": "{user} was automatically timed out for spamming.",
        "help.title": "📖 Command Overview",
        "serverinfo.title": "ℹ️ Server Info",
    },
}


def t(key: str, lang: str = "de", **kwargs) -> str:
    lang = lang if lang in TRANSLATIONS else "de"
    template = TRANSLATIONS[lang].get(key) or TRANSLATIONS["de"].get(key, key)
    return template.format(**kwargs) if kwargs else template

"""
Übersetzungen für die WEBSITE selbst (Startseite, Apply, News, Login,
Serverliste) -- getrennt von bot/utils/i18n.py, das die Antworten des
Discord-Bots übersetzt. Englisch ist der Standard, wie gewünscht.

Deckt aktuell die öffentlichen/allgemeinen Seiten ab (die nicht an einen
bestimmten Server gebunden sind). Die servergebundenen Einstellungsseiten
(z.B. settings.html) haben weiterhin ihre eigene Sprachsteuerung pro Server
(GuildSettings.language, siehe bot/utils/i18n.py) -- eine komplette
Übersetzung aller ~46 Templates ist ein größeres, eigenständiges Vorhaben.
"""

WEB_TRANSLATIONS = {
    "en": {
        "nav_apply": "Apply",
        "nav_news": "News",
        "nav_admin_panel": "Admin Panel",
        "nav_logout": "Logout",
        "footer_join_discord": "Join our Discord",

        "landing_title": "Your Discord Bot, fully in control",
        "landing_subtitle": "Moderation, team management, music, tickets, applications and more — "
                             "all in one place, for every server where you're an admin.",
        "landing_btn_dashboard": "Go to Server Dashboard",
        "landing_btn_admin": "Go to Admin Area",

        "feature1_title": "Moderation & Security",
        "feature1_desc": "Anti-Nuke, Anti-Spam, Anti-Hack, Anti-Advertising, team ranks and a full "
                          "punishment register — all configurable.",
        "feature2_title": "Music & Radio",
        "feature2_desc": "YouTube playback and real live radio stations, always on in your voice channel.",
        "feature3_title": "Tickets & Waiting Room",
        "feature3_desc": "Professional support panels with multiple designs and automatic help detection.",
        "feature4_title": "Application System",
        "feature4_desc": "Your own application forms for your team — applicants fill them out right here.",
        "feature5_title": "Level & Community",
        "feature5_desc": "XP system, invite tracking and giveaways — make activity on your server visible.",
        "feature6_title": "Multilingual & Autorole",
        "feature6_desc": "German or English per server, automatic role assignment for members, bots and admins separately.",

        "apply_title": "Apply for our Team",
        "apply_subtitle": "Want to help out? You can apply to join our team directly on our Discord "
                           "server — our staff reviews every application personally.",
        "apply_btn": "Join our Discord & Apply",
        "apply_step1_title": "Join the Discord",
        "apply_step1_desc": "Click the button above to join our official Discord server.",
        "apply_step2_title": "Find the Application",
        "apply_step2_desc": "Look for our application channel or ticket system, or check the server "
                             "dashboard for an application form.",
        "apply_step3_title": "Get Reviewed",
        "apply_step3_desc": "Our team reviews applications personally and will get back to you.",

        "news_title": "News",
        "news_empty": "No news yet.",

        "login_title": "Sign in",
        "login_subtitle": "Sign in with Discord to manage your servers.",
        "login_btn": "Sign in with Discord",

        "guilds_title": "Your Servers",
        "guilds_subtitle": "Servers where you have admin rights:",
        "guilds_manage_btn": "Manage",
        "guilds_invite_btn": "Invite Bot",
        "guilds_empty": "You don't have anything to manage on any server the bot knows or where you're an admin.",

        "lang_switch_label": "Language",
    },
    "de": {
        "nav_apply": "Bewerben",
        "nav_news": "News",
        "nav_admin_panel": "Admin-Panel",
        "nav_logout": "Logout",
        "footer_join_discord": "Unserem Discord beitreten",

        "landing_title": "Dein Discord-Bot, komplett un

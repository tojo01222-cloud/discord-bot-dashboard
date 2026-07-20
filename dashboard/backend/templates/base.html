<!DOCTYPE html>
<html lang="{{ site_lang|default('en') }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Bot Dashboard{% endblock %}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header class="topbar">
        <div class="topbar-inner">
            <a href="/" class="brand">Bot Dashboard</a>
            <nav style="display:flex; align-items:center; gap:18px;">
                <a href="/apply" class="logout-link" style="font-weight:700;">✨ {{ wt(site_lang, 'nav_apply') }}</a>
                <a href="/news" class="logout-link">{{ wt(site_lang, 'nav_news') }}</a>
                <a href="/set-site-language?lang={{ 'de' if site_lang == 'en' else 'en' }}&next={{ request.url.path }}"
                   class="logout-link" title="{{ wt(site_lang, 'lang_switch_label') }}">
                    {{ '🇩🇪 DE' if site_lang == 'en' else '🇬🇧 EN' }}
                </a>
                {% if user %}
                <div class="user-chip">
                    {% if user.avatar_hash %}
                    <img src="https://cdn.discordapp.com/avatars/{{ user.discord_id }}/{{ user.avatar_hash }}.png" alt="">
                    {% endif %}
                    <span>{{ user.username }}</span>
                    <a href="/admin/login" class="logout-link" style="margin-left:14px;">{{ wt(site_lang, 'nav_admin_panel') }}</a>
                    <a href="/logout" class="logout-link">{{ wt(site_lang, 'nav_logout') }}</a>
                </div>
                {% endif %}
            </nav>
        </div>
    </header>
    <main class="content">
        {% for message in messages %}
        <div class="flash flash-{{ message.type }}">{{ message.text }}</div>
        {% endfor %}
        {% block content %}{% endblock %}
    </main>
    <footer style="text-align:center; padding:24px; font-size:12px; color:#9297ab;">
        {% if operator_invite %}
        <a href="{{ operator_invite }}" target="_blank" class="btn btn-small btn-ghost" style="margin-bottom:12px; display:inline-block;">{{ wt(site_lang, 'footer_join_discord') }}</a>
        <br>
        {% endif %}
        <a href="/impressum" style="color:#9297ab;">Impressum</a> ·
        <a href="/datenschutz" style="color:#9297ab;">Datenschutz</a>
    </footer>
</body>
</html>

{% extends "base.html" %}
{% block title %}Deine Server — Bot Dashboard{% endblock %}
{% block content %}
<h1>Deine Server</h1>
<p>Server, auf denen du Admin-Rechte hast:</p>

<div class="guild-grid">
    {% for guild in manageable_guilds %}
    <div class="guild-card {% if not guild.bot_present %}guild-card-disabled{% endif %}">
        {% if guild.icon %}
        <img src="https://cdn.discordapp.com/icons/{{ guild.id }}/{{ guild.icon }}.png" alt="">
        {% else %}
        <div class="guild-icon-placeholder">{{ guild.name[0] }}</div>
        {% endif %}
        <span class="guild-name">{{ guild.name }}</span>
        {% if guild.bot_present %}
        <a href="/dashboard/{{ guild.id }}" class="btn btn-small">Verwalten</a>
        {% else %}
        <a href="{{ invite_url }}&guild_id={{ guild.id }}" target="_blank" class="btn btn-small btn-ghost">Bot einladen</a>
        {% endif %}
    </div>
    {% else %}
    <p>Du hast auf keinem Server, den der Bot kennt oder auf dem du Admin bist, etwas zu verwalten.</p>
    {% endfor %}
</div>
{% endblock %}

{% extends "base.html" %}
{% block title %}Economy — {{ guild.name }}{% endblock %}
{% block content %}
<a href="/dashboard/{{ guild.id }}" class="back-link">← Zurück zu den Einstellungen</a>
<h1>Economy — {{ guild.name }}</h1>

<h2>Leaderboard (Top 25)</h2>
{% for e in top %}
<div style="padding:8px 0; border-bottom:1px solid #262838;">{{ loop.index }}. Discord-ID {{ e.user_id }} — {{ e.balance }} Coins</div>
{% else %}
<p style="color:#9297ab;">Noch keine Daten.</p>
{% endfor %}

<h2 style="margin-top:32px;">Shop ({{ items|length }})</h2>
{% for i in items %}
<div style="display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid #262838;">
    <span><strong>{{ i.name }}</strong> — {{ i.price }} Coins{% if i.role_id %} (Rolle: {{ i.role_id }}){% endif %}</span>
    <form method="post" action="/dashboard/{{ guild.id }}/economy/shop/{{ i.id }}/loeschen">
        <button type="submit" class="btn btn-small btn-ghost">Entfernen</button>
    </form>
</div>
{% else %}
<p style="color:#9297ab;">Der Shop ist leer.</p>
{% endfor %}

<form method="post" action="/dashboard/{{ guild.id }}/economy/shop" class="settings-form" style="margin-top:20px;">
    <div class="field"><label>Name</label><input type="text" name="name" required></div>
    <div class="field"><label>Preis (Coins)</label><input type="number" name="price" min="1" required></div>
    <div class="field">
        <label>Rolle (optional, wird beim Kauf vergeben)</label>
        <select name="role_id">
            <option value="0">— keine Rolle —</option>
            {% for role in roles %}
            <option value="{{ role.id }}">{{ role.name }}</option>
            {% endfor %}
        </select>
    </div>
    <button type="submit" class="btn btn-small">Item hinzufügen</button>
</form>
{% endblock %}

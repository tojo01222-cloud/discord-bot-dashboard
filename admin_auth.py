{% extends "admin_base.html" %}
{% block title %}Zwei-Faktor-Login — Admin-Panel{% endblock %}
{% block content %}
<h1>Zwei-Faktor-Login (2FA)</h1>

<div class="admin-card">
    <p><strong>Status:</strong> {{ "✅ Aktiv" if enabled else "❌ Inaktiv" }}</p>

    {% if not enabled %}
    <h2 style="margin-top:16px; margin-bottom:8px;">Einrichten</h2>
    <p style="color:#9297ab; font-size:13px;">
        Füge dieses Geheimnis manuell in deine Authenticator-App ein (Google Authenticator, Authy usw.):
    </p>
    <code style="display:block; background:#0d0819; padding:10px; border-radius:8px; margin:10px 0; word-break:break-all;">{{ secret }}</code>
    <p style="color:#9297ab; font-size:12px;">Oder trag diesen Link manuell ein: <code>{{ provisioning_uri }}</code></p>

    <form method="post" action="/admin/2fa/aktivieren" class="admin-form" style="margin-top:16px;">
        <div>
            <label for="code">Bestätigungscode aus der App</label>
            <input type="text" id="code" name="code" required maxlength="6" pattern="[0-9]{6}">
        </div>
        <button type="submit" class="btn btn-small">Aktivieren</button>
    </form>
    {% else %}
    <form method="post" action="/admin/2fa/deaktivieren" style="margin-top:12px;">
        <button type="submit" class="btn btn-small btn-ghost">2FA deaktivieren</button>
    </form>
    {% endif %}
</div>
{% endblock %}

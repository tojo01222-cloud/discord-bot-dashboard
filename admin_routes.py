{% extends "base.html" %}
{% block title %}News{% endblock %}
{% block content %}
<a href="/" class="back-link">← Zurück</a>
<h1>News</h1>

{% if not posts %}
<p style="color:#9297ab;">Noch keine News.</p>
{% else %}
<div style="display:flex; flex-direction:column; gap:18px; margin-top:24px;">
    {% for post in posts %}
    <div class="feature-card">
        <h3>{{ post.title }}</h3>
        <p style="color:#9297ab; font-size:12px; margin-bottom:10px;">{{ post.created_at.strftime('%d.%m.%Y %H:%M') }}</p>
        <p style="color:#f5f6fa;">{{ post.content }}</p>
    </div>
    {% endfor %}
</div>
{% endif %}
{% endblock %}

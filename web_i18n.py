* { box-sizing: border-box; }
:root {
    --accent: #7c5cff;
    --accent2: #eb459e;
    --accent3: #22d3a8;
    --accent4: #f5a623;
    --bg: #0d0819;
    --bg-card: #17102a;
    --border: #2c2148;
    --text: #f5f6fa;
    --text-dim: #a29bc4;
}
html {
    overflow-x: hidden;
    width: 100%;
}
body {
    margin: 0;
    overflow-x: hidden;
    width: 100%;
    max-width: 100vw;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    background:
        radial-gradient(circle at 15% -10%, rgba(88,101,242,0.30), transparent 45%),
        radial-gradient(circle at 90% 5%, rgba(235,69,158,0.22), transparent 42%),
        radial-gradient(circle at 50% 100%, rgba(34,211,168,0.14), transparent 50%),
        var(--bg);
    color: var(--text);
    min-height: 100vh;
    line-height: 1.55;
}
.topbar {
    background: rgba(20,21,31,0.85);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 10;
}
.topbar-inner {
    max-width: 1100px;
    margin: 0 auto;
    padding: 14px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
}
.page-name {
    display: flex; align-items: center; gap: 10px;
    font-size: 17px; font-weight: 700; color: var(--text);
}
.brand-dot { color: var(--accent); text-decoration: none; font-size: 20px; transition: transform 0.2s ease; }
.brand-dot:hover { transform: scale(1.3); }
.nav-right { display: flex; align-items: center; gap: 14px; }
.lang-select {
    background: transparent; color: var(--text-dim); border: 1px solid var(--border);
    border-radius: 6px; padding: 5px 8px; font-size: 13px; cursor: pointer;
}
.btn-logout {
    display: flex; align-items: center; gap: 6px;
    background: rgba(255,255,255,0.05); border: 1px solid var(--border);
    color: var(--text-dim); text-decoration: none; font-size: 13px; font-weight: 600;
    padding: 7px 14px; border-radius: 8px;
    transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease;
}
.btn-logout:hover { background: rgba(235,69,158,0.15); color: #ff8dc6; border-color: #ff8dc6; }
@media (max-width: 720px) {
    .user-name-desktop-only { display: none; }
    .btn-logout span:last-child { display: none; }
    .page-name {
        font-size: 14px; overflow: hidden; text-overflow: ellipsis;
        white-space: nowrap; max-width: 40vw;
    }
    .topbar-inner { flex-wrap: nowrap; }
    .nav-right { flex-shrink: 0; gap: 8px; }
    .lang-select { padding: 4px 6px; font-size: 12px; }
    .hero h1 { font-size: 28px; }
    .hero { padding: 60px 16px 40px; }
    .content { padding: 24px 16px; }
    .feature-grid, .guild-grid, .overview-grid, .benefits-row { grid-template-columns: 1fr; }
    .legal-table th { width: auto; min-width: 110px; font-size: 12px; }
    .legal-table td { font-size: 12px; }
    .admin-stat-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 420px) {
    .page-name { max-width: 32vw; }
    .user-chip img { width: 26px; height: 26px; }
}
.brand {
    color: #fff;
    text-decoration: none;
    font-weight: 800;
    font-size: 20px;
    letter-spacing: -0.4px;
    background: linear-gradient(90deg, #fff 20%, #b6c0ff 60%, #ffb3de 100%);
    -webkit-background-clip: text;
    background-clip: text;
}
.user-chip { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.user-chip img { width: 32px; height: 32px; border-radius: 50%; border: 2px solid var(--accent); }
.logout-link { color: var(--text-dim); text-decoration: none; margin-left: 10px; transition: color 0.15s; }
.site-footer {
    text-align: center; padding: 40px 24px 28px; margin-top: 40px;
    border-top: 1px solid var(--border);
}
.site-footer > .btn { margin-bottom: 18px; display: inline-block; }
.footer-links { display: flex; justify-content: center; gap: 22px; margin: 16px 0 10px; flex-wrap: wrap; }
.footer-links a { color: var(--text-dim); text-decoration: none; font-size: 13px; transition: color 0.15s ease; }
.footer-links a:hover { color: var(--text); }
.footer-copyright { color: #a29bc4; font-size: 12px; }
.logout-link:hover { color: var(--accent2); }
.legal-table-wrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
.content {
    max-width: 1100px; margin: 0 auto; padding: 40px 24px;
    animation: fadeInUp 0.35s ease both;
}
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}
.feature-card, .guild-card, .admin-card, .admin-stat {
    transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), border-color 0.2s ease, box-shadow 0.25s ease;
}
.feature-card:hover, .guild-card:hover {
    box-shadow: 0 12px 32px rgba(124,92,255,0.25);
}
h1 {
    font-size: 28px; margin-bottom: 10px; font-weight: 800; letter-spacing: -0.5px;
    background: linear-gradient(90deg, #fff, #cfd6ff);
    -webkit-background-clip: text; background-clip: text; color: transparent;
}
h2 { font-size: 17px; color: var(--text); font-weight: 700; }
a { color: var(--accent3); }
p { color: var(--text-dim); }

.btn {
    display: inline-block;
    background: linear-gradient(135deg, var(--accent), #7c8cff);
    color: #fff;
    padding: 12px 26px;
    border: none;
    border-radius: 10px;
    text-decoration: none;
    font-weight: 700;
    cursor: pointer;
    font-size: 14px;
    box-shadow: 0 4px 18px rgba(88,101,242,0.4);
    transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.25s ease;
}
.btn:hover { transform: translateY(-2px); box-shadow: 0 8px 26px rgba(88,101,242,0.55); }
.btn-small { padding: 8px 18px; font-size: 13px; border-radius: 8px; }
.btn-ghost { background: transparent; border: 2px solid var(--border); color: var(--text); box-shadow: none; }
.btn-ghost:hover { border-color: var(--accent3); color: var(--accent3); box-shadow: none; transform: translateY(-2px); }
.btn-discord { background: linear-gradient(135deg, var(--accent), #7c8cff); }
.btn-pink { background: linear-gradient(135deg, var(--accent2), #ff7fc0); box-shadow: 0 4px 18px rgba(235,69,158,0.4); }
.btn-green { background: linear-gradient(135deg, var(--accent3), #4de8c4); box-shadow: 0 4px 18px rgba(34,211,168,0.35); color: #06231c; }

/* Landing Page */
.hero { text-align: center; padding: 90px 20px 60px; }
.hero-links { display: flex; justify-content: center; gap: 24px; margin-top: 22px; }
.hero-links a { color: var(--text-dim); text-decoration: none; font-size: 14px; font-weight: 600; transition: color 0.15s ease; }
.hero-links a:hover { color: var(--text); }
.hero-eyebrow {
    display: inline-block; padding: 6px 16px; border-radius: 999px;
    background: rgba(124,92,255,0.15); border: 1px solid rgba(124,92,255,0.3);
    color: #cfc3ff; font-size: 13px; font-weight: 600; margin-bottom: 20px;
}
.btn-cta { display: inline-flex; align-items: center; gap: 10px; }
.section-heading {
    text-align: center; font-size: 26px; font-weight: 800; margin: 64px 0 28px;
    background: linear-gradient(90deg, #fff, #cfd6ff); -webkit-background-clip: text;
    background-clip: text; color: transparent;
}
.benefits-row {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 24px; margin-bottom: 40px;
}
.benefit-item { display: flex; gap: 16px; }
.benefit-num {
    font-size: 28px; font-weight: 800; color: transparent;
    -webkit-text-stroke: 1.5px var(--accent); flex-shrink: 0;
}
.benefit-item h3 { font-size: 16px; margin-bottom: 6px; }
.benefit-item p { font-size: 13px; margin: 0; }
.hero h1 {
    font-size: 46px;
    font-weight: 800;
    background: linear-gradient(90deg, #fff, #b6c0ff 45%, #ffb3de 80%, var(--accent4));
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    margin-bottom: 16px;
}
.hero p { color: var(--text-dim); font-size: 18px; max-width: 580px; margin: 0 auto 36px; }
.overview-header {
    display: flex; align-items: center; gap: 18px; margin-bottom: 8px;
}
.overview-icon {
    width: 64px; height: 64px; border-radius: 16px; object-fit: cover;
    box-shadow: 0 8px 24px rgba(124,92,255,0.3);
}
.overview-icon-placeholder {
    display: flex; align-items: center; justify-content: center;
    font-size: 28px; font-weight: 800; color: #fff;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
}
.overview-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 18px;
}
.overview-card {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
    padding: 24px; text-decoration: none; color: inherit; display: block;
    transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), border-color 0.2s ease, box-shadow 0.25s ease;
}
.overview-card:hover {
    transform: translateY(-4px); border-color: var(--accent);
    box-shadow: 0 12px 32px rgba(124,92,255,0.25);
}
.overview-card .icon { font-size: 28px; margin-bottom: 10px; }
.overview-card h3 { font-size: 16px; margin-bottom: 6px; }
.overview-card p { font-size: 13px; margin: 0; }

.feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 20px;
    margin-top: 64px;
}
.feature-card {
    background: linear-gradient(160deg, var(--bg-card), #191a28);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 30px 26px;
    transition: transform 0.2s ease, border-color 0.2s ease;
    position: relative;
    overflow: hidden;
}
.feature-card::before {
    content: "";
    position: absolute; top: -40%; right: -30%;
    width: 140px; height: 140px; border-radius: 50%;
    background: radial-gradient(circle, var(--card-glow, var(--accent)), transparent 70%);
    opacity: 0.35;
}
.feature-card:nth-child(1) { --card-glow: var(--accent); }
.feature-card:nth-child(2) { --card-glow: var(--accent2); }
.feature-card:nth-child(3) { --card-glow: var(--accent3); }
.feature-card:nth-child(4) { --card-glow: var(--accent4); }
.feature-card:hover { transform: translateY(-5px); border-color: var(--accent); }
.feature-card .icon {
    font-size: 26px; margin-bottom: 14px; width: 52px; height: 52px;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 14px;
    box-shadow: 0 6px 18px rgba(124,92,255,0.35);
}
.feature-card h3 { font-size: 16px; margin: 0 0 8px; color: var(--text); font-weight: 700; }
.feature-card p { font-size: 13px; color: var(--text-dim); margin: 0; line-height: 1.6; }

.login-box {
    max-width: 460px;
    margin: 60px auto;
    text-align: center;
    background: linear-gradient(160deg, var(--bg-card), #191a28);
    padding: 46px 38px;
    border-radius: 22px;
    border: 1px solid var(--border);
    box-shadow: 0 24px 70px rgba(0,0,0,0.5);
}
.small-print { font-size: 12px; color: var(--text-dim); margin-top: 24px; }

.guild-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(195px, 1fr));
    gap: 18px;
    margin-top: 24px;
}
.guild-card {
    background: linear-gradient(160deg, var(--bg-card), #191a28);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 24px;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    transition: transform 0.2s ease, border-color 0.2s ease;
}
.guild-card:hover { transform: translateY(-4px); border-color: var(--accent2); }
.guild-card-disabled { opacity: 0.5; }
.guild-card img, .guild-icon-placeholder { width: 62px; height: 62px; border-radius: 50%; }
.guild-icon-placeholder {
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 22px; color: #fff;
}
.guild-name { font-weight: 700; color: var(--text); }

.back-link {
    color: var(--text-dim);
    text-decoration: none;
    font-size: 14px;
    display: inline-block;
    padding: 8px 0;
    margin-top: 4px;
    position: relative;
    z-index: 1;
}
.back-link:hover { color: var(--accent3); }

.settings-form { margin-top: 24px; display: flex; flex-direction: column; gap: 18px; max-width: 460px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 13px; color: var(--text-dim); font-weight: 600; }
.field select, .field input {
    background: rgba(255,255,255,0.03);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 12px 14px;
    border-radius: 10px;
    font-size: 14px;
}
.field select:focus, .field input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(88,101,242,0.25); }
.hint { color: var(--text-dim); font-size: 13px; margin-top: 24px; }

.flash { padding: 14px 18px; border-radius: 12px; margin-bottom: 16px; font-size: 14px; font-weight: 600; }
.flash-error { background: rgba(235,69,158,0.12); color: #ff8dc6; border: 1px solid rgba(235,69,158,0.35); }
.flash-success { background: rgba(34,211,168,0.12); color: #5df0cf; border: 1px solid rgba(34,211,168,0.35); }

.section-badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    padding: 4px 12px;
    border-radius: 999px;
    margin-bottom: 6px;
}
.badge-security { background: rgba(235,69,158,0.15); color: #ff8dc6; }
.badge-setup { background: rgba(88,101,242,0.15); color: #a8b1ff; }
.badge-community { background: rgba(34,211,168,0.15); color: #5df0cf; }
.badge-music { background: rgba(245,166,35,0.15); color: #ffc766; }

/* Rechtsseiten (Impressum, Datenschutz, Urheberrecht) */
.legal-page { max-width: 780px; margin: 0 auto; }
.legal-notice {
    background: rgba(255,255,255,0.04); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 18px; font-size: 13px; color: var(--text-dim); margin: 20px 0 36px;
}
.legal-section { margin-bottom: 36px; }
.legal-section h2 { font-size: 18px; margin-bottom: 12px; color: #fff; }
.legal-section p { line-height: 1.7; margin-bottom: 10px; }
.legal-table { width: 100%; border-collapse: collapse; margin-top: 8px; }
.legal-table th, .legal-table td {
    text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--border); font-size: 14px;
}
.legal-table th { color: var(--text-dim); font-weight: 600; width: 220px; }
.legal-list { padding-left: 20px; line-height: 1.8; }
.legal-list li { margin-bottom: 4px; }
.legal-copyright { text-align: center; color: #a29bc4; font-size: 12px; margin-top: 48px; }

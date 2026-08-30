#!/usr/bin/env python3
"""Generate internal BPS analysis hub + reports (noindex)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dashboard" / "data"
OUT = ROOT / "interno"


def eur(n, d=0):
    if n is None:
        return "—"
    s = f"{float(n):,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " €"


def num(n):
    if n is None:
        return "—"
    return f"{round(float(n)):,}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(n, d=1):
    if n is None:
        return "—"
    return f"{float(n):.{d}f}%"


CSS = """
:root{--navy:#0B1F3A;--blue:#0080E0;--gold:#D4AF37;--bg:#f4f7fb;--line:#d9e3ef;--muted:#5a6b7d;--green:#1FA97A;--coral:#E25B4C;--purple:#5B54C9}
*{box-sizing:border-box}body{margin:0;font-family:"Raleway",system-ui,sans-serif;background:var(--bg);color:var(--navy);line-height:1.5}
h1,h2,h3{font-family:"Poppins",sans-serif}a{color:var(--blue);text-decoration:none}
.wrap{max-width:1100px;margin:0 auto;padding:24px 18px 60px}
.top{background:linear-gradient(135deg,#0B1F3A,#0d3a66);color:#fff;padding:22px 18px}
.top .wrap{padding:0}.eyebrow{font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--gold)}
.top h1{margin:6px 0 4px;font-size:clamp(1.4rem,3vw,2rem)}.top p{margin:0;opacity:.9;font-size:.95rem}
.nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.nav a{background:rgba(255,255,255,.12);color:#fff;padding:7px 12px;border-radius:8px;font-size:12px;font-weight:700}
.nav a.on{outline:2px solid var(--gold)}
.note{background:#fff6d6;border:1px solid #e8d48a;border-radius:10px;padding:10px 12px;font-size:.85rem;margin:14px 0;color:#6a5a10}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:16px 0}
.stat{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;color:inherit}
.stat strong{display:block;font-family:"Poppins",sans-serif;font-size:1.35rem;font-weight:800}
.stat span{font-size:.78rem;color:var(--muted)}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;margin:14px 0}
.card h2{font-size:1.1rem;margin:0 0 8px}.card h3{font-size:.95rem;margin:14px 0 6px}
.card p,.card li{font-size:.9rem;color:#334}
ul{padding-left:18px}table{width:100%;border-collapse:collapse;font-size:.8rem;margin-top:8px}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right}th:first-child,td:first-child{text-align:left}
th{font-size:.65rem;text-transform:uppercase;color:var(--muted);background:#f7fafc}
.bad{color:var(--coral);font-weight:700}.good{color:var(--green);font-weight:700}
.footer{font-size:.8rem;color:var(--muted);margin-top:28px}
"""


def page(title: str, body: str, active: str = "") -> str:
    nav = [
        ("index.html", "Hub", "index"),
        ("redes.html", "Redes / social", "redes"),
        ("organico-ux.html", "Orgánico · UX", "organico"),
        ("paid.html", "Paid real", "paid"),
        ("../", "← Propuesta", ""),
    ]
    links = []
    for href, label, key in nav:
        cls = ' class="on"' if key and active == key else ""
        links.append(f'<a href="{href}"{cls}>{label}</a>')
    return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="robots" content="noindex,nofollow"/>
<title>{title} · BPS interno</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@600;700;800&family=Raleway:wght@400;500;600;700&display=swap" rel="stylesheet"/>
<style>{CSS}</style>
</head><body>
<header class="top"><div class="wrap">
  <div class="eyebrow">Uso interno · no compartir con cliente</div>
  <h1>{title}</h1>
  <p>Blue Parrot School · WC / Meta / Google / CrUX · {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
  <nav class="nav">{"".join(links)}</nav>
</div></header>
<main class="wrap">{body}
<p class="footer">Fuente: dashboard/db + exports. ROAS/CAC paid = pedidos WC verificados, no pixel.</p>
</main></body></html>"""


def main():
    OUT.mkdir(exist_ok=True)
    prop = json.loads((DATA / "proposal-from-db.json").read_text())
    crux = json.loads((DATA / "crux-history.json").read_text())
    organic = json.loads((DATA / "organic-purchase-landings.json").read_text())
    meta_x = json.loads((DATA / "meta-wc-cross-summary.json").read_text())
    gsc = json.loads((DATA / "ga4-gsc-crosscheck.json").read_text())

    cur = prop["periods"]["sy-2025-26"]
    g = cur["paid"]["google_ads"]
    m = cur["paid"]["meta"]
    mix = prop["YOY_PLAN"]["plan"]["mediaMix"]

    decl_ig = next((c for c in cur["channels"] if c["canal"] == "Instagram"), {})
    decl_fb = next((c for c in cur["channels"] if c["canal"] == "Facebook"), {})
    ma = meta_x.get("match_all") or {}

    hub = f"""
<div class="note">Informes <strong>internos</strong>. Propuesta cliente: <a href="../">/propuestas/blueparrotschool/</a>.</div>
<div class="grid">
  <a class="stat" href="redes.html"><strong>Redes</strong><span>Meta Ads + IG/FB declarado + cruce leads</span></a>
  <a class="stat" href="organico-ux.html"><strong>Orgánico · UX</strong><span>Landings GA4 + CrUX (LCP/INP/CLS)</span></a>
  <a class="stat" href="paid.html"><strong>Paid real</strong><span>Google + Meta vs WooCommerce</span></a>
</div>
<div class="card">
  <h2>Por qué Jun–Ago no es “verano flojo”</h2>
  <p>Keyword Planner: Cambridge <strong>Jun ~1,56× / Jul ~1,78×</strong> vs media. Pedidos WC 2025: Jun 141 · Jul <strong>178</strong> · Ago 98. Q4 debe ser pico comercial, no hibernación.</p>
</div>
"""

    redes = f"""
<div class="note">IG/FB en checkout ≠ Meta Ads verificado. Pixel purchase ≠ pedido WC.</div>
<div class="grid">
  <div class="stat"><strong>{eur(m.get("spend"), 0)}</strong><span>Meta Ads spend 25–26</span></div>
  <div class="stat"><strong>{num(m.get("wc_orders_verified"))}</strong><span>Pedidos WC verificados Meta</span></div>
  <div class="stat"><strong>{eur(m.get("cac"), 0)}</strong><span>CAC Meta→WC</span></div>
  <div class="stat"><strong>{f"{float(m['roas']):.2f}×" if m.get("roas") else "—"}</strong><span>ROAS Meta WC</span></div>
</div>
<div class="card">
  <h2>Declarado en checkout vs paid</h2>
  <table>
    <tr><th>Fuente</th><th>Pedidos</th><th>Ingresos</th><th>Qué mide</th></tr>
    <tr><td>Instagram (declarado)</td><td>{num(decl_ig.get("orders"))}</td><td>{eur(decl_ig.get("rev"), 0)}</td><td>Autodeclaración checkout</td></tr>
    <tr><td>Facebook (declarado)</td><td>{num(decl_fb.get("orders"))}</td><td>{eur(decl_fb.get("rev"), 0)}</td><td>Autodeclaración checkout</td></tr>
    <tr><td>Meta Ads → WC</td><td>{num(m.get("wc_orders_verified"))}</td><td>{eur(m.get("wc_revenue_verified"), 0)}</td><td>Cruce lead/form → pedido</td></tr>
  </table>
</div>
<div class="card">
  <h2>Cruce Meta leads → WC</h2>
  <div class="grid">
    <div class="stat"><strong>{num(ma.get("orders_matched"))}</strong><span>Pedidos matcheados</span></div>
    <div class="stat"><strong>{pct(ma.get("conv_lead_to_order_pct"))}</strong><span>Lead→pedido (cruce)</span></div>
    <div class="stat"><strong>{num((ma.get("lag") or {}).get("median"))} d</strong><span>Lag mediano</span></div>
    <div class="stat"><strong>{eur(ma.get("cac_orders_all_spend"), 0)}</strong><span>CAC spend total Meta</span></div>
  </div>
  <p>Lag p90 ~{(ma.get("lag") or {}).get("p90")} días → nurture 7–30 días obligatorio.</p>
  <h3>Acciones</h3>
  <ul>
    <li>Remarketing a leads sin compra &lt;30 días.</li>
    <li>Cortar campañas con lead→pedido &lt;1%.</li>
    <li>No optimizar a pixel purchase.</li>
    <li>Creatividades con certificado + fecha de convocatoria.</li>
  </ul>
</div>
"""

    org25 = organic.get("25-26") or []
    top_org = sorted(org25, key=lambda x: -(x.get("purchases") or 0))[:12]
    org_rows = []
    for r in top_org:
        cr = "—"
        if r.get("sessions"):
            cr = pct(100 * (r.get("purchases") or 0) / r["sessions"])
        org_rows.append(
            f"<tr><td>{r.get('landingPage')}</td><td>{num(r.get('sessions'))}</td>"
            f"<td>{num(r.get('purchases'))}</td><td>{eur(r.get('revenue'), 0)}</td><td>{cr}</td></tr>"
        )
    phone = (crux.get("phone") or [{}])[-1]
    desk = (crux.get("desktop") or [{}])[-1]
    gsc2526 = (gsc.get("gsc") or {}).get("25-26") or {}

    organico = f"""
<div class="note">CrUX = usuarios Chrome reales. LCP móvil actual es crítico para paid y orgánico.</div>
<div class="grid">
  <div class="stat"><strong>{num(gsc2526.get("clicks"))}</strong><span>GSC clics 25–26</span></div>
  <div class="stat"><strong>{num(gsc2526.get("impressions"))}</strong><span>GSC impresiones</span></div>
  <div class="stat"><strong>{num(phone.get("largest_contentful_paint"))} ms</strong><span>LCP móvil ({phone.get("ym")})</span></div>
  <div class="stat"><strong>{pct(100 * (phone.get("lcp_poor_share") or 0))}</strong><span>% LCP pobre (móvil)</span></div>
</div>
<div class="card">
  <h2>CrUX · última ventana</h2>
  <table>
    <tr><th>Métrica</th><th>Móvil</th><th>Desktop</th><th>Bueno</th></tr>
    <tr><td>LCP</td><td class="bad">{num(phone.get("largest_contentful_paint"))} ms</td><td class="bad">{num(desk.get("largest_contentful_paint"))} ms</td><td>≤2500 ms</td></tr>
    <tr><td>INP</td><td>{num(phone.get("interaction_to_next_paint"))} ms</td><td>{num(desk.get("interaction_to_next_paint"))} ms</td><td>≤200 ms</td></tr>
    <tr><td>CLS</td><td>{phone.get("cumulative_layout_shift")}</td><td>{desk.get("cumulative_layout_shift")}</td><td>≤0.1</td></tr>
    <tr><td>TTFB</td><td class="bad">{num(phone.get("experimental_time_to_first_byte"))} ms</td><td class="bad">{num(desk.get("experimental_time_to_first_byte"))} ms</td><td>≤800 ms</td></tr>
  </table>
  <p class="bad">LCP y TTFB altos frenan conversión. Prioridad técnica antes de escalar ppto.</p>
</div>
<div class="card">
  <h2>Landings orgánicas con compra (GA4 25–26)</h2>
  <table>
    <tr><th>Landing</th><th>Sesiones</th><th>Purchases</th><th>Revenue</th><th>CR</th></tr>
    {"".join(org_rows)}
  </table>
  <h3>Acciones</h3>
  <ul>
    <li>Arreglar LCP/TTFB en home y landings APTIS/Cambridge.</li>
    <li>SEO solo en URLs que ya convierten.</li>
    <li>Paid a las mismas URLs rápidas y congruentes.</li>
  </ul>
</div>
"""

    g_roas = f"{float(g['roas']):.2f}×" if g.get("roas") else "—"
    m_roas = f"{float(m['roas']):.2f}×" if m.get("roas") else "—"
    summer = [
        r
        for r in (prop.get("wc_monthly") or [])
        if r["month"] in ("2025-06", "2025-07", "2025-08", "2026-06", "2026-07", "2026-08")
    ]
    summer_rows = "".join(
        f"<tr><td>{r['month']}</td><td>{num(r['orders'])}</td><td>{eur(r['rev'], 0)}</td></tr>" for r in summer
    )
    blend = (mix.get("planTargets") or {}).get("blendRoas")

    paid = f"""
<div class="note">Gold = pedido WC. Silver = métricas de plataforma. No mezclar.</div>
<div class="grid">
  <div class="stat"><strong>{eur((g.get("spend") or 0) + (m.get("spend") or 0), 0)}</strong><span>Paid total 25–26</span></div>
  <div class="stat"><strong>{g_roas}</strong><span>ROAS Google WC</span></div>
  <div class="stat"><strong>{m_roas}</strong><span>ROAS Meta WC</span></div>
  <div class="stat"><strong>{f"{blend}×" if blend else "—"}</strong><span>ROAS blend plan 26–27</span></div>
</div>
<div class="card">
  <h2>Comparativa paid 25–26</h2>
  <table>
    <tr><th>Canal</th><th>Spend</th><th>Clics</th><th>Leads plat.</th><th>Compras plat.</th><th>Pedidos WC</th><th>CAC WC</th><th>ROAS WC</th></tr>
    <tr><td>Google Ads</td><td>{eur(g.get("spend"), 0)}</td><td>{num(g.get("clicks"))}</td>
      <td>{num(g.get("platform_lead_convs"))}</td><td>{num(g.get("platform_purchases"))}</td>
      <td>{num(g.get("wc_orders_verified"))}</td><td>{eur(g.get("cac"), 0)}</td><td>{g_roas}</td></tr>
    <tr><td>Meta Ads</td><td>{eur(m.get("spend"), 0)}</td><td>{num(m.get("clicks"))}</td>
      <td>{num(m.get("platform_leads") or m.get("platform_lead_convs"))}</td><td>—</td>
      <td>{num(m.get("wc_orders_verified"))}</td><td>{eur(m.get("cac"), 0)}</td><td>{m_roas}</td></tr>
  </table>
</div>
<div class="card">
  <h2>Estacionalidad WC (verano)</h2>
  <table><tr><th>Mes</th><th>Pedidos</th><th>Ingresos</th></tr>{summer_rows}</table>
  <p>Julio es pico. Jun–Jul: <strong>más</strong> IS/ppto Google certs.</p>
  <h3>Acciones</h3>
  <ul>
    <li>Mix ~75% Google / 25% Meta.</li>
    <li>Google certs + brand; Meta remarketing/cualificado.</li>
    <li>Medir lead→pedido WC, no solo CPL/pixel.</li>
  </ul>
</div>
"""

    (OUT / "index.html").write_text(page("Análisis internos BPS", hub, "index"), encoding="utf-8")
    (OUT / "redes.html").write_text(page("Análisis redes / social", redes, "redes"), encoding="utf-8")
    (OUT / "organico-ux.html").write_text(page("Orgánico · UX / rendimiento", organico, "organico"), encoding="utf-8")
    (OUT / "paid.html").write_text(page("Paid real (WC verificado)", paid, "paid"), encoding="utf-8")
    print(f"Wrote {OUT} ({sum(f.stat().st_size for f in OUT.iterdir()) // 1024} KB)")


if __name__ == "__main__":
    main()

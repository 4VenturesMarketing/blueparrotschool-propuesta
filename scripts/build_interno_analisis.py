#!/usr/bin/env python3
"""Generate internal BPS analysis hub + reports (noindex)."""
from __future__ import annotations

import json
from collections import defaultdict
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


def _crux_by_ym(rows):
    """Keep last sample per ym (API returns overlapping windows)."""
    out = {}
    for r in rows or []:
        ym = r.get("ym")
        if ym:
            out[ym] = r
    return [out[k] for k in sorted(out)]


def _pos(v):
    if v is None:
        return "—"
    return f"{float(v):.1f}".replace(".", ",")


def _ctr(v):
    if v is None:
        return "—"
    return pct(100 * float(v), 2)


def _short_url(u: str, n: int = 72) -> str:
    u = (u or "").replace("https://blueparrotschool.com", "")
    return (u[: n - 1] + "…") if len(u) > n else u


def _norm_landing(p: str) -> str:
    """Normalize landing path for YoY matching (trailing slash, query, host)."""
    p = (p or "").strip()
    p = p.replace("https://blueparrotschool.com", "").replace("http://blueparrotschool.com", "")
    p = p.split("?")[0].split("#")[0].strip() or "/"
    if p != "/" and p.endswith("/"):
        p = p.rstrip("/")
    return p or "/"


def _cr(sessions, purchases):
    if not sessions:
        return None
    return 100.0 * float(purchases or 0) / float(sessions)


def _meta_demo_sy(rows):
    """Aggregate Meta age/gender for school year Sep 2025 – Aug 2026."""
    age = defaultdict(lambda: {"spend": 0.0, "leads": 0.0, "purchases": 0.0, "clicks": 0.0})
    gender = defaultdict(lambda: {"spend": 0.0, "leads": 0.0, "purchases": 0.0, "clicks": 0.0})

    def in_sy(m: str) -> bool:
        y, mo = map(int, m.split("-"))
        return (y == 2025 and mo >= 9) or (y == 2026 and mo <= 8)

    for r in rows or []:
        if not in_sy(r.get("month") or ""):
            continue
        a, g = r.get("age") or "Unknown", r.get("gender") or "unknown"
        for bucket, key in ((age, a), (gender, g)):
            bucket[key]["spend"] += float(r.get("spend") or 0)
            bucket[key]["leads"] += float(r.get("leads") or 0)
            bucket[key]["purchases"] += float(r.get("purchases") or 0)
            bucket[key]["clicks"] += float(r.get("clicks") or 0)
    return age, gender


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
.muted{color:var(--muted);font-weight:400;font-size:.75rem}
.tag{display:inline-block;font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;background:#e8f4ff;color:var(--blue);padding:2px 6px;border-radius:4px;margin-left:6px;vertical-align:middle}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
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
<p class="footer">Fuente: dashboard/db + exports + GSC live. ROAS/CAC paid = pedidos WC verificados, no pixel.</p>
</main></body></html>"""


def main():
    OUT.mkdir(exist_ok=True)
    prop = json.loads((DATA / "proposal-from-db.json").read_text())
    crux = json.loads((DATA / "crux-history.json").read_text())
    organic = json.loads((DATA / "organic-purchase-landings.json").read_text())
    meta_x = json.loads((DATA / "meta-wc-cross-summary.json").read_text())
    gsc = json.loads((DATA / "ga4-gsc-crosscheck.json").read_text())
    gsc_d = json.loads((DATA / "gsc-yoy-detail.json").read_text()) if (DATA / "gsc-yoy-detail.json").exists() else {}
    meta_demo = json.loads((DATA / "meta-demo.json").read_text()) if (DATA / "meta-demo.json").exists() else {}

    cur = prop["periods"]["sy-2025-26"]
    g = cur["paid"]["google_ads"]
    m = cur["paid"]["meta"]
    mix = prop["YOY_PLAN"]["plan"]["mediaMix"]
    bp = prop.get("YOY_PLAN", {}).get("buyerProfile") or {}
    demo_wc = (prop.get("demo") or {}).get("wc_buyer") or {}
    cur_demo = demo_wc.get("cur") or {}
    persona = bp.get("persona") or {}

    decl_ig = next((c for c in cur["channels"] if c["canal"] == "Instagram"), {})
    decl_fb = next((c for c in cur["channels"] if c["canal"] == "Facebook"), {})
    ma = meta_x.get("match_all") or {}

    hub = f"""
<div class="note">Informes <strong>internos</strong>. Propuesta cliente: <a href="../">/propuestas/blueparrotschool/</a>.</div>
<div class="grid">
  <a class="stat" href="redes.html"><strong>Redes</strong><span>Perfil comprador + Meta Ads + IG/FB</span></a>
  <a class="stat" href="organico-ux.html"><strong>Orgánico · UX</strong><span>GSC YoY · CrUX · landings</span></a>
  <a class="stat" href="paid.html"><strong>Paid real</strong><span>Google + Meta vs WooCommerce</span></a>
</div>
<div class="card">
  <h2>Por qué Jun–Ago no es “verano flojo”</h2>
  <p>Keyword Planner: Cambridge <strong>Jun ~1,56× / Jul ~1,78×</strong> vs media. Pedidos WC 2025: jun 141 · Jul <strong>178</strong> · Ago 98. Q4 debe ser pico comercial, no hibernación.</p>
</div>
"""

    age_rows = ""
    for b in (cur_demo.get("age") or {}).get("bands") or bp.get("age_primary") or []:
        band = b.get("band")
        orders = b.get("orders")
        rev = b.get("rev")
        share = b.get("share_pct")
        known = (cur_demo.get("age") or {}).get("known_orders")
        if share is None and known and orders:
            share = 100 * orders / known
        age_rows += (
            f"<tr><td>{band}</td><td>{num(orders)}</td>"
            f"<td>{eur(rev, 0) if rev is not None else '—'}</td><td>{pct(share)}</td></tr>"
        )
    gen = (cur_demo.get("gender") or {}).get("gender") or {}
    gen_rows = "".join(
        f"<tr><td>{lab}</td><td>{num((gen.get(k) or {}).get('orders'))}</td>"
        f"<td>{eur((gen.get(k) or {}).get('rev'), 0)}</td>"
        f"<td>{pct((gen.get(k) or {}).get('pct_all'))}</td></tr>"
        for lab, k in (("Mujer", "mujer"), ("Hombre", "hombre"), ("Desconocido", "desconocido"))
    )
    city_rows = "".join(
        f"<tr><td>{c.get('name')}</td><td>{num(c.get('orders'))}</td><td>{eur(c.get('rev'), 0)}</td></tr>"
        for c in (cur_demo.get("cities") or [])[:10]
    )
    prod_rows = "".join(
        f"<tr><td>{p.get('family')}</td><td>{num(p.get('orders'))}</td><td>{eur(p.get('rev'), 0)}</td></tr>"
        for p in bp.get("product_mix") or []
    )
    motiv = "".join(f"<li>{x}</li>" for x in persona.get("motivations") or [])
    chans = "".join(f"<li>{x}</li>" for x in persona.get("channels") or [])

    meta_age, meta_gen = _meta_demo_sy(meta_demo.get("rows"))
    meta_age_rows = "".join(
        f"<tr><td>{k}</td><td>{eur(v['spend'], 0)}</td><td>{num(v['leads'])}</td>"
        f"<td>{num(v['purchases'])}</td>"
        f"<td>{eur(v['spend'] / v['leads'], 2) if v['leads'] else '—'}</td></tr>"
        for k, v in sorted(meta_age.items(), key=lambda x: -x[1]["spend"])
        if k != "Unknown"
    )
    meta_gen_rows = "".join(
        f"<tr><td>{k}</td><td>{eur(v['spend'], 0)}</td><td>{num(v['leads'])}</td>"
        f"<td>{num(v['purchases'])}</td></tr>"
        for k, v in sorted(meta_gen.items(), key=lambda x: -x[1]["spend"])
    )

    redes = f"""
<div class="note">IG/FB en checkout ≠ Meta Ads verificado. Pixel purchase ≠ pedido WC. Perfil = WC billing (edad/geo) + género inferido por nombre.</div>
<div class="grid">
  <div class="stat"><strong>{eur(m.get("spend"), 0)}</strong><span>Meta Ads spend 25–26</span></div>
  <div class="stat"><strong>{num(m.get("wc_orders_verified"))}</strong><span>Pedidos WC verificados Meta</span></div>
  <div class="stat"><strong>{eur(m.get("cac"), 0)}</strong><span>CAC Meta→WC</span></div>
  <div class="stat"><strong>{f"{float(m['roas']):.2f}×" if m.get("roas") else "—"}</strong><span>ROAS Meta WC</span></div>
</div>
<div class="card">
  <h2>Perfil completo del comprador (WC 25–26)</h2>
  <p><strong>{persona.get("title") or "—"}</strong> — {persona.get("summary") or ""}</p>
  <div class="grid">
    <div class="stat"><strong>{num(bp.get("n_orders"))}</strong><span>Pedidos perfilados</span></div>
    <div class="stat"><strong>{eur(bp.get("aov"), 0)}</strong><span>AOV</span></div>
    <div class="stat"><strong>{bp.get("top_product") or "—"}</strong><span>Producto #1</span></div>
    <div class="stat"><strong>{bp.get("geo_primary") or "—"}</strong><span>Geo primaria</span></div>
  </div>
  <h3>Edad (cobertura {pct((cur_demo.get("age") or {}).get("parsed_pct") or bp.get("age_coverage_pct"))})</h3>
  <table><tr><th>Banda</th><th>Pedidos</th><th>Ingresos</th><th>% conocidos</th></tr>{age_rows}</table>
  <h3>Género (cobertura {pct((cur_demo.get("gender") or {}).get("coverage_pct") or bp.get("gender_coverage_pct"))})</h3>
  <table><tr><th>Género</th><th>Pedidos</th><th>Ingresos</th><th>% del total</th></tr>{gen_rows}</table>
  <p>De conocidos: <strong>{pct((cur_demo.get("gender") or {}).get("mujer_of_known_pct"))} mujeres</strong> · {pct((cur_demo.get("gender") or {}).get("hombre_of_known_pct"))} hombres.</p>
  <h3>Top ciudades</h3>
  <table><tr><th>Ciudad</th><th>Pedidos</th><th>Ingresos</th></tr>{city_rows}</table>
  <h3>Mix de producto</h3>
  <table><tr><th>Familia</th><th>Pedidos</th><th>Ingresos</th></tr>{prod_rows}</table>
  <h3>Motivaciones / canales de descubrimiento</h3>
  <div class="grid"><div><ul>{motiv}</ul></div><div><ul>{chans}</ul></div></div>
  <p>Meta lead→buyer (cruce): conv {pct(bp.get("meta_lead_buyer", {}).get("conv_pct"))} · CAC {eur((bp.get("meta_lead_buyer") or {}).get("cac"), 0)} · lag mediano {(bp.get("meta_lead_buyer") or {}).get("median_lag_days")} d.</p>
</div>
<div class="card">
  <h2>Audiencia Meta Ads (spend/leads por demo · SY 25–26)</h2>
  <p>Inversión Meta se concentra en 25–44; el comprador WC es más joven (18–34). Alinear creatividades y lookalikes al perfil WC, no solo al que hace lead.</p>
  <h3>Por edad</h3>
  <table><tr><th>Edad</th><th>Spend</th><th>Leads</th><th>Purch. pixel</th><th>CPL</th></tr>{meta_age_rows}</table>
  <h3>Por género</h3>
  <table><tr><th>Género</th><th>Spend</th><th>Leads</th><th>Purch. pixel</th></tr>{meta_gen_rows}</table>
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
    <li>Remarketing a leads sin compra &lt;30 días · creatividades mujer 18–34 Madrid/Málaga + APTIS/Cambridge.</li>
    <li>Cortar campañas con lead→pedido &lt;1%.</li>
    <li>No optimizar a pixel purchase.</li>
    <li>Rebalancear spend Meta hacia 18–34 (hoy pesa más 25–44).</li>
  </ul>
</div>
"""

    org25 = organic.get("25-26") or []
    org24 = organic.get("24-25") or []
    prev_by = {}
    for r in org24:
        key = _norm_landing(r.get("landingPage") or "")
        # Keep highest-purchase row if duplicates after normalize
        if key not in prev_by or (r.get("purchases") or 0) > (prev_by[key].get("purchases") or 0):
            prev_by[key] = r
    top_org = sorted(org25, key=lambda x: -(x.get("purchases") or 0))[:12]
    org_rows = []
    org_new_n = 0
    for r in top_org:
        path = r.get("landingPage") or ""
        key = _norm_landing(path)
        prev = prev_by.get(key)
        is_new = prev is None
        if is_new:
            org_new_n += 1
        s24 = (prev or {}).get("sessions")
        s25 = r.get("sessions")
        p24 = (prev or {}).get("purchases") if prev else None
        p25 = r.get("purchases")
        rev24 = (prev or {}).get("revenue") if prev else None
        rev25 = r.get("revenue")
        cr24 = _cr(s24, p24) if prev else None
        cr25 = _cr(s25, p25)
        # Deltas vs prior course (None if landing was new)
        if prev:
            dp = (p25 or 0) - (p24 or 0)
            drev = (rev25 or 0) - (rev24 or 0)
            dcr = (cr25 - cr24) if cr25 is not None and cr24 is not None else None
            dp_lab = ("+" + num(dp)) if dp >= 0 else num(dp)
            dp_cls = "good" if dp >= 0 else "bad"
            drev_lab = ("+" + eur(drev, 0)) if drev >= 0 else eur(drev, 0)
            drev_cls = "good" if drev >= 0 else "bad"
            if dcr is None:
                dcr_lab, dcr_cls = "—", ""
            else:
                dcr_lab = f"{'+' if dcr >= 0 else ''}{dcr:.1f} pp".replace(".", ",")
                dcr_cls = "good" if dcr >= 0 else "bad"
        else:
            dp_lab = drev_lab = dcr_lab = "nueva"
            dp_cls = drev_cls = dcr_cls = ""
        tag = ' <span class="tag">nueva</span>' if is_new else ""
        org_rows.append(
            f"<tr><td>{path}{tag}</td>"
            f"<td>{num(s24) if prev else '—'}</td><td>{num(s25)}</td>"
            f"<td>{num(p24) if prev else '—'}</td><td>{num(p25)}</td>"
            f"<td class=\"{dp_cls}\">{dp_lab}</td>"
            f"<td>{eur(rev24, 0) if prev else '—'}</td><td>{eur(rev25, 0)}</td>"
            f"<td class=\"{drev_cls}\">{drev_lab}</td>"
            f"<td>{pct(cr24) if cr24 is not None else '—'}</td><td>{pct(cr25) if cr25 is not None else '—'}</td>"
            f"<td class=\"{dcr_cls}\">{dcr_lab}</td></tr>"
        )
    phone_series = _crux_by_ym(crux.get("phone"))
    desk_series = _crux_by_ym(crux.get("desktop"))
    phone = phone_series[-1] if phone_series else {}
    desk = desk_series[-1] if desk_series else {}
    gsc2526 = (gsc_d.get("totals") or {}).get("sy-2025-26") or (gsc.get("gsc") or {}).get("25-26") or {}
    gsc2425 = (gsc_d.get("totals") or {}).get("sy-2024-25") or (gsc.get("gsc") or {}).get("24-25") or {}

    def delta_n(a, b):
        if a is None or b is None:
            return "—"
        d = float(a) - float(b)
        sign = "+" if d >= 0 else ""
        return f"{sign}{num(d)}"

    def delta_pct(a, b):
        if not b:
            return "—"
        d = 100 * (float(a) - float(b)) / float(b)
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.0f}%".replace(".", ",")

    clk_d = delta_n(gsc2526.get("clicks"), gsc2425.get("clicks"))
    clk_p = delta_pct(gsc2526.get("clicks"), gsc2425.get("clicks"))
    impr_d = delta_n(gsc2526.get("impressions"), gsc2425.get("impressions"))
    pos_prev, pos_cur = gsc2425.get("position"), gsc2526.get("position")
    pos_improve = abs(float(pos_prev or 0) - float(pos_cur or 0))

    def device_map(rows):
        return {(r.get("keys") or ["?"])[0]: r for r in (rows or [])}

    d_prev = device_map((gsc_d.get("by_device") or {}).get("sy-2024-25"))
    d_cur = device_map((gsc_d.get("by_device") or {}).get("sy-2025-26"))
    device_rows = ""
    for dev in ("MOBILE", "DESKTOP", "TABLET"):
        p, c = d_prev.get(dev, {}), d_cur.get(dev, {})
        dclk = (c.get("clicks") or 0) - (p.get("clicks") or 0)
        cls = "good" if dclk >= 0 else "bad"
        device_rows += (
            f"<tr><td>{dev.title()}</td>"
            f"<td>{num(p.get('clicks'))}</td><td>{num(c.get('clicks'))}</td>"
            f"<td class=\"{cls}\">{delta_n(c.get('clicks'), p.get('clicks'))}</td>"
            f"<td>{_pos(p.get('position'))}</td><td>{_pos(c.get('position'))}</td>"
            f"<td>{_ctr(c.get('ctr'))}</td></tr>"
        )

    m25 = {(r.get("month") or "")[5:]: r for r in gsc_d.get("monthly_2526") or []}
    m24 = {(r.get("month") or "")[5:]: r for r in gsc_d.get("monthly_2425") or []}
    month_labels = [
        ("09", "Sep"),
        ("10", "Oct"),
        ("11", "Nov"),
        ("12", "Dic"),
        ("01", "Ene"),
        ("02", "Feb"),
        ("03", "Mar"),
        ("04", "Abr"),
        ("05", "May"),
        ("06", "Jun"),
        ("07", "Jul"),
        ("08", "Ago"),
    ]
    month_rows = ""
    for mm, lab in month_labels:
        a, b = m24.get(mm, {}), m25.get(mm, {})
        dclk = (b.get("clicks") or 0) - (a.get("clicks") or 0)
        cls = "good" if dclk >= 0 else "bad"
        dlab = ("+" + num(dclk)) if dclk >= 0 else num(dclk)
        month_rows += (
            f"<tr><td>{lab}</td><td>{num(a.get('clicks'))}</td><td>{num(b.get('clicks'))}</td>"
            f"<td class=\"{cls}\">{dlab}</td>"
            f"<td>{_pos(a.get('position'))}</td><td>{_pos(b.get('position'))}</td>"
            f"<td>{num(b.get('impressions'))}</td></tr>"
        )

    def q_rows(items, n=15):
        rows_h = ""
        for r in (items or [])[:n]:
            d = r.get("delta_clicks") or 0
            cls = "good" if d >= 0 else "bad"
            dlab = ("+" + num(d)) if d >= 0 else num(d)
            rows_h += (
                f"<tr><td>{r.get('query')}</td>"
                f"<td>{num(r.get('clicks_prev'))}</td><td>{num(r.get('clicks_cur'))}</td>"
                f"<td class=\"{cls}\">{dlab}</td>"
                f"<td>{_pos(r.get('pos_prev'))}</td><td>{_pos(r.get('pos_cur'))}</td></tr>"
            )
        return rows_h

    def page_rows(items, n=12):
        rows_h = ""
        for r in (items or [])[:n]:
            d = r.get("delta") or 0
            cls = "good" if d >= 0 else "bad"
            dlab = ("+" + num(d)) if d >= 0 else num(d)
            rows_h += (
                f"<tr><td>{_short_url(r.get('page'))}</td>"
                f"<td>{num(r.get('clicks_prev'))}</td><td>{num(r.get('clicks_cur'))}</td>"
                f"<td class=\"{cls}\">{dlab}</td>"
                f"<td>{_pos(r.get('pos_prev'))}</td><td>{_pos(r.get('pos_cur'))}</td></tr>"
            )
        return rows_h

    crux_hist_rows = ""
    desk_by = {r["ym"]: r for r in desk_series}
    for r in phone_series:
        ym = r["ym"]
        dsk = desk_by.get(ym, {})
        lcp = r.get("largest_contentful_paint") or 0
        cls_lcp = "bad" if lcp > 2500 else "good"
        crux_hist_rows += (
            f"<tr><td>{ym}</td>"
            f"<td class=\"{cls_lcp}\">{num(lcp)}</td><td>{pct(100 * (r.get('lcp_poor_share') or 0))}</td>"
            f"<td>{num(r.get('experimental_time_to_first_byte'))}</td>"
            f"<td>{num(r.get('interaction_to_next_paint'))}</td>"
            f"<td>{num(dsk.get('largest_contentful_paint'))}</td>"
            f"<td>{num(dsk.get('experimental_time_to_first_byte'))}</td></tr>"
        )

    organico = f"""
<div class="note">GSC live · cursos 24–25 vs 25–26 (hasta 2026-08-27). CrUX = Chrome UX reales. Posición media ↓ = mejora.</div>
<div class="grid">
  <div class="stat"><strong>{num(gsc2526.get("clicks"))}</strong><span>Clics GSC 25–26 ({clk_p} YoY)</span></div>
  <div class="stat"><strong>{num(gsc2526.get("impressions"))}</strong><span>Impresiones ({delta_pct(gsc2526.get("impressions"), gsc2425.get("impressions"))} YoY)</span></div>
  <div class="stat"><strong>{_pos(pos_cur)}</strong><span>Posición media (antes {_pos(pos_prev)})</span></div>
  <div class="stat"><strong>{num(phone.get("largest_contentful_paint"))} ms</strong><span>LCP móvil ({phone.get("ym")})</span></div>
</div>
<div class="card">
  <h2>Search Console · resumen YoY</h2>
  <table>
    <tr><th>Métrica</th><th>24–25</th><th>25–26</th><th>Δ</th></tr>
    <tr><td>Clics</td><td>{num(gsc2425.get("clicks"))}</td><td>{num(gsc2526.get("clicks"))}</td><td class="good">{clk_d} ({clk_p})</td></tr>
    <tr><td>Impresiones</td><td>{num(gsc2425.get("impressions"))}</td><td>{num(gsc2526.get("impressions"))}</td><td class="good">{impr_d}</td></tr>
    <tr><td>CTR</td><td>{_ctr(gsc2425.get("ctr"))}</td><td>{_ctr(gsc2526.get("ctr"))}</td><td>—</td></tr>
    <tr><td>Posición media</td><td>{_pos(pos_prev)}</td><td class="good">{_pos(pos_cur)}</td><td class="good">mejora ~{pos_improve:.0f} puestos</td></tr>
  </table>
  <p>El curso 25–26 <strong>duplicó clics</strong> (~{clk_p}) y mejoró posición de ~{_pos(pos_prev)} a ~{_pos(pos_cur)}. El CTR se mantiene ~1,6% — el volumen viene de más impresiones + mejor ranking, no de mejor CTR.</p>
</div>
<div class="card">
  <h2>Por dispositivo</h2>
  <table>
    <tr><th>Device</th><th>Clics 24–25</th><th>Clics 25–26</th><th>Δ</th><th>Pos 24–25</th><th>Pos 25–26</th><th>CTR 25–26</th></tr>
    {device_rows}
  </table>
  <p>Móvil: más impresiones y mejor posición (~8,5), pero <strong>CTR más bajo</strong> que desktop — coherente con LCP/TTFB pobres en phone.</p>
</div>
<div class="card">
  <h2>Evolución mensual (clics y posición)</h2>
  <table>
    <tr><th>Mes</th><th>Clics 24–25</th><th>Clics 25–26</th><th>Δ clics</th><th>Pos 24–25</th><th>Pos 25–26</th><th>Imp. 25–26</th></tr>
    {month_rows}
  </table>
  <p>Pico de clics orgánicos en sep–oct 25; caída hacia verano. Posición estable ~9–11 desde feb 26.</p>
</div>
<div class="card">
  <h2>Queries · tráfico ganado (top)</h2>
  <table><tr><th>Query</th><th>Clics 24–25</th><th>25–26</th><th>Δ</th><th>Pos ant.</th><th>Pos act.</th></tr>
  {q_rows(gsc_d.get("query_gains"), 15)}</table>
  <h2>Queries · tráfico perdido (top)</h2>
  <table><tr><th>Query</th><th>Clics 24–25</th><th>25–26</th><th>Δ</th><th>Pos ant.</th><th>Pos act.</th></tr>
  {q_rows(gsc_d.get("query_losses"), 15)}</table>
  <p>Ganancias = marca (blue parrot*) + APTIS practice. Pérdidas = long-tail WhatsApp/frases e intensivos APTIS que cayeron de ranking o salieron del top.</p>
</div>
<div class="card">
  <h2>Páginas · ganadas / perdidas</h2>
  <h3>Más clics YoY</h3>
  <table><tr><th>URL</th><th>24–25</th><th>25–26</th><th>Δ</th><th>Pos ant.</th><th>Pos act.</th></tr>
  {page_rows(gsc_d.get("page_gains"), 12)}</table>
  <h3>Menos clics YoY</h3>
  <table><tr><th>URL</th><th>24–25</th><th>25–26</th><th>Δ</th><th>Pos ant.</th><th>Pos act.</th></tr>
  {page_rows(gsc_d.get("page_losses"), 12)}</table>
</div>
<div class="card">
  <h2>CrUX · tiempos de carga (histórico móvil)</h2>
  <table>
    <tr><th>Ventana</th><th>LCP móvil ms</th><th>% LCP pobre</th><th>TTFB móvil</th><th>INP</th><th>LCP desk</th><th>TTFB desk</th></tr>
    {crux_hist_rows}
  </table>
  <table>
    <tr><th>Métrica</th><th>Móvil ahora</th><th>Desktop ahora</th><th>Bueno</th></tr>
    <tr><td>LCP</td><td class="bad">{num(phone.get("largest_contentful_paint"))} ms</td><td class="bad">{num(desk.get("largest_contentful_paint"))} ms</td><td>≤2.500 ms</td></tr>
    <tr><td>INP</td><td>{num(phone.get("interaction_to_next_paint"))} ms</td><td>{num(desk.get("interaction_to_next_paint"))} ms</td><td>≤200 ms</td></tr>
    <tr><td>CLS</td><td>{phone.get("cumulative_layout_shift")}</td><td>{desk.get("cumulative_layout_shift")}</td><td>≤0,1</td></tr>
    <tr><td>TTFB</td><td class="bad">{num(phone.get("experimental_time_to_first_byte"))} ms</td><td class="bad">{num(desk.get("experimental_time_to_first_byte"))} ms</td><td>≤800 ms</td></tr>
  </table>
  <p class="bad">LCP móvil ~8–10 s y TTFB &gt;1,5 s: Google puede limitar CTR/conversión aunque la posición mejore. El tráfico orgánico creció por ranking/brand; la conversión orgánico→pedido sigue lastrada por UX. Prioridad: TTFB+LCP home y landings APTIS antes de escalar SEO/paid a las mismas URLs.</p>
</div>
<div class="card">
  <h2>Landings orgánicas con compra (GA4 · YoY 24–25 vs 25–26)</h2>
  <p>Top conversores del curso actual (por purchases). Valores del curso anterior emparejados por URL (barra final normalizada).{f' · {org_new_n} nuevas en el top.' if org_new_n else ''} Revenue 24–25 = 0 en el export GA4 (solo sessions/purchases comparables YoY; Δ rev refleja el alta de revenue en 25–26).</p>
  <div class="scroll"><table>
    <tr>
      <th>Landing</th>
      <th>Ses. 24–25</th><th>Ses. 25–26</th>
      <th>Purch. 24–25</th><th>Purch. 25–26</th><th>Δ purch</th>
      <th>Rev. 24–25</th><th>Rev. 25–26</th><th>Δ rev</th>
      <th>CR 24–25</th><th>CR 25–26</th><th>Δ CR</th>
    </tr>
    {"".join(org_rows)}
  </table></div>
  <h3>Acciones</h3>
  <ul>
    <li>Arreglar LCP/TTFB en home, test APTIS y landings que ganan clics GSC.</li>
    <li>Recuperar URLs con pérdida (WhatsApp frases, intensivo APTIS) o consolidar en hubs que sí ranquean.</li>
    <li>SEO prioritario en URLs que ya convierten en GA4.</li>
    <li>Paid solo a URLs rápidas y alineadas con query intent.</li>
  </ul>
</div>
"""

    g_roas = f"{float(g['roas']):.2f}×" if g.get("roas") else "—"
    m_roas = f"{float(m['roas']):.2f}×" if m.get("roas") else "—"

    # Full school-year WC monthly YoY (Sep–Ago): 24–25 vs 25–26
    wc_by = {r["month"]: r for r in (prop.get("wc_monthly") or [])}
    sy_month_labels = [
        ("09", "Sep"),
        ("10", "Oct"),
        ("11", "Nov"),
        ("12", "Dic"),
        ("01", "Ene"),
        ("02", "Feb"),
        ("03", "Mar"),
        ("04", "Abr"),
        ("05", "May"),
        ("06", "Jun"),
        ("07", "Jul"),
        ("08", "Ago"),
    ]
    season_rows = ""
    tot_o24 = tot_o25 = tot_r24 = tot_r25 = 0
    for mm, lab in sy_month_labels:
        # calendar year for mm: Sep–Dec → start year; Jan–Aug → end year
        y24 = "2024" if int(mm) >= 9 else "2025"
        y25 = "2025" if int(mm) >= 9 else "2026"
        a = wc_by.get(f"{y24}-{mm}", {})
        b = wc_by.get(f"{y25}-{mm}", {})
        o24, o25 = int(a.get("orders") or 0), int(b.get("orders") or 0)
        r24, r25 = float(a.get("rev") or 0), float(b.get("rev") or 0)
        tot_o24 += o24
        tot_o25 += o25
        tot_r24 += r24
        tot_r25 += r25
        do, dr = o25 - o24, r25 - r24
        cls_o = "good" if do >= 0 else "bad"
        cls_r = "good" if dr >= 0 else "bad"
        d_o = ("+" + num(do)) if do >= 0 else num(do)
        d_r = ("+" + eur(dr, 0)) if dr >= 0 else eur(dr, 0)
        note = " <span class=\"muted\">(parcial)</span>" if (y25 == "2026" and mm == "08") else ""
        season_rows += (
            f"<tr><td>{lab}{note}</td>"
            f"<td>{num(o24)}</td><td>{num(o25)}</td><td class=\"{cls_o}\">{d_o}</td>"
            f"<td>{eur(r24, 0)}</td><td>{eur(r25, 0)}</td><td class=\"{cls_r}\">{d_r}</td></tr>"
        )
    do_tot, dr_tot = tot_o25 - tot_o24, tot_r25 - tot_r24
    cls_ot = "good" if do_tot >= 0 else "bad"
    cls_rt = "good" if dr_tot >= 0 else "bad"
    season_rows += (
        f"<tr><td><strong>Total curso</strong></td>"
        f"<td><strong>{num(tot_o24)}</strong></td><td><strong>{num(tot_o25)}</strong></td>"
        f"<td class=\"{cls_ot}\"><strong>{('+' + num(do_tot)) if do_tot >= 0 else num(do_tot)}</strong></td>"
        f"<td><strong>{eur(tot_r24, 0)}</strong></td><td><strong>{eur(tot_r25, 0)}</strong></td>"
        f"<td class=\"{cls_rt}\"><strong>{('+' + eur(dr_tot, 0)) if dr_tot >= 0 else eur(dr_tot, 0)}</strong></td></tr>"
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
  <h2>Estacionalidad WC · YoY por mes (cursos 24–25 vs 25–26)</h2>
  <p>Pedidos e ingresos WooCommerce por mes del curso (sep–ago). Ago 26 puede ser parcial.</p>
  <div class="scroll"><table>
    <tr>
      <th>Mes</th>
      <th>Ped. 24–25</th><th>Ped. 25–26</th><th>Δ ped.</th>
      <th>Ing. 24–25</th><th>Ing. 25–26</th><th>Δ ing.</th>
    </tr>
    {season_rows}
  </table></div>
  <p>Julio sigue siendo pico en ambos cursos. Mar 25 fue excepcional (187 ped.); 25–26 va por debajo casi todo el año — Jun–jul siguen siendo la ventana clave para subir IS/ppto Google certs, no hibernar.</p>
  <h3>Acciones</h3>
  <ul>
    <li>Mix ~75% Google / 25% Meta.</li>
    <li>Google certs + brand; Meta remarketing/cualificado.</li>
    <li>Medir lead→pedido WC, no solo CPL/pixel.</li>
    <li>Planificar ppto mensual con esta curva YoY (pico jul, valle dic/abr).</li>
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

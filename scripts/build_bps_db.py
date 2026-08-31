#!/usr/bin/env python3
"""
Build BPS marketing warehouse (SQLite).

Layers:
  gold   — business truth (WC orders, Meta→WC verified matches)
  silver — platform metrics (Meta/Google Ads/GA4/GSC) with clear definitions
  bronze — raw staging references

Run:  python3 scripts/build_bps_db.py
Out:  dashboard/db/bps.db + dashboard/db/DATA_DICTIONARY.md
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dashboard" / "data"
DB_DIR = ROOT / "dashboard" / "db"
DB_PATH = DB_DIR / "bps.db"

NOW = datetime.now().isoformat(timespec="seconds")

PERIODS = [
    ("sy-2024-25", "2024–25", "2024-09-01", "2025-08-31"),
    ("sy-2025-26", "2025–26", "2025-09-01", "2026-08-30"),
    ("sy-2026-27", "2026–27", "2026-09-01", "2027-08-31"),
]


def load(name: str):
    p = DATA / name
    if not p.exists():
        return None
    return json.loads(p.read_text())


def sy_for(date: str) -> str | None:
    d = date[:10]
    for pid, _, start, end in PERIODS:
        if start <= d <= end:
            return pid
    return None


def month_of(date: str) -> str:
    return date[:7]


# ── Channel classifier (same logic as proposal) ─────────────────────────────
def classify_channel(attrib: dict | None) -> tuple[str, str, str]:
    """Return (canal, tipo, fuente). tipo: paid|organic|declared|unknown"""
    a = attrib or {}
    utm_source = (a.get("_wc_order_attribution_utm_source") or a.get("utm_source") or "").lower().strip()
    utm_medium = (a.get("_wc_order_attribution_utm_medium") or a.get("utm_medium") or "").lower().strip()
    source_type = (a.get("_wc_order_attribution_source_type") or "").lower().strip()
    referral = (a.get("_billing_referral") or a.get("billing_referral") or "").strip()
    ref_l = referral.lower().strip()

    # Paid first — strict
    if utm_medium in ("cpc", "ppc", "paidsearch") or (
        "google" in utm_source and utm_medium in ("cpc", "ppc", "paid")
    ):
        return "Google Ads", "paid", "utm_medium=cpc / campaña Google"
    paid_meta_medium = utm_medium in ("paid", "paid_social", "paidsocial", "social_paid", "cpc", "cpm")
    paid_meta_source = any(x in utm_source for x in ("facebook", "instagram", "ig", "fb", "meta"))
    if paid_meta_source and paid_meta_medium:
        return "Meta Ads", "paid", "Anuncio Instagram / UTM paid social"
    if ref_l in (
        "anuncio de instagram",
        "anuncio de facebook",
        "anuncio instagram",
        "anuncio facebook",
        "anuncio de meta",
    ):
        return "Meta Ads", "paid", "Anuncio Instagram / UTM paid social"

    # Referrals / WOM
    if any(
        k in ref_l
        for k in (
            "boca",
            "amigo",
            "amiga",
            "amigos",
            "referid",
            "recomend",
            "familia",
            "conocido",
            "erasmus",
            "compañer",
            "companer",
            "alumno",
            "profesor",
        )
    ) or ref_l in ("referidos", "referido"):
        return "Referidos", "organic", "checkout referidos"

    # Organic search
    if source_type == "organic" or (utm_medium == "organic" and "google" in utm_source):
        return "Google Orgánico", "organic", "utm organic + source_type=organic"
    if utm_medium == "organic":
        return "Otros buscadores", "organic", "Bing / otros"
    if ref_l in ("google", "buscador", "google.com"):
        return "Google Orgánico", "organic", "checkout «Google» sin señal cpc"

    # Email / WA / IA
    if "chatgpt" in utm_source or "chatgpt" in ref_l or "openai" in utm_source or "ia" == ref_l:
        return "ChatGPT / IA", "organic", "referrer/checkout ChatGPT"
    if utm_medium == "email" or "clientify" in utm_source or any(
        k in ref_l for k in ("email", "newsletter", "correo", "mail")
    ):
        return "Email / CRM", "organic", "Clientify / email"
    if "whatsapp" in ref_l or "whatsapp" in utm_source:
        return "WhatsApp", "organic", "checkout WhatsApp"

    # Declared social (not paid)
    if "instagram" in ref_l or (
        utm_source in ("instagram", "ig") and utm_medium in ("", "social", "referral")
    ):
        return "Instagram", "declared", "checkout Instagram (sin anuncio)"
    if "facebook" in ref_l or (
        utm_source in ("facebook", "fb") and utm_medium in ("", "social", "referral")
    ):
        return "Facebook", "declared", "checkout Facebook (sin anuncio)"
    if any(k in ref_l for k in ("tiktok", "linkedin", "twitter", "x.com", "redes")):
        return "Redes (otros)", "declared", "checkout redes genérico"

    # Web / internet declared
    if any(k in ref_l for k in ("internet", "online", "web", "página", "pagina", "navegador")):
        return "Web / Internet", "declared", "checkout Web/Internet"

    # Direct
    if source_type == "typein" or utm_source in ("(direct)", "direct", "") or source_type == "":
        if not ref_l or ref_l in ("directo", "ninguno", "no lo sé", "no lo se", "ns/nc", "-"):
            return "Directo", "organic", "entrada directa / bookmark"
        # residual free-text without clear channel → still referidos-ish or otros
        if len(ref_l) < 40:
            return "Otros", "declared", f"checkout {referral[:40]}"

    if referral:
        return "Otros", "declared", f"checkout {referral[:40]}"
    return "Sin clasificar", "unknown", "sin señal UTM ni checkout"


PRODUCT_RULES = [
    (r"aptis", "APTIS"),
    (r"cambridge|first\b|advanced|preliminary|proficiency|b2\b|c1\b|c2\b|fce|cae", "Cambridge"),
    (r"ielts", "IELTS"),
    (r"toefl", "TOEFL"),
    (r"franc[eé]s|delf|dalf|alliance", "Francés"),
    (r"italian|cils|plida", "Italiano"),
    (r"alem[aá]n|goethe|testdaf", "Alemán"),
    (r"espa[nñ]ol|spanish|dele|siele", "Español"),
    (r"intensivo", "Intensivos (otros)"),
]


def product_family(name: str) -> str:
    n = (name or "").lower()
    for pat, fam in PRODUCT_RULES:
        if re.search(pat, n):
            return fam
    return "Otros cursos"


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE meta_run (
  id INTEGER PRIMARY KEY CHECK (id=1),
  built_at TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE dim_source (
  source_id TEXT PRIMARY KEY,
  system TEXT NOT NULL,
  layer TEXT NOT NULL CHECK (layer IN ('gold','silver','bronze')),
  trust TEXT NOT NULL CHECK (trust IN ('high','medium','low','estimate')),
  description TEXT NOT NULL,
  coverage_start TEXT,
  coverage_end TEXT,
  account_ref TEXT
);

CREATE TABLE dim_period (
  period_id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL
);

CREATE TABLE dim_metric (
  metric_id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  layer TEXT NOT NULL,
  trust TEXT NOT NULL,
  definition TEXT NOT NULL,
  use_for TEXT NOT NULL,
  do_not_confuse_with TEXT
);

CREATE TABLE dim_channel (
  channel_id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  tipo TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE fact_wc_order (
  order_id INTEGER PRIMARY KEY,
  order_date TEXT NOT NULL,
  period_id TEXT,
  month TEXT,
  status TEXT,
  total REAL NOT NULL,
  currency TEXT DEFAULT 'EUR',
  email TEXT,
  phone TEXT,
  full_name TEXT,
  city TEXT,
  state TEXT,
  country TEXT,
  channel_id TEXT,
  channel_tipo TEXT,
  channel_fuente TEXT,
  billing_referral TEXT,
  utm_source TEXT,
  utm_medium TEXT,
  utm_campaign TEXT,
  source_type TEXT,
  FOREIGN KEY (period_id) REFERENCES dim_period(period_id)
);

CREATE TABLE fact_wc_order_item (
  order_id INTEGER NOT NULL,
  line_idx INTEGER NOT NULL,
  product_name TEXT,
  family TEXT,
  qty REAL,
  line_total REAL,
  PRIMARY KEY (order_id, line_idx),
  FOREIGN KEY (order_id) REFERENCES fact_wc_order(order_id)
);

CREATE TABLE fact_meta_daily (
  date TEXT PRIMARY KEY,
  period_id TEXT,
  month TEXT,
  spend REAL, impressions INTEGER, clicks INTEGER, reach INTEGER,
  leads REAL, purchases REAL, cpc REAL, ctr REAL
);

CREATE TABLE fact_google_ads_campaign_daily (
  date TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  campaign TEXT,
  channel TEXT,
  status TEXT,
  spend REAL, impressions INTEGER, clicks INTEGER,
  conversions REAL, conv_value REAL, ctr REAL, cpc REAL,
  period_id TEXT, month TEXT,
  PRIMARY KEY (date, campaign_id)
);

CREATE TABLE fact_google_ads_conversion_daily (
  date TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  campaign TEXT,
  conv_name TEXT NOT NULL,
  conv_category TEXT NOT NULL, -- PURCHASE | SUBMIT_LEAD_FORM | ...
  conv_class TEXT NOT NULL,   -- purchase | lead | other
  conversions REAL,
  conv_value REAL,
  period_id TEXT, month TEXT,
  PRIMARY KEY (date, campaign_id, conv_name)
);

CREATE TABLE fact_meta_wc_match (
  order_id INTEGER PRIMARY KEY,
  order_date TEXT,
  period_id TEXT,
  month TEXT,
  order_total REAL,
  match_method TEXT,
  lag_days INTEGER,
  lead_uid TEXT,
  lead_source TEXT,
  form_name TEXT,
  campaign_name TEXT
);

CREATE TABLE fact_ga4_channel_period (
  period_id TEXT NOT NULL,
  channel_group TEXT NOT NULL,
  sessions REAL, users REAL, purchases REAL, revenue REAL, conversions REAL,
  PRIMARY KEY (period_id, channel_group)
);

CREATE TABLE fact_ga4_source_medium_period (
  period_id TEXT NOT NULL,
  source TEXT NOT NULL,
  medium TEXT NOT NULL,
  campaign TEXT,
  sessions REAL, purchases REAL, revenue REAL, conversions REAL,
  PRIMARY KEY (period_id, source, medium, campaign)
);

CREATE TABLE fact_ga4_period_totals (
  period_id TEXT PRIMARY KEY,
  sessions REAL, users REAL, purchases REAL, revenue REAL, conversions REAL, engaged_sessions REAL
);

CREATE TABLE fact_gsc_period (
  period_id TEXT PRIMARY KEY,
  clicks REAL, impressions REAL
);

CREATE TABLE fact_gsc_query (
  period_id TEXT NOT NULL,
  query TEXT NOT NULL,
  clicks REAL, impressions REAL, ctr REAL, position REAL,
  PRIMARY KEY (period_id, query)
);

CREATE TABLE kpi_period_channel (
  period_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  orders INTEGER, revenue REAL, aov REAL,
  PRIMARY KEY (period_id, channel_id)
);

CREATE TABLE kpi_paid_period (
  period_id TEXT NOT NULL,
  platform TEXT NOT NULL, -- meta | google_ads
  spend REAL,
  impressions REAL, clicks REAL, reach REAL,
  platform_leads REAL,
  platform_purchases REAL,   -- Meta pixel OR Google Ads PURCHASE category
  platform_lead_convs REAL,  -- Google Ads SUBMIT_LEAD_FORM
  wc_orders_verified REAL,   -- Meta match OR Google UTM cpc
  wc_revenue_verified REAL,
  cac REAL, roas REAL, conv_pct REAL,
  notes TEXT,
  PRIMARY KEY (period_id, platform)
);

CREATE VIEW v_orders_by_period AS
SELECT period_id, COUNT(*) AS orders, ROUND(SUM(total),2) AS revenue,
       ROUND(SUM(total)/COUNT(*),2) AS aov
FROM fact_wc_order WHERE period_id IS NOT NULL
GROUP BY period_id;

CREATE VIEW v_google_ads_purchase_vs_lead AS
SELECT period_id, conv_class,
       ROUND(SUM(conversions),2) AS conversions,
       ROUND(SUM(conv_value),2) AS conv_value
FROM fact_google_ads_conversion_daily
WHERE period_id IS NOT NULL
GROUP BY period_id, conv_class;
"""


def connect() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def seed_dims(conn: sqlite3.Connection):
    conn.execute(
        "INSERT INTO meta_run VALUES (1,?,?)",
        (
            NOW,
            "Gold=WC+Meta×WC match; Silver=Meta/Google/GA4/GSC; Google Ads splits PURCHASE vs SUBMIT_LEAD_FORM",
        ),
    )
    for pid, label, start, end in PERIODS:
        conn.execute("INSERT INTO dim_period VALUES (?,?,?,?)", (pid, label, start, end))

    sources = [
        ("wc_orders", "woocommerce", "gold", "high", "Pedidos WooCommerce con atribución UTM/checkout", "2021-02-04", "2026-08-30", "blueparrotschool.com"),
        ("meta_ads_api", "meta", "silver", "high", "Spend/imp/clics/leads/purchases pixel Meta Ads", "2024-09-01", "2026-08-30", "act_414283212550847"),
        ("meta_wc_match", "meta+wc", "gold", "high", "Cruce leads Meta (CSV+Clientify) → pedido WC por email/tel/nombre", "2021-10-14", "2026-08-30", "11.287 leads unificados"),
        ("google_ads_api", "google_ads", "silver", "high", "Campaign daily + conversiones por categoría (PURCHASE vs LEAD)", "2026-04-30", "2026-08-30", "CID 1064441284 / MCC 5963150101"),
        ("ga4", "ga4", "silver", "medium", "Sesiones/compras ecommerce por canal y source/medium", "2024-09-01", "2026-08-30", "properties/469240570"),
        ("gsc", "search_console", "silver", "high", "Clics e impresiones orgánicas Search Console", "2024-09-01", "2026-08-30", "https://blueparrotschool.com/"),
        ("wc_channel_declared", "woocommerce", "silver", "medium", "Canal declarado en checkout (Instagram/Facebook sin UTM paid)", None, None, None),
    ]
    conn.executemany(
        "INSERT INTO dim_source VALUES (?,?,?,?,?,?,?,?)", sources
    )

    metrics = [
        ("wc_orders", "Pedidos WC", "gold", "high", "Pedidos WooCommerce en periodo académico", "KPIs de negocio / AOV", "No confundir con conversiones Ads ni pixel Meta"),
        ("meta_orders_verified", "Pedidos Meta verificados", "gold", "high", "Match lead Meta → pedido WC", "CAC/ROAS Meta de negocio", "≠ Meta Ads checkout UTM (casi siempre 1); ≠ purchases pixel"),
        ("meta_orders_utm", "Pedidos Meta checkout UTM", "silver", "low", "UTM paid social / «Anuncio…» en checkout", "Diagnóstico de tracking UTM", "Subregistro — no usar para CAC"),
        ("meta_spend", "Inversión Meta", "silver", "high", "Spend Ads Manager (API)", "Paid media", "Cobertura completa SY 24–25 y 25–26 (2024-09-01 → 2026-08-30)"),
        ("meta_leads_platform", "Leads Meta plataforma", "silver", "high", "Resultados lead en insights Meta", "CPL plataforma", "≠ leads del universo de cruce CSV+Clientify"),
        ("meta_purchases_pixel", "Purchases Meta pixel", "silver", "medium", "Evento purchase reportado por Meta", "Optimización campañas", "≠ pedidos WC verificados"),
        ("gads_spend", "Inversión Google Ads", "silver", "high", "Cost micros campañas CID BPS", "Paid media", "Histórico local desde 2026-04-30"),
        ("gads_purchases", "Conversiones compra Google Ads", "silver", "high", "conversion_action category=PURCHASE (GA4 purchase)", "CPA compra / ROAS Ads", "≠ pedidos WC utm cpc; ≠ leads"),
        ("gads_leads", "Conversiones lead Google Ads", "silver", "high", "category=SUBMIT_LEAD_FORM (form_submit / submit_lead_form / Lead form)", "CPL Ads", "≠ compras; no sumar con purchases para CAC pedido"),
        ("gads_orders_utm", "Pedidos WC atrib. Google Ads", "gold", "high", "Pedidos WC con utm_medium=cpc", "CAC/ROAS de negocio Google", "≠ 326 conv agregadas Ads"),
        ("ga4_purchases", "Compras ecommerce GA4", "silver", "medium", "ecommercePurchases property blueparrotschool.com", "Embudo web", "Puede diferir de WC por atribución/timezone/filtros"),
        ("gsc_clicks", "Clics Search Console", "silver", "high", "Clics orgánicos GSC", "SEO / demanda", "≠ pedidos Google Orgánico WC"),
    ]
    conn.executemany(
        "INSERT INTO dim_metric VALUES (?,?,?,?,?,?,?)", metrics
    )


def ingest_wc(conn: sqlite3.Connection):
    raw = load("orders-full.json") or load("orders-with-pii.json")
    if not raw:
        raise SystemExit("Missing orders-full.json / orders-with-pii.json")
    orders = raw["orders"]
    pii = {}
    pii_raw = load("orders-with-pii.json")
    if pii_raw:
        for o in pii_raw["orders"]:
            pii[o["id"]] = o

    ch_count = defaultdict(int)
    for o in orders:
        oid = o["id"]
        p = pii.get(oid, {})
        attrib = o.get("attrib") or {}
        canal, tipo, fuente = classify_channel(attrib)
        ch_count[canal] += 1
        date = (o.get("date") or "")[:10]
        period = sy_for(date)
        conn.execute(
            """INSERT OR REPLACE INTO fact_wc_order VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                oid,
                date,
                period,
                month_of(date) if date else None,
                o.get("status"),
                float(o.get("total") or 0),
                o.get("currency") or "EUR",
                p.get("email") or o.get("email"),
                p.get("phone"),
                p.get("full_name") or None,
                o.get("city") or p.get("city"),
                o.get("state") or p.get("state"),
                o.get("country") or p.get("country") or "ES",
                canal,
                tipo,
                fuente,
                attrib.get("_billing_referral") or attrib.get("billing_referral"),
                attrib.get("_wc_order_attribution_utm_source"),
                attrib.get("_wc_order_attribution_utm_medium"),
                attrib.get("_wc_order_attribution_utm_campaign"),
                attrib.get("_wc_order_attribution_source_type"),
            ),
        )
        for i, item in enumerate(o.get("items") or []):
            name = item.get("name") or ""
            conn.execute(
                "INSERT OR REPLACE INTO fact_wc_order_item VALUES (?,?,?,?,?,?)",
                (
                    oid,
                    i,
                    name,
                    product_family(name),
                    float(item.get("qty") or 1),
                    float(item.get("total") or 0),
                ),
            )
        conn.execute(
            "INSERT OR IGNORE INTO dim_channel VALUES (?,?,?,?)",
            (canal, canal, tipo, fuente),
        )

    # kpi by period/channel
    rows = conn.execute(
        """SELECT period_id, channel_id, COUNT(*), SUM(total)
           FROM fact_wc_order WHERE period_id IS NOT NULL
           GROUP BY period_id, channel_id"""
    ).fetchall()
    for period_id, channel_id, orders_n, rev in rows:
        aov = (rev or 0) / orders_n if orders_n else 0
        conn.execute(
            "INSERT INTO kpi_period_channel VALUES (?,?,?,?,?)",
            (period_id, channel_id, orders_n, rev, aov),
        )
    print(f"WC orders: {len(orders)} · channels: {dict(ch_count)}")


def ingest_meta(conn: sqlite3.Connection):
    daily = load("meta-daily.json")
    if not daily:
        return
    rows = daily["rows"] if isinstance(daily, dict) else daily
    for r in rows:
        d = r["date"]
        conn.execute(
            "INSERT OR REPLACE INTO fact_meta_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                d,
                sy_for(d),
                month_of(d),
                r.get("spend"),
                r.get("impressions"),
                r.get("clicks"),
                r.get("reach"),
                r.get("leads"),
                r.get("purchases"),
                r.get("cpc"),
                r.get("ctr"),
            ),
        )
    print(f"Meta daily: {len(rows)}")


def ingest_google_ads(conn: sqlite3.Connection):
    raw = load("google-ads-conversions-raw.json")
    # Prefer fresh pull; fallback to google-daily.json
    if raw and raw.get("campaign_daily"):
        for r in raw["campaign_daily"]:
            d = r["date"]
            conn.execute(
                """INSERT OR REPLACE INTO fact_google_ads_campaign_daily
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    d,
                    str(r["campaign_id"]),
                    r.get("campaign"),
                    r.get("channel"),
                    r.get("status"),
                    r.get("spend"),
                    r.get("impressions"),
                    r.get("clicks"),
                    r.get("conversions"),
                    r.get("value"),
                    r.get("ctr"),
                    r.get("cpc"),
                    sy_for(d),
                    month_of(d),
                ),
            )
        for r in raw.get("conv_rows") or []:
            cat = r.get("conv_category") or "OTHER"
            if cat == "PURCHASE":
                klass = "purchase"
            elif cat == "SUBMIT_LEAD_FORM":
                klass = "lead"
            else:
                klass = "other"
            d = r["date"]
            conn.execute(
                """INSERT OR REPLACE INTO fact_google_ads_conversion_daily
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    d,
                    str(r.get("campaign_id")),
                    r.get("campaign"),
                    r.get("conv_name") or "",
                    cat,
                    klass,
                    r.get("conversions"),
                    r.get("value"),
                    sy_for(d),
                    month_of(d),
                ),
            )
        print(
            f"Google Ads: {len(raw['campaign_daily'])} camp-days · "
            f"{len(raw.get('conv_rows') or [])} conv-rows · "
            f"purchase={raw.get('summary',{}).get('purchase_conversions')} "
            f"leads={raw.get('summary',{}).get('lead_conversions')}"
        )
        return

    gd = load("google-daily.json")
    if not gd:
        return
    for r in gd["rows"]:
        d = r["date"]
        conn.execute(
            """INSERT OR REPLACE INTO fact_google_ads_campaign_daily
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                d,
                str(r["campaignId"]),
                r.get("campaignName"),
                r.get("channel"),
                r.get("status"),
                r.get("spend"),
                r.get("impressions"),
                r.get("clicks"),
                r.get("conversions"),
                r.get("convValue"),
                r.get("ctr"),
                r.get("cpc"),
                sy_for(d),
                month_of(d),
            ),
        )
    print(f"Google Ads fallback daily: {len(gd['rows'])}")


def ingest_meta_matches(conn: sqlite3.Connection):
    raw = load("meta-wc-matches.json")
    if not raw:
        return
    for m in raw["matches"]:
        d = (m.get("order_date") or "")[:10]
        conn.execute(
            "INSERT OR REPLACE INTO fact_meta_wc_match VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                m["order_id"],
                d,
                sy_for(d),
                month_of(d) if d else None,
                m.get("order_total"),
                m.get("match_method"),
                m.get("lag_days"),
                m.get("lead_uid"),
                m.get("lead_source"),
                m.get("form_name"),
                m.get("campaign_name"),
            ),
        )
    print(f"Meta×WC matches: {raw.get('n')}")


def ingest_ga4(conn: sqlite3.Connection):
    raw = load("ga4-bps-raw.json")
    if not raw:
        return
    for period_key, payload in raw.items():
        if not period_key.startswith("sy-"):
            continue
        tot = payload.get("totals") or {}
        conn.execute(
            "INSERT OR REPLACE INTO fact_ga4_period_totals VALUES (?,?,?,?,?,?,?)",
            (
                period_key,
                float(tot.get("sessions") or 0),
                float(tot.get("totalUsers") or 0),
                float(tot.get("ecommercePurchases") or 0),
                float(tot.get("purchaseRevenue") or 0),
                float(tot.get("conversions") or 0),
                float(tot.get("engagedSessions") or 0),
            ),
        )
        for r in payload.get("channels") or []:
            conn.execute(
                "INSERT OR REPLACE INTO fact_ga4_channel_period VALUES (?,?,?,?,?,?,?)",
                (
                    period_key,
                    r.get("sessionDefaultChannelGroup"),
                    float(r.get("sessions") or 0),
                    float(r.get("totalUsers") or 0),
                    float(r.get("ecommercePurchases") or 0),
                    float(r.get("purchaseRevenue") or 0),
                    float(r.get("conversions") or 0),
                ),
            )
        for r in payload.get("source_medium") or []:
            conn.execute(
                "INSERT OR REPLACE INTO fact_ga4_source_medium_period VALUES (?,?,?,?,?,?,?,?)",
                (
                    period_key,
                    r.get("sessionSource") or "",
                    r.get("sessionMedium") or "",
                    r.get("sessionCampaignName") or "(not set)",
                    float(r.get("sessions") or 0),
                    float(r.get("ecommercePurchases") or 0),
                    float(r.get("purchaseRevenue") or 0),
                    float(r.get("conversions") or 0),
                ),
            )
    print("GA4 periods loaded")


def ingest_gsc(conn: sqlite3.Connection):
    raw = load("ga4-gsc-crosscheck.json") or {}
    gsc = raw.get("gsc") or {}
    mapping = {"24-25": "sy-2024-25", "25-26": "sy-2025-26"}
    for k, pid in mapping.items():
        block = gsc.get(k) or {}
        if not block:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO fact_gsc_period VALUES (?,?,?)",
            (pid, block.get("clicks"), block.get("impressions")),
        )
    for q in gsc.get("top_queries_2526") or []:
        conn.execute(
            "INSERT OR REPLACE INTO fact_gsc_query VALUES (?,?,?,?,?,?)",
            (
                "sy-2025-26",
                q["keys"][0],
                q.get("clicks"),
                q.get("impressions"),
                q.get("ctr"),
                q.get("position"),
            ),
        )
    print("GSC loaded")


def build_paid_kpis(conn: sqlite3.Connection):
    """Canonical paid KPIs per school year — separates purchase vs lead for Google."""
    cross = load("meta-wc-cross-summary.json") or {}
    periods = cross.get("periods") or {}

    for pid, _, start, end in PERIODS[:2]:
        # Meta platform
        meta = conn.execute(
            """SELECT COALESCE(SUM(spend),0), COALESCE(SUM(impressions),0), COALESCE(SUM(clicks),0),
                      COALESCE(SUM(reach),0), COALESCE(SUM(leads),0), COALESCE(SUM(purchases),0)
               FROM fact_meta_daily WHERE period_id=?""",
            (pid,),
        ).fetchone()
        match = periods.get(pid) or {}
        # Spend always from Ads Manager daily (fact_meta_daily). Cross-summary only for WC match orders/rev/leads.
        m_spend = float(meta[0] or 0)
        m_orders = float(match.get("orders") or 0)
        m_rev = float(match.get("rev") or 0)
        m_leads = float(match.get("leads") or meta[4] or 0)
        cac = m_spend / m_orders if m_orders else None
        roas = m_rev / m_spend if m_spend else None
        conv = (100 * m_orders / m_leads) if m_leads else None
        conn.execute(
            "INSERT OR REPLACE INTO kpi_paid_period VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pid,
                "meta",
                m_spend,
                meta[1],
                meta[2],
                meta[3],
                meta[4],
                meta[5],
                None,
                m_orders,
                m_rev,
                cac,
                roas,
                conv,
                f"Verified Meta→WC. Platform leads={meta[4]:.0f}; cross leads={m_leads:.0f}; pixel purch={meta[5]:.0f}",
            ),
        )

        # Google Ads
        g = conn.execute(
            """SELECT COALESCE(SUM(spend),0), COALESCE(SUM(impressions),0), COALESCE(SUM(clicks),0)
               FROM fact_google_ads_campaign_daily WHERE period_id=?""",
            (pid,),
        ).fetchone()
        purch = conn.execute(
            """SELECT COALESCE(SUM(conversions),0), COALESCE(SUM(conv_value),0)
               FROM fact_google_ads_conversion_daily WHERE period_id=? AND conv_class='purchase'""",
            (pid,),
        ).fetchone()
        leads = conn.execute(
            """SELECT COALESCE(SUM(conversions),0)
               FROM fact_google_ads_conversion_daily WHERE period_id=? AND conv_class='lead'""",
            (pid,),
        ).fetchone()
        wc = conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(total),0) FROM fact_wc_order
               WHERE period_id=? AND channel_id='Google Ads'""",
            (pid,),
        ).fetchone()
        g_spend = float(g[0] or 0)
        g_orders = float(wc[0] or 0)
        g_rev = float(wc[1] or 0)
        lead_n = float(leads[0] or 0)
        purch_n = float(purch[0] or 0)
        conn.execute(
            "INSERT OR REPLACE INTO kpi_paid_period VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pid,
                "google_ads",
                g_spend,
                g[1],
                g[2],
                None,
                None,
                purch_n,
                lead_n,
                g_orders,
                g_rev,
                (g_spend / g_orders) if g_orders else None,
                (g_rev / g_spend) if g_spend else None,
                (100 * g_orders / lead_n) if lead_n else None,
                f"Ads PURCHASE={purch_n:.0f} (value {purch[1]:.0f}€) · LEADS={lead_n:.0f} · WC utm cpc={g_orders:.0f}. Coverage from {start} limited by Ads export.",
            ),
        )
    print("kpi_paid_period built")


def write_dictionary():
    md = f"""# BPS Marketing Data Dictionary

Built: `{NOW}`  
Database: `dashboard/db/bps.db`

## Trust layers

| Layer | Meaning | Tables |
|-------|---------|--------|
| **gold** | Business truth for decisions | `fact_wc_order`, `fact_meta_wc_match`, `kpi_period_channel` (WC), Google Ads WC UTM orders |
| **silver** | Platform metrics (correct in their system) | Meta/Google Ads/GA4/GSC facts |
| **bronze** | Staging / incomplete coverage | Older Meta months missing, Ads before 2026-04 |

## Google Ads: purchase vs lead

Account `1064441284` (login MCC `5963150101`):

| Class | conversion_action category | Primary actions |
|-------|----------------------------|-----------------|
| **purchase** | `PURCHASE` | Compra (GA4 purchase) |
| **lead** | `SUBMIT_LEAD_FORM` | form_submit, submit_lead_form, Lead form - Submit |

**Do not sum** purchase + lead into a single “CAC pedido”.  
Use purchase for ROAS/CPA compra; lead for CPL; WC `utm_medium=cpc` for business CAC.

## Meta: which order count?

| Metric | Use? |
|--------|------|
| Meta×WC match (`fact_meta_wc_match`) | **YES — canonical Meta→pedido** |
| Checkout UTM Meta Ads | NO (subregistro) |
| Meta pixel purchases | Campaign optimization only |

## Academic periods

| ID | Range |
|----|-------|
| sy-2024-25 | 2024-09-01 → 2025-08-31 |
| sy-2025-26 | 2025-09-01 → 2026-08-30 |
| sy-2026-27 | 2026-09-01 → 2027-08-31 |

## Rebuild

```bash
python3 scripts/build_bps_db.py
```

Requires local JSON under `dashboard/data/` (WC, Meta, matches, GA4, GSC, google-ads-conversions-raw).
"""
    (DB_DIR / "DATA_DICTIONARY.md").write_text(md)


def validate(conn: sqlite3.Connection):
    print("\n=== VALIDATION ===")
    for row in conn.execute("SELECT * FROM v_orders_by_period"):
        print("WC", row)
    for row in conn.execute("SELECT * FROM v_google_ads_purchase_vs_lead"):
        print("GAds class", row)
    for row in conn.execute("SELECT period_id, platform, spend, platform_purchases, platform_lead_convs, wc_orders_verified, cac, roas FROM kpi_paid_period"):
        print("PAID", row)
    for row in conn.execute(
        """SELECT period_id, channel_id, orders FROM kpi_period_channel
           WHERE channel_id IN ('Meta Ads','Google Ads','Google Orgánico','Instagram')
           ORDER BY period_id, orders DESC"""
    ):
        print("CH", row)
    # Meta match vs UTM
    for pid in ("sy-2024-25", "sy-2025-26"):
        m = conn.execute("SELECT COUNT(*) FROM fact_meta_wc_match WHERE period_id=?", (pid,)).fetchone()[0]
        u = conn.execute(
            "SELECT COUNT(*) FROM fact_wc_order WHERE period_id=? AND channel_id='Meta Ads'",
            (pid,),
        ).fetchone()[0]
        print(f"{pid}: Meta verified={m} · Meta UTM checkout={u}")


def main():
    conn = connect()
    seed_dims(conn)
    ingest_wc(conn)
    ingest_meta(conn)
    ingest_google_ads(conn)
    ingest_meta_matches(conn)
    ingest_ga4(conn)
    ingest_gsc(conn)
    build_paid_kpis(conn)
    conn.commit()
    validate(conn)
    write_dictionary()
    conn.close()
    print(f"\nDB → {DB_PATH}")
    print(f"Dict → {DB_DIR / 'DATA_DICTIONARY.md'}")


if __name__ == "__main__":
    main()

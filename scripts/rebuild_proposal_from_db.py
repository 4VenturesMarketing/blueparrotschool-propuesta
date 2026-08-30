#!/usr/bin/env python3
"""Export canonical payload from bps.db and rebuild propuesta-marketing-bps.html."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "dashboard" / "db" / "bps.db"
DATA = ROOT / "dashboard" / "data"
HTML = ROOT / "propuesta-marketing-bps.html"
OUT_JSON = DATA / "proposal-from-db.json"

PROVINCE = {
    "M": ("Madrid", 40.4168, -3.7038),
    "MA": ("Málaga", 36.7213, -4.4214),
    "SE": ("Sevilla", 37.3891, -5.9845),
    "B": ("Barcelona", 41.3874, 2.1686),
    "V": ("Valencia", 39.4699, -0.3763),
    "GR": ("Granada", 37.1773, -3.5986),
    "MU": ("Murcia", 37.9922, -1.1307),
    "CA": ("Cádiz", 36.5271, -6.2886),
    "Z": ("Zaragoza", 41.6488, -0.8891),
    "TO": ("Toledo", 39.8628, -4.0273),
    "A": ("Alicante", 38.3452, -0.4810),
    "CO": ("Córdoba", 37.8882, -4.7794),
    "J": ("Jaén", 37.7796, -3.7849),
    "AL": ("Almería", 36.8340, -2.4637),
    "GC": ("Las Palmas", 28.1235, -15.4366),
    "TF": ("S.C. Tenerife", 28.4636, -16.2518),
    "PM": ("Baleares", 39.5696, 2.6502),
    "BI": ("Bizkaia", 43.2630, -2.9350),
    "SS": ("Gipuzkoa", 43.3183, -1.9812),
    "VI": ("Álava", 42.8467, -2.6716),
    "PO": ("Pontevedra", 42.4310, -8.6444),
    "C": ("A Coruña", 43.3623, -8.4115),
    "O": ("Asturias", 43.3614, -5.8494),
    "S": ("Cantabria", 43.4623, -3.8099),
    "NA": ("Navarra", 42.8125, -1.6458),
    "LO": ("La Rioja", 42.4627, -2.4449),
    "BU": ("Burgos", 42.3439, -3.6969),
    "SA": ("Salamanca", 40.9701, -5.6635),
    "LE": ("León", 42.5987, -5.5671),
    "VA": ("Valladolid", 41.6523, -4.7245),
    "P": ("Palencia", 42.0096, -4.5288),
    "SG": ("Segovia", 40.9429, -4.1088),
    "AV": ("Ávila", 40.6566, -4.6815),
    "SO": ("Soria", 41.7636, -2.4649),
    "CU": ("Cuenca", 40.0704, -2.1374),
    "AB": ("Albacete", 38.9942, -1.8585),
    "CR": ("Ciudad Real", 38.9848, -3.9274),
    "GU": ("Guadalajara", 40.6330, -3.1660),
    "CS": ("Castellón", 39.9864, -0.0513),
    "T": ("Tarragona", 41.1189, 1.2445),
    "L": ("Lleida", 41.6176, 0.6200),
    "GI": ("Girona", 41.9794, 2.8214),
    "HU": ("Huesca", 42.1401, -0.4089),
    "TE": ("Teruel", 40.3456, -1.1065),
    "CC": ("Cáceres", 39.4753, -6.3724),
    "BA": ("Badajoz", 38.8794, -6.9707),
    "H": ("Huelva", 37.2614, -6.9447),
    "ML": ("Melilla", 35.2923, -2.9381),
    "CE": ("Ceuta", 35.8894, -5.3213),
}


AGE_BAND_ORDER = ["<18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]


def _load_wc_buyer() -> dict:
    """Buyer geo/demo from WC billing (birth + name gender + cities)."""
    birth = json.loads((DATA / "wc-birth-parsed.json").read_text())
    gender = json.loads((DATA / "wc-gender-from-names.json").read_text())
    geo = json.loads((DATA / "wc-geo-demo-sy.json").read_text())

    def age_block(sy_id: str) -> dict:
        b = birth[sy_id]
        bands = []
        known = 0
        for band in AGE_BAND_ORDER:
            cell = (b.get("age") or {}).get(band) or {"orders": 0, "rev": 0}
            known += cell.get("orders") or 0
            bands.append({"band": band, "orders": cell.get("orders") or 0, "rev": cell.get("rev") or 0})
        missing = (b.get("age") or {}).get("sin fecha") or {"orders": 0, "rev": 0}
        return {
            "orders": b["orders"],
            "parsed_pct": b["parsed_pct"],
            "no_birth": b["no_key"],
            "bands": bands,
            "known_orders": known,
            "missing": {"orders": missing.get("orders") or 0, "rev": missing.get("rev") or 0},
        }

    def gender_block(sy_id: str) -> dict:
        g = gender[sy_id]
        return {
            "orders": g["orders"],
            "coverage_pct": g["coverage_pct"],
            "mujer_of_known_pct": g["mujer_of_known_pct"],
            "hombre_of_known_pct": g["hombre_of_known_pct"],
            "gender": g["gender"],
        }

    def cities(sy_key: str, n: int = 10) -> list[dict]:
        rows = (geo.get(sy_key) or {}).get("city") or []
        return [{"name": r[0], "orders": r[1], "rev": r[2]} for r in rows[:n]]

    prev = age_block("sy-2024-25")
    cur = age_block("sy-2025-26")
    # Concentration Madrid+Málaga from geo demo provinces
    def mad_mal(sy_key: str) -> dict:
        prov = {(r[0]): r for r in ((geo.get(sy_key) or {}).get("province") or [])}
        orders = (geo.get(sy_key) or {}).get("orders") or 1
        mad = (prov.get("Madrid") or [None, 0, 0])[1]
        mal = (prov.get("Málaga") or [None, 0, 0])[1]
        return {
            "madrid": mad,
            "malaga": mal,
            "share_pct": round(100 * (mad + mal) / orders, 1),
            "madrid_pct": round(100 * mad / orders, 1),
            "malaga_pct": round(100 * mal / orders, 1),
            "orders": orders,
        }

    return {
        "source": {
            "age": "billing_birth / _billing_birth (parser dashboard/lib_parse_birth.py)",
            "gender": "inferido por nombre de pila (WC no guarda género)",
            "geo": "billing city/state del pedido",
        },
        "prev": {
            "age": prev,
            "gender": gender_block("sy-2024-25"),
            "cities": cities("wc_2024_25"),
            "hub": mad_mal("wc_2024_25"),
        },
        "cur": {
            "age": cur,
            "gender": gender_block("sy-2025-26"),
            "cities": cities("wc_2025_26"),
            "hub": mad_mal("wc_2025_26"),
        },
    }


def _enrich_buyer_profile(yoy: dict, wc_buyer: dict, periods: dict) -> None:
    """Overwrite age/gender primary with WC reality (not Meta spend mix)."""
    bp = yoy.setdefault("buyerProfile", {})
    cur_age = wc_buyer["cur"]["age"]
    known = max(cur_age["known_orders"], 1)
    age_primary = []
    for band in cur_age["bands"]:
        if band["orders"] <= 0:
            continue
        age_primary.append(
            {"band": band["band"], "share_pct": round(100 * band["orders"] / known, 1), "orders": band["orders"]}
        )
    age_primary.sort(key=lambda x: -x["orders"])
    bp["age_primary"] = age_primary[:4]
    bp["age_coverage_pct"] = cur_age["parsed_pct"]

    g = wc_buyer["cur"]["gender"]
    bp["gender_primary"] = [
        {"g": "female", "share_pct": g["mujer_of_known_pct"], "orders": g["gender"]["mujer"]["orders"]},
        {"g": "male", "share_pct": g["hombre_of_known_pct"], "orders": g["gender"]["hombre"]["orders"]},
    ]
    bp["gender_coverage_pct"] = g["coverage_pct"]

    hub = wc_buyer["cur"]["hub"]
    hub_prev = wc_buyer["prev"]["hub"]
    bp["geo_primary"] = f"Madrid + Málaga ({hub['share_pct']}% pedidos 25–26)"
    top2 = " + ".join(f"{b['band']} ({b['share_pct']}%)" for b in age_primary[:2])
    persona = bp.setdefault("persona", {})
    persona["title"] = "Mujer 18–34 · Madrid/Málaga · certificación"
    persona["summary"] = (
        f"Perfil WC 25–26: {g['mujer_of_known_pct']:.0f}% mujeres; edad {top2}. "
        f"Geo Madrid+Málaga {hub['share_pct']}%. Producto #1 APTIS/Cambridge."
    )
    persona["motivations"] = persona.get("motivations") or [
        "Certificación laboral/oposición",
        "Intensivo antes de convocatoria",
        "Flexibilidad online",
    ]

    yoy.setdefault("plan", {})["roadmap"] = [
        {
            "q": "Q1 · Sep–Nov",
            "items": [
                "Ramp-up curso: APTIS/Cambridge Search + PMax",
                "Brand Search always-on + remarketing leads sin compra",
                "Meta: lookalikes compradores WC (cortar frío sin pedido)",
                "UTM obligatorio + SLA contacto <1 h",
            ],
        },
        {
            "q": "Q2 · Dic–Feb",
            "items": [
                "Convocatorias invierno: landings por certificado",
                "Recortar audiencias Meta con lead→pedido <1%",
                "SEO/GSC: reforzar queries comerciales top",
                "Test extensiones call/WhatsApp en Search",
            ],
        },
        {
            "q": "Q3 · Mar–May",
            "items": [
                "Intensivos primavera + creatividades cualificadas Meta",
                "Optimizar CAC/ROAS WC por campaña (no por pixel)",
                "Ampliar brand + remarketing pre-verano",
                "Revisar CrUX/móvil en landings de conversión",
            ],
        },
        {
            "q": "Q4 · Jun–Ago",
            "items": [
                "Jun–Jul = pico demanda certs (Cambridge/APTIS): subir IS y ppto Google",
                "Campañas convocatoria verano + intensivos (no hibernar)",
                "Meta remarketing agresivo a leads Q3 sin compra",
                "Agosto: sostener brand + retarget; preparar creatividades septiembre",
                "No congelar tests: validar ofertas/plazas en el pico real de búsquedas",
            ],
        },
    ]

    _sync_plan_from_estimator(yoy)


def _weighted_kw_yoy(block: dict | None) -> float | None:
    """Volume-weighted YoY % from Keyword Planner top keywords."""
    kws = (block or {}).get("top_keywords") or []
    tw = 0.0
    wy = 0.0
    for k in kws:
        avg = float(k.get("avg_monthly") or 0)
        yoy = k.get("yoy_pct")
        if yoy is None or avg <= 0:
            continue
        tw += avg
        wy += avg * float(yoy)
    return (wy / tw) if tw else None


def _split_prev_cur(avg: float, yoy_pct: float | None) -> tuple[int, int, float | None]:
    """From blended monthly avg + YoY%, estimate school-year volumes."""
    if not avg:
        return 0, 0, None
    if yoy_pct is None:
        a = int(round(avg))
        return a, a, None
    ratio = 1 + float(yoy_pct) / 100.0
    if ratio <= 0.05:
        ratio = 0.05
    prev = int(round(2 * avg / (1 + ratio)))
    cur = int(round(prev * ratio))
    return prev, cur, round(float(yoy_pct), 1)


def _campaign_group(pid: str, brand: bool = False) -> dict:
    """Map estimator product → campaña genérica del simulador."""
    pid = (pid or "").strip().lower()
    if brand or pid in {"bps home", "bps", "marca"}:
        return {"id": "marca", "label": "Marca"}
    if pid in {"cambridge", "aptis", "ielts", "trinity", "delf"}:
        return {"id": "certificaciones", "label": "Certificaciones"}
    if pid in {"ingles", "español", "espanol", "frances", "italiano", "aleman", "chino", "portugues", "japones"}:
        return {"id": "idiomas", "label": "Otros idiomas"}
    if pid in {"kids"}:
        return {"id": "academias", "label": "Academias / Kids"}
    if pid in {"empresas"}:
        return {"id": "b2b", "label": "B2B / Empresas"}
    if pid in {"plataforma"}:
        return {"id": "online", "label": "Plataforma online"}
    return {"id": "otros", "label": "Otros"}


def _sync_plan_from_estimator(yoy: dict) -> None:
    """Align plan products + rates with estimador-google-ads-bps (all KW products)."""
    slim_path = DATA / "ads-estimator-slim.json"
    if not slim_path.exists():
        return
    slim = json.loads(slim_path.read_text())
    est_products = {}
    est_path = DATA / "ads-estimator.json"
    if est_path.exists():
        est_products = (json.loads(est_path.read_text()).get("products") or {})
    preset = ((slim.get("meta") or {}).get("presets") or {}).get("max_conv") or {}
    defaults_meta = (slim.get("meta") or {}).get("defaults") or {}
    plan = yoy.setdefault("plan", {})
    d = plan.setdefault("defaults", {})
    # Controles del simulador: IS ~20% y ppto total = Google(IS)/share (Google+Meta)
    d["isrPct"] = 20
    d["ctrPct"] = float(preset.get("ctr_pct") or defaults_meta.get("ctr_pct") or 5)
    d["cvrLeadPct"] = float(preset.get("cvr_lead_pct") or defaults_meta.get("cvr_lead_pct") or 4.2)
    d["leadToSalePct"] = float(preset.get("cvr_lead_to_sale_pct") or defaults_meta.get("cvr_lead_to_sale_pct") or 16)
    d["aov"] = float(d.get("aov") or defaults_meta.get("aov") or 230)
    d["estimatorPreset"] = "max_conv"
    d["intents"] = list(preset.get("intents") or ["comercial", "informacional", "marca"])
    d["googleShare"] = 0.65
    d["metaShare"] = 0.35
    plan["productIs"] = dict(preset.get("product_is") or {})
    # Alinear IS de genéricas al default del simulador (marca se queda ~90)
    for pid in list(plan["productIs"].keys()):
        sp = (slim.get("products") or {}).get(pid) or {}
        if not sp.get("brand") and pid != "bps home":
            plan["productIs"][pid] = d["isrPct"]
    plan["productLeadCvr"] = dict(preset.get("product_lead_cvr") or {})

    intent_set = set(d["intents"])
    default_on = set(preset.get("products") or ["bps home", "aptis", "cambridge", "ielts"])
    # Idiomas genéricos caros OFF por defecto (como el estimador)
    default_off = {"ingles", "frances", "aleman", "italiano", "portugues", "chino", "japones", "español"}

    # YoY Keyword Planner (weighted) → estima búsquedas curso 24–25 vs 25–26
    def _norm_pid(x: str) -> str:
        x = unicodedata.normalize("NFC", (x or "").strip().lower())
        return x.replace("ñ", "n")

    kw_yoy = {}
    kw_summary_path = DATA / "keyword-stats-summary.json"
    if kw_summary_path.exists():
        for s in (json.loads(kw_summary_path.read_text()).get("summaries") or []):
            kw_yoy[_norm_pid(s.get("product") or "")] = {
                "yoy_pct": float(s.get("weighted_yoy_pct") or 0),
                "top": s.get("top") or [],
            }

    products = []
    for pid, sp in (slim.get("products") or {}).items():
        if not sp:
            continue
        intents = sp.get("intents") or {}
        searches = 0.0
        bid_w = 0.0
        bid_n = 0.0
        intent_rows = []
        top_kw = []
        for name, block in intents.items():
            s = float(block.get("searches_month") or 0)
            if name in intent_set:
                searches += s
            if block.get("cpc_mid") and s and name in intent_set:
                bid_w += float(block["cpc_mid"]) * s
                bid_n += s
            intent_rows.append(
                {
                    "intent": name,
                    "searches_month": int(s),
                    "cpc_mid": block.get("cpc_mid"),
                    "n": block.get("n"),
                }
            )
            if name == "comercial":
                top_kw = (block.get("top_keywords") or [])[:8]
        totals = sp.get("totals") or {}
        # Para demanda KW: totales reales de todos los intents
        searches_all = float(totals.get("searches_month") or 0)
        cpc = round(bid_w / bid_n, 2) if bid_n else round(float(sp.get("default_cpc") or 0.48), 2)
        enabled = pid in default_on and pid not in default_off
        yoy_row = kw_yoy.get(_norm_pid(pid)) or {}
        yoy_pct = float(yoy_row.get("yoy_pct") or 0)
        avg = float(searches_all or searches or 0)
        searches_prev, searches_cur, yoy_pct = _split_prev_cur(avg, yoy_pct if avg else None)

        # YoY por intención (comercial / informacional) desde keywords del estimador
        est_intents = ((est_products.get(pid) or {}).get("intents") or intents)
        com_avg = float(totals.get("searches_comercial") or (intents.get("comercial") or {}).get("searches_month") or 0)
        info_avg = float(totals.get("searches_informacional") or (intents.get("informacional") or {}).get("searches_month") or 0)
        com_yoy = _weighted_kw_yoy(est_intents.get("comercial"))
        info_yoy = _weighted_kw_yoy(est_intents.get("informacional"))
        com_prev, com_cur, com_yoy = _split_prev_cur(com_avg, com_yoy)
        info_prev, info_cur, info_yoy = _split_prev_cur(info_avg, info_yoy)

        label = sp.get("label") or pid
        if bool(sp.get("brand")) or pid == "bps home":
            label = "BPS"
        products.append(
            {
                "id": pid,
                "label": label,
                "enabled": enabled,
                "brand": bool(sp.get("brand")),
                "campaignGroup": _campaign_group(pid, bool(sp.get("brand"))),
                "budgetShare": 0.25,
                "monthlySearches": int(searches or searches_all),
                "searches_comercial": int(com_avg),
                "searches_informacional": int(info_avg),
                "searches_marca": int(totals.get("searches_marca") or 0),
                "searches_total": int(searches_all or searches),
                "searches_prev": searches_prev,
                "searches_cur": searches_cur,
                "kw_yoy_pct": yoy_pct,
                "searches_com_prev": com_prev,
                "searches_com_cur": com_cur,
                "kw_yoy_com_pct": com_yoy,
                "searches_info_prev": info_prev,
                "searches_info_cur": info_cur,
                "kw_yoy_info_pct": info_yoy,
                "cpc": cpc,
                "ctrPct": float(sp.get("default_ctr_pct") or d["ctrPct"]),
                "aov": float(sp.get("aov") or d.get("aov") or 230),
                "defaultIs": float(sp.get("default_is_pct") or (90 if sp.get("brand") else d["isrPct"])),
                "seasonality": sp.get("seasonality") if isinstance(sp.get("seasonality"), list) else [1] * 12,
                "intents": intents,
                "intent_rows": intent_rows,
                "top_keywords": top_kw,
                "kw_n": int((intents.get("comercial") or {}).get("n") or 0),
                "wcFamily": (sp.get("wc_family") or sp.get("label") or pid),
            }
        )
    if products:
        wsum = sum(max(p["monthlySearches"], 1) for p in products if p["enabled"]) or 1
        for p in products:
            p["budgetShare"] = round((p["monthlySearches"] if p["enabled"] else 0) / wsum, 4)
        # orden: activos primero, luego por búsquedas
        products.sort(key=lambda p: (0 if p["enabled"] else 1, -p["searches_total"]))
        plan["products"] = products
        # Campañas genéricas para el simulador (UI + estimación agregada)
        groups = {}
        for p in products:
            g = p.get("campaignGroup") or _campaign_group(p["id"], bool(p.get("brand")))
            gid = g["id"]
            if gid not in groups:
                groups[gid] = {
                    "id": gid,
                    "label": g["label"],
                    "products": [],
                    "enabled": False,
                }
            groups[gid]["products"].append(p["id"])
            if p.get("enabled"):
                groups[gid]["enabled"] = True
        order = ["certificaciones", "marca", "idiomas", "academias", "b2b", "online", "otros"]
        plan["campaignGroups"] = sorted(
            groups.values(),
            key=lambda g: order.index(g["id"]) if g["id"] in order else 99,
        )
        # Ppto total real a IS default: Google(enabled)/googleShare (ej. 15%→~1370, 20%→~1680)
        g_share = float(d.get("googleShare") or 0.55)
        google_needed = 0.0
        for p in products:
            if not p.get("enabled"):
                continue
            searches = float(p.get("monthlySearches") or 0)
            cpc = float(p.get("cpc") or 0.48)
            ctr = float(p.get("ctrPct") or d.get("ctrPct") or 5) / 100.0
            is_brand = bool(p.get("brand") or p["id"] == "bps home")
            is_pct = float((plan.get("productIs") or {}).get(p["id"]) or (90 if is_brand else d["isrPct"]))
            google_needed += searches * (is_pct / 100.0) * ctr * cpc
        d["monthlyBudget"] = max(100, int(round(google_needed / g_share))) if g_share else max(100, int(round(google_needed)))
        d["googleNeededAtDefaultIs"] = round(google_needed, 2)

    # Canales = Meta Ads + Google Ads (shares por eficiencia WC 25–26, no 50/50)
    g_share = float(d.get("googleShare") or 0.65)
    m_share = float(d.get("metaShare") or 0.35)
    d["googleShare"] = g_share
    d["metaShare"] = m_share
    plan["channels"] = [
        {
            "id": "google",
            "label": "Google Ads",
            "type": "google",
            "enabled": True,
            "minBudget": 0,
            "budgetShare": g_share,
            "products": [p["id"] for p in products],
        },
        {
            "id": "meta",
            "label": "Meta Ads",
            "type": "meta",
            "enabled": True,
            "minBudget": 0,
            "budgetShare": m_share,
            "products": [p["id"] for p in products if not p.get("brand")],
        },
    ]


def _safe_div(a, b, default=0.0):
    try:
        if b in (0, None) or a is None:
            return default
        return float(a) / float(b)
    except Exception:
        return default


def _meta_seasonality_from_db(conn: sqlite3.Connection, period_id: str = "sy-2025-26") -> list[float]:
    """Factores mensuales Meta (ene–dic) normalizados a media 1.0 desde gasto real."""
    rows = conn.execute(
        """SELECT substr(date,1,7) AS month, SUM(spend) AS spend
           FROM fact_meta_daily WHERE period_id=? GROUP BY 1 ORDER BY 1""",
        (period_id,),
    ).fetchall()
    by_cal = {}
    for month, spend in rows:
        if not month or spend is None:
            continue
        cal = int(month.split("-")[1]) - 1  # 0=ene
        by_cal[cal] = by_cal.get(cal, 0.0) + float(spend)
    if not by_cal:
        return [1.0] * 12
    avg = sum(by_cal.values()) / len(by_cal)
    if avg <= 0:
        return [1.0] * 12
    out = []
    for i in range(12):
        if i in by_cal:
            out.append(round(by_cal[i] / avg, 3))
        else:
            out.append(1.0)
    # Renormalizar a media exacta 1.0
    mean = sum(out) / 12.0
    if mean > 0:
        out = [round(x / mean, 3) for x in out]
    return out


def _weighted_google_cpc(plan: dict, isr_pct: float) -> float:
    """CPC medio ponderado del estimador KW (suele ser > CPC real Ads)."""
    products = plan.get("products") or []
    product_is = plan.get("productIs") or {}
    spend = clicks = 0.0
    for p in products:
        if p.get("enabled") is False:
            continue
        searches = float(p.get("monthlySearches") or 0)
        ctr = float(p.get("ctrPct") or 5) / 100.0
        cpc = float(p.get("cpc") or 0.48)
        is_brand = bool(p.get("brand") or p.get("id") == "bps home")
        is_pct = float(product_is.get(p["id"]) or (90 if is_brand else isr_pct))
        clk = searches * (is_pct / 100.0) * ctr
        spend += clk * cpc
        clicks += clk
    return round(spend / clicks, 4) if clicks else 0.48


def _attach_media_mix(yoy: dict, periods: dict, conn: sqlite3.Connection | None = None) -> None:
    """Benchmarks reales por canal + recomendación de mix (no tratar Meta=Google)."""
    cur = periods.get("sy-2025-26") or {}
    meta = (cur.get("paid") or {}).get("meta") or {}
    gads = (cur.get("paid") or {}).get("google_ads") or {}

    def rates(ch: dict, lead_key: str) -> dict:
        spend = float(ch.get("spend") or 0)
        clicks = float(ch.get("clicks") or 0)
        imps = float(ch.get("impressions") or 0)
        leads = float(ch.get(lead_key) or ch.get("platform_leads") or ch.get("platform_lead_convs") or 0)
        orders = float(ch.get("wc_orders_verified") or 0)
        rev = float(ch.get("wc_revenue_verified") or 0)
        return {
            "spend": round(spend, 2),
            "clicks": int(clicks),
            "impressions": int(imps),
            "leads": int(leads),
            "orders": int(orders),
            "rev": round(rev, 2),
            "cpc": round(_safe_div(spend, clicks), 2),
            "ctrPct": round(100 * _safe_div(clicks, imps), 2),
            "cvrLeadPct": round(100 * _safe_div(leads, clicks), 2),
            "leadToSalePct": round(100 * _safe_div(orders, leads), 2),
            "cac": round(_safe_div(spend, orders), 0) if orders else None,
            "roas": round(_safe_div(rev, spend), 2) if spend else None,
        }

    g_r = rates(gads, "platform_lead_convs")
    m_r = rates(meta, "platform_leads")

    # Pedidos declarados IG/FB (no = Meta Ads verificado)
    declared = {"instagram": {"orders": 0, "rev": 0}, "facebook": {"orders": 0, "rev": 0}}
    for row in cur.get("channels") or []:
        name = (row.get("canal") or "").lower()
        if name == "instagram":
            declared["instagram"] = {"orders": int(row.get("orders") or 0), "rev": float(row.get("rev") or 0)}
        elif name == "facebook":
            declared["facebook"] = {"orders": int(row.get("orders") or 0), "rev": float(row.get("rev") or 0)}

    # Mix recomendado por eficiencia (peso ~ 1/CAC), acotado
    g_cac = g_r["cac"] or 120
    m_cac = m_r["cac"] or 300
    inv_g, inv_m = 1 / g_cac, 1 / m_cac
    g_share = inv_g / (inv_g + inv_m)
    g_share = max(0.55, min(0.75, g_share))  # Google mayoría, Meta no desaparece
    m_share = round(1 - g_share, 2)
    g_share = round(g_share, 2)

    verdict = "ambos"
    if g_r["roas"] and m_r["roas"] and g_r["roas"] >= 1.5 and m_r["roas"] < 1.0:
        verdict = "ambos_google_first"
    elif not g_r["spend"] and m_r["spend"]:
        verdict = "meta_only_hist"
    elif g_r["roas"] and g_r["roas"] >= 1.5 and (not m_r["roas"] or m_r["roas"] < 0.8):
        verdict = "ambos_google_first"

    plan = yoy.setdefault("plan", {})
    d = plan.setdefault("defaults", {})
    aov = float(d.get("aov") or 235)
    isr_pct = float(d.get("isrPct") or 20)
    model_cpc = _weighted_google_cpc(plan, isr_pct)

    # Baseline 25–26 (WC verificado)
    g_base_roas = float(g_r["roas"] or 2.34)
    m_base_roas = float(m_r["roas"] or 0.77)

    g_lead_base = float(g_r["cvrLeadPct"] or 3.7)
    g_sale_base = float(g_r["leadToSalePct"] or 13)
    m_lead_base = float(m_r["cvrLeadPct"] or 8.4)
    m_sale_base = float(m_r["leadToSalePct"] or 2)
    m_cpc = float(m_r["cpc"] or 0.48)
    g_cpc_hist = float(g_r["cpc"] or 0.48)

    # Subidas lógicas (relativas al baseline), no ROAS forzado
    # Clic→lead: LP + formularios + extensiones (+10–12%)
    # Lead→pedido: nurture + remarketing + brand (+20–30%; Meta más margen)
    g_lead = round(min(5.5, g_lead_base * 1.12), 2)
    g_sale = round(min(18.0, g_sale_base * 1.25), 2)
    m_lead = round(min(11.0, m_lead_base * 1.10), 2)
    m_sale = round(min(3.2, m_sale_base * 1.30), 2)

    # CPC KW del estimador suele ser > CPC real Ads: escalamos coste Google
    # para no castigar el ROAS del plan sin inventar CRs irreales
    cpc_scale = round(min(1.0, _safe_div(g_cpc_hist, model_cpc, 1.0)), 3) if model_cpc else 1.0
    g_cpc_eff = model_cpc * cpc_scale

    g_plan_roas = round(_safe_div((g_lead / 100.0) * (g_sale / 100.0) * aov, g_cpc_eff), 2)
    m_plan_roas = round(_safe_div((m_lead / 100.0) * (m_sale / 100.0) * aov, m_cpc), 2)
    blend_plan = round(g_share * g_plan_roas + m_share * m_plan_roas, 2)
    blend_base = round(g_share * g_base_roas + m_share * m_base_roas, 2)

    d["googleShare"] = g_share
    d["metaShare"] = m_share
    d["googleCvrLeadPct"] = g_lead
    d["googleLeadToSalePct"] = g_sale
    d["metaCvrLeadPct"] = m_lead
    d["metaLeadToSalePct"] = m_sale
    d["metaCpc"] = m_cpc
    d["metaCtrPct"] = m_r["ctrPct"] or 1.2
    d["cvrLeadPct"] = d["googleCvrLeadPct"]
    d["leadToSalePct"] = d["googleLeadToSalePct"]
    d["googleModelCpc"] = model_cpc
    d["googleCpcScale"] = cpc_scale
    d["planGoogleRoas"] = g_plan_roas
    d["planMetaRoas"] = m_plan_roas
    if conn is not None:
        d["metaSeasonality"] = _meta_seasonality_from_db(conn, "sy-2025-26")
    else:
        d.setdefault("metaSeasonality", [1.0] * 12)

    for ch in plan.get("channels") or []:
        if ch.get("id") == "google":
            ch["budgetShare"] = g_share
        elif ch.get("id") == "meta":
            ch["budgetShare"] = m_share

    # Recalcular ppto default con nuevo share
    google_needed = float(d.get("googleNeededAtDefaultIs") or 0)
    if google_needed > 0 and g_share > 0:
        d["monthlyBudget"] = max(100, int(round(google_needed / g_share)))

    plan["mediaMix"] = {
        "period": "2025–26",
        "verdict": verdict,
        "recommended": {"googleShare": g_share, "metaShare": m_share},
        "google": g_r,
        "meta": m_r,
        "baseline": {
            "googleRoas": g_base_roas,
            "metaRoas": m_base_roas,
            "blendRoas": blend_base,
            "googleCvrLeadPct": g_lead_base,
            "googleLeadToSalePct": g_sale_base,
            "metaCvrLeadPct": m_lead_base,
            "metaLeadToSalePct": m_sale_base,
        },
        "planTargets": {
            "googleRoas": g_plan_roas,
            "metaRoas": m_plan_roas,
            "blendRoas": blend_plan,
            "googleCvrLeadPct": g_lead,
            "googleLeadToSalePct": g_sale,
            "metaCvrLeadPct": m_lead,
            "metaLeadToSalePct": m_sale,
            "googleModelCpc": model_cpc,
            "googleCpcScale": cpc_scale,
            "note": "Mejoras lógicas vs 25–26: clic→lead +10–12%, lead→pedido +25–30%. CPC Google escalado al real Ads.",
        },
        "declared_social": declared,
        "headline": "Sí a los dos canales, con Google como motor de eficiencia y Meta como apoyo de volumen/remarketing.",
        "bullets": [
            f"Baseline 25–26 (WC): Google ROAS {g_base_roas}× · Meta {m_base_roas}× · clic→lead {g_lead_base}%/{m_lead_base}% · lead→pedido {g_sale_base}%/{m_sale_base}%.",
            f"Plan 26–27 (subida lógica): Google clic→lead {g_lead}% · lead→pedido {g_sale}% · ROAS ~{g_plan_roas}×. Meta {m_lead}% → {m_sale}% · ROAS ~{m_plan_roas}×. Blend ≈ {blend_plan}×.",
            "Cómo subir clic→lead: landings por certificado, formularios cortos, call/whatsapp extensions, velocidad móvil, congruencia anuncio→LP.",
            "Cómo subir lead→pedido: SLA <1h, secuencia email/WhatsApp 7–14 días, remarketing compradores WC, brand Search always-on, cortar leads fríos sin intent.",
            f"Instagram/Facebook declarados: {declared['instagram']['orders']+declared['facebook']['orders']} pedidos ≠ Meta Ads verificado ({m_r['orders']} WC).",
        ],
        "do": [
            "Google: certificaciones + brand search always-on (mejor CAC/ROAS WC).",
            "Meta: remarketing leads sin compra + lookalikes de compradores WC; cortar frío sin lead→pedido.",
            "No igualar presupuesto Meta=Google: la eficiencia WC no lo soporta.",
        ],
        "dont": [
            "No leer pixel purchases Meta como pedidos WC verificados.",
            "No confundir «me conocí por Instagram» con atribución paid Meta.",
        ],
    }


def export_payload() -> dict:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    def q(sql, args=()):
        return [dict(r) for r in conn.execute(sql, args)]

    periods = {}
    for p in q("SELECT * FROM dim_period WHERE period_id LIKE 'sy-%'"):
        pid = p["period_id"]
        if pid == "sy-2026-27":
            continue
        tot = q("SELECT * FROM v_orders_by_period WHERE period_id=?", (pid,))
        tot = tot[0] if tot else {"orders": 0, "revenue": 0, "aov": 0}
        channels = q(
            """SELECT channel_id AS canal, orders, revenue AS rev,
                      ROUND(aov,2) AS aov,
                      (SELECT tipo FROM dim_channel d WHERE d.channel_id=k.channel_id) AS tipo
               FROM kpi_period_channel k WHERE period_id=? ORDER BY orders DESC""",
            (pid,),
        )
        products = q(
            """SELECT family AS label, SUM(qty) AS qty, SUM(line_total) AS rev
               FROM fact_wc_order_item i
               JOIN fact_wc_order o ON o.order_id=i.order_id
               WHERE o.period_id=?
               GROUP BY family ORDER BY rev DESC""",
            (pid,),
        )
        geo_raw = q(
            """SELECT state, COUNT(*) AS orders, SUM(total) AS rev
               FROM fact_wc_order WHERE period_id=? AND state IS NOT NULL AND state!=''
               GROUP BY state ORDER BY orders DESC""",
            (pid,),
        )
        geo = []
        for g in geo_raw:
            name, lat, lng = PROVINCE.get(g["state"], (g["state"], None, None))
            if lat is None:
                continue
            geo.append({"code": g["state"], "name": name, "orders": g["orders"], "rev": g["rev"], "lat": lat, "lng": lng})

        paid = {}
        for row in q("SELECT * FROM kpi_paid_period WHERE period_id=?", (pid,)):
            paid[row["platform"]] = {
                "spend": row["spend"],
                "impressions": row["impressions"],
                "clicks": row["clicks"],
                "reach": row["reach"],
                "platform_leads": row["platform_leads"],
                "platform_purchases": row["platform_purchases"],
                "platform_lead_convs": row["platform_lead_convs"],
                "wc_orders_verified": row["wc_orders_verified"],
                "wc_revenue_verified": row["wc_revenue_verified"],
                "cac": row["cac"],
                "roas": row["roas"],
                "conv_pct": row["conv_pct"],
                "notes": row["notes"],
            }

        # Meta match funnel extras
        match_n = q(
            "SELECT COUNT(*) n, SUM(order_total) rev FROM fact_meta_wc_match WHERE period_id=?",
            (pid,),
        )[0]
        meta_utm = next((c for c in channels if c["canal"] == "Meta Ads"), {"orders": 0, "rev": 0})

        # Google Ads CTR/CPC from campaign daily
        gstats = q(
            """SELECT COALESCE(SUM(spend),0) spend, COALESCE(SUM(impressions),0) impressions,
                      COALESCE(SUM(clicks),0) clicks
               FROM fact_google_ads_campaign_daily WHERE period_id=?""",
            (pid,),
        )[0]
        if gstats["impressions"]:
            gstats["ctr"] = 100 * gstats["clicks"] / gstats["impressions"]
            gstats["cpc"] = gstats["spend"] / gstats["clicks"] if gstats["clicks"] else 0
        else:
            gstats["ctr"] = 0
            gstats["cpc"] = 0

        mstats = q(
            """SELECT COALESCE(SUM(spend),0) spend, COALESCE(SUM(impressions),0) impressions,
                      COALESCE(SUM(clicks),0) clicks, COALESCE(SUM(reach),0) reach,
                      COALESCE(SUM(leads),0) leads, COALESCE(SUM(purchases),0) purchases
               FROM fact_meta_daily WHERE period_id=?""",
            (pid,),
        )[0]
        if mstats["impressions"]:
            mstats["ctr"] = 100 * mstats["clicks"] / mstats["impressions"]
            mstats["cpc"] = mstats["spend"] / mstats["clicks"] if mstats["clicks"] else 0
        else:
            mstats["ctr"] = 0
            mstats["cpc"] = 0

        ga4 = q("SELECT * FROM fact_ga4_period_totals WHERE period_id=?", (pid,))
        gsc = q("SELECT * FROM fact_gsc_period WHERE period_id=?", (pid,))
        ga4_ch = q(
            "SELECT channel_group, sessions, purchases, revenue FROM fact_ga4_channel_period WHERE period_id=? ORDER BY sessions DESC",
            (pid,),
        )

        gads_split = q(
            """SELECT conv_class, ROUND(SUM(conversions),2) conversions, ROUND(SUM(conv_value),2) value
               FROM fact_google_ads_conversion_daily WHERE period_id=?
               GROUP BY conv_class""",
            (pid,),
        )

        periods[pid] = {
            "label": p["label"],
            "start": p["start_date"],
            "end": p["end_date"],
            "orders": tot["orders"],
            "rev": tot["revenue"],
            "aov": tot["aov"],
            "channels": channels,
            "products": products,
            "geo": geo[:15],
            "paid": paid,
            "meta_utm_checkout_orders": meta_utm.get("orders", 0),
            "meta_match_orders": match_n["n"],
            "meta_match_rev": match_n["rev"] or 0,
            "meta_platform": mstats,
            "google_platform": gstats,
            "google_conv_split": {r["conv_class"]: r for r in gads_split},
            "ga4": ga4[0] if ga4 else {},
            "ga4_channels": ga4_ch,
            "gsc": gsc[0] if gsc else {},
        }

    metrics = q("SELECT metric_id, label, layer, trust, definition, use_for, do_not_confuse_with FROM dim_metric")
    sources = q("SELECT * FROM dim_source")

    # Demo from existing bundle (not yet in SQLite facts)
    bundle = json.loads((DATA / "proposal-bundle-v2.json").read_text())
    yoy = json.loads((DATA / "proposal-yoy-plan.json").read_text())
    wc_buyer = _load_wc_buyer()
    _enrich_buyer_profile(yoy, wc_buyer, periods)
    _attach_media_mix(yoy, periods, conn)

    wc_monthly = q(
        """SELECT substr(order_date,1,7) AS month, COUNT(*) AS orders, SUM(total) AS rev
           FROM fact_wc_order
           WHERE order_date >= '2024-09-01' AND order_date < '2026-09-01'
           GROUP BY 1 ORDER BY 1"""
    )

    # Product family monthly from WC DB (todas las familias)
    prod_monthly = {}
    for r in q(
        """SELECT i.family AS grp, substr(o.order_date,1,7) AS month,
                  SUM(i.qty) AS qty, SUM(i.line_total) AS rev
           FROM fact_wc_order_item i
           JOIN fact_wc_order o ON o.order_id=i.order_id
           WHERE o.order_date >= '2024-09-01' AND o.order_date < '2026-09-01'
             AND i.family IS NOT NULL AND i.family != ''
           GROUP BY 1, 2 ORDER BY 1, 2"""
    ):
        g = r["grp"] or "Otros"
        cell = prod_monthly.setdefault(g, {})
        cell[r["month"]] = {"qty": float(r["qty"] or 0), "rev": float(r["rev"] or 0)}

    payload = {
        "builtAt": datetime.now().isoformat(timespec="seconds"),
        "sourceDb": "dashboard/db/bps.db",
        "SY": {
            "prev": {"id": "sy-2024-25", "label": "2024–25", "start": "2024-09-01", "end": "2025-08-31"},
            "cur": {"id": "sy-2025-26", "label": "2025–26", "start": "2025-09-01", "end": "2026-08-27"},
            "next": {"id": "sy-2026-27", "label": "2026–27", "start": "2026-09-01", "end": "2027-08-31"},
        },
        "periods": periods,
        "metrics": metrics,
        "sources": sources,
        "wc_monthly": wc_monthly,
        "product_monthly": prod_monthly,
        "demo": {
            "meta_demo_monthly": bundle.get("meta_demo_monthly") or [],
            "google_age_monthly": bundle.get("google_age_monthly") or [],
            "google_gender_monthly": bundle.get("google_gender_monthly") or [],
            "wc_buyer": wc_buyer,
        },
        "YOY_PLAN": yoy,
        "meta_platform_monthly": bundle.get("meta_platform_monthly") or [],
    }
    conn.close()
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False))
    print(f"Wrote {OUT_JSON} ({OUT_JSON.stat().st_size // 1024} KB)")
    return payload


JS_RUNTIME = r"""
const PAYLOAD = __PAYLOAD__;
const SY = PAYLOAD.SY;
const PREV = SY.prev.id, CUR = SY.cur.id;
const YOY_PLAN = PAYLOAD.YOY_PLAN;
const DEMO = PAYLOAD.demo;

const EUR = (n,d=0) => (n==null||isNaN(n))?'—':Number(n).toLocaleString('es-ES',{style:'currency',currency:'EUR',maximumFractionDigits:d});
const NUM = n => (n==null||isNaN(n))?'—':Math.round(Number(n)).toLocaleString('es-ES');
const PCT = n => (n==null||isNaN(n))?'—':Number(n).toFixed(1)+'%';
const COLORS = ['#0080E0','#5B54C9','#1FA97A','#F0C000','#E25B4C','#0B1F3A','#7EB8E8','#9B8FE8'];
let map, markersLayer, charts = {}, planState = null, planControlsReady = false;

function deltaHtml(cur, prev) {
  if (prev == null || prev === 0) return cur ? '<span class="delta-up">nuevo</span>' : '<span class="delta-flat">—</span>';
  const pct = 100*(cur-prev)/prev;
  const cls = Math.abs(pct)<0.5?'delta-flat':(pct>0?'delta-up':'delta-down');
  return `<span class="${cls}">${pct>0?'+':''}${pct.toFixed(1)}%</span>`;
}
function tableHtml(cols, rows) {
  if (!rows.length) return '<p style="color:var(--muted)">Sin datos.</p>';
  return `<div class="table-scroll"><table class="data"><thead><tr>${cols.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>{
    const cells = Array.isArray(r) ? r : (r.cells || []);
    const cls = (!Array.isArray(r) && r.className) ? ` class="${r.className}"` : '';
    return `<tr${cls}>${cells.map(c=>`<td>${c}</td>`).join('')}</tr>`;
  }).join('')}</tbody></table></div>`;
}
function P(id) { return PAYLOAD.periods[id] || {}; }
function inSyMonth(m, syId) {
  const sy = PAYLOAD.SY.prev.id===syId?PAYLOAD.SY.prev:PAYLOAD.SY.cur;
  return sy.start.slice(0,7) <= m && m <= sy.end.slice(0,7);
}

function renderDiagnostico() {
  const p = P(PREV), c = P(CUR);
  const metaP = p.paid?.meta||{}, metaC = c.paid?.meta||{};
  const gP = p.paid?.google_ads||{}, gC = c.paid?.google_ads||{};

  document.getElementById('diagKpis').innerHTML = `
    <div class="period-grid">
      <div class="period-col prev">
        <h3>Curso 2024–25</h3>
        <div class="stat-row">
          <div class="stat"><strong>${NUM(p.orders)}</strong><span>Pedidos WC</span></div>
          <div class="stat"><strong>${EUR(p.rev,0)}</strong><span>Ingresos WC</span></div>
          <div class="stat"><strong>${EUR(p.aov,0)}</strong><span>AOV</span></div>
          <div class="stat"><strong>${EUR((metaP.spend||0)+(gP.spend||0),0)}</strong><span>Inversión paid</span></div>
        </div>
      </div>
      <div class="period-col cur">
        <h3>Curso 2025–26</h3>
        <div class="stat-row">
          <div class="stat"><strong>${NUM(c.orders)}</strong><span>Pedidos WC ${deltaHtml(c.orders,p.orders)}</span></div>
          <div class="stat"><strong>${EUR(c.rev,0)}</strong><span>Ingresos WC ${deltaHtml(c.rev,p.rev)}</span></div>
          <div class="stat"><strong>${EUR(c.aov,0)}</strong><span>AOV</span></div>
          <div class="stat"><strong>${EUR((metaC.spend||0)+(gC.spend||0),0)}</strong><span>Inversión paid ${deltaHtml((metaC.spend||0)+(gC.spend||0),(metaP.spend||0)+(gP.spend||0))}</span></div>
        </div>
      </div>
    </div>
    <div class="stat-row" style="margin-top:12px">
      <div class="stat"><strong>${NUM(c.gsc?.clicks)}</strong><span>GSC clics 25–26</span><div class="delta">24–25: ${NUM(p.gsc?.clicks)} ${deltaHtml(c.gsc?.clicks,p.gsc?.clicks)}</div></div>
      <div class="stat"><strong>${NUM(c.ga4?.purchases)}</strong><span>GA4 purchases 25–26</span><div class="delta">WC pedidos: ${NUM(c.orders)}</div></div>
      <div class="stat"><strong>${NUM(metaC.wc_orders_verified)}</strong><span>Meta→WC</span><div class="delta">CAC ${EUR(metaC.cac,0)} · ROAS ${metaC.roas?Number(metaC.roas).toFixed(2)+'×':'—'}</div></div>
      <div class="stat"><strong>${NUM(gC.wc_orders_verified)}</strong><span>Google Ads → WC</span><div class="delta">Ads compra ${NUM(gC.platform_purchases)} · leads ${NUM(gC.platform_lead_convs)}</div></div>
    </div>
    <div class="chart-card" style="margin-top:16px"><h4>Pedidos WC por mes · 24–25 vs 25–26</h4><div class="chart-wrap" style="height:260px"><canvas id="chartWcMonthly"></canvas></div></div>`;
  renderWcMonthlyChart();

  const organic = (ch)=> !['Meta Ads','Google Ads'].includes(ch.canal);
  const orgP = (p.channels||[]).filter(organic), orgC = (c.channels||[]).filter(organic);
  const names = [...new Set([...orgP.map(x=>x.canal),...orgC.map(x=>x.canal)])];
  const orgRows = names.map(name=>{
    const a=orgP.find(x=>x.canal===name)||{orders:0,rev:0};
    const b=orgC.find(x=>x.canal===name)||{orders:0,rev:0};
    return [name, NUM(a.orders), NUM(b.orders), deltaHtml(b.orders,a.orders), EUR(a.rev,0), EUR(b.rev,0), deltaHtml(b.rev,a.rev)];
  }).sort((a,b)=>parseFloat(String(b[5]).replace(/[^\\d,-]/g,''))-parseFloat(String(a[5]).replace(/[^\\d,-]/g,'')));

  const paidRows = [
    ['Meta Ads <span class="tag tag-verified">leads→WC</span>',
      NUM(metaP.wc_orders_verified), NUM(metaC.wc_orders_verified), deltaHtml(metaC.wc_orders_verified,metaP.wc_orders_verified),
      EUR(metaP.wc_revenue_verified,0), EUR(metaC.wc_revenue_verified,0),
      PCT(metaP.conv_pct), PCT(metaC.conv_pct),
      EUR(metaP.cac,0), EUR(metaC.cac,0),
      metaP.roas?Number(metaP.roas).toFixed(2)+'×':'—', metaC.roas?Number(metaC.roas).toFixed(2)+'×':'—'],
    ['Google Ads <span class="tag tag-verified">UTM cpc WC</span>',
      NUM(gP.wc_orders_verified), NUM(gC.wc_orders_verified), deltaHtml(gC.wc_orders_verified,gP.wc_orders_verified),
      EUR(gP.wc_revenue_verified,0), EUR(gC.wc_revenue_verified,0),
      '—', gC.platform_lead_convs?PCT(100*(gC.wc_orders_verified||0)/gC.platform_lead_convs):'—',
      gP.wc_orders_verified?EUR(gP.spend/gP.wc_orders_verified,0):'—', EUR(gC.cac,0),
      gP.roas?Number(gP.roas).toFixed(2)+'×':'—', gC.roas?Number(gC.roas).toFixed(2)+'×':'—'],
  ];

  document.getElementById('panelDiagCanales').innerHTML = `
    <h3 style="font-size:1rem;margin:8px 0">Orgánico y declarado</h3>
    ${tableHtml(['Canal','Ped. 24–25','Ped. 25–26','Δ','Ing. 24–25','Ing. 25–26','Δ ing.'], orgRows)}
    <h3 style="font-size:1rem;margin:22px 0 8px">Paid verificado</h3>
    ${tableHtml(['Canal','Ped. 24–25','Ped. 25–26','Δ','Ing. 24–25','Ing. 25–26','Conv% 24–25','Conv% 25–26','CAC 24–25','CAC 25–26','ROAS 24–25','ROAS 25–26'], paidRows)}`;

  const mp = p.meta_platform||{}, mc = c.meta_platform||{};
  const gp = p.google_platform||{}, gc = c.google_platform||{};
  const splitP = p.google_conv_split||{};
  const splitC = c.google_conv_split||{};
  const platRows = [
    ['Impresiones', NUM(mp.impressions), NUM(mc.impressions), NUM(gp.impressions), NUM(gc.impressions)],
    ['Alcance', NUM(mp.reach), NUM(mc.reach), '—', '—'],
    ['Clics', NUM(mp.clicks), NUM(mc.clicks), NUM(gp.clicks), NUM(gc.clicks)],
    ['CTR', (mp.ctr||0).toFixed(2)+'%', (mc.ctr||0).toFixed(2)+'%', (gp.ctr||0).toFixed(2)+'%', (gc.ctr||0).toFixed(2)+'%'],
    ['CPC', EUR(mp.cpc,2), EUR(mc.cpc,2), EUR(gp.cpc,2), EUR(gc.cpc,2)],
    ['Inversión', EUR(mp.spend,0), EUR(mc.spend,0), EUR(gp.spend,0), EUR(gc.spend,0)],
    ['Leads plataforma', NUM(mp.leads), NUM(mc.leads), NUM(splitP.lead?.conversions||gP.platform_lead_convs), NUM(splitC.lead?.conversions||gC.platform_lead_convs)],
    ['Compras plataforma', NUM(mp.purchases), NUM(mc.purchases), NUM(splitP.purchase?.conversions||gP.platform_purchases), NUM(splitC.purchase?.conversions||gC.platform_purchases)],
    ['Valor compras Ads', '—', '—', EUR(splitP.purchase?.value||0,0), EUR(splitC.purchase?.value||0,0)],
    ['Pedidos finales WC ✓', NUM(metaP.wc_orders_verified), NUM(metaC.wc_orders_verified), NUM(gP.wc_orders_verified), NUM(gC.wc_orders_verified)],
    ['CAC pedido WC', EUR(metaP.cac,0), EUR(metaC.cac,0), gP.cac?EUR(gP.cac,0):'—', EUR(gC.cac,0)],
    ['ROAS pedido WC', metaP.roas?Number(metaP.roas).toFixed(2)+'×':'—', metaC.roas?Number(metaC.roas).toFixed(2)+'×':'—', gP.roas?Number(gP.roas).toFixed(2)+'×':'—', gC.roas?Number(gC.roas).toFixed(2)+'×':'—'],
  ];

  const platMonthly = PAYLOAD.meta_platform_monthly||[];
  const sumPlat = (syId) => {
    const m={};
    for (const r of platMonthly) {
      if (!inSyMonth(r.month, syId)) continue;
      const p=(r.dim_1||'?').toLowerCase();
      if (!m[p]) m[p]={spend:0,leads:0};
      m[p].spend+=r.spend||0; m[p].leads+=r.leads||0;
    }
    return m;
  };
  const pp=sumPlat(PREV), pc=sumPlat(CUR);
  const platNames=[...new Set([...Object.keys(pp),...Object.keys(pc)])].filter(n=>!['unknown','messenger','threads'].includes(n)&&(pp[n]?.spend||pc[n]?.spend));

  document.getElementById('panelDiagPlat').innerHTML = `
    ${tableHtml(['KPI','Meta 24–25','Meta 25–26','Google Ads 24–25','Google Ads 25–26'], platRows)}`;

  document.getElementById('panelDiagProducto').innerHTML =
    `<div class="chart-card">
      <h4>Pedidos WC y facturación por familia · 24–25 vs 25–26</h4>
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0 6px">
        <button type="button" id="productChartAll" style="font:inherit;font-size:.78rem;padding:4px 10px;border:1px solid var(--line);border-radius:8px;background:#fff;cursor:pointer">Todos</button>
        <button type="button" id="productChartTop" style="font:inherit;font-size:.78rem;padding:4px 10px;border:1px solid var(--line);border-radius:8px;background:#fff;cursor:pointer">Top 4</button>
        <button type="button" id="productChartNone" style="font:inherit;font-size:.78rem;padding:4px 10px;border:1px solid var(--line);border-radius:8px;background:#fff;cursor:pointer">Ninguno</button>
      </div>
      <div id="productChartToggles" style="display:flex;flex-wrap:wrap;gap:6px 12px;margin:0 0 10px"></div>
      <div class="chart-wrap" style="height:300px"><canvas id="chartProductYoy"></canvas></div>
      <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:16px 0 6px">
        <p style="font-size:.82rem;color:var(--muted);margin:0">Estacionalidad mensual (pedidos)</p>
        <select id="productMonthFocus" style="font:inherit;font-size:.85rem;padding:4px 8px;border:1px solid var(--line);border-radius:8px"></select>
      </div>
      <div class="chart-wrap" style="height:260px"><canvas id="chartProductMonthly"></canvas></div>
     </div>
    ${tableHtml(['Familia','Ud. 24–25','Ing. 24–25','Ud. 25–26','Ing. 25–26','Δ ing.'],
      [...new Set([...(p.products||[]).map(x=>x.label),...(c.products||[]).map(x=>x.label)])].map(label=>{
        const a=(p.products||[]).find(x=>x.label===label)||{qty:0,rev:0};
        const b=(c.products||[]).find(x=>x.label===label)||{qty:0,rev:0};
        return [label, NUM(a.qty), EUR(a.rev,0), NUM(b.qty), EUR(b.rev,0), deltaHtml(b.rev,a.rev)];
      }).sort((a,b)=>parseFloat(String(b[4]).replace(/[^\\d,-]/g,''))-parseFloat(String(a[4]).replace(/[^\\d,-]/g,''))))}
     <h3 style="font-size:1rem;margin:22px 0 8px">Demanda keywords por curso · 24–25 vs 25–26</h3>
     <p style="font-size:.85rem;color:var(--muted);margin:0 0 8px">YoY comercial e informacional ponderado por volumen de keywords (Keyword Planner).</p>
     <div class="chart-card" style="margin-bottom:14px">
       <h4>Búsquedas / mes · comercial e info</h4>
       <div id="kwChartToggles" style="display:flex;flex-wrap:wrap;gap:6px 12px;margin:8px 0 10px"></div>
       <div class="chart-wrap" style="height:300px"><canvas id="chartKwYoy"></canvas></div>
     </div>
     ${tableHtml(['Curso','Com. 24–25','Com. 25–26','Δ Com.','Info 24–25','Info 25–26','Δ Info','CPC'],
       YOY_PLAN.plan.products.map(pr=>{
         const fmtYoy = (y) => y==null ? '—' : ((y>0?'+':'') + Number(y).toFixed(1) + '%');
         return [
           pr.label,
           NUM(pr.searches_com_prev||0),
           NUM(pr.searches_com_cur||0),
           fmtYoy(pr.kw_yoy_com_pct),
           NUM(pr.searches_info_prev||0),
           NUM(pr.searches_info_cur||0),
           fmtYoy(pr.kw_yoy_info_pct),
           EUR(pr.cpc,2)
         ];
       }))}`;
  if (!window._productChartSel) {
    const pm = PAYLOAD.product_monthly || {};
    const fams = Object.keys(pm).sort((a,b)=>{
      const sa=Object.values(pm[a]||{}).reduce((s,x)=>s+(x.qty||0),0);
      const sb=Object.values(pm[b]||{}).reduce((s,x)=>s+(x.qty||0),0);
      return sb-sa;
    });
    window._productChartSel = new Set(fams.slice(0,4));
    window._productMonthFocus = fams[0] || null;
  }
  if (!window._kwChartSel) {
    window._kwChartSel = new Set(
      YOY_PLAN.plan.products
        .filter(p => p.enabled !== false && !p.brand && p.id !== 'bps home')
        .slice(0, 6)
        .map(p => p.id)
    );
  }
  renderProductChartToggles();
  renderProductYoyChart();
  renderProductMonthlyChart();
  renderKwChartToggles();
  renderKwYoyChart();

  renderDiagGeo();
  renderDiagDemo();
}

function renderKwChartToggles() {
  const el = document.getElementById('kwChartToggles');
  if (!el) return;
  const prods = YOY_PLAN.plan.products || [];
  el.innerHTML = prods.map(p => {
    const on = window._kwChartSel.has(p.id);
    return `<label class="plan-toggle" style="margin:0"><input type="checkbox" data-kwid="${p.id}" ${on?'checked':''}/> ${p.label}</label>`;
  }).join('');
  el.querySelectorAll('[data-kwid]').forEach(inp=>{
    inp.addEventListener('change', ()=>{
      if (inp.checked) window._kwChartSel.add(inp.dataset.kwid);
      else window._kwChartSel.delete(inp.dataset.kwid);
      renderKwYoyChart();
    });
  });
}

function renderKwYoyChart() {
  const ctx = document.getElementById('chartKwYoy'); if (!ctx) return;
  if (charts.chartKwYoy) charts.chartKwYoy.destroy();
  const sel = window._kwChartSel || new Set();
  const rows = (YOY_PLAN.plan.products||[]).filter(p=>sel.has(p.id));
  const labels = rows.map(p=>p.label);
  charts.chartKwYoy = new Chart(ctx,{
    type:'bar',
    data:{labels, datasets:[
      {label:'Comercial 24–25', data:rows.map(p=>p.searches_com_prev||0), backgroundColor:'#9B8FE8'},
      {label:'Comercial 25–26', data:rows.map(p=>p.searches_com_cur||0), backgroundColor:'#5B54C9'},
      {label:'Info 24–25', data:rows.map(p=>p.searches_info_prev||0), backgroundColor:'#7EB8E8'},
      {label:'Info 25–26', data:rows.map(p=>p.searches_info_cur||0), backgroundColor:'#0080E0'},
    ]},
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{legend:{position:'bottom',labels:{boxWidth:10,font:{size:11}}}},
      scales:{y:{beginAtZero:true, ticks:{precision:0}, title:{display:true,text:'Búsquedas / mes'}}}
    }
  });
}

function productFamilyRank() {
  const pm = PAYLOAD.product_monthly || {};
  return Object.keys(pm).sort((a,b)=>{
    const sa=Object.values(pm[a]||{}).reduce((s,x)=>s+(x.qty||0),0);
    const sb=Object.values(pm[b]||{}).reduce((s,x)=>s+(x.qty||0),0);
    return sb-sa;
  });
}
function productYearTotals(f) {
  const pm = (PAYLOAD.product_monthly || {})[f] || {};
  let prev=0, cur=0, prevRev=0, curRev=0;
  for (const [m, cell] of Object.entries(pm)) {
    const qty = cell.qty || 0;
    const rev = cell.rev || 0;
    if (m >= '2024-09' && m < '2025-09') { prev += qty; prevRev += rev; }
    else if (m >= '2025-09' && m < '2026-09') { cur += qty; curRev += rev; }
  }
  return {prev, cur, prevRev, curRev};
}
function renderProductChartToggles() {
  const el = document.getElementById('productChartToggles');
  if (!el) return;
  const fams = productFamilyRank();
  el.innerHTML = fams.map(f => {
    const on = window._productChartSel.has(f);
    const t = productYearTotals(f);
    const d = t.prev ? ((t.cur - t.prev) / t.prev * 100) : null;
    const dTxt = d==null ? '' : ` <span style="color:var(--muted);font-size:.75rem">(${d>0?'+':''}${d.toFixed(0)}%)</span>`;
    return `<label class="plan-toggle" style="margin:0"><input type="checkbox" data-pfam="${f}" ${on?'checked':''}/> ${f}${dTxt}</label>`;
  }).join('');
  el.querySelectorAll('[data-pfam]').forEach(inp=>{
    inp.addEventListener('change', ()=>{
      if (inp.checked) window._productChartSel.add(inp.dataset.pfam);
      else window._productChartSel.delete(inp.dataset.pfam);
      if (inp.checked) window._productMonthFocus = inp.dataset.pfam;
      renderProductFocusSelect();
      renderProductYoyChart();
      renderProductMonthlyChart();
    });
  });
  const bind = (id, fn) => {
    const btn = document.getElementById(id);
    if (!btn || btn._bound) return;
    btn._bound = true;
    btn.addEventListener('click', fn);
  };
  bind('productChartAll', ()=>{
    window._productChartSel = new Set(Object.keys(PAYLOAD.product_monthly||{}));
    renderProductChartToggles();
    renderProductFocusSelect();
    renderProductYoyChart();
    renderProductMonthlyChart();
  });
  bind('productChartTop', ()=>{
    window._productChartSel = new Set(productFamilyRank().slice(0,4));
    window._productMonthFocus = productFamilyRank()[0] || null;
    renderProductChartToggles();
    renderProductFocusSelect();
    renderProductYoyChart();
    renderProductMonthlyChart();
  });
  bind('productChartNone', ()=>{
    window._productChartSel = new Set();
    renderProductChartToggles();
    renderProductFocusSelect();
    renderProductYoyChart();
    renderProductMonthlyChart();
  });
  renderProductFocusSelect();
}
function renderProductFocusSelect() {
  const sel = document.getElementById('productMonthFocus');
  if (!sel) return;
  const fams = productFamilyRank().filter(f => window._productChartSel.has(f));
  const all = fams.length ? fams : productFamilyRank();
  if (!window._productMonthFocus || !all.includes(window._productMonthFocus)) {
    window._productMonthFocus = all[0] || null;
  }
  sel.innerHTML = all.map(f => `<option value="${f}" ${f===window._productMonthFocus?'selected':''}>${f}</option>`).join('');
  if (!sel._bound) {
    sel._bound = true;
    sel.addEventListener('change', ()=>{
      window._productMonthFocus = sel.value;
      renderProductMonthlyChart();
    });
  }
}
function renderProductYoyChart() {
  const ctx = document.getElementById('chartProductYoy'); if (!ctx) return;
  if (charts.chartProductYoy) charts.chartProductYoy.destroy();
  const families = productFamilyRank().filter(f => window._productChartSel.has(f));
  const totals = families.map(productYearTotals);
  charts.chartProductYoy = new Chart(ctx,{
    type:'bar',
    data:{
      labels: families,
      datasets:[
        {label:'Pedidos WC 24–25', data:totals.map(t=>Math.round(t.prev)), backgroundColor:'#9B8FE8', borderRadius:4, yAxisID:'y'},
        {label:'Pedidos WC 25–26', data:totals.map(t=>Math.round(t.cur)), backgroundColor:'#0080E0', borderRadius:4, yAxisID:'y'},
        {label:'Facturación 24–25', data:totals.map(t=>Math.round(t.prevRev||0)), backgroundColor:'rgba(155,143,232,.35)', borderColor:'#5B54C9', borderWidth:1, borderRadius:4, yAxisID:'y1'},
        {label:'Facturación 25–26', data:totals.map(t=>Math.round(t.curRev||0)), backgroundColor:'rgba(0,128,224,.35)', borderColor:'#0B1F3A', borderWidth:1, borderRadius:4, yAxisID:'y1'},
      ]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{position:'bottom',labels:{boxWidth:12,font:{size:11}}},
        tooltip:{callbacks:{
          label:(c)=>{
            const v=c.raw||0;
            if ((c.dataset.label||'').startsWith('Facturación')) return ` ${c.dataset.label}: ${EUR(v,0)}`;
            return ` ${c.dataset.label}: ${NUM(v)}`;
          },
          afterBody:(items)=>{
            if (!items.length) return '';
            const i=items[0].dataIndex;
            const t=totals[i];
            const lines=[];
            if (t.prev) lines.push(`Δ pedidos ${(((t.cur-t.prev)/t.prev)*100)>0?'+':''}${(((t.cur-t.prev)/t.prev)*100).toFixed(1)}%`);
            if (t.prevRev) lines.push(`Δ facturación ${(((t.curRev-t.prevRev)/t.prevRev)*100)>0?'+':''}${(((t.curRev-t.prevRev)/t.prevRev)*100).toFixed(1)}%`);
            return lines;
          }
        }}
      },
      scales:{
        x:{grid:{display:false}},
        y:{position:'left', beginAtZero:true, ticks:{precision:0}, title:{display:true,text:'Pedidos WC'}},
        y1:{position:'right', beginAtZero:true, grid:{drawOnChartArea:false}, ticks:{callback:(v)=>EUR(v,0)}, title:{display:true,text:'Facturación €'}}
      }
    }
  });
}
function renderProductMonthlyChart() {
  const pm = PAYLOAD.product_monthly || {};
  const months = ['09','10','11','12','01','02','03','04','05','06','07','08'];
  const labels = ['Sep','Oct','Nov','Dic','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago'];
  const f = window._productMonthFocus;
  const ctx = document.getElementById('chartProductMonthly'); if (!ctx) return;
  if (charts.chartProductMonthly) charts.chartProductMonthly.destroy();
  if (!f || !pm[f]) {
    charts.chartProductMonthly = new Chart(ctx,{type:'bar',data:{labels,datasets:[]},options:{responsive:true,maintainAspectRatio:false}});
    return;
  }
  const seriesFor = (yearStart) => months.map(mm => {
    const y = mm >= '09' ? yearStart : yearStart + 1;
    return (pm[f][`${y}-${mm}`]||{}).qty||0;
  });
  const prev = seriesFor(2024);
  const cur = seriesFor(2025);
  const t = productYearTotals(f);
  const d = t.prev ? ((t.cur-t.prev)/t.prev*100) : null;
  charts.chartProductMonthly = new Chart(ctx,{
    type:'bar',
    data:{
      labels,
      datasets:[
        {label:f+' 24–25', data:prev, backgroundColor:'rgba(155,143,232,.85)', borderRadius:3},
        {label:f+' 25–26', data:cur, backgroundColor:'rgba(0,128,224,.9)', borderRadius:3},
      ]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{position:'bottom',labels:{boxWidth:10,font:{size:11}}},
        title:{
          display:true,
          text: d==null ? f : `${f} · curso ${d>0?'+':''}${d.toFixed(0)}% YoY`,
          font:{size:13, weight:'600'},
          color:'#0B1F3A',
          padding:{bottom:8}
        },
        tooltip:{callbacks:{
          afterBody:(items)=>{
            if (items.length<2) return '';
            const a=items[0].raw||0, b=items[1].raw||0;
            if (!a) return '';
            const dd=((b-a)/a*100);
            return `Δ mes ${(dd>0?'+':'')+dd.toFixed(0)}%`;
          }
        }}
      },
      scales:{
        x:{grid:{display:false}},
        y:{beginAtZero:true, ticks:{precision:0}, title:{display:true,text:'Pedidos / mes'}}
      }
    }
  });
}

function renderDiagGeo() {
  const c = P(CUR), p = P(PREV);
  const prevMap = Object.fromEntries((p.geo||[]).map(r=>[r.name,r]));
  document.getElementById('panelDiagGeo').innerHTML = tableHtml(
    ['Provincia','Ped. 25–26','Ped. 24–25','Δ ped.','Ing. 25–26','Ing. 24–25','Δ ing.'],
    (c.geo||[]).map(r=>{const pr=prevMap[r.name]||{orders:0,rev:0}; return [r.name,NUM(r.orders),NUM(pr.orders),deltaHtml(r.orders,pr.orders),EUR(r.rev,0),EUR(pr.rev,0),deltaHtml(r.rev,pr.rev)];}));
  if (!window.L) return;
  const el = document.getElementById('geoMap');
  if (!map) {
    map = L.map(el,{scrollWheelZoom:false}).setView([40,-3.5],5.5);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{attribution:'© OSM'}).addTo(map);
    markersLayer = L.layerGroup().addTo(map);
  }
  markersLayer.clearLayers();
  const provs = c.geo||[];
  const maxO = Math.max(...provs.map(x=>x.orders),1);
  provs.forEach(pr=>{
    const m = L.circleMarker([pr.lat,pr.lng],{radius:8+Math.sqrt(pr.orders/maxO)*24,color:'#0B1F3A',weight:1.5,fillColor:'#0080E0',fillOpacity:.75});
    m.bindTooltip(`<strong>${pr.name}</strong><br>${NUM(pr.orders)} ped.<br>${EUR(pr.rev,0)}`,{className:'geo-tip',sticky:true});
    markersLayer.addLayer(m);
  });
  if (provs.length) map.fitBounds(L.featureGroup(markersLayer.getLayers()).getBounds().pad(0.35));
  setTimeout(()=>map.invalidateSize(),100);
}

function pieOrUpdate(id, labels, values, unit='eur') {
  const ctx = document.getElementById(id); if (!ctx) return;
  if (charts[id]) charts[id].destroy();
  const total = values.reduce((a,b)=>a+b,0)||1;
  const fmt = (v) => unit==='num' ? NUM(v) : EUR(v,0);
  charts[id] = new Chart(ctx,{type:'doughnut',data:{labels,datasets:[{data:values,backgroundColor:COLORS.slice(0,labels.length),borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{boxWidth:10,font:{size:11}}},tooltip:{callbacks:{label:c=>` ${c.label}: ${fmt(c.raw)} (${(100*c.raw/total).toFixed(0)}%)`}}},cutout:'55%'}});
}

function barCompareOrUpdate(id, labels, prevVals, curVals, labelPrev='2024–25', labelCur='2025–26') {
  const ctx = document.getElementById(id); if (!ctx) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(ctx,{type:'bar',data:{labels,datasets:[
    {label:labelPrev,data:prevVals,backgroundColor:'#9B8FE8'},
    {label:labelCur,data:curVals,backgroundColor:'#0080E0'},
  ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{boxWidth:10,font:{size:11}}}},scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
}

function renderWcMonthlyChart() {
  const months = ['09','10','11','12','01','02','03','04','05','06','07','08'];
  const labels = ['Sep','Oct','Nov','Dic','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago'];
  const by = {};
  for (const r of (PAYLOAD.wc_monthly||[])) by[r.month]=r;
  const prev = months.map((mm)=> (by[`${mm >= '09' ? '2024' : '2025'}-${mm}`]||{}).orders||0);
  const cur = months.map((mm)=> (by[`${mm >= '09' ? '2025' : '2026'}-${mm}`]||{}).orders||0);
  barCompareOrUpdate('chartWcMonthly', labels, prev, cur);
}

function topShare(entries, n=2) {
  const total = entries.reduce((s,x)=>s+x[1],0)||1;
  return entries.slice(0,n).map(([k,v])=>({label:k, pct: Math.round(100*v/total)}));
}
function prettyAge(label) {
  const s = String(label||'').replace(/^AGE_RANGE_/,'').replace(/_/g,'-').replace('65-UP','65+').toLowerCase();
  if (/undetermined|unknown|not.?specified/.test(s)) return 'sin clasificar';
  return s;
}
function prettyGender(label) {
  const s=String(label||'').toLowerCase();
  if (/undetermined|unknown|not.?specified/.test(s)) return 'sin clasificar';
  if (s.includes('female')||s==='mujer') return 'mujer';
  if (s.includes('male')||s==='hombre') return 'hombre';
  return s;
}

function renderDiagDemo() {
  const bp = YOY_PLAN.buyerProfile;
  const wb = DEMO.wc_buyer || {};
  const ageC = (wb.cur||{}).age || {};
  const gC = (wb.cur||{}).gender || {};
  const ageTop = (bp.age_primary||[]).slice(0,2);
  const ageLine = ageTop.map(a=>`${a.band} (${a.share_pct}%)`).join(' y ') || '—';
  const mujer = (bp.gender_primary||[])[0];

  const sumDemo = (rows, key, syId) => {
    const m={};
    for (const r of rows) {
      if (!inSyMonth(r.month,syId)) continue;
      const k=r[key]||'?';
      if (/unknown|undetermined|not.?specified|^\?$/i.test(k)) continue;
      m[k]=(m[k]||0)+(r.spend||0);
    }
    return Object.entries(m).sort((a,b)=>b[1]-a[1]);
  };
  const ma = sumDemo(DEMO.meta_demo_monthly||[],'dim_1',CUR);
  const mg = sumDemo(DEMO.meta_demo_monthly||[],'dim_2',CUR);
  const ga = sumDemo(DEMO.google_age_monthly||[],'age',CUR).map(([k,v])=>[prettyAge(k),v]);
  const gg = sumDemo(DEMO.google_gender_monthly||[],'gender',CUR).map(([k,v])=>[prettyGender(k),v]);
  const metaAge = topShare(ma);
  const metaGen = topShare(mg);
  const gAge = topShare(ga);
  const gGen = topShare(gg);

  document.getElementById('panelDiagPersona').innerHTML = `
    <div class="profile-grid">
      <div class="persona-box">
        <h3>Comprador WC</h3>
        <p><strong>${mujer && mujer.share_pct>=50 ? 'Mujer' : 'Perfil mixto'} ${ageTop[0]?ageTop[0].band:''}</strong> en Madrid/Málaga.</p>
        <ul>
          <li>Edad dominante: ${ageLine}</li>
          <li>${mujer ? Math.round(mujer.share_pct)+'% mujeres' : '—'} (entre clasificados)</li>
          <li>Producto #1: ${bp.top_product} · AOV ~${EUR(bp.aov||0,0)}</li>
        </ul>
      </div>
      <div class="persona-box">
        <h3>Audiencia Meta</h3>
        <p><strong>${metaGen[0]?prettyGender(metaGen[0].label):'—'} ${metaAge[0]?metaAge[0].label:''}</strong> (mix de inversión 25–26).</p>
        <ul>
          <li>Edad: ${metaAge.map(x=>x.label+' '+x.pct+'%').join(' · ')||'—'}</li>
          <li>Género: ${metaGen.map(x=>prettyGender(x.label)+' '+x.pct+'%').join(' · ')||'—'}</li>
          <li>Perfil de pauta, no de pedido WC</li>
        </ul>
      </div>
      <div class="persona-box">
        <h3>Audiencia Google</h3>
        <p><strong>${gGen[0]?gGen[0].label:'—'} ${gAge[0]?gAge[0].label:''}</strong> (mix de inversión 25–26 · excl. undetermined).</p>
        <ul>
          <li>Edad: ${gAge.map(x=>x.label+' '+x.pct+'%').join(' · ')||'—'}</li>
          <li>Género: ${gGen.map(x=>x.label+' '+x.pct+'%').join(' · ')||'—'}</li>
          <li>Perfil de pauta Search/PMax</li>
        </ul>
      </div>
    </div>`;
}

function initPlanState() {
  const d = YOY_PLAN.plan.defaults;
  const gLead = d.googleCvrLeadPct != null ? d.googleCvrLeadPct : (d.cvrLeadPct != null ? d.cvrLeadPct : 3.7);
  const gSale = d.googleLeadToSalePct != null ? d.googleLeadToSalePct : (d.leadToSalePct != null ? d.leadToSalePct : 13);
  const mLead = d.metaCvrLeadPct != null ? d.metaCvrLeadPct : 8.4;
  const mSale = d.metaLeadToSalePct != null ? d.metaLeadToSalePct : 2.0;
  const groups = YOY_PLAN.plan.campaignGroups || [];
  planState = {
    monthlyBudget: d.monthlyBudget || 1000,
    isrPct: d.isrPct || 50,
    aov: d.aov || 230,
    cvrLeadPct: gLead,
    leadToSalePct: gSale,
    cvrLeadBase: gLead,
    leadSaleBase: gSale,
    googleCvrLeadPct: gLead,
    googleLeadToSalePct: gSale,
    metaCvrLeadPct: mLead,
    metaLeadToSalePct: mSale,
    metaCvrLeadBase: mLead,
    metaLeadSaleBase: mSale,
    products: Object.fromEntries(YOY_PLAN.plan.products.map(p=>[p.id,{enabled:p.enabled!==false}])),
    campaigns: Object.fromEntries(groups.map(g=>[g.id,{enabled:g.enabled!==false}])),
    channels: Object.fromEntries((YOY_PLAN.plan.channels||[]).filter(c=>c.type!=='organic').map(c=>[c.id,{enabled:c.enabled!==false}])),
    productIs: Object.assign({}, YOY_PLAN.plan.productIs || {}),
  };
}
function asFrac(x, fallback) {
  if (x==null || isNaN(x)) return fallback;
  return x > 1 ? x/100 : x;
}
function seasonFactor(p, monthIdx=null) {
  const s = p.seasonality;
  if (!Array.isArray(s) || !s.length) return 1;
  if (monthIdx==null) return 1;
  const cal = [8,9,10,11,0,1,2,3,4,5,6,7][monthIdx];
  return s[cal] != null ? s[cal] : 1;
}
function metaSeasonFactor(monthIdx=null) {
  if (monthIdx==null) return 1;
  const s = (YOY_PLAN.plan.defaults||{}).metaSeasonality;
  if (!Array.isArray(s) || !s.length) return 1;
  const cal = [8,9,10,11,0,1,2,3,4,5,6,7][monthIdx];
  const f = s[cal];
  return (f != null && isFinite(f) && f > 0) ? f : 1;
}
function estimateGoogleProduct(p, monthIdx=null) {
  const intents = new Set((YOY_PLAN.plan.defaults||{}).intents || ['comercial','informacional','marca']);
  let searches = 0, bidW = 0, bidN = 0;
  const intentMap = p.intents || {};
  for (const [intent, block] of Object.entries(intentMap)) {
    if (!intents.has(intent)) continue;
    const s = block.searches_month || 0;
    searches += s;
    if (block.cpc_mid && s) { bidW += block.cpc_mid * s; bidN += s; }
  }
  if (!searches) searches = p.monthlySearches || 0;
  const season = seasonFactor(p, monthIdx);
  searches = searches * season;
  const rawCpc = bidN ? (bidW / bidN) : (p.cpc || 0.48);
  const cpcScale = ((YOY_PLAN.plan.defaults||{}).googleCpcScale != null)
    ? Number(YOY_PLAN.plan.defaults.googleCpcScale) : 1;
  const cpc = rawCpc * (isFinite(cpcScale) && cpcScale > 0 ? cpcScale : 1);
  const isBrand = !!(p.brand || p.id === 'bps home');
  const stored = (planState.productIs || {})[p.id];
  const isPct = stored != null ? stored : (isBrand ? 90 : (planState.isrPct || 50));
  const ctrPct = p.ctrPct != null ? p.ctrPct : ((YOY_PLAN.plan.defaults||{}).ctrPct || 5);
  const leadCvr = planState.googleCvrLeadPct != null
    ? planState.googleCvrLeadPct
    : (planState.cvrLeadPct != null ? planState.cvrLeadPct : ((YOY_PLAN.plan.defaults||{}).googleCvrLeadPct || 3.7));
  const l2s = planState.googleLeadToSalePct != null
    ? planState.googleLeadToSalePct
    : (planState.leadToSalePct != null ? planState.leadToSalePct : ((YOY_PLAN.plan.defaults||{}).googleLeadToSalePct || 13));
  const aov = planState.aov || ((YOY_PLAN.plan.defaults||{}).aov) || 230;
  const impressions = searches * (isPct / 100);
  const clicks = impressions * (ctrPct / 100);
  const spend = clicks * cpc;
  const leads = clicks * (leadCvr / 100);
  const orders = leads * (l2s / 100);
  const rev = orders * aov;
  return {searches, impressions, clicks, spend, leads, orders, rev, cpc, ctr: ctrPct/100, is: isPct, leadCvr, season};
}
function calcPlan(monthIdx=null) {
  if (!planState) initPlanState();
  const {monthlyBudget,isrPct,aov,products,channels} = planState;
  const empty = {rows:[],totImp:0,totClk:0,totCost:0,totLeads:0,totOrders:0,totRev:0,isrPct,active:[],unlocked:0,monthIdx,googleNeeded:0,scale:1,overBudget:false,productRows:[],campaignRows:[],googleOnly:{},metaOnly:{}};
  if (!isFinite(monthlyBudget) || monthlyBudget <= 0) return empty;

  const byId = Object.fromEntries((YOY_PLAN.plan.channels||[]).map(c=>[c.id,c]));
  const googleOn = channels.google?.enabled !== false;
  const metaOn = channels.meta?.enabled !== false;

  const metaPaid = (P(CUR).paid||{}).meta || {};
  const dflt = YOY_PLAN.plan.defaults || {};
  const metaCpc = planState.metaCpc != null ? planState.metaCpc
    : ((metaPaid.clicks>0) ? (metaPaid.spend/metaPaid.clicks) : (dflt.metaCpc || 0.48));
  const metaCtr = planState.metaCtrPct != null ? (planState.metaCtrPct/100)
    : ((metaPaid.impressions>0) ? (metaPaid.clicks/metaPaid.impressions) : ((dflt.metaCtrPct||1.2)/100));
  // Ratios PROPIOS de Meta (no los de Google)
  const metaLeadRate = (planState.metaCvrLeadPct != null ? planState.metaCvrLeadPct : (dflt.metaCvrLeadPct || 8.4)) / 100;
  const metaL2O = (planState.metaLeadToSalePct != null ? planState.metaLeadToSalePct : (dflt.metaLeadToSalePct || 2.0)) / 100;

  let g = {imp:0,clk:0,cost:0,leads:0,orders:0,rev:0};
  const gRows=[];
  if (googleOn) {
    for (const p of YOY_PLAN.plan.products) {
      if (products[p.id]?.enabled===false) continue;
      const e = estimateGoogleProduct(p, monthIdx);
      gRows.push({p,e});
      g.imp+=e.impressions; g.clk+=e.clicks; g.cost+=e.spend;
      g.leads+=e.leads; g.orders+=e.orders; g.rev+=e.rev;
    }
  }

  const rows=[];
  if (googleOn && byId.google && g.cost>0) {
    rows.push({
      ch: byId.google, budget: g.cost, cost: g.cost,
      imp: Math.round(g.imp), clk: Math.round(g.clk),
      leads: Math.round(g.leads), orders: Math.round(g.orders), rev: g.rev,
      cpc: g.clk ? g.cost/g.clk : 0, ctr: g.imp ? g.clk/g.imp : 0, active:true
    });
  }

  let meta = {imp:0,clk:0,cost:0,leads:0,orders:0,rev:0};
  if (metaOn && byId.meta) {
    const share = (byId.meta.budgetShare != null ? byId.meta.budgetShare : (dflt.metaShare || 0.35));
    // Base = % del ppto medio; con monthIdx aplica estacionalidad real Meta 25–26
    const baseCost = googleOn ? (monthlyBudget * share) : monthlyBudget;
    const cost = baseCost * metaSeasonFactor(monthIdx);
    if (cost >= 50) {
      const clk = Math.round(cost / Math.max(metaCpc,0.05));
      const imp = Math.round(clk / Math.max(metaCtr,0.001));
      const leads = Math.round(clk * metaLeadRate);
      const orders = Math.round(leads * metaL2O);
      const rev = orders * aov;
      meta = {imp, clk, cost, leads, orders, rev, season: metaSeasonFactor(monthIdx)};
      rows.push({ch: byId.meta, budget:cost, cost, imp, clk, leads, orders, rev, cpc:metaCpc, ctr:metaCtr, active:true});
    }
  }

  const totCost = rows.reduce((s,r)=>s+r.cost,0);
  const totImp = rows.reduce((s,r)=>s+r.imp,0);
  const totClk = rows.reduce((s,r)=>s+r.clk,0);
  const totLeads = rows.reduce((s,r)=>s+r.leads,0);
  const totOrders = rows.reduce((s,r)=>s+r.orders,0);
  const totRev = rows.reduce((s,r)=>s+r.rev,0);

  // Agregar por campaña genérica (Google detallado + Meta prorrateada)
  const groupMeta = Object.fromEntries((YOY_PLAN.plan.campaignGroups||[]).map(g=>[g.id,g]));
  const byCamp = {};
  for (const {p,e} of gRows) {
    const ginfo = p.campaignGroup || {id:'otros', label:'Otros'};
    const gid = ginfo.id || 'otros';
    if (!byCamp[gid]) {
      byCamp[gid] = {
        id: gid,
        label: (groupMeta[gid]||{}).label || ginfo.label || gid,
        searches:0, clicks:0, leads:0, orders:0, googleSpend:0, googleRev:0, metaSpend:0, metaLeads:0, metaOrders:0, metaRev:0
      };
    }
    const row = byCamp[gid];
    row.searches += e.searches||0;
    row.clicks += e.clicks||0;
    row.leads += e.leads||0;
    row.orders += e.orders||0;
    row.googleSpend += e.spend||0;
    row.googleRev += e.rev||0;
  }
  // Meta no es keyword: se reparte por peso de Google entre campañas no-marca
  let metaEligible = Object.values(byCamp).filter(c => c.id !== 'marca');
  if (!metaEligible.length && meta.cost > 0) {
    // Solo marca en Google: asignar Meta a campañas activas no-marca
    for (const g of (YOY_PLAN.plan.campaignGroups || [])) {
      if (g.id === 'marca') continue;
      const campOn = planState.campaigns?.[g.id]?.enabled !== false;
      const anyOn = (g.products || []).some(pid => planState.products[pid]?.enabled !== false);
      if (!campOn && !anyOn) continue;
      byCamp[g.id] = byCamp[g.id] || {
        id: g.id, label: g.label,
        searches:0, clicks:0, leads:0, orders:0, googleSpend:0, googleRev:0,
        metaSpend:0, metaLeads:0, metaOrders:0, metaRev:0
      };
    }
    metaEligible = Object.values(byCamp).filter(c => c.id !== 'marca');
  }
  const weightBase = metaEligible.reduce((s,c)=>s+(c.googleSpend||0),0);
  if (meta.cost > 0 && metaEligible.length) {
    for (const c of metaEligible) {
      const w = weightBase > 0 ? (c.googleSpend / weightBase) : (1 / metaEligible.length);
      c.metaSpend = meta.cost * w;
      c.metaLeads = meta.leads * w;
      c.metaOrders = meta.orders * w;
      c.metaRev = meta.rev * w;
    }
  }
  const campaignRows = Object.values(byCamp).map(c => ({
    id: c.id,
    label: c.label,
    spend: c.googleSpend + c.metaSpend,
    googleSpend: c.googleSpend,
    metaSpend: c.metaSpend,
    leads: c.leads + c.metaLeads,
    orders: c.orders + c.metaOrders,
    rev: c.googleRev + c.metaRev,
  })).filter(c => c.spend > 0.5 || c.leads > 0 || c.orders > 0).sort((a,b)=>b.spend-a.spend);

  const gShare = googleShareFrac();
  const googleCap = gShare ? monthlyBudget * gShare : monthlyBudget;

  return {
    rows,
    totImp, totClk, totCost, totLeads, totOrders, totRev,
    isrPct, active: rows.map(r=>r.ch.label), unlocked: rows.length, monthIdx,
    googleNeeded: g.cost, scale: 1, overBudget: g.cost > googleCap + 1,
    googleOnly: {spend: g.cost, clicks: Math.round(g.clk), leads: Math.round(g.leads), orders: Math.round(g.orders), rev: g.rev},
    metaOnly: {spend: meta.cost, clicks: meta.clk, leads: meta.leads, orders: meta.orders, rev: meta.rev},
    productRows: gRows.map(({p,e})=>({id:p.id,label:p.label, ...e})),
    campaignRows
  };
}
function calcPlanYear() {
  const monthResults = [];
  for (let i=0;i<12;i++) monthResults.push(calcPlan(i));
  const ids = [];
  const labels = {};
  for (const r of monthResults) {
    for (const row of r.rows) {
      if (!labels[row.ch.id]) { labels[row.ch.id] = row.ch.label; ids.push(row.ch.id); }
    }
  }
  const byCampaign = {};
  for (const id of ids) {
    byCampaign[id] = {
      label: labels[id],
      cost: monthResults.map(r => (r.rows.find(x=>x.ch.id===id)||{}).cost || 0),
      leads: monthResults.map(r => (r.rows.find(x=>x.ch.id===id)||{}).leads || 0),
      orders: monthResults.map(r => (r.rows.find(x=>x.ch.id===id)||{}).orders || 0),
    };
  }
  const months = monthResults.map((r,i)=>({i, cost:r.totCost, leads:r.totLeads, orders:r.totOrders, rev:r.totRev, active:r.unlocked}));
  return {
    months, byCampaign,
    sumCost: months.reduce((s,m)=>s+m.cost,0),
    sumLeads: months.reduce((s,m)=>s+m.leads,0),
    sumOrders: months.reduce((s,m)=>s+m.orders,0),
    sumRev: months.reduce((s,m)=>s+m.rev,0),
  };
}
function applyPlanIsr(isrPct) {
  planState.isrPct = isrPct;
  if (!planState.productIs) planState.productIs = Object.assign({}, YOY_PLAN.plan.productIs || {});
  YOY_PLAN.plan.products.forEach(p => {
    if (!p.brand && p.id !== 'bps home') planState.productIs[p.id] = isrPct;
  });
}
function googleSpendCurrent() {
  let cost = 0;
  for (const p of YOY_PLAN.plan.products) {
    if (planState.products[p.id]?.enabled === false) continue;
    cost += estimateGoogleProduct(p).spend;
  }
  return cost;
}
function googleShareFrac() {
  const metaOn = planState.channels?.meta?.enabled !== false;
  const googleOn = planState.channels?.google?.enabled !== false;
  if (!googleOn) return 0;
  if (!metaOn) return 1;
  const gShare = ((YOY_PLAN.plan.channels || []).find(c => c.id === 'google') || {}).budgetShare;
  return (gShare != null && gShare > 0) ? gShare : 0.55;
}
function budgetFromIsr() {
  const g = googleSpendCurrent();
  const share = googleShareFrac();
  if (!share) return Math.max(100, Math.round(g));
  return Math.max(100, Math.round(g / share));
}
function volumeCrFactor(budget) {
  const ref = (YOY_PLAN.plan.defaults || {}).monthlyBudget || 1000;
  // Más ppto → audiencia más amplia → CR un poco peores (rendimientos decrecientes)
  const f = Math.pow(ref / Math.max(budget, 100), 0.22);
  return Math.max(0.55, Math.min(1.45, f));
}
function applyVolumeCrs(budget) {
  const f = volumeCrFactor(budget);
  const d = YOY_PLAN.plan.defaults || {};
  const baseL = planState.cvrLeadBase != null ? planState.cvrLeadBase : (d.googleCvrLeadPct != null ? d.googleCvrLeadPct : 3.7);
  const baseS = planState.leadSaleBase != null ? planState.leadSaleBase : (d.googleLeadToSalePct != null ? d.googleLeadToSalePct : 13);
  const baseML = planState.metaCvrLeadBase != null ? planState.metaCvrLeadBase : (d.metaCvrLeadPct != null ? d.metaCvrLeadPct : 8.4);
  const baseMS = planState.metaLeadSaleBase != null ? planState.metaLeadSaleBase : (d.metaLeadToSalePct != null ? d.metaLeadToSalePct : 2.0);
  planState.googleCvrLeadPct = Math.max(0.5, Math.min(25, Math.round(baseL * f * 10) / 10));
  planState.googleLeadToSalePct = Math.max(2, Math.min(50, Math.round(baseS * f * 10) / 10));
  planState.cvrLeadPct = planState.googleCvrLeadPct;
  planState.leadToSalePct = planState.googleLeadToSalePct;
  // Meta: escala más suave (ya parte de lead→venta bajo)
  const fm = Math.max(0.7, Math.min(1.25, f));
  planState.metaCvrLeadPct = Math.max(1, Math.min(20, Math.round(baseML * fm * 10) / 10));
  planState.metaLeadToSalePct = Math.max(0.5, Math.min(15, Math.round(baseMS * fm * 10) / 10));
  const elL = document.getElementById('planCvrLead');
  const elS = document.getElementById('planLeadSale');
  if (elL) elL.value = planState.googleCvrLeadPct;
  if (elS) elS.value = planState.googleLeadToSalePct;
  const elML = document.getElementById('planMetaCvrLead');
  const elMS = document.getElementById('planMetaLeadSale');
  if (elML) elML.value = planState.metaCvrLeadPct;
  if (elMS) elMS.value = planState.metaLeadToSalePct;
}
function setCrsFromUser(cvrLead, leadSale, budget) {
  const f = volumeCrFactor(budget);
  planState.googleCvrLeadPct = cvrLead;
  planState.googleLeadToSalePct = leadSale;
  planState.cvrLeadPct = cvrLead;
  planState.leadToSalePct = leadSale;
  planState.cvrLeadBase = f ? (cvrLead / f) : cvrLead;
  planState.leadSaleBase = f ? (leadSale / f) : leadSale;
}
function setMetaCrsFromUser(cvrLead, leadSale, budget) {
  const f = Math.max(0.7, Math.min(1.25, volumeCrFactor(budget)));
  planState.metaCvrLeadPct = cvrLead;
  planState.metaLeadToSalePct = leadSale;
  planState.metaCvrLeadBase = f ? (cvrLead / f) : cvrLead;
  planState.metaLeadSaleBase = f ? (leadSale / f) : leadSale;
}
function isrFromBudget(budget) {
  const share = googleShareFrac();
  const target = share ? budget * share : budget;
  const savedIs = planState.isrPct;
  const savedPi = Object.assign({}, planState.productIs || {});
  applyPlanIsr(20);
  const c20 = googleSpendCurrent();
  applyPlanIsr(40);
  const c40 = googleSpendCurrent();
  planState.isrPct = savedIs;
  planState.productIs = savedPi;
  const k = (c40 - c20) / 20;
  if (!(k > 0.01)) {
    // casi todo es marca fija: no se puede bajar con IS
    return Math.max(5, Math.min(100, Math.round(savedIs / 5) * 5));
  }
  const brandPart = c20 - 20 * k;
  let isr = (target - brandPart) / k;
  if (!isFinite(isr)) isr = savedIs;
  isr = Math.max(5, Math.min(100, Math.round(isr / 5) * 5));
  return isr;
}
function bindPlanControls() {
  const readNum = (id, fallback) => {
    const el = document.getElementById(id);
    if (!el) return fallback;
    const v = parseFloat(el.value);
    return (isFinite(v) && v >= 0) ? v : fallback;
  };
  const sync = (ev) => {
    const src = ev && ev.target ? ev.target.id : '';
    planState.aov = readNum('planAov', planState.aov);
    document.querySelectorAll('[data-ch]').forEach(el=>{ planState.channels[el.dataset.ch]={enabled:el.checked}; });
    // Campañas genéricas: solo al togglear una campaña se activan/desactivan sus productos
    const groups = YOY_PLAN.plan.campaignGroups || [];
    if (src && ev?.target?.dataset?.camp) {
      const gid = ev.target.dataset.camp;
      const on = !!ev.target.checked;
      planState.campaigns[gid] = {enabled: on};
      const g = groups.find(x => x.id === gid);
      (g?.products||[]).forEach(pid => { planState.products[pid] = {enabled: on}; });
    } else if (groups.length && document.querySelector('[data-camp]')) {
      document.querySelectorAll('[data-camp]').forEach(el=>{
        planState.campaigns[el.dataset.camp] = {enabled: el.checked};
      });
    } else {
      document.querySelectorAll('[data-prod]').forEach(el=>{ planState.products[el.dataset.prod]={enabled:el.checked}; });
    }

    if (src === 'planCvrLead' || src === 'planLeadSale') {
      planState.monthlyBudget = readNum('planBudget', planState.monthlyBudget);
      setCrsFromUser(
        readNum('planCvrLead', planState.googleCvrLeadPct),
        readNum('planLeadSale', planState.googleLeadToSalePct),
        planState.monthlyBudget
      );
    } else if (src === 'planMetaCvrLead' || src === 'planMetaLeadSale') {
      planState.monthlyBudget = readNum('planBudget', planState.monthlyBudget);
      setMetaCrsFromUser(
        readNum('planMetaCvrLead', planState.metaCvrLeadPct),
        readNum('planMetaLeadSale', planState.metaLeadToSalePct),
        planState.monthlyBudget
      );
    } else if (src === 'planIsr') {
      applyPlanIsr(readNum('planIsr', planState.isrPct));
      planState.monthlyBudget = budgetFromIsr();
      const budEl = document.getElementById('planBudget');
      if (budEl) budEl.value = planState.monthlyBudget;
      applyVolumeCrs(planState.monthlyBudget);
    } else if (src === 'planBudget') {
      planState.monthlyBudget = readNum('planBudget', planState.monthlyBudget);
      const nextIs = isrFromBudget(planState.monthlyBudget);
      applyPlanIsr(nextIs);
      const isrEl = document.getElementById('planIsr');
      if (isrEl) isrEl.value = planState.isrPct;
      applyVolumeCrs(planState.monthlyBudget);
    } else if (ev?.target?.dataset?.ch) {
      // Al activar/desactivar Meta/Google, recalibrar ppto total a la IS actual
      applyPlanIsr(planState.isrPct);
      planState.monthlyBudget = budgetFromIsr();
      const budEl = document.getElementById('planBudget');
      if (budEl) budEl.value = planState.monthlyBudget;
      applyVolumeCrs(planState.monthlyBudget);
    } else if (src === 'planAov') {
      planState.monthlyBudget = readNum('planBudget', planState.monthlyBudget);
      // AOV global: ya se lee arriba; fuerza recálculo coherente KPIs ↔ campañas
    } else {
      planState.monthlyBudget = readNum('planBudget', planState.monthlyBudget);
      const prevIs = planState.isrPct;
      planState.isrPct = readNum('planIsr', planState.isrPct);
      if (planState.isrPct !== prevIs) applyPlanIsr(planState.isrPct);
      planState.cvrLeadPct = readNum('planCvrLead', planState.cvrLeadPct);
      planState.leadToSalePct = readNum('planLeadSale', planState.leadToSalePct);
      planState.googleCvrLeadPct = planState.cvrLeadPct;
      planState.googleLeadToSalePct = planState.leadToSalePct;
      planState.metaCvrLeadPct = readNum('planMetaCvrLead', planState.metaCvrLeadPct);
      planState.metaLeadToSalePct = readNum('planMetaLeadSale', planState.metaLeadToSalePct);
    }

    const isrVal = document.getElementById('planIsrVal');
    if (isrVal) isrVal.textContent = planState.isrPct + '%';
    renderPlanResults();
    renderRoadmap();
  };
  ['planBudget','planIsr','planAov','planCvrLead','planLeadSale','planMetaCvrLead','planMetaLeadSale'].forEach(id=>{
    const el=document.getElementById(id);
    if (!el) return;
    el.addEventListener('input', sync);
    el.addEventListener('change', sync);
  });
  document.querySelectorAll('[data-ch],[data-prod],[data-camp]').forEach(el=>el.addEventListener('change', sync));
}
function renderPlan() {
  if (!planState) initPlanState();
  const panel = document.getElementById('panelPlan');
  if (!planControlsReady) {
    panel.innerHTML = `
      <div id="planControls" class="plan-controls">
        <div><label>Presupuesto paid / mes (€)</label><input type="number" id="planBudget" value="${planState.monthlyBudget}" min="100" step="50"/></div>
        <div><label>Impression share Google (%)</label><input type="range" id="planIsr" min="5" max="100" step="5" value="${planState.isrPct}"/><span id="planIsrVal">${planState.isrPct}%</span></div>
        <div><label>AOV (€)</label><input type="number" id="planAov" value="${planState.aov}" min="50" step="5"/></div>
        <div><label>Google · CR clic → lead (%)</label><input type="number" id="planCvrLead" value="${planState.googleCvrLeadPct}" min="0.1" max="40" step="0.1"/></div>
        <div><label>Google · CR lead → pedido WC (%)</label><input type="number" id="planLeadSale" value="${planState.googleLeadToSalePct}" min="0.1" max="80" step="0.5"/></div>
        <div><label>Meta · CR clic → lead (%)</label><input type="number" id="planMetaCvrLead" value="${planState.metaCvrLeadPct}" min="0.1" max="40" step="0.1"/></div>
        <div><label>Meta · CR lead → pedido WC (%)</label><input type="number" id="planMetaLeadSale" value="${planState.metaLeadToSalePct}" min="0.1" max="40" step="0.1"/></div>
      </div>
      <div class="grid-2" style="margin:12px 0">
        <div><h3 style="font-size:.95rem;margin-bottom:8px">Canales</h3>
          ${(YOY_PLAN.plan.channels||[]).filter(c=>c.type!=='organic').map(c=>`<label class="plan-toggle"><input type="checkbox" data-ch="${c.id}" ${planState.channels[c.id]?.enabled!==false?'checked':''}/> ${c.label}</label>`).join('')}
        </div>
        <div><h3 style="font-size:.95rem;margin-bottom:8px">Campañas</h3>
          <div style="display:flex;flex-wrap:wrap;gap:6px 14px">
            ${(YOY_PLAN.plan.campaignGroups||[]).map(g=>{
              const checked = planState.campaigns?.[g.id]?.enabled !== false;
              return `<label class="plan-toggle" style="margin:0"><input type="checkbox" data-camp="${g.id}" ${checked?'checked':''}/> ${g.label}</label>`;
            }).join('')}
          </div>
        </div>
      </div>
      <div id="planResults"></div>
      <div class="chart-card" style="margin-top:16px"><h4>Planificación mensual · € por canal</h4><div class="chart-wrap" style="height:320px"><canvas id="chartPlanMonthly"></canvas></div></div>`;
    bindPlanControls();
    planControlsReady = true;
  }
  renderPlanResults();
}
function renderPlanResults() {
  if (!planState) initPlanState();
  const r = calcPlan();
  const y = calcPlanYear();
  const gYear = ((y.byCampaign||{}).google?.cost || []).reduce((s,v)=>s+(v||0),0);
  const mYear = ((y.byCampaign||{}).meta?.cost || []).reduce((s,v)=>s+(v||0),0);
  const el = document.getElementById('planResults');
  if (!el) return;
  const g = r.googleOnly || {};
  const m = r.metaOnly || {};
  const mix = YOY_PLAN.plan.mediaMix || {};
  const gRow = (r.rows||[]).find(x=>x.ch.id==='google');
  const mRow = (r.rows||[]).find(x=>x.ch.id==='meta');
  const chCompare = [];
  if (gRow) {
    chCompare.push([
      'Google Ads',
      EUR(gRow.cost,0),
      NUM(gRow.imp),
      NUM(gRow.clk),
      EUR(gRow.cpc,2),
      ((gRow.ctr||0)*100).toFixed(2)+'%',
      NUM(gRow.leads),
      NUM(gRow.orders),
      gRow.orders ? EUR(gRow.cost/gRow.orders,0) : '—',
      gRow.cost ? (gRow.rev/gRow.cost).toFixed(2)+'×' : '—',
      EUR(gRow.rev,0)
    ]);
  }
  if (mRow) {
    chCompare.push([
      'Meta Ads',
      EUR(mRow.cost,0),
      NUM(mRow.imp),
      NUM(mRow.clk),
      EUR(mRow.cpc,2),
      ((mRow.ctr||0)*100).toFixed(2)+'%',
      NUM(mRow.leads),
      NUM(mRow.orders),
      mRow.orders ? EUR(mRow.cost/mRow.orders,0) : '—',
      mRow.cost ? (mRow.rev/mRow.cost).toFixed(2)+'×' : '—',
      EUR(mRow.rev,0)
    ]);
  }
  if (chCompare.length) {
    chCompare.push({
      className: 'row-total',
      cells: [
        'Total',
        EUR(r.totCost,0),
        NUM(r.totImp),
        NUM(r.totClk),
        r.totClk ? EUR(r.totCost/r.totClk,2) : '—',
        r.totImp ? ((r.totClk/r.totImp)*100).toFixed(2)+'%' : '—',
        NUM(r.totLeads),
        NUM(r.totOrders),
        r.totOrders ? EUR(r.totCost/r.totOrders,0) : '—',
        r.totCost ? (r.totRev/r.totCost).toFixed(2)+'×' : '—',
        EUR(r.totRev,0)
      ]
    });
  }
  const campRows = (r.campaignRows||[]).map(x=>[
    x.label,
    EUR(x.googleSpend,0),
    EUR(x.metaSpend,0),
    EUR(x.spend,0),
    NUM(x.leads),
    NUM(x.orders),
    EUR(x.rev,0)
  ]);
  if (campRows.length) {
    const camps = r.campaignRows || [];
    const cg = camps.reduce((s,x)=>s+(x.googleSpend||0),0);
    const cm = camps.reduce((s,x)=>s+(x.metaSpend||0),0);
    const cs = camps.reduce((s,x)=>s+(x.spend||0),0);
    const cl = camps.reduce((s,x)=>s+(x.leads||0),0);
    const co = camps.reduce((s,x)=>s+(x.orders||0),0);
    const crv = camps.reduce((s,x)=>s+(x.rev||0),0);
    campRows.push({
      className: 'row-total',
      cells: ['Total', EUR(cg,0), EUR(cm,0), EUR(cs,0), NUM(cl), NUM(co), EUR(crv,0)]
    });
  }
  const ig = (mix.declared_social||{}).instagram || {};
  const fb = (mix.declared_social||{}).facebook || {};
  el.innerHTML = `
    <div class="persona-box" style="margin:12px 0">
      <h3 style="margin:0 0 6px">Mix de medios · recomendación</h3>
      <p style="margin:0 0 8px"><strong>${mix.headline || 'Google + Meta con roles distintos.'}</strong></p>
      <p style="margin:0 0 10px;font-size:.9rem">
        Baseline 25–26: Google <strong>${(mix.baseline||{}).googleRoas ?? mix.google?.roas ?? '—'}×</strong>
        · Meta <strong>${(mix.baseline||{}).metaRoas ?? mix.meta?.roas ?? '—'}×</strong>
        · blend <strong>${(mix.baseline||{}).blendRoas ?? '—'}×</strong>
        &nbsp;→&nbsp; Objetivo plan 26–27: Google <strong>${(mix.planTargets||{}).googleRoas ?? '—'}×</strong>
        · Meta <strong>${(mix.planTargets||{}).metaRoas ?? '—'}×</strong>
        · blend <strong>${(mix.planTargets||{}).blendRoas ?? '—'}×</strong>
      </p>
      <ul style="margin:0;padding-left:18px;font-size:.9rem">
        ${(mix.bullets||[]).map(b=>`<li style="margin-bottom:4px">${b}</li>`).join('') || '<li>Sin benchmarks cargados.</li>'}
      </ul>
      <p style="font-size:.85rem;color:var(--muted);margin:10px 0 0">
        Hacer Google: sí (eficiencia WC). Hacer Meta: sí, pero acotada (volumen/remarketing). ¿Los dos? Sí — mix ~${Math.round((mix.recommended||{}).googleShare*100||65)}/${Math.round((mix.recommended||{}).metaShare*100||35)}.
        IG+FB declarados ${NUM((ig.orders||0)+(fb.orders||0))} pedidos ≠ Meta Ads verificado.
        El simulador usa CRs de <em>plan</em> (mejora), no los CRs crudos 25–26.
      </p>
    </div>
    <p style="font-size:.9rem;color:var(--muted);margin:8px 0">
      Canales: <strong>${(r.active||[]).join(' · ')||'ninguno'}</strong>
      · Google = demanda KW × IS × CTR × CPC (rates Search) + estacionalidad KW
      · Meta = ppto × share × estacionalidad gasto Meta 25–26 × CPC/CTR/CR propios
      ${r.overBudget?` · <span style="color:#E25B4C">Google ${EUR(r.googleNeeded,0)} &gt; cupo Google ${EUR(planState.monthlyBudget * googleShareFrac(),0)} — baja IS% o sube ppto</span>`:''}
    </p>
    <div class="plan-kpi-row">
      <div class="stat"><strong>${EUR(r.totCost,0)}</strong><span>Inversión/mes</span></div>
      <div class="stat"><strong>${NUM(r.totClk)}</strong><span>Clics/mes</span></div>
      <div class="stat"><strong>${NUM(r.totLeads)}</strong><span>Leads/mes</span></div>
      <div class="stat"><strong>${NUM(r.totOrders)}</strong><span>Pedidos WC/mes</span></div>
      <div class="stat"><strong>${EUR(r.totRev,0)}</strong><span>Ingresos/mes</span></div>
      <div class="stat"><strong>${r.totCost?(r.totRev/r.totCost).toFixed(2)+'×':'—'}</strong><span>ROAS conjunto</span></div>
    </div>
    <div class="plan-kpi-row" style="margin-top:8px">
      <div class="stat"><strong>${EUR(y.sumCost,0)}</strong><span>Ppto curso 26–27</span><div class="delta">Google ${EUR(gYear,0)} · Meta ${EUR(mYear,0)} · con estacionalidad</div></div>
      <div class="stat"><strong>${NUM(y.sumOrders)}</strong><span>Pedidos WC/curso</span></div>
      <div class="stat"><strong>${EUR(y.sumRev,0)}</strong><span>Ingresos paid/curso</span></div>
      <div class="stat"><strong>${y.sumCost?(y.sumRev/y.sumCost).toFixed(2)+'×':'—'}</strong><span>ROAS curso</span></div>
    </div>
    <h3 style="font-size:.95rem;margin:12px 0 6px">Qué aporta cada canal (simulación)</h3>
    ${tableHtml(['Canal','Inversión','Impr.','Clics','CPC','CTR','Leads','Pedidos WC','CAC','ROAS','Ingresos'], chCompare)}
    <h3 style="font-size:.95rem;margin:16px 0 6px">Estimación por campaña</h3>
    ${tableHtml(['Campaña','Google','Meta','Total','Leads','Pedidos','Ingresos'], campRows)}
    <p style="font-size:.85rem;color:var(--muted);margin-top:8px">
      Mix ppto ~${Math.round(googleShareFrac()*100)}% Google / ~${Math.round((1-googleShareFrac())*100)}% Meta.
      Ratios Google ${planState.googleCvrLeadPct}%→${planState.googleLeadToSalePct}% · Meta ${planState.metaCvrLeadPct}%→${planState.metaLeadToSalePct}% · AOV ${EUR(planState.aov,0)}.
      ROAS por canal = plan 26–27 (mejora vs baseline ${(mix.baseline||{}).googleRoas ?? '—'}× / ${(mix.baseline||{}).metaRoas ?? '—'}×). La fila Total es el blend.
    </p>`;
  renderPlanMonthlyChart();
}
function renderPlanMonthlyChart() {
  const y = calcPlanYear();
  const labels = ['Sep','Oct','Nov','Dic','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago'];
  const ctx = document.getElementById('chartPlanMonthly'); if (!ctx) return;
  if (charts.chartPlanMonthly) charts.chartPlanMonthly.destroy();
  const palette = {'google':'#0080E0','meta':'#5B54C9'};
  const campIds = Object.keys(y.byCampaign || {});
  const datasets = campIds.map((id)=>({
    label: y.byCampaign[id].label,
    data: y.byCampaign[id].cost.map(v=>Math.round(v)),
    borderColor: palette[id] || '#0B1F3A',
    backgroundColor: 'transparent',
    yAxisID: 'y',
    tension: .3,
    borderWidth: 2,
  }));
  datasets.push({
    label: 'Leads (total)',
    data: y.months.map(m=>m.leads),
    borderColor: '#9B8FE8',
    borderDash: [6,4],
    yAxisID: 'y1',
    tension: .3,
    borderWidth: 1.5,
  });
  datasets.push({
    label: 'Pedidos (total)',
    data: y.months.map(m=>m.orders),
    borderColor: '#1FA97A',
    borderDash: [2,3],
    yAxisID: 'y1',
    tension: .3,
    borderWidth: 1.5,
  });
  charts.chartPlanMonthly = new Chart(ctx,{
    type:'line',
    data:{labels, datasets},
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{position:'bottom',labels:{boxWidth:10,font:{size:11}}}},
      scales:{
        y:{position:'left', beginAtZero:true, title:{display:true,text:'Inversión € / canal'}},
        y1:{position:'right', beginAtZero:true, grid:{drawOnChartArea:false}, title:{display:true,text:'Leads / pedidos'}}
      }
    }
  });
}

function renderRoadmap() {
  if (!planState) initPlanState();
  const y = calcPlanYear();
  const gYear = ((y.byCampaign||{}).google?.cost || []).reduce((s,v)=>s+(v||0),0);
  const mYear = ((y.byCampaign||{}).meta?.cost || []).reduce((s,v)=>s+(v||0),0);
  const quarters = YOY_PLAN.plan.roadmap || [
    {q:'Q1 · Sep–Nov', items:['Ramp-up APTIS/Cambridge','Remarketing leads','Brand Search always-on','SLA <1 h']},
    {q:'Q2 · Dic–Feb', items:['Convocatorias invierno','Cortar Meta fría','SEO queries top','Extensiones call/WA']},
    {q:'Q3 · Mar–May', items:['Intensivos primavera','Optimizar CAC/ROAS WC','Brand + remarketing','CrUX landings']},
    {q:'Q4 · Jun–Ago', items:['Jun–Jul pico certs: subir IS/ppto Google','Convocatoria verano + intensivos','Meta remarketing leads Q3','Agosto: brand + prep septiembre','No hibernar en pico de búsquedas']},
  ];
  document.getElementById('panelRoadmap').innerHTML = `
    <div class="stat-row" style="margin-bottom:14px">
      <div class="stat"><strong>${EUR(y.sumCost,0)}</strong><span>Ppto curso 26–27</span><div class="delta">Google ${EUR(gYear,0)} · Meta ${EUR(mYear,0)}</div></div>
      <div class="stat"><strong>${NUM(y.sumOrders)}</strong><span>Pedidos paid/curso</span></div>
      <div class="stat"><strong>${EUR(y.sumRev,0)}</strong><span>Ingresos paid/curso</span></div>
      <div class="stat"><strong>${EUR(planState.monthlyBudget,0)}</strong><span>Presupuesto medio / mes</span></div>
    </div>
    <div class="roadmap-grid">${quarters.map(q=>`
      <div class="card action"><h3>${q.q}</h3><ul>${q.items.map(i=>`<li>${i}</li>`).join('')}</ul></div>
    `).join('')}</div>`;
}

function renderAll() { renderDiagnostico(); renderPlan(); renderRoadmap(); }
renderAll();
"""


def inject(payload: dict):
    html = HTML.read_text()

    # CSS helpers
    if ".profile-grid" not in html:
        html = html.replace(
            ".persona-box{background:linear-gradient(135deg,var(--sky),#fff);border:1px solid var(--line);border-radius:14px;padding:18px;margin:14px 0}",
            ".profile-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:14px 0}"
            ".roadmap-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}"
            ".persona-box{background:linear-gradient(135deg,var(--sky),#fff);border:1px solid var(--line);border-radius:14px;padding:18px;margin:0}"
            "@media(max-width:900px){.profile-grid,.roadmap-grid{grid-template-columns:1fr}}",
        )
    if "table.data tr.row-total" not in html:
        html = html.replace(
            "table.data tbody tr:hover td{background:#f8fbfe}",
            "table.data tbody tr:hover td{background:#f8fbfe}"
            "table.data tr.row-total td{background:var(--bg-soft);font-weight:800;border-top:2px solid var(--line)}"
            "table.data tr.row-total td:first-child{background:var(--bg-soft)}",
        )

    # Geo lead (short)
    html = re.sub(
        r'(<section id="diag-geo"[\s\S]*?<p class="section-lead">)[\s\S]*?(</p>)',
        r"\1Mapa y tablas 24–25 vs 25–26 (billing WC).\2",
        html,
        count=1,
    )

    new_demo = """<section id="diag-demo">
  <div class="wrap">
    <span class="section-badge real">Histórico</span>
    <p class="section-label">Demo</p>
    <h2 class="section-title">Quién compra — perfiles tipo</h2>
    <p class="section-lead">Tres perfiles: comprador WooCommerce, audiencia Meta y audiencia Google.</p>
    <div id="panelDiagPersona"></div>
  </div>
</section>"""
    html = re.sub(r'<section id="diag-demo">[\s\S]*?</section>', new_demo, html, count=1)

    html = re.sub(
        r'(<section id="simulador"[\s\S]*?<p class="section-lead">)[\s\S]*?(</p>)',
        r"\1Presupuesto, IS%, AOV y CR lead/venta. Canales: Google Ads y Meta Ads.\2",
        html,
        count=1,
    )
    html = re.sub(
        r'(<section id="roadmap"[\s\S]*?<h2 class="section-title">)[\s\S]*?(</h2>\s*<p class="section-lead">)[\s\S]*?(</p>)',
        r"\1Hoja de ruta\2Cuatro trimestres · curso 26/27.\3",
        html,
        count=1,
    )
    # drop roadmap footer note
    html = re.sub(
        r'(<div id="panelRoadmap"></div>)\s*<div class="note"[\s\S]*?</div>',
        r"\1",
        html,
        count=1,
    )

    payload_json = json.dumps(payload, ensure_ascii=False)
    js = JS_RUNTIME.replace("__PAYLOAD__", payload_json)
    new_html, n = re.subn(
        r"<script src=\"https://unpkg.com/leaflet@1\.9\.4/dist/leaflet\.js\" crossorigin=\"\"></script>\s*<script>.*?</script>\s*</body>",
        "<script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\" crossorigin=\"\"></script>\n<script>\n"
        + js
        + "\n</script>\n</body>",
        html,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise SystemExit(f"Failed to inject script (replacements={n})")
    HTML.write_text(new_html)
    # also refresh cache-bust copy
    (ROOT / "propuesta-marketing-bps-v2.html").write_text(new_html)
    print(f"Updated {HTML} and v2 ({HTML.stat().st_size // 1024} KB)")


def main():
    if not DB.exists():
        raise SystemExit(f"Missing {DB}. Run scripts/build_bps_db.py first.")
    payload = export_payload()
    inject(payload)
    # sanity
    cur = payload["periods"]["sy-2025-26"]
    print(
        "25-26:",
        cur["orders"],
        "orders · Meta verified",
        cur["paid"]["meta"]["wc_orders_verified"],
        "· GAds purchase",
        cur["paid"]["google_ads"]["platform_purchases"],
        "leads",
        cur["paid"]["google_ads"]["platform_lead_convs"],
        "WC utm",
        cur["paid"]["google_ads"]["wc_orders_verified"],
    )


if __name__ == "__main__":
    main()

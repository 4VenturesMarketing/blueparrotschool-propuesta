#!/usr/bin/env python3
"""Refresh GA4, GSC and Google Ads conversion split into dashboard/data/."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import yaml
from google.ads.googleads.client import GoogleAdsClient
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dashboard" / "data"
CFG = Path.home() / ".config" / "bps"
ADS_YAML = Path("/Users/4ventures/google-ads.yaml")
LOGIN_CUSTOMER = "5963150101"
CUSTOMER = "1064441284"
GA4_PROPERTY = "469240570"
GSC_SITE = "https://blueparrotschool.com/"
NOW = datetime.now().isoformat(timespec="seconds")


def ga4():
    creds = Credentials.from_authorized_user_file(str(CFG / "google-token.json"))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    client = BetaAnalyticsDataClient(credentials=creds)

    def report(start, end, dims, metrics, limit=100):
        r = client.run_report(
            RunReportRequest(
                property=f"properties/{GA4_PROPERTY}",
                date_ranges=[DateRange(start_date=start, end_date=end)],
                dimensions=[Dimension(name=d) for d in dims] if dims else [],
                metrics=[Metric(name=m) for m in metrics],
                limit=limit,
            )
        )
        rows = []
        for row in r.rows:
            item = {}
            for i, d in enumerate(r.dimension_headers):
                item[d.name] = row.dimension_values[i].value
            for i, m in enumerate(r.metric_headers):
                item[m.name] = row.metric_values[i].value
            rows.append(item)
        return rows

    out = {"fetchedAt": NOW, "property": GA4_PROPERTY}
    for label, start, end in [
        ("sy-2024-25", "2024-09-01", "2025-08-31"),
        ("sy-2025-26", "2025-09-01", "2026-08-27"),
    ]:
        tot = report(
            start,
            end,
            [],
            ["sessions", "totalUsers", "ecommercePurchases", "purchaseRevenue", "conversions", "engagedSessions"],
        )
        ch = report(
            start,
            end,
            ["sessionDefaultChannelGroup"],
            ["sessions", "totalUsers", "ecommercePurchases", "purchaseRevenue", "conversions"],
        )
        sm = report(
            start,
            end,
            ["sessionSource", "sessionMedium", "sessionCampaignName"],
            ["sessions", "ecommercePurchases", "purchaseRevenue", "conversions"],
            100,
        )
        out[label] = {"totals": tot[0] if tot else {}, "channels": ch, "source_medium": sm}
    (DATA / "ga4-bps-raw.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print("GA4 saved")


def gsc():
    creds = Credentials.from_authorized_user_file(str(CFG / "google-token.json"))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    sc = build("searchconsole", "v1", credentials=creds)
    out = {"fetchedAt": NOW, "site": GSC_SITE, "gsc": {}}
    for label, start, end in [
        ("24-25", "2024-09-01", "2025-08-31"),
        ("25-26", "2025-09-01", "2026-08-27"),
    ]:
        resp = (
            sc.searchanalytics()
            .query(
                siteUrl=GSC_SITE,
                body={"startDate": start, "endDate": end, "dimensions": ["device"], "rowLimit": 10},
            )
            .execute()
        )
        clicks = sum(r.get("clicks", 0) for r in resp.get("rows", []))
        imps = sum(r.get("impressions", 0) for r in resp.get("rows", []))
        out["gsc"][label] = {"clicks": clicks, "impressions": imps, "by_device": resp.get("rows", [])}
    resp = (
        sc.searchanalytics()
        .query(
            siteUrl=GSC_SITE,
            body={
                "startDate": "2025-09-01",
                "endDate": "2026-08-27",
                "dimensions": ["query"],
                "rowLimit": 50,
            },
        )
        .execute()
    )
    out["gsc"]["top_queries_2526"] = resp.get("rows", [])
    (DATA / "ga4-gsc-crosscheck.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print("GSC saved")


def google_ads():
    cfg = yaml.safe_load(ADS_YAML.read_text())
    cfg["login_customer_id"] = LOGIN_CUSTOMER
    client = GoogleAdsClient.load_from_dict(cfg)
    ga = client.get_service("GoogleAdsService")

    actions = []
    for row in ga.search(
        customer_id=CUSTOMER,
        query="""
        SELECT conversion_action.id, conversion_action.name, conversion_action.type,
               conversion_action.category, conversion_action.status, conversion_action.primary_for_goal
        FROM conversion_action""",
    ):
        a = row.conversion_action
        actions.append(
            {
                "id": a.id,
                "name": a.name,
                "type": a.type_.name,
                "category": a.category.name,
                "status": a.status.name,
                "primary": bool(a.primary_for_goal),
            }
        )

    conv_rows = []
    for row in ga.search(
        customer_id=CUSTOMER,
        query="""
        SELECT segments.date, segments.conversion_action, segments.conversion_action_name,
               segments.conversion_action_category, campaign.id, campaign.name,
               metrics.conversions, metrics.conversions_value, metrics.all_conversions, metrics.all_conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '2025-01-01' AND '2026-08-28'
        """,
    ):
        cat = row.segments.conversion_action_category
        conv_rows.append(
            {
                "date": row.segments.date,
                "conv_action_resource": row.segments.conversion_action,
                "conv_name": row.segments.conversion_action_name,
                "conv_category": cat.name if cat else None,
                "campaign_id": str(row.campaign.id),
                "campaign": row.campaign.name,
                "conversions": float(row.metrics.conversions),
                "value": float(row.metrics.conversions_value),
                "all_conversions": float(row.metrics.all_conversions),
                "all_value": float(row.metrics.all_conversions_value),
            }
        )

    camp_daily = []
    for row in ga.search(
        customer_id=CUSTOMER,
        query="""
        SELECT segments.date, campaign.id, campaign.name, campaign.advertising_channel_type, campaign.status,
               metrics.cost_micros, metrics.clicks, metrics.impressions, metrics.conversions, metrics.conversions_value,
               metrics.ctr, metrics.average_cpc
        FROM campaign
        WHERE segments.date BETWEEN '2025-01-01' AND '2026-08-28'
        """,
    ):
        camp_daily.append(
            {
                "date": row.segments.date,
                "campaign_id": str(row.campaign.id),
                "campaign": row.campaign.name,
                "channel": row.campaign.advertising_channel_type.name,
                "status": row.campaign.status.name,
                "spend": row.metrics.cost_micros / 1e6,
                "clicks": int(row.metrics.clicks),
                "impressions": int(row.metrics.impressions),
                "conversions": float(row.metrics.conversions),
                "value": float(row.metrics.conversions_value),
                "ctr": float(row.metrics.ctr),
                "cpc": row.metrics.average_cpc / 1e6 if row.metrics.average_cpc else 0,
            }
        )

    by_cat = defaultdict(lambda: {"conversions": 0.0, "value": 0.0})
    by_name = defaultdict(lambda: {"conversions": 0.0, "value": 0.0, "category": None})
    for r in conv_rows:
        if not r["conv_name"]:
            continue
        by_cat[r["conv_category"]]["conversions"] += r["conversions"]
        by_cat[r["conv_category"]]["value"] += r["value"]
        by_name[r["conv_name"]]["conversions"] += r["conversions"]
        by_name[r["conv_name"]]["value"] += r["value"]
        by_name[r["conv_name"]]["category"] = r["conv_category"]

    purchase = by_cat.get("PURCHASE", {}).get("conversions", 0)
    leads = by_cat.get("SUBMIT_LEAD_FORM", {}).get("conversions", 0)
    out = {
        "customer_id": CUSTOMER,
        "login_customer_id": LOGIN_CUSTOMER,
        "fetchedAt": NOW,
        "actions": actions,
        "by_category": {k: dict(v) for k, v in by_cat.items()},
        "by_name": {k: dict(v) for k, v in by_name.items()},
        "summary": {
            "purchase_conversions": purchase,
            "lead_conversions": leads,
            "spend": sum(r["spend"] for r in camp_daily),
        },
        "conv_rows": conv_rows,
        "campaign_daily": camp_daily,
    }
    (DATA / "google-ads-conversions-raw.json").write_text(json.dumps(out, indent=2))
    print(f"Google Ads saved · purchase={purchase:.0f} leads={leads:.0f} spend={out['summary']['spend']:.0f}")


if __name__ == "__main__":
    ga4()
    gsc()
    google_ads()
    print("Done. Rebuild DB with: python3 scripts/build_bps_db.py")

"""
Google Analytics 4 Integration
Docs: https://developers.google.com/analytics/devguides/reporting/data/v1
"""
from fastapi import APIRouter, HTTPException, Query
import os

router = APIRouter()

PROPERTY_ID = os.getenv("GA4_PROPERTY_ID")
CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "./credentials.json")


def get_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.oauth2 import service_account
    if not os.path.exists(CREDENTIALS_FILE):
        raise HTTPException(400, "credentials.json não encontrado")
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    return BetaAnalyticsDataClient(credentials=creds)


@router.get("/status")
async def status():
    if not PROPERTY_ID:
        return {"connected": False, "message": "GA4_PROPERTY_ID não configurado"}
    if not os.path.exists(CREDENTIALS_FILE):
        return {"connected": False, "message": "credentials.json não encontrado"}
    try:
        get_client()
        return {"connected": True, "property_id": PROPERTY_ID}
    except Exception as e:
        return {"connected": False, "message": str(e)}


@router.get("/overview")
async def overview(days: int = Query(30, ge=1, le=365)):
    """Sessões, usuários, taxa de rejeição, receita"""
    if not PROPERTY_ID:
        raise HTTPException(400, "GA4 não configurado")

    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Metric, Dimension,
    )

    client = get_client()
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="newUsers"),
            Metric(name="bounceRate"),
            Metric(name="averageSessionDuration"),
            Metric(name="purchaseRevenue"),
            Metric(name="transactions"),
            Metric(name="ecommercePurchases"),
        ],
    )
    response = client.run_report(request)
    row = response.rows[0].metric_values if response.rows else []

    def val(i):
        return row[i].value if i < len(row) else "0"

    return {
        "sessions": int(val(0)),
        "total_users": int(val(1)),
        "new_users": int(val(2)),
        "bounce_rate": round(float(val(3)) * 100, 2),
        "avg_session_duration_sec": round(float(val(4)), 0),
        "purchase_revenue": round(float(val(5)), 2),
        "transactions": int(val(6)),
        "conversions": int(val(7)),
    }


@router.get("/traffic-sources")
async def traffic_sources(days: int = Query(30)):
    """Fontes de tráfego"""
    if not PROPERTY_ID:
        raise HTTPException(400, "GA4 não configurado")

    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric, Dimension, OrderBy

    client = get_client()
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        dimensions=[Dimension(name="sessionDefaultChannelGrouping")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="purchaseRevenue"),
        ],
        limit=10,
    )
    response = client.run_report(request)

    result = []
    for row in response.rows:
        result.append({
            "channel": row.dimension_values[0].value,
            "sessions": int(row.metric_values[0].value),
            "users": int(row.metric_values[1].value),
            "revenue": round(float(row.metric_values[2].value), 2),
        })
    result.sort(key=lambda x: x["sessions"], reverse=True)
    return result


@router.get("/sessions-by-day")
async def sessions_by_day(days: int = Query(30)):
    """Sessões por dia"""
    if not PROPERTY_ID:
        raise HTTPException(400, "GA4 não configurado")

    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric, Dimension, OrderBy

    client = get_client()
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="sessions"), Metric(name="totalUsers")],
    )
    response = client.run_report(request)

    result = []
    for row in response.rows:
        raw_date = row.dimension_values[0].value  # YYYYMMDD
        result.append({
            "date": f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}",
            "sessions": int(row.metric_values[0].value),
            "users": int(row.metric_values[1].value),
        })
    result.sort(key=lambda x: x["date"])
    return result


@router.get("/top-pages")
async def top_pages(days: int = Query(30), limit: int = Query(10)):
    """Páginas mais acessadas"""
    if not PROPERTY_ID:
        raise HTTPException(400, "GA4 não configurado")

    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric, Dimension, OrderBy

    client = get_client()
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        dimensions=[Dimension(name="pagePath"), Dimension(name="pageTitle")],
        metrics=[Metric(name="screenPageViews"), Metric(name="sessions")],
        limit=limit,
    )
    response = client.run_report(request)

    rows = [
        {
            "path": row.dimension_values[0].value,
            "title": row.dimension_values[1].value,
            "views": int(row.metric_values[0].value),
            "sessions": int(row.metric_values[1].value),
        }
        for row in response.rows
    ]
    rows.sort(key=lambda x: x["views"], reverse=True)
    return rows

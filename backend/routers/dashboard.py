"""
Dashboard — dados consolidados de todas as fontes
"""
from fastapi import APIRouter, Query
import asyncio

router = APIRouter()

@router.get("/summary")
async def full_summary(days: int = Query(30)):
    from routers.nuvemshop import orders_summary as ns_summary
    from routers.analytics import overview as ga_overview
    from routers.meta import overview as meta_overview

    async def safe_call(coro):
        try:
            return await coro
        except Exception as e:
            print(f"[dashboard] erro: {type(e).__name__}: {e}")
            return None

    ns, ga, meta = await asyncio.gather(
        safe_call(ns_summary(days=days)),
        safe_call(ga_overview(days=days)),
        safe_call(meta_overview(days=days)),
    )

    meta_spend = meta.get("spend_brl", 0) if meta else 0
    roas = round(ns["total_revenue"] / meta_spend, 2) if meta_spend and ns and ns.get("total_revenue") else None
    cac  = round(meta_spend / ns["paid_orders"], 2) if meta_spend and ns and ns.get("paid_orders") else None

    return {
        "period_days":   days,
        "ecommerce":     ns,
        "analytics":     ga,
        "paid_ads":      meta,
        "cross_metrics": {"roas": roas, "cac": cac},
    }

@router.get("/connections")
async def connections_status():
    from routers.nuvemshop import status as ns_status
    from routers.analytics  import status as ga_status
    from routers.meta       import status as meta_status

    async def safe_call(coro):
        try:
            return await coro
        except Exception as e:
            return {"connected": False, "message": str(e)}

    ns_r, ga_r, meta_r = await asyncio.gather(
        safe_call(ns_status()),
        safe_call(ga_status()),
        safe_call(meta_status()),
    )

    meta_connected = (
        meta_r.get("brl", {}).get("connected") or meta_r.get("usd", {}).get("connected")
    ) if isinstance(meta_r, dict) else False
    meta_name = meta_r.get("brl", {}).get("account_name", "Meta Ads") if isinstance(meta_r, dict) else "—"

    return {
        "nuvemshop":        ns_r,
        "google_analytics": ga_r,
        "meta_ads":         {"connected": meta_connected, "account_name": meta_name, "accounts": meta_r},
    }

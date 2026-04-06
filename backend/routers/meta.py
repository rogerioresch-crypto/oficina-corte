"""
Meta Ads Integration — 3 contas
- Conta 01 (BRL): act_87371826          → gasto × 1.1383 (imposto)
- Conta 02 (USD): act_1137907124668278  → gasto × cotação USD/BRL × (1 + spread 5%)
- Conta 03 (USD): act_432634632394891   → gasto × cotação USD/BRL × (1 + spread 5%)
"""
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional
import httpx, os, json
from pathlib import Path

router = APIRouter()

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
API_VERSION  = "v20.0"
BASE         = f"https://graph.facebook.com/{API_VERSION}"

ACCOUNTS = {
    "brl": {
        "id":       os.getenv("META_ACCOUNT_BRL_ID", "act_87371826"),
        "currency": "BRL",
        "tax":      float(os.getenv("META_ACCOUNT_BRL_TAX", "1.1383")),
        "label":    "Conta 01 (BRL)",
    },
    "usd2": {
        "id":       os.getenv("META_ACCOUNT_USD2_ID", "act_1137907124668278"),
        "currency": "USD",
        "spread":   float(os.getenv("META_ACCOUNT_USD2_SPREAD", "0.05")),
        "label":    "Conta 02 (USD)",
    },
    "usd3": {
        "id":       os.getenv("META_ACCOUNT_USD3_ID", "act_432634632394891"),
        "currency": "USD",
        "spread":   float(os.getenv("META_ACCOUNT_USD3_SPREAD", "0.05")),
        "label":    "Conta 03 (USD)",
    },
}

SETTINGS_FILE = Path(__file__).parent.parent / "settings.json"

def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return {"usd_rate_manual": None, "use_manual_rate": False}

def save_settings(data: dict):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))

async def get_usd_brl_rate() -> float:
    settings = load_settings()
    spread = ACCOUNTS["usd2"]["spread"]
    if settings.get("use_manual_rate") and settings.get("usd_rate_manual"):
        return round(float(settings["usd_rate_manual"]) * (1 + spread), 4)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://economia.awesomeapi.com.br/last/USD-BRL")
            r.raise_for_status()
            rate = float(r.json()["USDBRL"]["bid"])
            return round(rate * (1 + spread), 4)
    except Exception:
        fallback = float(settings.get("usd_rate_manual") or 5.50)
        return round(fallback * (1 + spread), 4)

def _actions_val(actions: list, key: str) -> float:
    return float(next((a["value"] for a in actions if a["action_type"] == key), 0))

class SettingsIn(BaseModel):
    usd_rate_manual: Optional[float] = None
    use_manual_rate: bool = False

@router.get("/settings")
async def get_settings():
    settings = load_settings()
    rate_api = None
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://economia.awesomeapi.com.br/last/USD-BRL")
            rate_api = float(r.json()["USDBRL"]["bid"])
    except Exception:
        pass
    return {
        **settings,
        "usd_rate_api": rate_api,
        "brl_tax": float(os.getenv("META_ACCOUNT_BRL_TAX", "1.1383")),
        "usd_spread_pct": float(os.getenv("META_ACCOUNT_USD_SPREAD", "0.05")) * 100,
    }

@router.post("/settings")
async def update_settings(body: SettingsIn):
    settings = load_settings()
    if body.usd_rate_manual is not None:
        settings["usd_rate_manual"] = body.usd_rate_manual
    settings["use_manual_rate"] = body.use_manual_rate
    save_settings(settings)
    return {"ok": True, "settings": settings}

@router.get("/status")
async def status():
    if not ACCESS_TOKEN:
        return {"connected": False, "message": "Token não configurado"}
    results = {}
    async with httpx.AsyncClient(timeout=15) as client:
        for key, acc in ACCOUNTS.items():
            r = await client.get(f"{BASE}/{acc['id']}", params={"access_token": ACCESS_TOKEN, "fields": "name,currency,account_status"})
            if r.status_code == 200:
                d = r.json()
                results[key] = {"connected": True, "label": acc["label"], "account_name": d.get("name"), "currency": d.get("currency")}
            else:
                results[key] = {"connected": False, "label": acc["label"], "message": r.json().get("error", {}).get("message")}
    return results

@router.get("/overview")
async def overview(days: int = Query(30)):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    until = datetime.now().strftime("%Y-%m-%d")
    usd_rate = await get_usd_brl_rate()
    totals = {"spend_brl": 0.0, "spend_usd_original": 0.0, "impressions": 0, "clicks": 0, "reach": 0, "purchases": 0, "revenue_brl": 0.0, "accounts": {}}

    for key, acc in ACCOUNTS.items():
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{BASE}/{acc['id']}/insights", params={"access_token": ACCESS_TOKEN, "time_range": f'{{"since":"{since}","until":"{until}"}}', "fields": "spend,impressions,clicks,ctr,cpc,reach,actions,action_values", "level": "account"})
        d = r.json().get("data", [{}])[0] if r.status_code == 200 else {}
        spend_raw = float(d.get("spend", 0))
        purchases = _actions_val(d.get("actions", []), "purchase")
        revenue_raw = _actions_val(d.get("action_values", []), "purchase")
        if key == "brl":
            spend_brl = round(spend_raw * acc["tax"], 2)
            revenue_brl = round(revenue_raw * acc["tax"], 2)
        else:
            totals["spend_usd_original"] += spend_raw
            spend_brl = round(spend_raw * usd_rate, 2)
            revenue_brl = round(revenue_raw * usd_rate, 2)
        totals["spend_brl"] += spend_brl
        totals["impressions"] += int(d.get("impressions", 0))
        totals["clicks"] += int(d.get("clicks", 0))
        totals["reach"] += int(d.get("reach", 0))
        totals["purchases"] += int(purchases)
        totals["revenue_brl"] += revenue_brl
        totals["accounts"][key] = {"label": acc["label"], "currency": acc["currency"], "spend_original": round(spend_raw, 2), "spend_brl": spend_brl, "impressions": int(d.get("impressions", 0)), "clicks": int(d.get("clicks", 0)), "purchases": int(purchases), "revenue_brl": revenue_brl, "ctr": round(float(d.get("ctr", 0)), 4), "cpc_original": round(float(d.get("cpc", 0)), 2)}

    spend_total = totals["spend_brl"]
    revenue_total = totals["revenue_brl"]
    roas = round(revenue_total / spend_total, 2) if spend_total > 0 else 0
    return {"period_days": days, "usd_rate_used": usd_rate, "spend_brl": round(totals["spend_brl"], 2), "spend_usd_original": round(totals["spend_usd_original"], 2), "impressions": totals["impressions"], "clicks": totals["clicks"], "reach": totals["reach"], "purchases": totals["purchases"], "revenue_brl": round(totals["revenue_brl"], 2), "roas": roas, "ctr": round(totals["clicks"] / totals["impressions"] * 100, 2) if totals["impressions"] > 0 else 0, "accounts": totals["accounts"]}

@router.get("/spend-by-day")
async def spend_by_day(days: int = Query(30)):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    until = datetime.now().strftime("%Y-%m-%d")
    usd_rate = await get_usd_brl_rate()
    day_map: dict = {}
    for key, acc in ACCOUNTS.items():
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{BASE}/{acc['id']}/insights", params={"access_token": ACCESS_TOKEN, "time_range": f'{{"since":"{since}","until":"{until}"}}', "fields": "spend,impressions,clicks", "time_increment": 1, "level": "account"})
        if r.status_code != 200:
            continue
        for row in r.json().get("data", []):
            date = row["date_start"]
            spend_raw = float(row.get("spend", 0))
            spend_brl = spend_raw * (acc["tax"] if key == "brl" else usd_rate)
            if date not in day_map:
                day_map[date] = {"date": date, "spend": 0.0, "impressions": 0, "clicks": 0}
            day_map[date]["spend"] += spend_brl
            day_map[date]["impressions"] += int(row.get("impressions", 0))
            day_map[date]["clicks"] += int(row.get("clicks", 0))
    result = sorted(day_map.values(), key=lambda x: x["date"])
    for r in result:
        r["spend"] = round(r["spend"], 2)
    return result

@router.get("/spend-by-date/{target_date}")
async def spend_by_date(target_date: str):
    """Retorna gasto por conta para uma data específica (YYYY-MM-DD).
    Valores iguais ao Meta Ads — sem multiplicadores de imposto ou spread."""

    # Cotação limpa (sem spread) para converter USD → BRL
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://economia.awesomeapi.com.br/last/USD-BRL")
            raw_usd_rate = float(r.json()["USDBRL"]["bid"])
    except Exception:
        settings = load_settings()
        raw_usd_rate = float(settings.get("usd_rate_manual") or 5.50)

    result = {"date": target_date, "usd_rate": raw_usd_rate, "accounts": {}, "total_brl": 0.0}

    async with httpx.AsyncClient(timeout=30) as client:
        for key, acc in ACCOUNTS.items():
            r = await client.get(
                f"{BASE}/{acc['id']}/insights",
                params={
                    "access_token": ACCESS_TOKEN,
                    "time_range": f'{{"since":"{target_date}","until":"{target_date}"}}',
                    "fields": "spend,impressions,clicks",
                    "level": "account",
                }
            )
            rows = r.json().get("data", []) if r.status_code == 200 else []
            d = rows[0] if rows else {}
            spend_raw = float(d.get("spend", 0))
            # BRL: valor Meta × 1.1383 (imposto)
            # USD: valor Meta × cotação × 1.05 (spread)
            if key == "brl":
                tax = float(os.getenv("META_ACCOUNT_BRL_TAX", "1.1383"))
                spend_brl = round(spend_raw * tax, 2)
            else:
                spread = 1 + acc.get("spread", 0.05)
                spend_brl = round(spend_raw * raw_usd_rate * spread, 2)
            result["accounts"][key] = {
                "label": acc["label"],
                "currency": acc["currency"],
                "spend_original": round(spend_raw, 2),
                "spend_brl": spend_brl,
            }
            result["total_brl"] += spend_brl

    result["total_brl"] = round(result["total_brl"], 2)
    return result


@router.get("/campaigns/summary")
async def campaigns_summary(days: int = Query(30)):
    import json as _json
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    until = datetime.now().strftime("%Y-%m-%d")
    time_range_str = _json.dumps({"since": since, "until": until})
    usd_rate = await get_usd_brl_rate()
    results = []
    async with httpx.AsyncClient(timeout=60) as client:
        for key, acc in ACCOUNTS.items():
            r = await client.get(
                f"{BASE}/{acc['id']}/campaigns",
                params={"access_token": ACCESS_TOKEN, "fields": "name,status,objective", "limit": 200}
            )
            if r.status_code != 200:
                continue
            campaigns = r.json().get("data", [])
            for camp in campaigns:
                ins = await client.get(
                    f"{BASE}/{camp['id']}/insights",
                    params={
                        "access_token": ACCESS_TOKEN,
                        "time_range": time_range_str,
                        "fields": "spend,impressions,clicks,ctr,cpc,reach,actions",
                        "limit": 1,
                    }
                )
                if ins.status_code != 200:
                    d = {}
                else:
                    d = (ins.json().get("data") or [{}])[0]
                spend_raw = float(d.get("spend", 0))
                if key == "brl":
                    spend_brl = spend_raw * acc["tax"]
                else:
                    spread = acc.get("spread", 0.05)
                    spend_brl = spend_raw * usd_rate * (1 + spread)
                results.append({
                    "id": camp["id"],
                    "name": camp["name"],
                    "status": camp["status"],
                    "objective": camp.get("objective"),
                    "account": acc["label"],
                    "currency_original": acc["currency"],
                    "spend_original": round(spend_raw, 2),
                    "spend_brl": round(spend_brl, 2),
                    "impressions": int(d.get("impressions", 0)),
                    "clicks": int(d.get("clicks", 0)),
                    "ctr": round(float(d.get("ctr", 0)), 4),
                    "cpc_original": round(float(d.get("cpc", 0)), 2),
                    "reach": int(d.get("reach", 0)),
                    "purchases": int(_actions_val(d.get("actions", []), "purchase")),
                })
    return sorted(results, key=lambda x: x["spend_brl"], reverse=True)

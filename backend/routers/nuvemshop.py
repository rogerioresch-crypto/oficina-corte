"""
NuvemShop Integration
Docs: https://tiendanube.github.io/api-documentation/
"""
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
import httpx
import os

router = APIRouter()

BASE_URL = "https://api.tiendanube.com/v1"
ACCESS_TOKEN = os.getenv("NUVEMSHOP_ACCESS_TOKEN")
USER_ID = os.getenv("NUVEMSHOP_USER_ID")
APP_ID = os.getenv("NUVEMSHOP_CLIENT_ID")


def get_headers():
    return {
        "Authentication": f"bearer {ACCESS_TOKEN}",
        "User-Agent": f"Analytics Pro ({APP_ID})",
        "Content-Type": "application/json",
    }


@router.get("/status")
async def status():
    """Verifica conexão com a NuvemShop"""
    if not ACCESS_TOKEN or not USER_ID:
        return {"connected": False, "message": "Credenciais não configuradas"}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/{USER_ID}/store", headers=get_headers())
        if r.status_code == 200:
            data = r.json()
            return {"connected": True, "store_name": data.get("name"), "plan": data.get("plan_name")}
        return {"connected": False, "message": r.text}


@router.get("/orders/summary")
async def orders_summary(
    days: int = Query(30, ge=1, le=365),
    since: str = Query(None),
    until: str = Query(None),
):
    """Resumo de pedidos — aceita ?days=N ou ?since=YYYY-MM-DD&until=YYYY-MM-DD"""
    if not ACCESS_TOKEN or not USER_ID:
        raise HTTPException(400, "NuvemShop não configurada")

    if since and until:
        since_date = since
        until_date = until
    else:
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        until_date = datetime.now().strftime("%Y-%m-%d")

    all_orders = []
    page = 1

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            r = await client.get(
                f"{BASE_URL}/{USER_ID}/orders",
                headers=get_headers(),
                params={"created_at_min": since_date, "created_at_max": until_date + "T23:59:59", "page": page, "per_page": 200},
            )
            if r.status_code == 404:
                break
            if r.status_code != 200:
                raise HTTPException(r.status_code, r.text)
            batch = r.json()
            if not batch:
                break
            all_orders.extend(batch)
            page += 1

    total_revenue = sum(float(o.get("total", 0)) for o in all_orders)
    paid_orders = [o for o in all_orders if o.get("payment_status") == "paid"]
    cancelled = [o for o in all_orders if o.get("status") == "cancelled"]

    return {
        "since": since_date,
        "until": until_date,
        "total_orders": len(all_orders),
        "paid_orders": len(paid_orders),
        "cancelled_orders": len(cancelled),
        "total_revenue": round(total_revenue, 2),
        "avg_ticket": round(total_revenue / len(paid_orders), 2) if paid_orders else 0,
    }


@router.get("/orders/by-day")
async def orders_by_day(days: int = Query(30, ge=7, le=365)):
    """Pedidos agrupados por dia"""
    if not ACCESS_TOKEN or not USER_ID:
        raise HTTPException(400, "NuvemShop não configurada")

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    all_orders = []
    page = 1

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            r = await client.get(
                f"{BASE_URL}/{USER_ID}/orders",
                headers=get_headers(),
                params={"created_at_min": since, "page": page, "per_page": 200},
            )
            if r.status_code == 404:
                break
            if r.status_code != 200:
                raise HTTPException(r.status_code, r.text)
            batch = r.json()
            if not batch:
                break
            all_orders.extend(batch)
            page += 1

    daily = {}
    for o in all_orders:
        day = o["created_at"][:10]
        if day not in daily:
            daily[day] = {"date": day, "orders": 0, "revenue": 0}
        daily[day]["orders"] += 1
        daily[day]["revenue"] += float(o.get("total", 0))

    result = sorted(daily.values(), key=lambda x: x["date"])
    for d in result:
        d["revenue"] = round(d["revenue"], 2)
    return result


@router.get("/products/top")
async def top_products(limit: int = Query(10, ge=1, le=50)):
    """Produtos mais vendidos"""
    if not ACCESS_TOKEN or not USER_ID:
        raise HTTPException(400, "NuvemShop não configurada")

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE_URL}/{USER_ID}/orders",
            headers=get_headers(),
            params={"per_page": 200, "fields": "products"},
        )
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text)
        orders = r.json()

    products: dict = {}
    for order in orders:
        for item in order.get("products", []):
            pid = item.get("product_id")
            name = item.get("name", "Produto")
            qty = item.get("quantity", 1)
            price = float(item.get("price", 0)) * qty
            if pid not in products:
                products[pid] = {"id": pid, "name": name, "quantity": 0, "revenue": 0}
            products[pid]["quantity"] += qty
            products[pid]["revenue"] += price

    top = sorted(products.values(), key=lambda x: x["revenue"], reverse=True)[:limit]
    for p in top:
        p["revenue"] = round(p["revenue"], 2)
    return top


@router.get("/customers/new")
async def new_customers(days: int = Query(30)):
    """Novos clientes no período"""
    if not ACCESS_TOKEN or not USER_ID:
        raise HTTPException(400, "NuvemShop não configurada")

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE_URL}/{USER_ID}/customers",
            headers=get_headers(),
            params={"created_at_min": since, "per_page": 200},
        )
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text)
    return {"new_customers": len(r.json()), "period_days": days}

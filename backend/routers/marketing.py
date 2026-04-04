"""
Marketing Dashboard — API Routes
- /api/marketing/daily        : lançamentos diários (GET lista, POST upsert)
- /api/marketing/daily/{date} : lançamento de um dia (GET, PUT, DELETE)
- /api/marketing/goals        : metas mensais (GET, POST/PUT)
- /api/marketing/dashboard    : KPIs consolidados do mês
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime, timedelta
import calendar
import shutil
import os
import glob

from database import get_db, init_db

router = APIRouter()
init_db()

# ─────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────

class DailyEntry(BaseModel):
    date: str                       # YYYY-MM-DD
    receita_captada: float = 0
    receita_plataforma: float = 0
    receita_whatsapp: float = 0
    invest_fb01: float = 0
    invest_fb02: float = 0
    invest_fb03: float = 0
    invest_google: float = 0
    sessoes_total: int = 0
    sessoes_midia: int = 0
    transacoes: int = 0
    receita_direct: float = 0
    receita_organic: float = 0
    receita_edrone: float = 0
    receita_cartstack: float = 0
    receita_social: float = 0
    receita_ig_shopping: float = 0
    receita_facebook: float = 0
    receita_google_ga4: float = 0
    custo_edrone: float = 0
    notas: str = ""


class MonthlyGoal(BaseModel):
    year_month: str                 # YYYY-MM
    meta_receita_captada: float = 0
    meta_receita_faturada: float = 0
    meta_investimento: float = 0
    meta_sessoes: int = 0
    meta_transacoes: int = 0
    meta_ticket_medio: float = 0
    meta_roas_captado: float = 0
    meta_roas_faturado: float = 0
    meta_cpa: float = 0


# ─────────────────────────────────────────────
#  HELPERS — KPI calculations
# ─────────────────────────────────────────────

def _calc_kpis(rows: list[dict]) -> dict:
    """Agrega linhas diárias e calcula todos os KPIs."""
    rc   = sum(r["receita_captada"]    for r in rows)
    rp   = sum(r["receita_plataforma"] for r in rows)
    rw   = sum(r["receita_whatsapp"]   for r in rows)
    fb1  = sum(r["invest_fb01"]        for r in rows)
    fb2  = sum(r.get("invest_fb02", 0) for r in rows)
    fb3  = sum(r["invest_fb03"]        for r in rows)
    gads = sum(r["invest_google"]      for r in rows)
    sess = sum(r["sessoes_total"]      for r in rows)
    smi  = sum(r["sessoes_midia"]      for r in rows)
    trx  = sum(r["transacoes"]         for r in rows)
    ced  = sum(r["custo_edrone"]       for r in rows)

    invest   = fb1 + fb2 + fb3 + gads + ced
    fat      = rp + rw                         # Receita Faturada total
    roas_cap = round(rc / invest, 4)   if invest else 0
    roas_fat = round(fat / invest, 4)  if invest else 0
    cpa      = round(invest / trx, 2)  if trx   else 0
    cps_g    = round(invest / sess, 2) if sess   else 0
    cps_m    = round(invest / smi, 2)  if smi    else 0
    conv     = round(trx / sess * 100, 4) if sess else 0
    ticket   = round(rc / trx, 2)     if trx   else 0
    aprov    = round(fat / rc * 100, 2) if rc   else 0
    pct_mid  = round(invest / fat * 100, 2) if fat else 0
    pct_smi  = round(smi / sess * 100, 2) if sess else 0

    return {
        "receita_captada":   round(rc, 2),
        "receita_plataforma": round(rp, 2),
        "receita_whatsapp":  round(rw, 2),
        "receita_faturada":  round(fat, 2),
        "invest_fb01":       round(fb1, 2),
        "invest_fb02":       round(fb2, 2),
        "invest_fb03":       round(fb3, 2),
        "invest_google":     round(gads, 2),
        "invest_total":      round(invest, 2),
        "custo_edrone":      round(ced, 2),
        "sessoes_total":     sess,
        "sessoes_midia":     smi,
        "transacoes":        trx,
        "roas_captado":      roas_cap,
        "roas_faturado":     roas_fat,
        "cpa":               cpa,
        "cps_geral":         cps_g,
        "cps_midia":         cps_m,
        "taxa_conversao":    conv,
        "ticket_medio":      ticket,
        "pct_aprovacao":     aprov,
        "pct_em_midia":      pct_mid,
        "pct_sessoes_midia": pct_smi,
        # Canais
        "canais": {
            "direct":      round(sum(r["receita_direct"]      for r in rows), 2),
            "organic":     round(sum(r["receita_organic"]     for r in rows), 2),
            "edrone":      round(sum(r["receita_edrone"]      for r in rows), 2),
            "cartstack":   round(sum(r["receita_cartstack"]   for r in rows), 2),
            "social":      round(sum(r["receita_social"]      for r in rows), 2),
            "ig_shopping": round(sum(r["receita_ig_shopping"] for r in rows), 2),
            "facebook":    round(sum(r["receita_facebook"]    for r in rows), 2),
            "google_ga4":  round(sum(r["receita_google_ga4"]  for r in rows), 2),
            "whatsapp":    round(rw, 2),
        },
    }


def _projection(kpis: dict, days_elapsed: int, days_in_month: int) -> dict:
    """Projeção linear para o mês completo."""
    if days_elapsed == 0:
        return {}
    factor = days_in_month / days_elapsed
    return {
        "receita_captada":  round(kpis["receita_captada"]  * factor, 2),
        "receita_faturada": round(kpis["receita_faturada"] * factor, 2),
        "invest_total":     round(kpis["invest_total"]     * factor, 2),
        "transacoes":       round(kpis["transacoes"]       * factor, 0),
    }


def _goal_pct(value: float, goal: float) -> float:
    return round(value / goal * 100, 2) if goal else 0


# ─────────────────────────────────────────────
#  DAILY ENTRIES
# ─────────────────────────────────────────────

@router.get("/daily")
def list_daily(year_month: str = Query(..., description="YYYY-MM")):
    """Lista todos os lançamentos do mês."""
    prefix = year_month + "-"
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_entries WHERE date LIKE ? ORDER BY date",
            (prefix + "%",)
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/daily")
def upsert_daily(entry: DailyEntry):
    """Cria ou atualiza um lançamento diário."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("""
            INSERT INTO daily_entries
                (date, receita_captada, receita_plataforma, receita_whatsapp,
                 invest_fb01, invest_fb02, invest_fb03, invest_google,
                 sessoes_total, sessoes_midia, transacoes,
                 receita_direct, receita_organic, receita_edrone,
                 receita_cartstack, receita_social, receita_ig_shopping,
                 receita_facebook, receita_google_ga4, custo_edrone, notas, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(date) DO UPDATE SET
                receita_captada=excluded.receita_captada,
                receita_plataforma=excluded.receita_plataforma,
                receita_whatsapp=excluded.receita_whatsapp,
                invest_fb01=excluded.invest_fb01,
                invest_fb02=excluded.invest_fb02,
                invest_fb03=excluded.invest_fb03,
                invest_google=excluded.invest_google,
                sessoes_total=excluded.sessoes_total,
                sessoes_midia=excluded.sessoes_midia,
                transacoes=excluded.transacoes,
                receita_direct=excluded.receita_direct,
                receita_organic=excluded.receita_organic,
                receita_edrone=excluded.receita_edrone,
                receita_cartstack=excluded.receita_cartstack,
                receita_social=excluded.receita_social,
                receita_ig_shopping=excluded.receita_ig_shopping,
                receita_facebook=excluded.receita_facebook,
                receita_google_ga4=excluded.receita_google_ga4,
                custo_edrone=excluded.custo_edrone,
                notas=excluded.notas,
                updated_at=excluded.updated_at
        """, (
            entry.date, entry.receita_captada, entry.receita_plataforma,
            entry.receita_whatsapp, entry.invest_fb01, entry.invest_fb02, entry.invest_fb03,
            entry.invest_google, entry.sessoes_total, entry.sessoes_midia,
            entry.transacoes, entry.receita_direct, entry.receita_organic,
            entry.receita_edrone, entry.receita_cartstack, entry.receita_social,
            entry.receita_ig_shopping, entry.receita_facebook, entry.receita_google_ga4,
            entry.custo_edrone, entry.notas, now,
        ))
    return {"ok": True, "date": entry.date}


@router.get("/daily/{entry_date}")
def get_daily(entry_date: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM daily_entries WHERE date = ?", (entry_date,)
        ).fetchone()
    if not row:
        return {}
    return dict(row)


@router.delete("/daily/{entry_date}")
def delete_daily(entry_date: str):
    with get_db() as conn:
        conn.execute("DELETE FROM daily_entries WHERE date = ?", (entry_date,))
    return {"ok": True}


# ─────────────────────────────────────────────
#  MONTHLY GOALS
# ─────────────────────────────────────────────

@router.get("/goals/{year_month}")
def get_goals(year_month: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM monthly_goals WHERE year_month = ?", (year_month,)
        ).fetchone()
    return dict(row) if row else {"year_month": year_month}


@router.post("/goals")
def upsert_goals(goal: MonthlyGoal):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("""
            INSERT INTO monthly_goals
                (year_month, meta_receita_captada, meta_receita_faturada,
                 meta_investimento, meta_sessoes, meta_transacoes,
                 meta_ticket_medio, meta_roas_captado, meta_roas_faturado,
                 meta_cpa, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(year_month) DO UPDATE SET
                meta_receita_captada=excluded.meta_receita_captada,
                meta_receita_faturada=excluded.meta_receita_faturada,
                meta_investimento=excluded.meta_investimento,
                meta_sessoes=excluded.meta_sessoes,
                meta_transacoes=excluded.meta_transacoes,
                meta_ticket_medio=excluded.meta_ticket_medio,
                meta_roas_captado=excluded.meta_roas_captado,
                meta_roas_faturado=excluded.meta_roas_faturado,
                meta_cpa=excluded.meta_cpa,
                updated_at=excluded.updated_at
        """, (
            goal.year_month, goal.meta_receita_captada, goal.meta_receita_faturada,
            goal.meta_investimento, goal.meta_sessoes, goal.meta_transacoes,
            goal.meta_ticket_medio, goal.meta_roas_captado, goal.meta_roas_faturado,
            goal.meta_cpa, now,
        ))
    return {"ok": True, "year_month": goal.year_month}


# ─────────────────────────────────────────────
#  DASHBOARD — KPIs consolidados
# ─────────────────────────────────────────────

@router.get("/dashboard/{year_month}")
def dashboard(year_month: str):
    """
    Retorna KPIs do mês: realizado, projeção e % de atingimento de meta.
    """
    today = date.today()
    y, m  = map(int, year_month.split("-"))
    days_in_month = calendar.monthrange(y, m)[1]

    # Dias com lançamentos até hoje (ou até o último dia do mês se for mês passado)
    last_day = date(y, m, days_in_month)
    ref_day  = min(today, last_day)
    days_elapsed = ref_day.day if (today.year == y and today.month == m) else days_in_month

    prefix = year_month + "-"
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_entries WHERE date LIKE ? ORDER BY date",
            (prefix + "%",)
        ).fetchall()
        goal_row = conn.execute(
            "SELECT * FROM monthly_goals WHERE year_month = ?", (year_month,)
        ).fetchone()

    rows = [dict(r) for r in rows]
    kpis = _calc_kpis(rows) if rows else _calc_kpis([])
    proj = _projection(kpis, days_elapsed, days_in_month)
    goal = dict(goal_row) if goal_row else {}

    # % atingimento
    ating = {
        "receita_captada":  _goal_pct(kpis["receita_captada"],  goal.get("meta_receita_faturada") or goal.get("meta_receita_captada", 0)),
        "receita_faturada": _goal_pct(kpis["receita_faturada"], goal.get("meta_receita_faturada", 0)),
        "invest_total":     _goal_pct(kpis["invest_total"],     goal.get("meta_investimento", 0)),
        "transacoes":       _goal_pct(kpis["transacoes"],       goal.get("meta_transacoes", 0)),
    }

    # % projeção vs meta
    proj_ating = {
        "receita_captada":  _goal_pct(proj.get("receita_captada", 0),  goal.get("meta_receita_captada", 0)),
        "receita_faturada": _goal_pct(proj.get("receita_faturada", 0), goal.get("meta_receita_faturada", 0)),
    }

    return {
        "year_month":    year_month,
        "days_in_month": days_in_month,
        "days_elapsed":  days_elapsed,
        "days_remaining": days_in_month - days_elapsed,
        "kpis":          kpis,
        "projection":    proj,
        "goal":          goal,
        "atingimento":   ating,
        "proj_ating":    proj_ating,
        "daily":         rows,
    }


# ─────────────────────────────────────────────
#  BACKUP
# ─────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "marketing.db")
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "backups")

@router.post("/backup")
def create_backup():
    """Cria um backup do banco com timestamp."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"marketing_{ts}.db")
    shutil.copy2(DB_PATH, dest)
    # Mantém apenas os 10 backups mais recentes
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "marketing_*.db")))
    for old in backups[:-10]:
        os.remove(old)
    return {"ok": True, "arquivo": f"marketing_{ts}.db", "total_backups": min(len(backups), 10)}

@router.get("/backup/list")
def list_backups():
    """Lista backups disponíveis."""
    if not os.path.exists(BACKUP_DIR):
        return []
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "marketing_*.db")), reverse=True)
    return [{"arquivo": os.path.basename(b), "tamanho_kb": round(os.path.getsize(b)/1024, 1)} for b in backups]


# ─────────────────────────────────────────────
#  RESUMO HISTÓRICO (últimos N meses)
# ─────────────────────────────────────────────

@router.get("/history")
def history(months: int = Query(6, ge=1, le=24)):
    today = date.today()
    result = []
    for i in range(months - 1, -1, -1):
        # mês i meses atrás
        first = date(today.year, today.month, 1) - timedelta(days=i * 28)
        ym = first.strftime("%Y-%m")
        prefix = ym + "-"
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_entries WHERE date LIKE ?", (prefix + "%",)
            ).fetchall()
        rows = [dict(r) for r in rows]
        k = _calc_kpis(rows) if rows else {"receita_captada": 0, "receita_faturada": 0, "invest_total": 0, "roas_captado": 0, "roas_faturado": 0, "cpa": 0, "transacoes": 0}
        result.append({"year_month": ym, **k})
    return result

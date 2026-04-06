"""
SQLite database — Marketing Dashboard
Tabelas: daily_entries, monthly_goals
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "marketing.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_db():
    conn = _conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS daily_entries (
                date                TEXT PRIMARY KEY,   -- YYYY-MM-DD
                receita_captada     REAL DEFAULT 0,     -- Analytics / manual
                receita_plataforma  REAL DEFAULT 0,     -- Nuvemshop
                receita_whatsapp    REAL DEFAULT 0,     -- Manual vendedoras
                invest_fb01         REAL DEFAULT 0,     -- FB Conta BRL
                invest_fb03         REAL DEFAULT 0,     -- FB Conta USD
                invest_google       REAL DEFAULT 0,     -- Google Ads
                sessoes_total       INTEGER DEFAULT 0,
                sessoes_midia       INTEGER DEFAULT 0,
                transacoes          INTEGER DEFAULT 0,
                receita_direct      REAL DEFAULT 0,
                receita_organic     REAL DEFAULT 0,
                receita_edrone      REAL DEFAULT 0,
                receita_cartstack   REAL DEFAULT 0,
                receita_social      REAL DEFAULT 0,
                receita_ig_shopping REAL DEFAULT 0,
                receita_facebook    REAL DEFAULT 0,
                receita_google_ga4  REAL DEFAULT 0,
                custo_edrone        REAL DEFAULT 0,     -- Custo disparo Edrone
                notas               TEXT DEFAULT '',
                updated_at          TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS monthly_goals (
                year_month              TEXT PRIMARY KEY,  -- YYYY-MM
                meta_receita_captada    REAL DEFAULT 0,
                meta_receita_faturada   REAL DEFAULT 0,
                meta_investimento       REAL DEFAULT 0,
                meta_sessoes            INTEGER DEFAULT 0,
                meta_transacoes         INTEGER DEFAULT 0,
                meta_ticket_medio       REAL DEFAULT 0,
                meta_roas_captado       REAL DEFAULT 0,
                meta_roas_faturado      REAL DEFAULT 0,
                meta_cpa                REAL DEFAULT 0,
                updated_at              TEXT DEFAULT (datetime('now','localtime'))
            );
        """)

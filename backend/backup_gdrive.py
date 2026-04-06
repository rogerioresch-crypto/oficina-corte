#!/usr/bin/env python3
"""
backup_gdrive.py — Faz backup do marketing.db para o Google Drive
Uso: python3 backup_gdrive.py
Agendamento: cron ou launchd (ver instruções no final)
"""

import os
import shutil
import datetime
import json
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ─── Configuração ──────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
DB_PATH        = BASE_DIR / "marketing.db"
CREDS_PATH     = BASE_DIR / "credentials.json"
BACKUP_DIR     = BASE_DIR / "backups"
GDRIVE_FOLDER  = "Marketing DB Backups"   # nome da pasta no Google Drive
MAX_LOCAL_BKPS = 10                        # quantos backups locais manter
MAX_DRIVE_BKPS = 30                        # quantos backups no Drive manter

SCOPES = ["https://www.googleapis.com/auth/drive"]

# ───────────────────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        str(CREDS_PATH), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)

def get_or_create_folder(service, folder_name):
    """Retorna o ID da pasta no Drive, criando se não existir."""
    q = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=q, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    # Cria a pasta
    meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    folder = service.files().create(body=meta, fields="id").execute()
    log(f"Pasta '{folder_name}' criada no Drive (id={folder['id']})")
    return folder["id"]

def make_local_backup():
    """Cria cópia local do .db com timestamp e limpa os antigos."""
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = BACKUP_DIR / f"marketing_{ts}.db"
    shutil.copy2(DB_PATH, dst)
    log(f"Backup local criado: {dst.name}")

    # Mantém apenas os N mais recentes
    backups = sorted(BACKUP_DIR.glob("marketing_*.db"))
    for old in backups[:-MAX_LOCAL_BKPS]:
        old.unlink()
        log(f"Backup local antigo removido: {old.name}")

    return dst

def upload_to_drive(service, local_file, folder_id):
    """Faz upload do arquivo para o Google Drive."""
    file_name = local_file.name
    media = MediaFileUpload(str(local_file), mimetype="application/octet-stream", resumable=True)
    meta = {"name": file_name, "parents": [folder_id]}
    uploaded = service.files().create(body=meta, media_body=media, fields="id,name,size").execute()
    size_kb = int(uploaded.get("size", 0)) // 1024
    log(f"Upload concluído: {uploaded['name']} ({size_kb} KB) → Drive")
    return uploaded["id"]

def cleanup_drive(service, folder_id):
    """Mantém apenas os N backups mais recentes no Drive."""
    q = f"'{folder_id}' in parents and name contains 'marketing_' and trashed=false"
    results = service.files().list(
        q=q, fields="files(id, name, createdTime)", orderBy="createdTime"
    ).execute()
    files = results.get("files", [])
    for old in files[:-MAX_DRIVE_BKPS]:
        service.files().delete(fileId=old["id"]).execute()
        log(f"Backup antigo removido do Drive: {old['name']}")

def main():
    log("═" * 50)
    log("Iniciando backup do marketing.db → Google Drive")

    if not DB_PATH.exists():
        log(f"ERRO: banco não encontrado em {DB_PATH}")
        return

    # 1. Backup local
    local_file = make_local_backup()

    # 2. Conecta no Drive
    log("Conectando ao Google Drive...")
    service = get_drive_service()

    # 3. Garante pasta no Drive
    folder_id = get_or_create_folder(service, GDRIVE_FOLDER)

    # 4. Upload
    upload_to_drive(service, local_file, folder_id)

    # 5. Limpa backups antigos do Drive
    cleanup_drive(service, folder_id)

    log("Backup concluído com sucesso!")
    log("═" * 50)

if __name__ == "__main__":
    main()

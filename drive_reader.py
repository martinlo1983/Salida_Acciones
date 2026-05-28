"""
drive_reader.py
---------------
Accede a Google Drive usando una Service Account y descarga los archivos
fuente del sistema.

Soporta dos tipos de archivo:
  - CSV/xlsx nativos: se descargan con get_media
  - Google Sheets: se exportan como xlsx via export_media
"""

import os
import io
import logging
import tempfile
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]

GSHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_EXPORT_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# ─── Nombres de archivo en Drive ─────────────────────────────────────────────
FILE_NAMES = {
    "rendimiento":   os.getenv("DRIVE_FILE_RENDIMIENTO",   "PP_Tenencia.csv"),
    "transacciones": os.getenv("DRIVE_FILE_TRANSACCIONES", "PP_Transacciones.csv"),
    "satelites":     os.getenv("DRIVE_FILE_SATELITES",     "ETFs_Satelites"),
    "acciones":      os.getenv("DRIVE_FILE_ACCIONES",      "Analizador_Acciones"),
    "monitor":       os.getenv("DRIVE_FILE_MONITOR",       "SALIDAS_MONITOR"),
}

DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")


class DriveClient:
    def __init__(self, service_account_json: str):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(service_account_json)
            sa_path = f.name

        creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
        self.service = build("drive", "v3", credentials=creds, cache_discovery=False)
        os.unlink(sa_path)
        logger.info("DriveClient inicializado correctamente.")

        # LOG DE DIAGNÓSTICO — lista todos los archivos visibles para la service account
        try:
            all_files = self.service.files().list(
                fields="files(id, name, mimeType)", pageSize=50
            ).execute().get("files", [])
            logger.info("Archivos visibles para la service account (%d):", len(all_files))
            for af in all_files:
                logger.info("  nombre='%s' | mime=%s", af["name"], af["mimeType"])
        except Exception as e:
            logger.warning("No se pudo listar archivos: %s", e)

    def _get_all_subfolder_ids(self, root_id: str) -> list[str]:
        all_ids = [root_id]
        queue = [root_id]
        while queue:
            parent = queue.pop()
            query = (
                f"'{parent}' in parents "
                f"and mimeType = 'application/vnd.google-apps.folder' "
                f"and trashed = false"
            )
            result = (
                self.service.files()
                .list(q=query, fields="files(id, name)", pageSize=100)
                .execute()
            )
            for folder in result.get("files", []):
                all_ids.append(folder["id"])
                queue.append(folder["id"])
        return all_ids

    def _find_file(self, name: str) -> Optional[dict]:
        """Retorna dict con {id, mimeType} o None si no encuentra."""
        if DRIVE_FOLDER_ID:
            folder_ids = self._get_all_subfolder_ids(DRIVE_FOLDER_ID)
            parents_clause = " or ".join(f"'{fid}' in parents" for fid in folder_ids)
            query = f"name = '{name}' and trashed = false and ({parents_clause})"
        else:
            query = f"name = '{name}' and trashed = false"

        result = (
            self.service.files()
            .list(q=query, fields="files(id, name, mimeType)", pageSize=5)
            .execute()
        )
        files = result.get("files", [])
        logger.info("Buscando '%s' — encontrados: %s", name, [(f["name"], f["mimeType"]) for f in files])
        if not files:
            return None
        if len(files) > 1:
            logger.warning("Múltiples archivos '%s' en Drive — usando el primero.", name)
        return files[0]

    def download(self, key: str) -> bytes:
        """
        Descarga un archivo por su clave lógica.
        Si es un Google Sheet, lo exporta como xlsx automáticamente.
        """
        name = FILE_NAMES[key]
        file_info = self._find_file(name)
        if not file_info:
            raise FileNotFoundError(
                f"Archivo '{name}' no encontrado en Drive. "
                f"Verificá que esté compartido con la service account."
            )

        buffer = io.BytesIO()
        file_id = file_info["id"]
        mime = file_info.get("mimeType", "")

        if mime == GSHEET_MIME:
            # Google Sheet → exportar como xlsx
            request = self.service.files().export_media(
                fileId=file_id, mimeType=XLSX_EXPORT_MIME
            )
            logger.info("Exportando Google Sheet '%s' como xlsx...", name)
        else:
            # Archivo nativo (csv, xlsx, etc.)
            request = self.service.files().get_media(fileId=file_id)

        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        logger.info("Descargado: %s (%d bytes)", name, buffer.tell())
        return buffer.getvalue()

    def upload_or_update(self, key: str, data: bytes, mime_type: str) -> str:
        name = FILE_NAMES[key]
        file_info = self._find_file(name)
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=True)

        if file_info:
            self.service.files().update(
                fileId=file_info["id"], media_body=media
            ).execute()
            logger.info("Actualizado en Drive: %s", name)
            return file_info["id"]
        else:
            raise FileNotFoundError(
                f"Archivo '{name}' no encontrado en Drive para actualizar. "
                f"Crealo manualmente en tu Drive, compartilo con la service account "
                f"con permiso de Editor, y volvé a correr."
            )

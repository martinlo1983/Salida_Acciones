"""
drive_reader.py
---------------
Accede a Google Drive usando una Service Account y descarga los archivos
fuente del sistema. Devuelve los bytes crudos para que cada módulo los
parsee independientemente.

Archivos esperados en Drive (configurables vía variables de entorno):
  - PP_Balance_de_activos.csv
  - PP_Valores_y_rendimiento_Rendimiento_de_los_activos.csv
  - Todas_las_transacciones.csv
  - ETFs_Satelites.xlsx
  - Analizador_Acciones.xlsx
  - SALIDAS_MONITOR.xlsx  (output — se crea si no existe)
"""

import os
import io
import logging
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
]

# ─── Nombres de archivo (override con env vars si querés renombrarlos) ────────
FILE_NAMES = {
    "rendimiento":   os.getenv("DRIVE_FILE_RENDIMIENTO",   "PP_Tenencia.csv"),
    "transacciones": os.getenv("DRIVE_FILE_TRANSACCIONES", "PP_Transacciones.csv"),
    "satelites":     os.getenv("DRIVE_FILE_SATELITES",     "ETFs_Satelites.xlsx"),
    "acciones":      os.getenv("DRIVE_FILE_ACCIONES",      "Analizador_Acciones.xlsx"),
    "monitor":       os.getenv("DRIVE_FILE_MONITOR",       "SALIDAS_MONITOR.xlsx"),
}

# ID de carpeta de Drive (opcional — si se deja vacío busca en todo Drive)
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")


class DriveClient:
    def __init__(self, service_account_json: str):
        """
        service_account_json: contenido JSON de la service account
                              (viene del secret GOOGLE_SA_JSON en Actions)
        """
        import json
        import tempfile

        # Escribir JSON a archivo temporal que google-auth pueda leer
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(service_account_json)
            sa_path = f.name

        creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
        self.service = build("drive", "v3", credentials=creds, cache_discovery=False)
        os.unlink(sa_path)
        logger.info("DriveClient inicializado correctamente.")

    def _get_all_subfolder_ids(self, root_id: str) -> list[str]:
        """
        Devuelve el root_id más todos los IDs de subcarpetas (recursivo).
        Necesario porque Drive no tiene búsqueda nativa de árbol completo.
        """
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

    def _find_file_id(self, name: str) -> Optional[str]:
        """
        Busca el file ID por nombre dentro de la carpeta raíz y todas sus
        subcarpetas. Si no hay carpeta raíz configurada, busca en todo Drive.
        """
        if DRIVE_FOLDER_ID:
            # Construir lista de todos los IDs de carpeta del árbol
            folder_ids = self._get_all_subfolder_ids(DRIVE_FOLDER_ID)
            # La API admite hasta ~100 condiciones OR — en la práctica más que suficiente
            parents_clause = " or ".join(f"'{fid}' in parents" for fid in folder_ids)
            query = f"name = '{name}' and trashed = false and ({parents_clause})"
        else:
            query = f"name = '{name}' and trashed = false"

        result = (
            self.service.files()
            .list(q=query, fields="files(id, name, parents)", pageSize=5)
            .execute()
        )
        files = result.get("files", [])
        if not files:
            return None
        if len(files) > 1:
            logger.warning(
                "Múltiples archivos con nombre '%s' en Drive — usando el primero.", name
            )
        return files[0]["id"]

    def download(self, key: str) -> bytes:
        """Descarga un archivo por su clave lógica (ver FILE_NAMES)."""
        name = FILE_NAMES[key]
        file_id = self._find_file_id(name)
        if not file_id:
            raise FileNotFoundError(
                f"Archivo '{name}' no encontrado en Drive. "
                f"Verificá que esté compartido con la service account."
            )
        buffer = io.BytesIO()
        request = self.service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        logger.info("Descargado: %s (%d bytes)", name, buffer.tell())
        return buffer.getvalue()

    def upload_or_update(self, key: str, data: bytes, mime_type: str) -> str:
        """
        Sube o actualiza un archivo en Drive.
        Si ya existe (por nombre), lo sobreescribe. Si no, lo crea.
        Retorna el file ID resultante.
        """
        name = FILE_NAMES[key]
        file_id = self._find_file_id(name)
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=True)

        if file_id:
            self.service.files().update(fileId=file_id, media_body=media).execute()
            logger.info("Actualizado en Drive: %s", name)
            return file_id
        else:
            metadata = {"name": name}
            if DRIVE_FOLDER_ID:
                metadata["parents"] = [DRIVE_FOLDER_ID]
            result = (
                self.service.files()
                .create(body=metadata, media_body=media, fields="id")
                .execute()
            )
            new_id = result["id"]
            logger.info("Creado en Drive: %s (id=%s)", name, new_id)
            return new_id

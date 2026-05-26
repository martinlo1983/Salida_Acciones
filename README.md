# Monitor de Salidas — Satélites y Tácticos

Sistema automático que evalúa mensualmente si hay que realizar acciones
sobre las posiciones de largo plazo, reproduciendo las reglas del documento
**Reglas de Salida — Satélites y Tácticos (v1.0)**.

---

## Estructura del repositorio

```
salidas_monitor/
├── scripts/
│   ├── main.py               ← Orquestador principal
│   ├── tenencia.py           ← Lee CSV de PP + transacciones → posiciones activas
│   ├── drive_reader.py       ← Acceso a Google Drive (service account)
│   ├── market_data.py        ← Precios, máximos y volatilidad (yfinance)
│   ├── reglas_satelites.py   ← S1 trailing stop / S2 rotación / S3 parking
│   └── reglas_tacticos.py    ← T1 stop fijo / T2 trailing / T3 TIR / T4 modelo
├── .github/workflows/
│   └── monitor.yml           ← GitHub Actions (día 1 de cada mes + manual)
├── requirements.txt
└── README.md
```

---

## Archivos en Google Drive

El script espera encontrar estos archivos en Drive (compartidos con la service account):

| Clave interna    | Nombre de archivo por defecto                                         | Origen          |
|------------------|-----------------------------------------------------------------------|-----------------|
| `balance`        | `PP_Balance_de_activos.csv`                                           | Portfolio Performance — exportar mensualmente |
| `rendimiento`    | `PP_Valores_y_rendimiento_Rendimiento_de_los_activos.csv`             | Portfolio Performance — exportar mensualmente |
| `transacciones`  | `Todas_las_transacciones.csv`                                         | Portfolio Performance — exportar mensualmente |
| `satelites`      | `ETFs_Satelites.xlsx`                                                 | Tu sistema de ranking — se actualiza automáticamente |
| `acciones`       | `Analizador_Acciones.xlsx`                                            | Tu analizador de acciones — se actualiza automáticamente |
| `monitor`        | `SALIDAS_MONITOR.xlsx`                                                | **Output** — creado/actualizado por este script |

Si querés cambiar algún nombre de archivo, usá variables de entorno:
```
DRIVE_FILE_BALANCE=MiArchivo_Balance.csv
DRIVE_FILE_SATELITES=Ranking_ETFs.xlsx
# etc.
```

---

## Setup — paso a paso

### 1. Crear Service Account en Google Cloud

1. Ir a [Google Cloud Console](https://console.cloud.google.com/)
2. Crear un proyecto (o usar uno existente)
3. Habilitar la **Google Drive API**
4. Crear una **Service Account** → descargar el JSON de credenciales
5. Copiar el email de la service account (termina en `@...gserviceaccount.com`)

### 2. Compartir archivos de Drive con la Service Account

En Google Drive, compartir cada uno de los 5 archivos fuente con el email
de la service account, con permiso de **Lectura** (viewer). Para el archivo
output `SALIDAS_MONITOR.xlsx` dar permiso de **Escritura** (editor), o
simplemente compartir la carpeta entera con Editor.

### 3. Configurar Secrets en GitHub

En el repositorio → Settings → Secrets and variables → Actions:

| Secret            | Valor                                                    |
|-------------------|----------------------------------------------------------|
| `GOOGLE_SA_JSON`  | Contenido completo del JSON de la service account        |
| `DRIVE_FOLDER_ID` | (Opcional) ID de la carpeta de Drive donde están los archivos. Se obtiene de la URL: `drive.google.com/drive/folders/ESTE_ID` |

### 4. TIR objetivo por acción (opcional)

En `scripts/main.py`, completar el dict `TIR_OBJETIVO` con los tickers
donde querés activar T3:

```python
TIR_OBJETIVO = {
    "ORCL": 25,   # 25% TIR anual objetivo
    "ADBE": 30,
    "OXY":  20,
}
```

---

## Lógica de fecha de primera compra

El script lee `Todas_las_transacciones.csv` y aplica esta regla:

> Si la posición llegó en algún momento a 0 unidades (o fue vendida totalmente),
> la fecha de entrada válida es la **primera compra posterior** a esa salida.

Esto garantiza que los stops y el máximo se calculan desde la **entrada actual**,
no desde compras anteriores en posiciones que fueron liquidadas y reabiertas.

---

## Output — SALIDAS_MONITOR.xlsx

Dos hojas:

**ESTADO_ACTUAL** — Snapshot de la corrida más reciente, coloreado por alerta:
- 🟢 Verde → MANTENER
- 🟡 Amarillo → VIGILAR
- 🟠 Naranja → acción próxima (TIR objetivo alcanzada, Euforia)
- 🔴 Rojo → acción inmediata requerida

**HISTORIAL** — Todas las corridas anteriores acumuladas (una fila por posición por fecha).

---

## Ejecución manual

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar credenciales
export GOOGLE_SA_JSON='{"type":"service_account",...}'
export DRIVE_FOLDER_ID='1aBcDeFgHiJkLmNoPqRsTuV'   # opcional

# Correr
cd scripts
python main.py
```

---

## Frecuencia de actualización

| Qué           | Cuándo actualizar          | Cómo                                    |
|---------------|----------------------------|-----------------------------------------|
| CSVs de PP    | Mensualmente (antes del día 1) | Exportar desde Portfolio Performance y reemplazar en Drive |
| ETFs_Satelites.xlsx | Automático (ya corre mensual) | Tu script de ranking ya lo actualiza |
| Analizador_Acciones.xlsx | Automático | Tu script de acciones ya lo actualiza |
| TIR_OBJETIVO  | Cuando entrás a una posición nueva con objetivo | Editar `main.py` |

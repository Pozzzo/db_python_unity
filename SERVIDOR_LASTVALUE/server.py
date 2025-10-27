# server.py
import os
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# ======================
# Configuración de la BD
# ======================
DB_NAME = "last_value.sqlite"
HERE = Path(__file__).parent

# Detecta BD junto al server.py o en ../DB/last_value.sqlite (estructura previa)
CANDIDATES = [HERE / DB_NAME, HERE.parent / "DB" / DB_NAME]
DB_PATH = next((p for p in CANDIDATES if p.exists()), CANDIDATES[0])

# Permite sobreescribir por variable de entorno (opcional)
env_db = os.getenv("LASTVALUE_DB")
if env_db:
    p = Path(env_db)
    DB_PATH = p if p.is_absolute() else (HERE / p)

# ======================
# Mapeos y orden
# ======================
SCHULERS: Dict[str, int] = {
    "Schuler1": 982,
    "Schuler2": 1028,
    "Schuler3": 1029,
    "Schuler4": 810,
    "Schuler5": 1030,
}

# Orden de el_id (arriba → abajo)
EL_IDS: List[int] = [69, 48, 116, 154, 152, 153, 52, 54, 160, 137, 50]

# Etiquetas que quieres ver en la primera columna
DPELEMENT_BY_EL: Dict[int, str] = {
    69:  "Barras.VelocidadAcunado.Valor",
    48:  "DatosGen.ModoTrabajo.Led",
    116: "DatosGen.ModoTrabajo.Modo",
    154: "DatosGen.Denominacion",
    152: "DatosGen.OT",
    153: "DatosGen.Operador",
    52:  "Tendencia.Avance",
    54:  "OEE.Rendimiento",
    160: "Tendencia.MetaActual",
    137: "TiempoMuerto",
    50:  "Tendencia.Programado",
}

# ======================
# FastAPI app
# ======================
app = FastAPI(title="Schuler Dashboard", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sirve archivos estáticos desde la carpeta del proyecto (HTML/JS/CSS/imagenes)
app.mount("/static", StaticFiles(directory=str(HERE), html=True), name="static")

# ======================
# SQLite helpers
# ======================
def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(500, f"No se encontró la BD en: {DB_PATH}")
    con = sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro&cache=shared",
        uri=True,
        check_same_thread=False,
        timeout=10.0,
    )
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON;")
    return con

SQL_LAST = """
SELECT
  dp_id, el_id,
  CAST(value AS TEXT) AS value,
  strftime('%Y-%m-%d %H:%M:%S', system_time/1000000000, 'unixepoch','localtime') AS system_time
FROM last_value
WHERE dp_id = ? AND el_id = ?
ORDER BY system_time DESC
LIMIT 1
"""

def fetch_last(con: sqlite3.Connection, dp_id: int, el_id: int) -> Optional[Dict[str, Any]]:
    row = con.execute(SQL_LAST, (dp_id, el_id)).fetchone()
    return dict(row) if row else None

def build_rows() -> List[Dict[str, Any]]:
    """
    Devuelve filas estilo Excel:
    Schuler | DP | DPELEMENT | EL_ID | Valor | FechaHora
    """
    con = get_conn()
    try:
        rows: List[Dict[str, Any]] = []
        for sch_name, dp in SCHULERS.items():
            for el in EL_IDS:
                etiqueta = DPELEMENT_BY_EL.get(el, f"el_{el}")
                r = fetch_last(con, dp, el)
                rows.append({
                    "Schuler": sch_name,
                    "DP": dp,
                    "DPELEMENT": etiqueta,
                    "EL_ID": el,
                    "Valor": (r["value"] if r else None),
                    "FechaHora": (r["system_time"] if r else None),
                })
        return rows
    finally:
        con.close()

# ======================
# Rutas HTML / API
# ======================

@app.get("/health")
def health():
    return {"db_path": str(DB_PATH), "db_exists": DB_PATH.exists()}

# Raíz: intenta servir un HTML local; si no existe, redirige al dashboard
@app.get("/", response_class=HTMLResponse)
def root():
    index = HERE / "index.html"
    if index.exists():
        return FileResponse(str(index))
    # si no hay archivo, redirige al dashboard renderizado por servidor
    return RedirectResponse(url="/_dashboard", status_code=307)

# Alias corto del dashboard HTML
@app.get("/_dashboard", response_class=HTMLResponse)
def dashboard_alias():
    return dashboard_schuler()

@app.get("/dashboard/schuler", response_class=HTMLResponse)
def dashboard_schuler():
    rows = build_rows()

    # Render HTML por secciones Schuler y filas en el orden de EL_IDS
    sections = []
    for sch in SCHULERS.keys():
        sec = [
            f"<h2>{sch} <small style='color:#666'>(dp_id {SCHULERS[sch]})</small></h2>",
            "<table><thead><tr>"
            "<th style='width:45%'>DPELEMENT</th>"
            "<th style='width:25%'>Valor</th>"
            "<th>FechaHora</th>"
            "</tr></thead><tbody>"
        ]
        for el in EL_IDS:
            r = next((x for x in rows if x["Schuler"] == sch and x["EL_ID"] == el), None)
            val = "" if not r or r["Valor"] is None else str(r["Valor"])
            ts  = "" if not r or r["FechaHora"] is None else r["FechaHora"]
            sec.append(
                f"<tr>"
                f"<td>{DPELEMENT_BY_EL.get(el, f'el_{el}')}</td>"
                f"<td>{val}</td>"
                f"<td>{ts}</td>"
                f"</tr>"
            )
        sec.append("</tbody></table>")
        sections.append("\n".join(sec))

    style = """
    <style>
      body{font-family:Segoe UI,Arial,sans-serif;margin:16px}
      table{border-collapse:collapse;width:100%;margin:12px 0}
      th,td{border:1px solid #e6e6e6;padding:8px}
      th{background:#f5f6f8;text-align:left}
      tr:nth-child(even){background:#fafafa}
      h2{margin:20px 0 6px}
    </style>
    """
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Dashboard Schuler</title>"
        f"{style}</head><body>"
        "<h1>Dashboard Schuler</h1>"
        f"{''.join(sections)}"
        "</body></html>"
    )
    return HTMLResponse(html)

@app.get("/api/schuler")
def api_schuler():
    rows = build_rows()
    # Agrupar por Schuler
    out: Dict[str, Any] = {}
    for sch, dp in SCHULERS.items():
        items = [r for r in rows if r["Schuler"] == sch]
        out[sch] = {"dp_id": dp, "items": items}
    return JSONResponse(out)

# Endpoint puntual por pareja (útil para pruebas)
@app.get("/value/{dp_id}/{el_id}")
def get_value_by_path(dp_id: int, el_id: int):
    con = get_conn()
    try:
        r = fetch_last(con, dp_id, el_id)
    finally:
        con.close()
    if not r:
        raise HTTPException(404, f"No hay valor para dp_id={dp_id} y el_id={el_id}")
    return r

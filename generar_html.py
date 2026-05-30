"""
generar_html.py
---------------
Genera el dashboard HTML de monitoreo de salidas.
Se llama desde main.py despues de calcular todos los resultados.
Recibe los datos en memoria (no lee Excel).
"""

import json
from datetime import datetime


TOOLTIPS = {
    "ticker": "Símbolo del subyacente en NYSE/NASDAQ",
    "categoria": "Largo Satelites (ETFs) o Largo Acciones (individuales)",
    "tipo_empresa": "Clasificación fundamental: GROWTH, VALUE, CÍCLICA, TURNAROUND, ESPECULATIVA",
    "tipo_ab": "A = convicción/promedia a la baja | B = oportunidad táctica con stop fijo",
    "cantidad": "Número de CEDEARs en cartera (Portfolio Performance)",
    "coste_compra_usd": "Costo total de compra en USD (Portfolio Performance)",
    "valor_mercado_usd": "Valor de mercado actual en USD (Portfolio Performance)",
    "ganancia_pct": "Ganancia % sobre el costo de compra, calculada desde PP en USD",
    "ppp_equiv_usd": "Precio de compra equivalente del subyacente = precio_actual_yfinance / (1 + ganancia%)",
    "fecha_primera_compra": "Fecha de la primera compra de la posición actual. Si hubo salida total y re-entrada, toma la re-entrada",
    "precio_actual_usd": "Último precio de cierre del subyacente en NYSE (yfinance)",
    "maximo_desde_entrada_usd": "Mayor precio de cierre del subyacente desde la fecha de primera compra",
    "sigma_mensual_12m": "Volatilidad mensual promedio últimos 12 meses (desvío estándar de retornos mensuales)",
    "grupo_satelite": "Grupo temático del ETF según ranking (Tecnología/Growth, Commodities, Índices amplios, etc.)",
    "rank_bruto": "Posición en el ranking de momentum considerando todos los ETFs del universo",
    "rank_efectivo": "Posición entre los ETFs que pasaron los filtros: Mom 3m > 0 y precio > MM200",
    "score_etf": "Score de momentum del ETF (combinación de Mom 12m y Mom 3m)",
    "score_top5": "Score promedio de los 5 primeros del ranking efectivo",
    "delta_momentum": "Diferencia relativa entre el score del ETF y el top 5. >20% en rank 6-10 dispara S2",
    "stop_s1_usd": "Nivel del trailing stop S1 = Máximo × (1 - k×σ). Si precio cae aquí → salir",
    "kxsigma": "Distancia porcentual del stop S1 al máximo (k × sigma mensual). Máx 25%",
    "s1_activado": "True si el precio actual cayó por debajo del stop S1",
    "s2_decision": "MANTENER / VIGILAR / ROTAR según posición en ranking efectivo y delta_momentum",
    "s3_activado": "True si el ETF cayó fuera del top 15 del ranking bruto → salida inmediata a parking",
    "stop_t1_usd": "Stop fijo desde PPP (solo Tipo B). = PPP × (1 - X%). Se activa antes de +10% de ganancia",
    "t1_activo": "True si el stop T1 está vigente (ganancia < 10% y es Tipo B)",
    "t1_activado": "True si el precio cayó por debajo del stop T1",
    "stop_t2_usd": "Trailing stop T2 = Máximo × (1 - Y%). Se activa cuando la ganancia supera el 10%",
    "t2_activo": "True si el trailing stop T2 está vigente (ganancia ≥ 10%)",
    "t2_activado": "True si el precio cayó por debajo del stop T2",
    "y_pct": "Distancia porcentual del trailing stop T2 al máximo. Varía según tipo y ganancia acumulada",
    "fase_modelo": "Fase del modelo táctico (del Analizador de Acciones): ACUMULACIÓN, EXPANSIÓN, EUFORIA, DETERIORO",
    "accion_modelo": "Acción sugerida por el modelo táctico",
    "flag_revision": "True si el modelo marcó revisión de tesis fundamental",
    "tamano_posicion_pct": "Tamaño de posición sugerido por el modelo táctico (%)",
    "t3_estado": "Estado de TIR objetivo (T3): si se definió un objetivo de retorno anual y si fue alcanzado",
    "alerta_emoji": "Semáforo: 🟢 Mantener | 🟡 Vigilar | 🟠 Acción próxima | 🔴 Acción inmediata",
    "alerta_texto": "Descripción de la alerta con el mecanismo disparado y los valores clave",
}


def _safe(v, decimals=2):
    if v is None or (isinstance(v, float) and v != v):
        return None
    if isinstance(v, float):
        return round(v, decimals)
    return v


def generar_html(resultados: list[dict], cambios: list[dict], historial: list[dict]) -> str:
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    rows_estado = []
    for r in resultados:
        rows_estado.append({k: _safe(v) for k, v in r.items()})

    _data_js = json.dumps({
        "estado": rows_estado,
        "cambios": [{k: _safe(v) for k, v in c.items()} for c in cambios],
        "historial": [{k: _safe(v) for k, v in h.items()} for h in historial],
        "tooltips": TOOLTIPS,
        "fecha": fecha,
    }, default=str, ensure_ascii=False)
    data_js = _data_js  # keep name for template

    _TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Monitor de Salidas</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0f1117;--bg2:#161922;--bg3:#1e2230;--bg4:#252a3a;
  --border:#2a3148;--border2:#3a4460;
  --text:#e8ecf4;--text2:#8892aa;--text3:#5a6480;
  --green:#22c55e;--green-bg:#0d2018;
  --yellow:#eab308;--yellow-bg:#1a1600;
  --orange:#f97316;--orange-bg:#1a0e00;
  --red:#ef4444;--red-bg:#1a0a0a;
  --blue:#60a5fa;--accent:#6366f1;
  --font-mono:'DM Mono',monospace;
  --font-head:'Syne',sans-serif;
}}
body{{background:var(--bg);color:var(--text);font-family:var(--font-mono);font-size:13px;line-height:1.5;min-height:100vh}}
.app{{display:flex;flex-direction:column;min-height:100vh}}

/* HEADER */
.header{{background:var(--bg2);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;justify-content:space-between}}
.header-title{{font-family:var(--font-head);font-size:18px;font-weight:700;letter-spacing:-0.5px}}
.header-meta{{font-size:11px;color:var(--text3)}}
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:500;letter-spacing:0.5px}}

/* TABS */
.tabs{{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 24px;display:flex;gap:0}}
.tab{{padding:12px 20px;cursor:pointer;font-family:var(--font-head);font-size:13px;color:var(--text2);border-bottom:2px solid transparent;transition:all 0.15s;user-select:none}}
.tab:hover{{color:var(--text)}}
.tab.active{{color:var(--accent);border-bottom-color:var(--accent)}}

/* CONTENT */
.content{{flex:1;padding:20px 24px;display:none}}
.content.active{{display:block}}

/* FILTERS */
.filters{{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;align-items:center}}
.filter-input{{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:6px 12px;border-radius:6px;font-family:var(--font-mono);font-size:12px;outline:none}}
.filter-input:focus{{border-color:var(--border2)}}
.filter-btn{{background:var(--bg3);border:1px solid var(--border);color:var(--text2);padding:6px 12px;border-radius:6px;cursor:pointer;font-family:var(--font-mono);font-size:12px;transition:all 0.1s}}
.filter-btn:hover,.filter-btn.active{{background:var(--bg4);border-color:var(--border2);color:var(--text)}}
.filter-label{{font-size:11px;color:var(--text3);margin-right:2px}}

/* TABLE */
.table-wrap{{overflow-x:auto;border-radius:8px;border:1px solid var(--border)}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
thead{{background:var(--bg3)}}
th{{padding:10px 12px;text-align:left;color:var(--text3);font-weight:500;white-space:nowrap;border-bottom:1px solid var(--border);position:relative;cursor:help}}
th .tip{{display:none;position:absolute;top:100%;left:0;z-index:100;background:#1e2a3a;border:1px solid var(--border2);border-radius:6px;padding:8px 12px;font-size:11px;color:var(--text2);width:240px;white-space:normal;line-height:1.5;pointer-events:none}}
th:hover .tip{{display:block}}
td{{padding:8px 12px;border-bottom:1px solid var(--border);white-space:nowrap;vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:var(--bg3)}}
.sortable{{cursor:pointer}}
.sortable:hover{{color:var(--text)}}

/* ALERT CELLS */
.a-green{{color:var(--green)}}
.a-yellow{{color:var(--yellow)}}
.a-orange{{color:var(--orange)}}
.a-red{{color:var(--red)}}
.row-green{{background:var(--green-bg)!important}}
.row-yellow{{background:var(--yellow-bg)!important}}
.row-orange{{background:var(--orange-bg)!important}}
.row-red{{background:var(--red-bg)!important}}

/* TICKER DETAIL */
.detail-wrap{{display:flex;gap:20px;flex-wrap:wrap}}
.ticker-list{{width:180px;flex-shrink:0;display:flex;flex-direction:column;gap:4px;max-height:calc(100vh - 200px);overflow-y:auto}}
.ticker-btn{{background:var(--bg3);border:1px solid var(--border);color:var(--text2);padding:8px 12px;border-radius:6px;cursor:pointer;text-align:left;font-family:var(--font-mono);font-size:12px;transition:all 0.1s;display:flex;justify-content:space-between;align-items:center}}
.ticker-btn:hover{{background:var(--bg4)}}
.ticker-btn.active{{background:var(--bg4);border-color:var(--accent);color:var(--text)}}
.detail-panel{{flex:1;min-width:0}}
.detail-header{{display:flex;align-items:baseline;gap:16px;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid var(--border)}}
.detail-ticker{{font-family:var(--font-head);font-size:32px;font-weight:700}}
.detail-cat{{font-size:12px;color:var(--text3);background:var(--bg3);padding:4px 10px;border-radius:4px;border:1px solid var(--border)}}
.detail-alert{{font-size:13px;padding:6px 14px;border-radius:6px;font-weight:500}}
.alert-green{{background:var(--green-bg);color:var(--green);border:1px solid #164430}}
.alert-yellow{{background:var(--yellow-bg);color:var(--yellow);border:1px solid #332a00}}
.alert-orange{{background:var(--orange-bg);color:var(--orange);border:1px solid #331e00}}
.alert-red{{background:var(--red-bg);color:var(--red);border:1px solid #331414}}

/* METRICS GRID */
.metrics-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px}}
.metric{{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:12px}}
.metric-label{{font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:0.5px}}
.metric-value{{font-size:18px;font-weight:500;color:var(--text)}}
.metric-value.pos{{color:var(--green)}}
.metric-value.neg{{color:var(--red)}}

/* CHART SECTION */
.chart-section{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px}}
.chart-title{{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px}}

/* PRICE CHART */
.price-chart{{position:relative;height:200px;display:flex;align-items:flex-end;gap:0;padding:0 8px}}
.price-bar-wrap{{display:flex;flex-direction:column;align-items:center;flex:1}}
.price-bar{{width:32px;border-radius:4px 4px 0 0;position:relative;transition:opacity 0.1s;cursor:default}}
.price-bar:hover{{opacity:0.8}}
.bar-label{{font-size:9px;color:var(--text3);margin-top:4px;text-align:center}}
.bar-value{{font-size:10px;color:var(--text2);margin-bottom:3px;text-align:center}}

/* STOP LEVELS */
.stops-wrap{{display:flex;flex-direction:column;gap:6px}}
.stop-row{{display:flex;align-items:center;gap:10px;padding:8px 12px;background:var(--bg3);border-radius:6px;border:1px solid var(--border)}}
.stop-name{{font-size:11px;color:var(--text3);width:80px;flex-shrink:0}}
.stop-bar-wrap{{flex:1;height:6px;background:var(--bg4);border-radius:3px;position:relative}}
.stop-bar{{height:100%;border-radius:3px;position:absolute;left:0}}
.stop-price{{font-size:12px;color:var(--text);width:70px;text-align:right}}
.stop-pct{{font-size:10px;width:52px;text-align:right}}
.stop-active{{color:var(--red);font-size:10px;margin-left:4px}}
.current-marker{{position:absolute;width:2px;background:var(--blue);height:14px;top:-4px;border-radius:1px}}

/* CAMBIOS */
.cambio-card{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:10px;display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:start}}
.cambio-ticker{{font-family:var(--font-head);font-size:20px;font-weight:700}}
.cambio-dir{{font-size:11px;padding:2px 8px;border-radius:4px}}
.dir-emp{{background:#2d1010;color:var(--red);border:1px solid #4a1f1f}}
.dir-mej{{background:var(--green-bg);color:var(--green);border:1px solid #164430}}
.cambio-fecha{{font-size:10px;color:var(--text3)}}
.cambio-detail{{grid-column:1/-1;display:flex;gap:12px;flex-wrap:wrap}}
.cambio-box{{flex:1;min-width:200px;padding:8px 12px;background:var(--bg3);border-radius:6px;border:1px solid var(--border)}}
.cambio-box-label{{font-size:9px;color:var(--text3);margin-bottom:3px;text-transform:uppercase}}
.cambio-box-text{{font-size:11px;color:var(--text2)}}

/* HISTORIAL */
.hist-count{{font-size:11px;color:var(--text3);margin-bottom:12px}}
.empty{{color:var(--text3);font-size:12px;padding:32px;text-align:center;border:1px solid var(--border);border-radius:8px}}
</style>
</head>
<body>
<div class="app">
<div class="header">
  <div class="header-title">Monitor de Salidas</div>
  <div class="header-meta">Actualizado: {fecha}</div>
</div>
<div class="tabs">
  <div class="tab active" onclick="switchTab('estado')">Estado actual</div>
  <div class="tab" onclick="switchTab('detalle')">Detalle por ticker</div>
  <div class="tab" onclick="switchTab('cambios')">Cambios</div>
  <div class="tab" onclick="switchTab('historial')">Historial</div>
</div>

<div id="tab-estado" class="content active">
  <div class="filters">
    <span class="filter-label">Buscar:</span>
    <input class="filter-input" id="search" placeholder="ticker o nombre..." oninput="renderEstado()" style="width:160px">
    <span class="filter-label">Categoría:</span>
    <button class="filter-btn active" onclick="setFilter('cat','all',this)">Todos</button>
    <button class="filter-btn" onclick="setFilter('cat','sat',this)">Satélites</button>
    <button class="filter-btn" onclick="setFilter('cat','acc',this)">Acciones</button>
    <span class="filter-label">Tipo:</span>
    <button class="filter-btn active" onclick="setFilter('tipo','all',this)">A+B</button>
    <button class="filter-btn" onclick="setFilter('tipo','A',this)">Tipo A</button>
    <button class="filter-btn" onclick="setFilter('tipo','B',this)">Tipo B</button>
    <span class="filter-label">Alerta:</span>
    <button class="filter-btn active" onclick="setFilter('alert','all',this)">Todas</button>
    <button class="filter-btn a-red" onclick="setFilter('alert','🔴',this)">🔴</button>
    <button class="filter-btn a-orange" onclick="setFilter('alert','🟠',this)">🟠</button>
    <button class="filter-btn a-yellow" onclick="setFilter('alert','🟡',this)">🟡</button>
    <button class="filter-btn a-green" onclick="setFilter('alert','🟢',this)">🟢</button>
  </div>
  <div class="table-wrap">
    <table id="estado-table">
      <thead id="estado-head"></thead>
      <tbody id="estado-body"></tbody>
    </table>
  </div>
</div>

<div id="tab-detalle" class="content">
  <div class="detail-wrap">
    <div class="ticker-list" id="ticker-list"></div>
    <div class="detail-panel" id="detail-panel">
      <div class="empty">Seleccioná un ticker para ver el detalle</div>
    </div>
  </div>
</div>

<div id="tab-cambios" class="content">
  <div id="cambios-list"></div>
</div>

<div id="tab-historial" class="content">
  <div class="filters">
    <span class="filter-label">Ticker:</span>
    <input class="filter-input" id="hist-search" placeholder="filtrar ticker..." oninput="renderHistorial()" style="width:130px">
  </div>
  <div class="hist-count" id="hist-count"></div>
  <div class="table-wrap">
    <table><thead id="hist-head"></thead><tbody id="hist-body"></tbody></table>
  </div>
</div>
</div>

<script>
const DATA = __DATA_PLACEHOLDER__;
const filters = {{cat:'all', tipo:'all', alert:'all'}};
let sortCol = null, sortDir = 1;

const COLS_SHOW = [
  'ticker','categoria','tipo_ab','tipo_empresa','ganancia_pct',
  'precio_actual_usd','ppp_equiv_usd','maximo_desde_entrada_usd',
  'stop_s1_usd','stop_t1_usd','stop_t2_usd',
  'rank_efectivo','s2_decision','fase_modelo',
  'alerta_emoji','alerta_texto'
];
const COLS_LABELS = {{
  ticker:'Ticker', categoria:'Categoría', tipo_ab:'Tipo', tipo_empresa:'Empresa',
  ganancia_pct:'Gan %', precio_actual_usd:'Precio', ppp_equiv_usd:'PPP equiv',
  maximo_desde_entrada_usd:'Máx entrada', stop_s1_usd:'Stop S1',
  stop_t1_usd:'Stop T1', stop_t2_usd:'Stop T2',
  rank_efectivo:'Rank ef.', s2_decision:'S2', fase_modelo:'Fase',
  alerta_emoji:'', alerta_texto:'Alerta'
}};

const EMOJI_CLASS = {{'🟢':'green','🟡':'yellow','🟠':'orange','🔴':'red'}};

function switchTab(id) {{
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', ['estado','detalle','cambios','historial'][i]===id));
  document.querySelectorAll('.content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  if(id==='detalle') renderDetalle();
  if(id==='cambios') renderCambios();
  if(id==='historial') renderHistorial();
}}

function setFilter(key, val, btn) {{
  filters[key] = val;
  btn.closest('.filters').querySelectorAll('.filter-btn').forEach(b => {{
    if(b.textContent === btn.textContent && b.onclick === btn.onclick) return;
  }});
  const group = ['all','sat','acc','A','B','🔴','🟠','🟡','🟢'];
  btn.parentElement.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderEstado();
}}

function fmt(col, val) {{
  if(val === null || val === undefined) return '<span style="color:#3a4460">—</span>';
  if(col === 'ganancia_pct') {{
    const cls = val >= 0 ? 'pos' : 'neg';
    return `<span class="${{cls}}">${{val >= 0?'+':''}}${{val.toFixed(1)}}%</span>`;
  }}
  if(['precio_actual_usd','ppp_equiv_usd','maximo_desde_entrada_usd','stop_s1_usd','stop_t1_usd','stop_t2_usd'].includes(col))
    return val ? '$'+val.toFixed(2) : '—';
  if(col === 'alerta_emoji') {{
    const cls = EMOJI_CLASS[val] || '';
    return `<span class="a-${{cls}}">${{val}}</span>`;
  }}
  if(col === 'rank_efectivo') return val !== null ? '#'+val : '—';
  if(typeof val === 'boolean') return val ? '<span style="color:var(--red)">SI</span>' : '<span style="color:var(--text3)">no</span>';
  return String(val);
}}

function filteredData() {{
  const q = (document.getElementById('search')?.value||'').toLowerCase();
  return DATA.estado.filter(r => {{
    if(q && !r.ticker?.toLowerCase().includes(q)) return false;
    if(filters.cat==='sat' && !r.categoria?.includes('Satelites')) return false;
    if(filters.cat==='acc' && !r.categoria?.includes('Acciones')) return false;
    if(filters.tipo!=='all' && r.tipo_ab !== filters.tipo) return false;
    if(filters.alert!=='all' && r.alerta_emoji !== filters.alert) return false;
    return true;
  }});
}}

function renderEstado() {{
  const head = document.getElementById('estado-head');
  const body = document.getElementById('estado-body');
  head.innerHTML = '<tr>' + COLS_SHOW.map(c => {{
    const tip = DATA.tooltips[c] || '';
    return `<th class="sortable" onclick="sortBy('${{c}}')">${{COLS_LABELS[c]||c}}<div class="tip">${{tip}}</div></th>`;
  }}).join('') + '</tr>';
  let rows = filteredData();
  if(sortCol) rows.sort((a,b) => {{
    const av = a[sortCol] ?? '', bv = b[sortCol] ?? '';
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  }});
  const emojiOrder = {{'🔴':0,'🟠':1,'🟡':2,'🟢':3}};
  if(!sortCol) rows.sort((a,b) => (emojiOrder[a.alerta_emoji]??9) - (emojiOrder[b.alerta_emoji]??9));
  body.innerHTML = rows.map(r => {{
    const ec = EMOJI_CLASS[r.alerta_emoji] || '';
    return `<tr class="row-${{ec}}">` + COLS_SHOW.map(c => `<td>${{fmt(c,r[c])}}</td>`).join('') + '</tr>';
  }}).join('');
}}

function sortBy(col) {{
  if(sortCol === col) sortDir *= -1; else {{ sortCol = col; sortDir = 1; }}
  renderEstado();
}}

function renderDetalle() {{
  const list = document.getElementById('ticker-list');
  const data = DATA.estado;
  const emojiOrder = {{'🔴':0,'🟠':1,'🟡':2,'🟢':3}};
  const sorted = [...data].sort((a,b) => (emojiOrder[a.alerta_emoji]??9)-(emojiOrder[b.alerta_emoji]??9));
  list.innerHTML = sorted.map((r,i) => {{
    const ec = EMOJI_CLASS[r.alerta_emoji]||'';
    return `<button class="ticker-btn" onclick="showTicker('${{r.ticker}}')" id="btn-${{r.ticker}}">
      <span>${{r.ticker}}</span>
      <span class="a-${{ec}}">${{r.alerta_emoji}}</span>
    </button>`;
  }}).join('');
  if(sorted.length) showTicker(sorted[0].ticker);
}}

function showTicker(ticker) {{
  document.querySelectorAll('.ticker-btn').forEach(b => b.classList.toggle('active', b.id==='btn-'+ticker));
  const r = DATA.estado.find(x => x.ticker===ticker);
  if(!r) return;
  const ec = EMOJI_CLASS[r.alerta_emoji]||'green';
  const panel = document.getElementById('detail-panel');

  const gan = r.ganancia_pct;
  const ganStr = gan!==null ? (gan>=0?'+':'')+gan.toFixed(1)+'%' : '—';
  const ganCls = gan>=0?'pos':'neg';

  const precio = r.precio_actual_usd;
  const maximo = r.maximo_desde_entrada_usd;
  const ppp = r.ppp_equiv_usd;

  const stops = [];
  if(r.stop_s1_usd) stops.push({{name:'Stop S1', val:r.stop_s1_usd, active:r.s1_activado, color:'#f97316'}});
  if(r.stop_t1_usd && r.t1_activo) stops.push({{name:'Stop T1', val:r.stop_t1_usd, active:r.t1_activado, color:'#ef4444'}});
  if(r.stop_t2_usd && r.t2_activo) stops.push({{name:'Stop T2', val:r.stop_t2_usd, active:r.t2_activado, color:'#f97316'}});
  if(ppp) stops.push({{name:'PPP equiv', val:ppp, active:false, color:'#8892aa'}});

  const allVals = [precio, maximo, ppp, ...stops.map(s=>s.val)].filter(v=>v!=null);
  const minV = Math.min(...allVals)*0.97;
  const maxV = Math.max(...allVals)*1.01;
  const range = maxV - minV;
  const pct = v => ((v - minV)/range*100).toFixed(1);

  const barsData = [
    {{label:'PPP\nequiv', val:ppp, color:'#5a6480', height: pct(ppp)}},
    {{label:'Precio\nactual', val:precio, color:'#60a5fa', height: pct(precio)}},
    {{label:'Máximo\nentrada', val:maximo, color:'#22c55e', height: pct(maximo)}},
  ];

  const barsHtml = barsData.filter(b=>b.val).map(b => `
    <div class="price-bar-wrap">
      <div class="bar-value">$${{b.val?.toFixed(2)}}</div>
      <div class="price-bar" style="height:${{b.height}}%;background:${{b.color}};min-height:20px"></div>
      <div class="bar-label">${{b.label}}</div>
    </div>`).join('');

  const stopsHtml = stops.length ? stops.map(s => {{
    const distPct = precio && s.val ? ((precio-s.val)/precio*100) : 0;
    const barW = Math.max(0, Math.min(100, (s.val/maxV)*100));
    const curW = precio ? (precio/maxV*100) : 0;
    return `<div class="stop-row">
      <span class="stop-name">${{s.name}}</span>
      <div class="stop-bar-wrap">
        <div class="stop-bar" style="width:${{barW}}%;background:${{s.color}};opacity:0.7"></div>
        <div class="current-marker" style="left:${{curW}}%"></div>
      </div>
      <span class="stop-price">$${{s.val?.toFixed(2)}}</span>
      <span class="stop-pct ${{s.active?'a-red':distPct<5?'a-orange':distPct<15?'a-yellow':'a-green'}}">${{s.active?'ACTIVADO':distPct.toFixed(1)+'% margen'}}</span>
    </div>`;
  }}).join('') : '<div style="color:var(--text3);font-size:12px">Sin stops calculados</div>';

  const extraSat = r.categoria?.includes('Satelites') ? `
    <div class="metrics-grid" style="margin-top:12px">
      ${{metricBox('Rank bruto', r.rank_bruto ? '#'+r.rank_bruto : '—')}}
      ${{metricBox('Rank efectivo', r.rank_efectivo ? '#'+r.rank_efectivo : '—')}}
      ${{metricBox('Score ETF', r.score_etf ? (r.score_etf*100).toFixed(1)+'%' : '—')}}
      ${{metricBox('Delta momentum', r.delta_momentum ? (r.delta_momentum*100).toFixed(1)+'%' : '—')}}
    </div>
    <div class="stops-wrap" style="margin-top:8px">
      <div class="stop-row"><span class="stop-name">S2 decision</span><span style="color:var(--text)">${{r.s2_decision||'—'}}</span></div>
      <div class="stop-row"><span class="stop-name">S3 activado</span><span class="${{r.s3_activado?'a-red':'a-green'}}">${{r.s3_activado?'SÍ':'No'}}</span></div>
    </div>` : `
    <div class="metrics-grid" style="margin-top:12px">
      ${{metricBox('Fase modelo', r.fase_modelo||'—')}}
      ${{metricBox('Acción modelo', r.accion_modelo||'—')}}
      ${{metricBox('Tamaño pos.', r.tamano_posicion_pct ? r.tamano_posicion_pct+'%' : '—')}}
      ${{metricBox('Flag revisión', r.flag_revision ? 'SÍ' : 'No')}}
    </div>`;

  panel.innerHTML = `
    <div class="detail-header">
      <span class="detail-ticker">${{ticker}}</span>
      <span class="detail-cat">${{r.categoria||''}}</span>
      ${{r.tipo_ab ? `<span class="detail-cat">Tipo ${{r.tipo_ab}}</span>` : ''}}
      <span class="detail-alert alert-${{ec}}">${{r.alerta_emoji}} ${{r.alerta_texto||''}}</span>
    </div>
    <div class="metrics-grid">
      ${{metricBox('Ganancia', ganStr, ganCls)}}
      ${{metricBox('Precio actual', precio ? '$$'+precio.toFixed(2) : '—')}}
      ${{metricBox('PPP equiv', ppp ? '$$'+ppp.toFixed(2) : '—')}}
      ${{metricBox('Máximo entrada', maximo ? '$$'+maximo.toFixed(2) : '—')}}
      ${{metricBox('Sigma mensual', r.sigma_mensual_12m ? r.sigma_mensual_12m.toFixed(1)+'%' : '—')}}
      ${{metricBox('Desde', r.fecha_primera_compra||'—')}}
    </div>
    <div class="chart-section">
      <div class="chart-title">Niveles de precio</div>
      <div class="price-chart" style="height:160px">${{barsHtml}}</div>
    </div>
    <div class="chart-section">
      <div class="chart-title">Stops y márgenes</div>
      <div class="stops-wrap">${{stopsHtml}}</div>
    </div>
    ${{extraSat}}
  `;
}}

function metricBox(label, val, cls='') {{
  return `<div class="metric">
    <div class="metric-label">${{label}}</div>
    <div class="metric-value ${{cls}}">${{val}}</div>
  </div>`;
}}

function renderCambios() {{
  const wrap = document.getElementById('cambios-list');
  if(!DATA.cambios.length) {{
    wrap.innerHTML = '<div class="empty">Sin cambios registrados aún</div>';
    return;
  }}
  const sorted = [...DATA.cambios].sort((a,b) => b.fecha_cambio?.localeCompare(a.fecha_cambio||'')||0);
  wrap.innerHTML = sorted.map(c => {{
    const dirCls = c.direccion==='EMPEORÓ' ? 'dir-emp' : 'dir-mej';
    const ecNue = EMOJI_CLASS[c.alerta_nueva]||'';
    return `<div class="cambio-card">
      <div>
        <div class="cambio-ticker">${{c.ticker}}</div>
        <div style="font-size:11px;color:var(--text3)">${{c.categoria||''}}</div>
      </div>
      <div>
        <span class="cambio-dir ${{dirCls}}">${{c.direccion}}</span>
        <div style="margin-top:6px;font-size:12px">
          <span style="color:var(--text3)">${{c.alerta_anterior}}</span>
          <span style="color:var(--text3)"> → </span>
          <span class="a-${{ecNue}}">${{c.alerta_nueva}}</span>
        </div>
      </div>
      <div class="cambio-fecha">${{c.fecha_cambio?.slice(0,16)||''}}</div>
      <div class="cambio-detail">
        <div class="cambio-box">
          <div class="cambio-box-label">Antes</div>
          <div class="cambio-box-text">${{c.texto_anterior||'—'}}</div>
        </div>
        <div class="cambio-box" style="border-color:${{ecNue==='red'?'#4a1f1f':ecNue==='orange'?'#4a2f00':'var(--border)'}}">
          <div class="cambio-box-label">Ahora</div>
          <div class="cambio-box-text a-${{ecNue}}">${{c.texto_nuevo||'—'}}</div>
        </div>
      </div>
    </div>`;
  }}).join('');
}}

function renderHistorial() {{
  const q = (document.getElementById('hist-search')?.value||'').toLowerCase();
  const rows = DATA.historial.filter(r => !q || r.ticker?.toLowerCase().includes(q));
  document.getElementById('hist-count').textContent = rows.length + ' registros';
  const cols = ['fecha_run','ticker','categoria','alerta_emoji','alerta_texto','ganancia_pct','precio_actual_usd','fase_modelo','s2_decision'];
  const labels = {{fecha_run:'Fecha',ticker:'Ticker',categoria:'Cat',alerta_emoji:'',alerta_texto:'Alerta',ganancia_pct:'Gan%',precio_actual_usd:'Precio',fase_modelo:'Fase',s2_decision:'S2'}};
  document.getElementById('hist-head').innerHTML = '<tr>'+cols.map(c=>`<th>${{labels[c]||c}}</th>`).join('')+'</tr>';
  const sorted = [...rows].sort((a,b) => (b.fecha_run||'').localeCompare(a.fecha_run||''));
  document.getElementById('hist-body').innerHTML = sorted.slice(0,200).map(r => {{
    const ec = EMOJI_CLASS[r.alerta_emoji]||'';
    return `<tr class="row-${{ec}}">` + cols.map(c => `<td>${{fmt(c,r[c])}}</td>`).join('') + '</tr>';
  }}).join('');
}}

renderEstado();
</script>
</body>
</html>"""
    html = _TEMPLATE.replace("__DATA_PLACEHOLDER__", data_js)
    return html

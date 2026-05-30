"""
generar_html.py - Dashboard HTML del Monitor de Salidas.
"""

import json
from datetime import datetime


TOOLTIPS = {
    "ticker": "Simbolo del subyacente en NYSE/NASDAQ",
    "categoria": "Largo Satelites (ETFs) o Largo Acciones (individuales)",
    "tipo_empresa": "Clasificacion fundamental: GROWTH, VALUE, CICLICA, TURNAROUND, ESPECULATIVA",
    "tipo_ab": "A = conviccion (promedia a la baja) / B = oportunidad tactica con stop fijo",
    "cantidad": "Numero de CEDEARs en cartera",
    "coste_compra_usd": "Costo total de compra en USD (Portfolio Performance)",
    "valor_mercado_usd": "Valor de mercado actual en USD (Portfolio Performance)",
    "ganancia_pct": "Ganancia % sobre el costo de compra calculada desde PP en USD",
    "ppp_equiv_usd": "Precio de compra equivalente del subyacente = precio_yfinance / (1 + ganancia%)",
    "fecha_primera_compra": "Fecha de primera compra de la posicion actual (respeta re-entradas)",
    "precio_actual_usd": "Ultimo precio de cierre del subyacente en NYSE (yfinance)",
    "maximo_desde_entrada_usd": "Mayor precio de cierre del subyacente desde la fecha de entrada",
    "sigma_mensual_12m": "Volatilidad mensual promedio ultimos 12 meses",
    "grupo_satelite": "Grupo tematico del ETF segun ranking",
    "rank_bruto": "Posicion en el ranking de momentum (todos los ETFs)",
    "rank_efectivo": "Posicion entre ETFs que pasaron filtros: Mom3m>0 y precio>MM200",
    "score_etf": "Score de momentum del ETF",
    "score_top5": "Score promedio de los 5 primeros del ranking",
    "delta_momentum": "Diferencia relativa entre score del ETF y top5. >20% en rank 6-10 dispara S2",
    "stop_s1_usd": "Trailing stop S1 = Maximo x (1 - k x sigma). Salir si precio cae aqui",
    "kxsigma": "Distancia porcentual del stop S1 al maximo. Max 25%",
    "s1_activado": "True si el precio cayo por debajo del stop S1",
    "s2_decision": "MANTENER / VIGILAR / ROTAR segun ranking efectivo y delta_momentum",
    "s3_activado": "True si el ETF cayo fuera del top 15 del ranking bruto",
    "stop_t1_usd": "Stop fijo desde PPP (solo Tipo B) = PPP x (1 - X%)",
    "t1_activo": "True si stop T1 esta vigente (ganancia < 10% y es Tipo B)",
    "t1_activado": "True si el precio cayo por debajo del stop T1",
    "stop_t2_usd": "Trailing stop T2 = Maximo x (1 - Y%). Se activa con ganancia >= 10%",
    "t2_activo": "True si trailing stop T2 esta vigente",
    "t2_activado": "True si el precio cayo por debajo del stop T2",
    "y_pct": "Distancia porcentual del trailing stop T2 al maximo",
    "fase_modelo": "Fase del modelo tactico del Analizador de Acciones",
    "accion_modelo": "Accion sugerida por el modelo tactico",
    "flag_revision": "True si el modelo marco revision de tesis fundamental",
    "tamano_posicion_pct": "Tamano de posicion sugerido por el modelo (%)",
    "t3_estado": "Estado de TIR objetivo",
    "alerta_emoji": "Semaforo: verde=Mantener / amarillo=Vigilar / naranja=Accion proxima / rojo=Accion inmediata",
    "alerta_texto": "Descripcion de la alerta con el mecanismo disparado y valores clave",
}


def _safe(v, decimals=2):
    if v is None:
        return None
    if isinstance(v, float) and v != v:
        return None
    if isinstance(v, float):
        return round(v, decimals)
    return v


def generar_html(resultados: list, cambios: list, historial: list) -> str:
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    data = {
        "estado":   [{k: _safe(v) for k, v in r.items()} for r in resultados],
        "cambios":  [{k: _safe(v) for k, v in c.items()} for c in cambios],
        "historial":[{k: _safe(v) for k, v in h.items()} for h in historial],
        "tooltips": TOOLTIPS,
        "fecha":    fecha,
    }
    data_json = json.dumps(data, default=str, ensure_ascii=False)

    css = """
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d0f16;--bg2:#13161f;--bg3:#1a1d28;--bg4:#20243a;
  --border:#252a3d;--border2:#323855;
  --text:#dde3f0;--text2:#7a85a0;--text3:#4a5270;
  --green:#22c55e;--green-dim:#0f3320;--green-bg:rgba(34,197,94,0.08);
  --yellow:#eab308;--yellow-bg:rgba(234,179,8,0.08);
  --orange:#f97316;--orange-bg:rgba(249,115,22,0.08);
  --red:#ef4444;--red-dim:#3b1010;--red-bg:rgba(239,68,68,0.08);
  --blue:#4d9de0;--accent:#6366f1;--accent2:#4f46e5;
  --purple:#a78bfa;
}
html,body{background:var(--bg);color:var(--text);font-family:'DM Mono',monospace;font-size:13px;line-height:1.5;min-height:100vh}
.app{display:flex;flex-direction:column;height:100vh;overflow:hidden}

/* HEADER */
.hdr{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:center;justify-content:space-between;height:52px;flex-shrink:0}
.hdr-title{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;letter-spacing:-0.3px;color:var(--text)}
.hdr-meta{font-size:11px;color:var(--text3)}

/* TABS */
.tabs{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 24px;display:flex;flex-shrink:0}
.tab{padding:11px 18px;cursor:pointer;font-family:'Syne',sans-serif;font-size:12px;font-weight:600;color:var(--text2);border-bottom:2px solid transparent;transition:all 0.15s;letter-spacing:0.3px}
.tab:hover{color:var(--text)}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}

/* CONTENT */
.content{flex:1;overflow-y:auto;padding:20px 24px;display:none}
.content.active{display:block}

/* FILTERS */
.filters{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center}
.fi{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:5px 10px;border-radius:5px;font-family:'DM Mono',monospace;font-size:12px;outline:none}
.fi:focus{border-color:var(--border2)}
.fb{background:var(--bg3);border:1px solid var(--border);color:var(--text2);padding:5px 10px;border-radius:5px;cursor:pointer;font-family:'DM Mono',monospace;font-size:11px;transition:all 0.1s}
.fb:hover,.fb.on{background:var(--bg4);border-color:var(--border2);color:var(--text)}
.fl{font-size:11px;color:var(--text3);margin-right:2px}

/* TABLE */
.tw{overflow-x:auto;border-radius:8px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-size:12px}
thead{background:var(--bg3)}
th{padding:9px 12px;text-align:left;color:var(--text3);font-weight:400;white-space:nowrap;border-bottom:1px solid var(--border);cursor:pointer;position:relative;user-select:none}
th:hover{color:var(--text2)}
.tip{display:none;position:absolute;top:100%;left:0;z-index:200;background:#1a2035;border:1px solid var(--border2);border-radius:6px;padding:8px 12px;font-size:11px;color:var(--text2);width:240px;white-space:normal;line-height:1.5;pointer-events:none;font-weight:400}
th:hover .tip{display:block}
td{padding:7px 12px;border-bottom:1px solid var(--border);white-space:nowrap;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--bg3)}
.rr td{background:var(--red-bg)}.ro td{background:var(--orange-bg)}.ry td{background:var(--yellow-bg)}.rg td{background:var(--green-bg)}
.ag{color:var(--green)}.ay{color:var(--yellow)}.ao{color:var(--orange)}.ar{color:var(--red)}
.pos{color:var(--green)}.neg{color:var(--red)}.dim{color:var(--text3)}

/* DETALLE LAYOUT */
.det-wrap{display:flex;gap:0;height:calc(100vh - 130px)}
.det-sidebar{width:152px;flex-shrink:0;border-right:1px solid var(--border);overflow-y:auto;padding:8px}
.tbtn{display:flex;justify-content:space-between;align-items:center;padding:7px 9px;border-radius:5px;border:1px solid transparent;cursor:pointer;font-size:11px;color:var(--text2);background:transparent;width:100%;margin-bottom:3px;font-family:'DM Mono',monospace}
.tbtn:hover{background:var(--bg3)}
.tbtn.on{background:var(--bg3);border-color:var(--accent);color:var(--text)}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.dg{background:var(--green)}.dy{background:var(--yellow)}.do{background:var(--orange)}.dr{background:var(--red)}

/* DETALLE MAIN */
.det-main{flex:1;overflow-y:auto;padding:20px 24px;min-width:0}
.det-hdr{display:flex;align-items:center;gap:12px;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--border);flex-wrap:wrap}
.det-ticker{font-family:'Syne',sans-serif;font-size:30px;font-weight:700;color:var(--text)}
.tag{font-size:10px;color:var(--text3);background:var(--bg3);padding:3px 9px;border-radius:4px;border:1px solid var(--border)}
.alert-pill{font-size:12px;padding:5px 12px;border-radius:5px;font-weight:500}
.ap-g{background:var(--green-bg);color:var(--green);border:1px solid rgba(34,197,94,0.25)}
.ap-y{background:var(--yellow-bg);color:var(--yellow);border:1px solid rgba(234,179,8,0.25)}
.ap-o{background:var(--orange-bg);color:var(--orange);border:1px solid rgba(249,115,22,0.25)}
.ap-r{background:var(--red-bg);color:var(--red);border:1px solid rgba(239,68,68,0.25)}

/* METRIC CARDS */
.mcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin-bottom:16px}
.mc{background:var(--bg3);border:1px solid var(--border);border-radius:7px;padding:10px 12px}
.mc-label{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:5px}
.mc-val{font-size:17px;font-weight:500;color:var(--text)}
.mc-val.pos{color:var(--green)}.mc-val.neg{color:var(--red)}.mc-val.sm{font-size:13px}

/* PRICE CHART PANEL */
.panel{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px}
.panel-title{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:14px;font-weight:500}

/* PRICE RULER - horizontal visual */
.ruler-wrap{position:relative;margin:8px 0 32px 0;height:56px}
.ruler-track{position:absolute;top:24px;left:0;right:0;height:3px;background:var(--border2);border-radius:2px}
.ruler-marker{position:absolute;display:flex;flex-direction:column;align-items:center;transform:translateX(-50%)}
.ruler-dot{width:12px;height:12px;border-radius:50%;border:2px solid var(--bg2);top:18px;position:absolute}
.ruler-label{font-size:9px;color:var(--text3);white-space:nowrap;top:36px;position:absolute}
.ruler-price{font-size:11px;font-weight:500;top:0;position:absolute;white-space:nowrap}
.ruler-zone{position:absolute;top:22px;height:7px;border-radius:3px;opacity:0.3}

/* STOPS TABLE */
.stops-list{display:flex;flex-direction:column;gap:6px}
.stop-row{display:grid;grid-template-columns:90px 1fr 70px 80px 60px;align-items:center;gap:10px;padding:8px 12px;background:var(--bg3);border-radius:6px;border:1px solid var(--border)}
.stop-name{font-size:11px;color:var(--text2)}
.stop-bar-bg{height:5px;background:var(--bg4);border-radius:3px;position:relative}
.stop-bar-fill{height:100%;border-radius:3px;position:absolute;left:0;top:0}
.stop-cur{position:absolute;width:2px;height:11px;top:-3px;border-radius:1px;background:var(--blue)}
.stop-price{font-size:12px;color:var(--text);text-align:right}
.stop-dist{font-size:11px;text-align:right}
.stop-status{font-size:10px;text-align:right}

/* MODEL SECTION */
.model-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}

/* CAMBIOS */
.chg-card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:8px}
.chg-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.chg-ticker{font-family:'Syne',sans-serif;font-size:18px;font-weight:700}
.chg-dir-e{font-size:10px;padding:2px 8px;border-radius:4px;background:var(--red-bg);color:var(--red);border:1px solid rgba(239,68,68,0.25)}
.chg-dir-m{font-size:10px;padding:2px 8px;border-radius:4px;background:var(--green-bg);color:var(--green);border:1px solid rgba(34,197,94,0.25)}
.chg-boxes{display:flex;gap:10px;margin-top:8px}
.chg-box{flex:1;padding:8px 12px;background:var(--bg3);border-radius:6px;border:1px solid var(--border)}
.chg-box-lbl{font-size:9px;color:var(--text3);text-transform:uppercase;margin-bottom:3px}
.chg-box-txt{font-size:11px;color:var(--text2)}

.empty{color:var(--text3);font-size:12px;padding:40px;text-align:center;border:1px solid var(--border);border-radius:8px}
"""

    js = r"""
const D = window._DATA;
const F = {cat:'all',tipo:'all',alert:'all'};
let SC=null,SD=1;

const COLS=['ticker','categoria','tipo_ab','tipo_empresa','ganancia_pct','precio_actual_usd',
  'ppp_equiv_usd','maximo_desde_entrada_usd','stop_s1_usd','stop_t1_usd','stop_t2_usd',
  'rank_efectivo','s2_decision','fase_modelo','alerta_emoji','alerta_texto'];
const LBL={ticker:'Ticker',categoria:'Cat',tipo_ab:'Tipo',tipo_empresa:'Empresa',
  ganancia_pct:'Gan%',precio_actual_usd:'Precio',ppp_equiv_usd:'PPP',
  maximo_desde_entrada_usd:'Max',stop_s1_usd:'S1',stop_t1_usd:'T1',stop_t2_usd:'T2',
  rank_efectivo:'Rank',s2_decision:'S2',fase_modelo:'Fase',alerta_emoji:'',alerta_texto:'Alerta'};
const EC={'🟢':'g','🟡':'y','🟠':'o','🔴':'r'};
const EO={'🔴':0,'🟠':1,'🟡':2,'🟢':3};
const CLR={g:'#22c55e',y:'#eab308',o:'#f97316',r:'#ef4444'};

function switchTab(id){
  ['estado','detalle','cambios','historial'].forEach((t,i)=>{
    document.querySelectorAll('.tab')[i].classList.toggle('active',t===id);
    document.getElementById('t-'+t).classList.toggle('active',t===id);
  });
  if(id==='detalle') initDetalle();
  if(id==='cambios') renderCambios();
  if(id==='historial') renderHistorial();
}

function setF(k,v,b){
  F[k]=v;
  b.parentElement.querySelectorAll('.fb').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');
  renderEstado();
}

function fmt(col,val){
  if(val===null||val===undefined) return '<span class="dim">—</span>';
  if(col==='ganancia_pct'){const c=val>=0?'pos':'neg';return '<span class="'+c+'">'+(val>=0?'+':'')+Number(val).toFixed(1)+'%</span>';}
  if(['precio_actual_usd','ppp_equiv_usd','maximo_desde_entrada_usd','stop_s1_usd','stop_t1_usd','stop_t2_usd'].includes(col))
    return '$'+Number(val).toFixed(2);
  if(col==='alerta_emoji') return '<span class="a'+(EC[val]||'')+'">'+val+'</span>';
  if(col==='rank_efectivo') return val!==null?'#'+val:'<span class="dim">—</span>';
  if(typeof val==='boolean') return val?'<span class="ar">SI</span>':'<span class="dim">no</span>';
  return String(val);
}

function fd(){
  const q=(document.getElementById('srch')||{value:''}).value.toLowerCase();
  return D.estado.filter(r=>{
    if(q&&!r.ticker?.toLowerCase().includes(q)) return false;
    if(F.cat==='sat'&&!r.categoria?.includes('Satelites')) return false;
    if(F.cat==='acc'&&!r.categoria?.includes('Acciones')) return false;
    if(F.tipo!=='all'&&r.tipo_ab!==F.tipo) return false;
    if(F.alert!=='all'&&r.alerta_emoji!==F.alert) return false;
    return true;
  });
}

function renderEstado(){
  const tips=D.tooltips;
  document.getElementById('eh').innerHTML='<tr>'+COLS.map(c=>'<th onclick="sortBy(\''+c+'\')">'+LBL[c]+'<div class="tip">'+(tips[c]||'')+'</div></th>').join('')+'</tr>';
  let rows=fd();
  if(SC) rows.sort((a,b)=>{const av=a[SC]??'',bv=b[SC]??'';return av<bv?-SD:av>bv?SD:0;});
  else rows.sort((a,b)=>(EO[a.alerta_emoji]??9)-(EO[b.alerta_emoji]??9));
  document.getElementById('eb').innerHTML=rows.map(r=>'<tr class="r'+(EC[r.alerta_emoji]||'')+'">'+COLS.map(c=>'<td>'+fmt(c,r[c])+'</td>').join('')+'</tr>').join('');
}

function sortBy(c){if(SC===c)SD*=-1;else{SC=c;SD=1;}renderEstado();}

function initDetalle(){
  const sorted=[...D.estado].sort((a,b)=>(EO[a.alerta_emoji]??9)-(EO[b.alerta_emoji]??9));
  document.getElementById('dlist').innerHTML=sorted.map(r=>'<button class="tbtn" onclick="showT(\''+r.ticker+'\')" id="dbtn-'+r.ticker+'"><span>'+r.ticker+'</span><div class="dot d'+(EC[r.alerta_emoji]||'g')+'"></div></button>').join('');
  if(sorted.length) showT(sorted[0].ticker);
}

function ruler(r){
  const vals=[r.ppp_equiv_usd,r.precio_actual_usd,r.maximo_desde_entrada_usd,r.stop_s1_usd,r.stop_t1_usd,r.stop_t2_usd].filter(v=>v!=null&&v>0);
  if(!vals.length) return '<div class="dim" style="padding:20px 0;text-align:center">Sin datos de precio</div>';
  const mn=Math.min(...vals)*0.92, mx=Math.max(...vals)*1.04, rng=mx-mn;
  const pct=v=>((v-mn)/rng*100).toFixed(2);

  const markers=[
    {v:r.ppp_equiv_usd, color:'#a78bfa', label:'Compra', price:r.ppp_equiv_usd},
    {v:r.maximo_desde_entrada_usd, color:'#22c55e', label:'Maximo', price:r.maximo_desde_entrada_usd},
    {v:r.precio_actual_usd, color:'#4d9de0', label:'Precio actual', price:r.precio_actual_usd},
  ];
  if(r.stop_s1_usd) markers.push({v:r.stop_s1_usd, color:'#f97316', label:'Stop S1', price:r.stop_s1_usd});
  if(r.stop_t1_usd&&r.t1_activo) markers.push({v:r.stop_t1_usd, color:'#ef4444', label:'Stop T1', price:r.stop_t1_usd});
  if(r.stop_t2_usd&&r.t2_activo) markers.push({v:r.stop_t2_usd, color:'#ef4444', label:'Stop T2', price:r.stop_t2_usd});

  // Zone: compra to actual (profit/loss area)
  const zoneL=Math.min(pct(r.ppp_equiv_usd||0),pct(r.precio_actual_usd||0));
  const zoneW=Math.abs(pct(r.ppp_equiv_usd||0)-pct(r.precio_actual_usd||0));
  const gan=(r.ganancia_pct||0);
  const zoneColor=gan>=0?'rgba(34,197,94,0.15)':'rgba(239,68,68,0.15)';

  let html='<div class="ruler-wrap">';
  html+='<div class="ruler-track"></div>';
  // Gain zone
  html+='<div class="ruler-zone" style="left:'+zoneL+'%;width:'+zoneW+'%;background:'+(gan>=0?'#22c55e':'#ef4444')+'"></div>';
  // Markers
  markers.forEach(m=>{
    const p=pct(m.v);
    html+='<div class="ruler-marker" style="left:'+p+'%">';
    html+='<div class="ruler-price" style="color:'+m.color+'">$'+Number(m.v).toFixed(2)+'</div>';
    html+='<div class="ruler-dot" style="background:'+m.color+';width:10px;height:10px;border-radius:50%;border:2px solid #13161f;position:absolute;top:19px"></div>';
    html+='<div class="ruler-label">'+m.label+'</div>';
    html+='</div>';
  });
  html+='</div>';

  // Legend
  html+='<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:4px">';
  const leg=[
    {c:'#a78bfa',l:'Precio compra (PPP equiv)'},
    {c:'#4d9de0',l:'Precio actual'},
    {c:'#22c55e',l:'Maximo desde entrada'},
    {c:'#f97316',l:'Stop S1'},
    {c:'#ef4444',l:'Stop T1 / T2'},
  ];
  leg.forEach(x=>{ html+='<span style="display:flex;align-items:center;gap:5px;font-size:10px;color:#7a85a0"><span style="width:8px;height:8px;border-radius:50%;background:'+x.c+';display:inline-block"></span>'+x.l+'</span>'; });
  html+='</div>';
  return html;
}

function stopRows(r){
  const pr=r.precio_actual_usd, mx=r.maximo_desde_entrada_usd;
  const allVals=[pr,mx,r.ppp_equiv_usd,r.stop_s1_usd,r.stop_t1_usd,r.stop_t2_usd].filter(v=>v!=null&&v>0);
  if(!allVals.length) return '<div class="dim">Sin datos</div>';
  const maxV=Math.max(...allVals);
  const stops=[];
  if(r.stop_s1_usd) stops.push({n:'Stop S1 (trailing)',v:r.stop_s1_usd,act:r.s1_activado,c:'#f97316'});
  if(r.stop_t1_usd&&r.t1_activo) stops.push({n:'Stop T1 (fijo)',v:r.stop_t1_usd,act:r.t1_activado,c:'#ef4444'});
  if(r.stop_t2_usd&&r.t2_activo) stops.push({n:'Stop T2 (trailing)',v:r.stop_t2_usd,act:r.t2_activado,c:'#ef4444'});
  if(r.ppp_equiv_usd) stops.push({n:'PPP equiv (ref)',v:r.ppp_equiv_usd,act:false,c:'#a78bfa'});
  if(!stops.length) return '<div class="dim">Sin stops activos</div>';
  const curW=pr?(pr/maxV*100):0;
  return stops.map(s=>{
    const fw=(s.v/maxV*100).toFixed(1);
    const dist=pr&&s.v?((pr-s.v)/pr*100):0;
    const dcls=s.act?'ar':dist<5?'ao':dist<15?'ay':'ag';
    const dstr=s.act?'ACTIVADO':'+'+dist.toFixed(1)+'% margen';
    return '<div class="stop-row">'+
      '<div class="stop-name">'+s.n+'</div>'+
      '<div class="stop-bar-bg"><div class="stop-bar-fill" style="width:'+fw+'%;background:'+s.c+';opacity:0.5"></div><div class="stop-cur" style="left:'+curW+'%"></div></div>'+
      '<div class="stop-price">$'+s.v.toFixed(2)+'</div>'+
      '<div class="stop-dist '+dcls+'">'+dstr+'</div>'+
      '<div class="stop-status '+(s.act?'ar':'dim')+'">'+(s.act?'ACTIVADO':'ok')+'</div>'+
    '</div>';
  }).join('');
}

function showT(ticker){
  document.querySelectorAll('.tbtn').forEach(b=>b.classList.toggle('on',b.id==='dbtn-'+ticker));
  const r=D.estado.find(x=>x.ticker===ticker);
  if(!r) return;
  const ec=EC[r.alerta_emoji]||'g';
  const gan=r.ganancia_pct;
  const sat=r.categoria?.includes('Satelites');
  const ganStr=(gan!==null?(gan>=0?'+':'')+Number(gan).toFixed(1)+'%':'—');
  const ganCls=gan>=0?'pos':'neg';

  // Extra info for satellites vs stocks
  let extraCards='';
  if(sat){
    extraCards='<div class="mc"><div class="mc-label">Rank bruto</div><div class="mc-val sm">'+(r.rank_bruto?'#'+r.rank_bruto:'—')+'</div></div>'+
      '<div class="mc"><div class="mc-label">Rank efectivo</div><div class="mc-val sm">'+(r.rank_efectivo?'#'+r.rank_efectivo:'—')+'</div></div>'+
      '<div class="mc"><div class="mc-label">Score ETF</div><div class="mc-val sm">'+(r.score_etf?(r.score_etf*100).toFixed(1)+'%':'—')+'</div></div>'+
      '<div class="mc"><div class="mc-label">Delta momentum</div><div class="mc-val sm '+(r.delta_momentum>0.2?'neg':'')+'">'+(r.delta_momentum?(r.delta_momentum*100).toFixed(1)+'%':'—')+'</div></div>';
  } else {
    extraCards='<div class="mc"><div class="mc-label">Fase modelo</div><div class="mc-val sm">'+(r.fase_modelo||'—')+'</div></div>'+
      '<div class="mc"><div class="mc-label">Accion modelo</div><div class="mc-val sm '+(r.accion_modelo?.includes('VENTA')?'neg':'')+'">'+(r.accion_modelo||'—')+'</div></div>'+
      '<div class="mc"><div class="mc-label">Tamano pos.</div><div class="mc-val sm">'+(r.tamano_posicion_pct!=null?r.tamano_posicion_pct+'%':'—')+'</div></div>'+
      '<div class="mc"><div class="mc-label">Flag revision</div><div class="mc-val sm '+(r.flag_revision?'neg':'')+'">'+(r.flag_revision?'SI':'No')+'</div></div>';
  }

  const satExtra=sat?
    '<div class="panel"><div class="panel-title">Ranking y rotacion</div>'+
    '<div style="display:flex;gap:10px;flex-wrap:wrap;font-size:12px">'+
    '<div style="flex:1;min-width:180px;padding:10px;background:var(--bg3);border-radius:6px;border:1px solid var(--border)"><div style="color:var(--text3);font-size:10px;margin-bottom:4px">DECISION S2</div><div style="color:var(--text)">'+(r.s2_decision||'—')+'</div></div>'+
    '<div style="flex:1;min-width:180px;padding:10px;background:var(--bg3);border-radius:6px;border:1px solid var(--border)"><div style="color:var(--text3);font-size:10px;margin-bottom:4px">S3 ACTIVADO</div><div class="'+(r.s3_activado?'ar':'ag')+'">'+(r.s3_activado?'SI — Salir a parking':'No')+'</div></div>'+
    '</div></div>':'';

  document.getElementById('dmain').innerHTML=
    '<div class="det-hdr">'+
      '<span class="det-ticker">'+ticker+'</span>'+
      '<span class="tag">'+(r.categoria||'')+'</span>'+
      (r.tipo_ab?'<span class="tag">Tipo '+r.tipo_ab+'</span>':'')+
      (r.tipo_empresa?'<span class="tag">'+r.tipo_empresa+'</span>':'')+
      '<span class="alert-pill ap-'+ec+'">'+r.alerta_emoji+' '+(r.alerta_texto||'')+'</span>'+
    '</div>'+

    '<div class="mcards">'+
      '<div class="mc"><div class="mc-label">Ganancia PP</div><div class="mc-val '+ganCls+'">'+ganStr+'</div></div>'+
      '<div class="mc"><div class="mc-label">Precio actual</div><div class="mc-val">'+(r.precio_actual_usd?'$'+Number(r.precio_actual_usd).toFixed(2):'—')+'</div></div>'+
      '<div class="mc"><div class="mc-label">PPP equiv</div><div class="mc-val">'+(r.ppp_equiv_usd?'$'+Number(r.ppp_equiv_usd).toFixed(2):'—')+'</div></div>'+
      '<div class="mc"><div class="mc-label">Maximo entrada</div><div class="mc-val">'+(r.maximo_desde_entrada_usd?'$'+Number(r.maximo_desde_entrada_usd).toFixed(2):'—')+'</div></div>'+
      '<div class="mc"><div class="mc-label">Sigma mensual</div><div class="mc-val">'+(r.sigma_mensual_12m?Number(r.sigma_mensual_12m).toFixed(1)+'%':'—')+'</div></div>'+
      '<div class="mc"><div class="mc-label">Desde</div><div class="mc-val sm">'+(r.fecha_primera_compra||'—')+'</div></div>'+
      extraCards+
    '</div>'+

    '<div class="panel">'+
      '<div class="panel-title">Niveles de precio — PPP compra / precio actual / stops / maximo</div>'+
      ruler(r)+
    '</div>'+

    '<div class="panel">'+
      '<div class="panel-title">Stops activos y margenes</div>'+
      '<div class="stops-list">'+stopRows(r)+'</div>'+
    '</div>'+

    satExtra;
}

function renderCambios(){
  const w=document.getElementById('clist');
  if(!D.cambios||!D.cambios.length){w.innerHTML='<div class="empty">Sin cambios registrados aun</div>';return;}
  const sorted=[...D.cambios].sort((a,b)=>(b.fecha_cambio||'').toString().localeCompare((a.fecha_cambio||'').toString()));
  w.innerHTML=sorted.map(c=>{
    const ec=EC[c.alerta_nueva]||'g';
    const dir=c.direccion==='EMPEORO'?'chg-dir-e':'chg-dir-m';
    return '<div class="chg-card">'+
      '<div class="chg-head">'+
        '<div style="display:flex;align-items:center;gap:10px">'+
          '<span class="chg-ticker">'+c.ticker+'</span>'+
          '<span class="'+dir+'">'+c.direccion+'</span>'+
          '<span style="font-size:12px;color:var(--text3)">'+c.alerta_anterior+' → <span class="a'+ec+'">'+c.alerta_nueva+'</span></span>'+
        '</div>'+
        '<span style="font-size:10px;color:var(--text3)">'+(c.fecha_cambio||'').toString().slice(0,16)+'</span>'+
      '</div>'+
      '<div class="chg-boxes">'+
        '<div class="chg-box"><div class="chg-box-lbl">Antes</div><div class="chg-box-txt">'+(c.texto_anterior||'—')+'</div></div>'+
        '<div class="chg-box" style="border-color:'+(ec==='r'?'rgba(239,68,68,0.3)':ec==='o'?'rgba(249,115,22,0.3)':'var(--border)')+'"><div class="chg-box-lbl">Ahora</div><div class="chg-box-txt a'+ec+'">'+(c.texto_nuevo||'—')+'</div></div>'+
      '</div>'+
    '</div>';
  }).join('');
}

function renderHistorial(){
  const q=(document.getElementById('hs')||{value:''}).value.toLowerCase();
  const rows=D.historial.filter(r=>!q||r.ticker?.toLowerCase().includes(q));
  document.getElementById('hc').textContent=rows.length+' registros';
  const cols=['fecha_run','ticker','categoria','alerta_emoji','alerta_texto','ganancia_pct','precio_actual_usd','fase_modelo','s2_decision'];
  const labs={fecha_run:'Fecha',ticker:'Ticker',categoria:'Cat',alerta_emoji:'',alerta_texto:'Alerta',ganancia_pct:'Gan%',precio_actual_usd:'Precio',fase_modelo:'Fase',s2_decision:'S2'};
  document.getElementById('hh').innerHTML='<tr>'+cols.map(c=>'<th>'+labs[c]+'</th>').join('')+'</tr>';
  const sorted=[...rows].sort((a,b)=>(b.fecha_run||'').toString().localeCompare((a.fecha_run||'').toString()));
  document.getElementById('hb').innerHTML=sorted.slice(0,300).map(r=>'<tr class="r'+(EC[r.alerta_emoji]||'')+'">'+cols.map(c=>'<td>'+fmt(c,r[c])+'</td>').join('')+'</tr>').join('');
}

renderEstado();
"""

    body = (
        '<div class="app">'
        '<div class="hdr"><div class="hdr-title">Monitor de Salidas</div><div class="hdr-meta">Actualizado: ' + fecha + '</div></div>'
        '<div class="tabs">'
        '<div class="tab active" onclick="switchTab(\'estado\')">Estado actual</div>'
        '<div class="tab" onclick="switchTab(\'detalle\')">Detalle por ticker</div>'
        '<div class="tab" onclick="switchTab(\'cambios\')">Cambios</div>'
        '<div class="tab" onclick="switchTab(\'historial\')">Historial</div>'
        '</div>'

        '<div id="t-estado" class="content active">'
        '<div class="filters">'
        '<span class="fl">Buscar:</span><input class="fi" id="srch" placeholder="ticker..." oninput="renderEstado()" style="width:130px">'
        '<span class="fl">Cat:</span>'
        '<button class="fb on" onclick="setF(\'cat\',\'all\',this)">Todos</button>'
        '<button class="fb" onclick="setF(\'cat\',\'sat\',this)">Satelites</button>'
        '<button class="fb" onclick="setF(\'cat\',\'acc\',this)">Acciones</button>'
        '<span class="fl">Tipo:</span>'
        '<button class="fb on" onclick="setF(\'tipo\',\'all\',this)">A+B</button>'
        '<button class="fb" onclick="setF(\'tipo\',\'A\',this)">Tipo A</button>'
        '<button class="fb" onclick="setF(\'tipo\',\'B\',this)">Tipo B</button>'
        '<span class="fl">Alerta:</span>'
        '<button class="fb on" onclick="setF(\'alert\',\'all\',this)">Todas</button>'
        '<button class="fb ar" onclick="setF(\'alert\',\'🔴\',this)">🔴</button>'
        '<button class="fb ao" onclick="setF(\'alert\',\'🟠\',this)">🟠</button>'
        '<button class="fb ay" onclick="setF(\'alert\',\'🟡\',this)">🟡</button>'
        '<button class="fb ag" onclick="setF(\'alert\',\'🟢\',this)">🟢</button>'
        '</div>'
        '<div class="tw"><table><thead id="eh"></thead><tbody id="eb"></tbody></table></div>'
        '</div>'

        '<div id="t-detalle" class="content" style="padding:0">'
        '<div class="det-wrap">'
        '<div class="det-sidebar" id="dlist"></div>'
        '<div class="det-main" id="dmain"><div class="empty">Selecciona un ticker de la lista</div></div>'
        '</div>'
        '</div>'

        '<div id="t-cambios" class="content"><div id="clist"></div></div>'

        '<div id="t-historial" class="content">'
        '<div class="filters"><span class="fl">Ticker:</span><input class="fi" id="hs" placeholder="filtrar..." oninput="renderHistorial()" style="width:120px"></div>'
        '<div id="hc" style="font-size:11px;color:var(--text3);margin-bottom:12px"></div>'
        '<div class="tw"><table><thead id="hh"></thead><tbody id="hb"></tbody></table></div>'
        '</div>'

        '</div>'
    )

    html = (
        '<!DOCTYPE html>\n'
        '<html lang="es">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>Monitor de Salidas</title>\n'
        '<style>' + css + '</style>\n'
        '<script>window._DATA=' + data_json + ';</script>\n'
        '</head>\n'
        '<body>\n'
        + body +
        '\n<script>' + js + '</script>\n'
        '</body>\n'
        '</html>\n'
    )
    return html


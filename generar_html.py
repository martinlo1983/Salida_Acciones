"""
generar_html.py - Dashboard HTML del Monitor de Salidas.
Usa concatenacion de strings para evitar conflictos con f-strings y {{ }}.
"""

import json
from datetime import datetime


TOOLTIPS = {
    "ticker": "Simbolo del subyacente en NYSE/NASDAQ",
    "categoria": "Largo Satelites (ETFs) o Largo Acciones (individuales)",
    "tipo_empresa": "Clasificacion fundamental: GROWTH, VALUE, CICLICA, TURNAROUND, ESPECULATIVA",
    "tipo_ab": "A = conviccion / B = oportunidad tactica con stop fijo",
    "cantidad": "Numero de CEDEARs en cartera",
    "coste_compra_usd": "Costo total de compra en USD (Portfolio Performance)",
    "valor_mercado_usd": "Valor de mercado actual en USD (Portfolio Performance)",
    "ganancia_pct": "Ganancia % sobre el costo de compra calculada desde PP",
    "ppp_equiv_usd": "Precio compra equivalente del subyacente = precio_yfinance / (1 + ganancia%)",
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
    "kxsigma": "Distancia porcentual del stop S1 al maximo (k x sigma). Max 25%",
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
    "t3_estado": "Estado de TIR objetivo: si se definio un objetivo de retorno anual",
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
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f1117;--bg2:#161922;--bg3:#1e2230;--bg4:#252a3a;
  --border:#2a3148;--border2:#3a4460;
  --text:#e8ecf4;--text2:#8892aa;--text3:#5a6480;
  --green:#22c55e;--green-bg:#0d2018;
  --yellow:#eab308;--yellow-bg:#1a1600;
  --orange:#f97316;--orange-bg:#1a0e00;
  --red:#ef4444;--red-bg:#1a0a0a;
  --blue:#60a5fa;--accent:#6366f1;
  --mono:'DM Mono',monospace;--head:'Syne',sans-serif;
}
body{background:var(--bg);color:var(--text);font-family:var(--mono);font-size:13px;line-height:1.5;min-height:100vh}
.app{display:flex;flex-direction:column;min-height:100vh}
.header{background:var(--bg2);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;justify-content:space-between}
.header-title{font-family:var(--head);font-size:18px;font-weight:700}
.header-meta{font-size:11px;color:var(--text3)}
.tabs{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 24px;display:flex}
.tab{padding:12px 20px;cursor:pointer;font-family:var(--head);font-size:13px;color:var(--text2);border-bottom:2px solid transparent;transition:all 0.15s}
.tab:hover{color:var(--text)}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.content{flex:1;padding:20px 24px;display:none}
.content.active{display:block}
.filters{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;align-items:center}
.fi{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:6px 12px;border-radius:6px;font-family:var(--mono);font-size:12px;outline:none}
.fi:focus{border-color:var(--border2)}
.fb{background:var(--bg3);border:1px solid var(--border);color:var(--text2);padding:6px 12px;border-radius:6px;cursor:pointer;font-family:var(--mono);font-size:12px;transition:all 0.1s}
.fb:hover,.fb.active{background:var(--bg4);border-color:var(--border2);color:var(--text)}
.fl{font-size:11px;color:var(--text3)}
.tw{overflow-x:auto;border-radius:8px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-size:12px}
thead{background:var(--bg3)}
th{padding:10px 12px;text-align:left;color:var(--text3);font-weight:500;white-space:nowrap;border-bottom:1px solid var(--border);cursor:pointer;position:relative}
th:hover{color:var(--text)}
.tip{display:none;position:absolute;top:100%;left:0;z-index:100;background:#1e2a3a;border:1px solid var(--border2);border-radius:6px;padding:8px 12px;font-size:11px;color:var(--text2);width:240px;white-space:normal;line-height:1.5;pointer-events:none}
th:hover .tip{display:block}
td{padding:8px 12px;border-bottom:1px solid var(--border);white-space:nowrap;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--bg3)}
.pos{color:var(--green)}.neg{color:var(--red)}.dim{color:var(--text3)}
.rg td{background:var(--green-bg)}.ry td{background:var(--yellow-bg)}.ro td{background:var(--orange-bg)}.rr td{background:var(--red-bg)}
.ag{color:var(--green)}.ay{color:var(--yellow)}.ao{color:var(--orange)}.ar{color:var(--red)}
.dw{display:flex;gap:20px;flex-wrap:wrap}
.tl{width:180px;flex-shrink:0;display:flex;flex-direction:column;gap:4px;max-height:calc(100vh - 180px);overflow-y:auto}
.tb{background:var(--bg3);border:1px solid var(--border);color:var(--text2);padding:8px 12px;border-radius:6px;cursor:pointer;text-align:left;font-family:var(--mono);font-size:12px;display:flex;justify-content:space-between;align-items:center;transition:all 0.1s}
.tb:hover{background:var(--bg4)}
.tb.active{background:var(--bg4);border-color:var(--accent);color:var(--text)}
.dp{flex:1;min-width:0}
.dh{display:flex;align-items:baseline;gap:16px;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid var(--border);flex-wrap:wrap}
.dt{font-family:var(--head);font-size:32px;font-weight:700}
.dc{font-size:12px;color:var(--text3);background:var(--bg3);padding:4px 10px;border-radius:4px;border:1px solid var(--border)}
.da{font-size:13px;padding:6px 14px;border-radius:6px;font-weight:500}
.da-g{background:var(--green-bg);color:var(--green);border:1px solid #164430}
.da-y{background:var(--yellow-bg);color:var(--yellow);border:1px solid #332a00}
.da-o{background:var(--orange-bg);color:var(--orange);border:1px solid #331e00}
.da-r{background:var(--red-bg);color:var(--red);border:1px solid #331414}
.mg{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:16px}
.mc{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:12px}
.ml{font-size:10px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:0.5px}
.mv{font-size:18px;font-weight:500}
.cs{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px}
.ct{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px}
.pc{display:flex;align-items:flex-end;gap:8px;height:160px;padding:0 4px}
.bw{display:flex;flex-direction:column;align-items:center;flex:1}
.bar{border-radius:4px 4px 0 0;width:40px;min-height:8px}
.bl{font-size:9px;color:var(--text3);margin-top:4px;text-align:center}
.bv{font-size:10px;color:var(--text2);margin-bottom:3px;text-align:center}
.sw{display:flex;flex-direction:column;gap:6px}
.sr{display:flex;align-items:center;gap:10px;padding:8px 12px;background:var(--bg3);border-radius:6px;border:1px solid var(--border)}
.sn{font-size:11px;color:var(--text3);width:80px;flex-shrink:0}
.sb{flex:1;height:6px;background:var(--bg4);border-radius:3px;position:relative}
.sf{height:100%;border-radius:3px;position:absolute;left:0}
.sp{font-size:12px;color:var(--text);width:70px;text-align:right}
.sm{font-size:10px;width:60px;text-align:right}
.cm{position:absolute;width:2px;background:var(--blue);height:14px;top:-4px;border-radius:1px}
.cc{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:10px}
.ck{font-family:var(--head);font-size:20px;font-weight:700}
.cd{font-size:11px;padding:2px 8px;border-radius:4px}
.ce{background:#2d1010;color:var(--red);border:1px solid #4a1f1f}
.cm2{background:var(--green-bg);color:var(--green);border:1px solid #164430}
.cf{font-size:10px;color:var(--text3)}
.cb{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px}
.cx{flex:1;min-width:180px;padding:8px 12px;background:var(--bg3);border-radius:6px;border:1px solid var(--border)}
.cxl{font-size:9px;color:var(--text3);margin-bottom:3px;text-transform:uppercase}
.cxt{font-size:11px;color:var(--text2)}
.empty{color:var(--text3);font-size:12px;padding:32px;text-align:center;border:1px solid var(--border);border-radius:8px}
"""

    js = r"""
const D = window._DATA;
const filters = {cat:'all', tipo:'all', alert:'all'};
let sortCol=null, sortDir=1;

const COLS = ['ticker','categoria','tipo_ab','tipo_empresa','ganancia_pct','precio_actual_usd',
  'ppp_equiv_usd','maximo_desde_entrada_usd','stop_s1_usd','stop_t1_usd','stop_t2_usd',
  'rank_efectivo','s2_decision','fase_modelo','alerta_emoji','alerta_texto'];
const LABELS = {ticker:'Ticker',categoria:'Cat',tipo_ab:'Tipo',tipo_empresa:'Empresa',
  ganancia_pct:'Gan%',precio_actual_usd:'Precio',ppp_equiv_usd:'PPP',
  maximo_desde_entrada_usd:'Maximo',stop_s1_usd:'S1',stop_t1_usd:'T1',stop_t2_usd:'T2',
  rank_efectivo:'Rank',s2_decision:'S2',fase_modelo:'Fase',alerta_emoji:'',alerta_texto:'Alerta'};
const EC = {'🟢':'g','🟡':'y','🟠':'o','🔴':'r'};
const EO = {'🔴':0,'🟠':1,'🟡':2,'🟢':3};

function switchTab(id) {
  ['estado','detalle','cambios','historial'].forEach((t,i) => {
    document.querySelectorAll('.tab')[i].classList.toggle('active', t===id);
    document.getElementById('tab-'+t).classList.toggle('active', t===id);
  });
  if(id==='detalle') renderDetalle();
  if(id==='cambios') renderCambios();
  if(id==='historial') renderHistorial();
}

function setF(key,val,btn) {
  filters[key]=val;
  btn.parentElement.querySelectorAll('.fb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  renderEstado();
}

function fmt(col,val) {
  if(val===null||val===undefined) return '<span class="dim">—</span>';
  if(col==='ganancia_pct') { const c=val>=0?'pos':'neg'; return '<span class="'+c+'">'+(val>=0?'+':'')+val.toFixed(1)+'%</span>'; }
  if(['precio_actual_usd','ppp_equiv_usd','maximo_desde_entrada_usd','stop_s1_usd','stop_t1_usd','stop_t2_usd'].includes(col))
    return '$'+Number(val).toFixed(2);
  if(col==='alerta_emoji') return '<span class="a'+EC[val]+'">'+val+'</span>';
  if(col==='rank_efectivo') return val!==null?'#'+val:'—';
  if(typeof val==='boolean') return val?'<span class="ar">SI</span>':'<span class="dim">no</span>';
  return String(val);
}

function fd() {
  const q=(document.getElementById('search')||{value:''}).value.toLowerCase();
  return D.estado.filter(r=>{
    if(q && !r.ticker?.toLowerCase().includes(q)) return false;
    if(filters.cat==='sat'&&!r.categoria?.includes('Satelites')) return false;
    if(filters.cat==='acc'&&!r.categoria?.includes('Acciones')) return false;
    if(filters.tipo!=='all'&&r.tipo_ab!==filters.tipo) return false;
    if(filters.alert!=='all'&&r.alerta_emoji!==filters.alert) return false;
    return true;
  });
}

function renderEstado() {
  const tips = D.tooltips;
  document.getElementById('estado-head').innerHTML='<tr>'+COLS.map(c=>
    '<th onclick="sortBy(\''+c+'\')">'+LABELS[c]+'<div class="tip">'+(tips[c]||'')+'</div></th>'
  ).join('')+'</tr>';
  let rows=fd();
  if(sortCol) rows.sort((a,b)=>{const av=a[sortCol]??'',bv=b[sortCol]??'';return av<bv?-sortDir:av>bv?sortDir:0;});
  else rows.sort((a,b)=>(EO[a.alerta_emoji]??9)-(EO[b.alerta_emoji]??9));
  document.getElementById('estado-body').innerHTML=rows.map(r=>
    '<tr class="r'+(EC[r.alerta_emoji]||'')+'">'+COLS.map(c=>'<td>'+fmt(c,r[c])+'</td>').join('')+'</tr>'
  ).join('');
}

function sortBy(col) { if(sortCol===col) sortDir*=-1; else{sortCol=col;sortDir=1;} renderEstado(); }

function renderDetalle() {
  const sorted=[...D.estado].sort((a,b)=>(EO[a.alerta_emoji]??9)-(EO[b.alerta_emoji]??9));
  document.getElementById('tl').innerHTML=sorted.map(r=>
    '<button class="tb" onclick="showT(\''+r.ticker+'\')" id="btn-'+r.ticker+'"><span>'+r.ticker+'</span><span class="a'+(EC[r.alerta_emoji]||'')+'">'+r.alerta_emoji+'</span></button>'
  ).join('');
  if(sorted.length) showT(sorted[0].ticker);
}

function showT(ticker) {
  document.querySelectorAll('.tb').forEach(b=>b.classList.toggle('active',b.id==='btn-'+ticker));
  const r=D.estado.find(x=>x.ticker===ticker);
  if(!r) return;
  const ec=EC[r.alerta_emoji]||'g';
  const gan=r.ganancia_pct;
  const ganS=(gan!==null?(gan>=0?'+':'')+gan.toFixed(1)+'%':'—');
  const ganC=gan>=0?'pos':'neg';
  const pr=r.precio_actual_usd, mx=r.maximo_desde_entrada_usd, pp=r.ppp_equiv_usd;
  const stops=[];
  if(r.stop_s1_usd) stops.push({n:'Stop S1',v:r.stop_s1_usd,a:r.s1_activado,c:'#f97316'});
  if(r.stop_t1_usd&&r.t1_activo) stops.push({n:'Stop T1',v:r.stop_t1_usd,a:r.t1_activado,c:'#ef4444'});
  if(r.stop_t2_usd&&r.t2_activo) stops.push({n:'Stop T2',v:r.stop_t2_usd,a:r.t2_activado,c:'#f97316'});
  if(pp) stops.push({n:'PPP equiv',v:pp,a:false,c:'#5a6480'});
  const vals=[pr,mx,pp,...stops.map(s=>s.v)].filter(v=>v!=null);
  const mn=Math.min(...vals)*0.97, mx2=Math.max(...vals)*1.01, rng=mx2-mn;
  const pct=v=>((v-mn)/rng*100).toFixed(1);
  const bars=[{l:'PPP',v:pp,c:'#5a6480'},{l:'Precio',v:pr,c:'#60a5fa'},{l:'Maximo',v:mx,c:'#22c55e'}];
  const barsH=bars.filter(b=>b.v).map(b=>'<div class="bw"><div class="bv">$'+b.v.toFixed(2)+'</div><div class="bar" style="height:'+pct(b.v)+'%;background:'+b.c+';min-height:8px"></div><div class="bl">'+b.l+'</div></div>').join('');
  const stopsH=stops.length?stops.map(s=>{
    const dp=pr&&s.v?((pr-s.v)/pr*100):0;
    const bw=Math.max(0,Math.min(100,(s.v/mx2)*100));
    const cw=pr?(pr/mx2*100):0;
    const cls=s.a?'ar':dp<5?'ao':dp<15?'ay':'ag';
    return '<div class="sr"><span class="sn">'+s.n+'</span><div class="sb"><div class="sf" style="width:'+bw+'%;background:'+s.c+';opacity:0.7"></div><div class="cm" style="left:'+cw+'%"></div></div><span class="sp">$'+s.v.toFixed(2)+'</span><span class="sm '+cls+'">'+(s.a?'ACTIVADO':dp.toFixed(1)+'% marg')+'</span></div>';
  }).join(''):'<div class="dim">Sin stops calculados</div>';
  const sat=r.categoria?.includes('Satelites');
  const extra=sat?
    '<div class="mg" style="margin-top:12px">'+mb('Rank bruto',r.rank_bruto?'#'+r.rank_bruto:'—')+mb('Rank ef.',r.rank_efectivo?'#'+r.rank_efectivo:'—')+mb('Score',r.score_etf?(r.score_etf*100).toFixed(1)+'%':'—')+mb('Delta',r.delta_momentum?(r.delta_momentum*100).toFixed(1)+'%':'—')+'</div><div class="sw" style="margin-top:8px"><div class="sr"><span class="sn">S2</span><span>'+( r.s2_decision||'—')+'</span></div><div class="sr"><span class="sn">S3</span><span class="'+(r.s3_activado?'ar':'ag')+'">'+(r.s3_activado?'SI':'No')+'</span></div></div>':
    '<div class="mg" style="margin-top:12px">'+mb('Fase',r.fase_modelo||'—')+mb('Accion',r.accion_modelo||'—')+mb('Tamano pos.',r.tamano_posicion_pct?r.tamano_posicion_pct+'%':'—')+mb('Flag rev.',r.flag_revision?'SI':'No')+'</div>';
  document.getElementById('dp').innerHTML=
    '<div class="dh"><span class="dt">'+ticker+'</span><span class="dc">'+(r.categoria||'')+'</span>'+(r.tipo_ab?'<span class="dc">Tipo '+r.tipo_ab+'</span>':'')+
    '<span class="da da-'+ec+'">'+r.alerta_emoji+' '+(r.alerta_texto||'')+'</span></div>'+
    '<div class="mg">'+mb('Ganancia','<span class="'+ganC+'">'+ganS+'</span>')+mb('Precio',pr?'$'+pr.toFixed(2):'—')+mb('PPP equiv',pp?'$'+pp.toFixed(2):'—')+mb('Maximo',mx?'$'+mx.toFixed(2):'—')+mb('Sigma',r.sigma_mensual_12m?r.sigma_mensual_12m.toFixed(1)+'%':'—')+mb('Desde',r.fecha_primera_compra||'—')+'</div>'+
    '<div class="cs"><div class="ct">Niveles de precio</div><div class="pc">'+barsH+'</div></div>'+
    '<div class="cs"><div class="ct">Stops y margenes</div><div class="sw">'+stopsH+'</div></div>'+extra;
}

function mb(l,v) { return '<div class="mc"><div class="ml">'+l+'</div><div class="mv">'+v+'</div></div>'; }

function renderCambios() {
  const w=document.getElementById('cambios-list');
  if(!D.cambios.length){w.innerHTML='<div class="empty">Sin cambios registrados aun</div>';return;}
  const sorted=[...D.cambios].sort((a,b)=>(b.fecha_cambio||'').localeCompare(a.fecha_cambio||''));
  w.innerHTML=sorted.map(c=>{
    const ec=EC[c.alerta_nueva]||'g';
    const dir=c.direccion==='EMPEORO'?'ce':'cm2';
    return '<div class="cc"><div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px"><div><span class="ck">'+c.ticker+'</span> <span class="cd '+dir+'">'+c.direccion+'</span></div><span class="cf">'+(c.fecha_cambio||'').toString().slice(0,16)+'</span></div>'+
      '<div style="font-size:12px;margin-bottom:8px"><span class="dim">'+c.alerta_anterior+'</span> → <span class="a'+ec+'">'+c.alerta_nueva+'</span></div>'+
      '<div class="cb"><div class="cx"><div class="cxl">Antes</div><div class="cxt">'+(c.texto_anterior||'—')+'</div></div>'+
      '<div class="cx" style="border-color:'+(ec==='r'?'#4a1f1f':ec==='o'?'#4a2f00':'var(--border)')+'"><div class="cxl">Ahora</div><div class="cxt a'+ec+'">'+(c.texto_nuevo||'—')+'</div></div></div></div>';
  }).join('');
}

function renderHistorial() {
  const q=(document.getElementById('hs')||{value:''}).value.toLowerCase();
  const rows=D.historial.filter(r=>!q||r.ticker?.toLowerCase().includes(q));
  document.getElementById('hc').textContent=rows.length+' registros';
  const cols=['fecha_run','ticker','categoria','alerta_emoji','alerta_texto','ganancia_pct','precio_actual_usd','fase_modelo'];
  const labs={fecha_run:'Fecha',ticker:'Ticker',categoria:'Cat',alerta_emoji:'',alerta_texto:'Alerta',ganancia_pct:'Gan%',precio_actual_usd:'Precio',fase_modelo:'Fase'};
  document.getElementById('hh').innerHTML='<tr>'+cols.map(c=>'<th>'+labs[c]+'</th>').join('')+'</tr>';
  const sorted=[...rows].sort((a,b)=>(b.fecha_run||'').toString().localeCompare((a.fecha_run||'').toString()));
  document.getElementById('hb').innerHTML=sorted.slice(0,300).map(r=>
    '<tr class="r'+(EC[r.alerta_emoji]||'')+'">'+cols.map(c=>'<td>'+fmt(c,r[c])+'</td>').join('')+'</tr>'
  ).join('');
}

renderEstado();
"""

    html = (
        '<!DOCTYPE html>\n'
        '<html lang="es">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>Monitor de Salidas</title>\n'
        '<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700&display=swap" rel="stylesheet">\n'
        '<style>' + css + '</style>\n'
        '<script>window._DATA = ' + data_json + ';</script>\n'
        '</head>\n'
        '<body>\n'
        '<div class="app">\n'
        '<div class="header"><div class="header-title">Monitor de Salidas</div><div class="header-meta">Actualizado: ' + fecha + '</div></div>\n'
        '<div class="tabs">'
        '<div class="tab active" onclick="switchTab(\'estado\')">Estado actual</div>'
        '<div class="tab" onclick="switchTab(\'detalle\')">Detalle por ticker</div>'
        '<div class="tab" onclick="switchTab(\'cambios\')">Cambios</div>'
        '<div class="tab" onclick="switchTab(\'historial\')">Historial</div>'
        '</div>\n'
        '<div id="tab-estado" class="content active">\n'
        '<div class="filters">'
        '<span class="fl">Buscar:</span><input class="fi" id="search" placeholder="ticker..." oninput="renderEstado()" style="width:140px">'
        '<span class="fl">Cat:</span>'
        '<button class="fb active" onclick="setF(\'cat\',\'all\',this)">Todos</button>'
        '<button class="fb" onclick="setF(\'cat\',\'sat\',this)">Satelites</button>'
        '<button class="fb" onclick="setF(\'cat\',\'acc\',this)">Acciones</button>'
        '<span class="fl">Tipo:</span>'
        '<button class="fb active" onclick="setF(\'tipo\',\'all\',this)">A+B</button>'
        '<button class="fb" onclick="setF(\'tipo\',\'A\',this)">Tipo A</button>'
        '<button class="fb" onclick="setF(\'tipo\',\'B\',this)">Tipo B</button>'
        '<span class="fl">Alerta:</span>'
        '<button class="fb active" onclick="setF(\'alert\',\'all\',this)">Todas</button>'
        '<button class="fb ar" onclick="setF(\'alert\',\'🔴\',this)">🔴</button>'
        '<button class="fb ao" onclick="setF(\'alert\',\'🟠\',this)">🟠</button>'
        '<button class="fb ay" onclick="setF(\'alert\',\'🟡\',this)">🟡</button>'
        '<button class="fb ag" onclick="setF(\'alert\',\'🟢\',this)">🟢</button>'
        '</div>\n'
        '<div class="tw"><table><thead id="estado-head"></thead><tbody id="estado-body"></tbody></table></div>\n'
        '</div>\n'
        '<div id="tab-detalle" class="content">'
        '<div class="dw"><div class="tl" id="tl"></div><div class="dp" id="dp"><div class="empty">Selecciona un ticker</div></div></div>'
        '</div>\n'
        '<div id="tab-cambios" class="content"><div id="cambios-list"></div></div>\n'
        '<div id="tab-historial" class="content">'
        '<div class="filters"><span class="fl">Ticker:</span><input class="fi" id="hs" placeholder="filtrar..." oninput="renderHistorial()" style="width:130px"></div>'
        '<div id="hc" style="font-size:11px;color:var(--text3);margin-bottom:12px"></div>'
        '<div class="tw"><table><thead id="hh"></thead><tbody id="hb"></tbody></table></div>'
        '</div>\n'
        '</div>\n'
        '<script>' + js + '</script>\n'
        '</body>\n'
        '</html>\n'
    )
    return html

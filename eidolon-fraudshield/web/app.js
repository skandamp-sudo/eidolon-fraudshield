'use strict';
const $ = id => document.getElementById(id);
let events = [], lastState = null, drawerId = null, lastCount = -1;
const h = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = n => 'SU ' + new Intl.NumberFormat('en-IN',{maximumFractionDigits:0}).format(Number(n)||0);
const shortMoney = n => {
  n = Number(n)||0;
  return n >= 10000000 ? 'SU '+(n/10000000).toFixed(2)+'Cr' : n >= 100000 ? 'SU '+(n/100000).toFixed(2)+'L' : money(n);
};
const fmt = n=>new Intl.NumberFormat('en-IN').format(Number(n)||0);
const pct = v => (Number(v)*100).toFixed(1)+'%';
const scoreColor = t => t==='HIGH'?'#f17b7f':t==='MEDIUM'?'#e9b76b':'#4ad1aa';
function toast(message){const el=$('toast');el.textContent=message;el.classList.add('show');clearTimeout(window._toastTimer);window._toastTimer=setTimeout(()=>el.classList.remove('show'),3700)}
async function api(path,method='GET',body){
  const res=await fetch(path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,cache:'no-store'});
  let data;try{data=await res.json()}catch{throw new Error('Invalid server response')}
  if(!res.ok)throw new Error(data.error||('HTTP '+res.status));return data;
}
function plot(items){
  const samples=[...items].reverse();let line='',fill='';
  if(samples.length){const pts=samples.map((t,i)=>[samples.length===1?310:i*620/(samples.length-1),200-(Math.max(0,Math.min(100,t.score))*2)]);
    line=pts.map(([x,y],i)=>(i?'L':'M')+x.toFixed(2)+' '+y.toFixed(2)).join(' ');
    fill=line+' L'+pts[pts.length-1][0].toFixed(2)+' 200 L'+pts[0][0].toFixed(2)+' 200 Z';
  }$('plot-line').setAttribute('d',line);$('plot-fill').setAttribute('d',fill);
}
function row(t){return `<tr data-open-id="${Number(t.id)}"><td><span class="txid">${h(t.txid)}</span></td><td><span class="tx-type">${h(t.type.replace('_',' '))}</span></td><td><span class="amount">${money(t.amount)}</span></td><td><div class="score-cell" style="color:${scoreColor(t.tier)}">${Number(t.score).toFixed(1)}<div class="score-track"><span style="background:${scoreColor(t.tier)};width:${Math.min(100,Math.max(0,t.score))}%"></span></div></div></td><td><span class="risk-tag ${h(t.tier)}">${h(t.tier)}</span></td><td><span class="decision-tag">${h(t.reviewed_as==='UNREVIEWED'?t.decision:t.reviewed_as.replace('_',' '))}</span></td><td class="td-arrow">↗</td></tr>`}
function render(state){
  lastState=state;events=state.events;const s=state.summary,r=state.replay;
  $('metric-total').textContent=fmt(s.total);$('hero-processed').textContent=fmt(s.total);
  $('metric-high').textContent=fmt(s.high);$('metric-medium').textContent=fmt(s.pending);
  $('metric-volume').textContent=shortMoney(s.volume);$('table-count').textContent=String(s.total);
  $('risk-low').textContent=fmt(s.low);$('risk-medium').textContent=fmt(s.medium);$('risk-high').textContent=fmt(s.high);$('donut-total').textContent=fmt(s.total);
  const total=s.total||1;const low=(s.low/total)*360,medium=(s.medium/total)*360;
  $('donut').style.background=`conic-gradient(#3ac59f 0deg ${low}deg,#edae64 ${low}deg ${low+medium}deg,#f0777b ${low+medium}deg 360deg)`;
  const test=state.model.test||{};$('test-f1').textContent=test.f1==null?'—':pct(test.f1);$('test-recall').textContent=test.recall==null?'—':pct(test.recall);$('test-precision').textContent=test.precision==null?'—':pct(test.precision);
  $('replay-btn').disabled=r.running;$('replay-btn').innerHTML=r.running?'◌ &nbsp; Replay running':'<span>▶</span> Start live replay';
  $('replay-status').textContent=r.error?('Replay error: '+r.error):r.running?'Streaming transactions through the risk engine…':r.done?'Replay completed. Start another run at any time.':'Stream idle. Start a replay to simulate incoming transactions.';
  $('replay-progress').textContent=`${r.done} / ${r.target}`;
  $('refresh-time').textContent='Updated '+new Date().toLocaleTimeString('en-IN');
  if(s.total!==lastCount){
    lastCount=s.total;plot(events);
    $('event-rows').innerHTML=events.length?events.map(row).join(''):'<tr><td colspan="7" class="empty">No transactions yet. Start the live replay to populate the system.</td></tr>';
    const alerts=events.filter(x=>x.tier==='HIGH'&&x.reviewed_as==='UNREVIEWED').slice(0,5);
    $('alerts').innerHTML=alerts.length?alerts.map(t=>`<div class="alert" role="button" tabindex="0" data-open-id="${Number(t.id)}"><div class="alert-left"><span class="alert-icon">!</span><div><strong>${h(t.txid)}</strong><small>${h(t.type)} · ${money(t.amount)}</small></div></div><div class="alert-right"><strong>${Number(t.score).toFixed(1)} / 100</strong><small>OPEN CASE →</small></div></div>`).join(''):'<div class="empty-alert">No recent unreviewed high-risk signals. Try a live replay.</div>';
  }
  if(drawerId!==null){const latest=events.find(e=>e.id===drawerId);if(latest&&$('overlay').classList.contains('open')){const status=$('review-status');if(status)status.textContent=latest.reviewed_as;}}
}
async function refresh(){try{render(await api('/api/state'))}catch(e){$('replay-status').textContent='Connection error: '+e.message}}
function openDrawer(body,title='Investigation'){$('drawer-title').textContent=title;$('drawer-body').innerHTML=body;$('overlay').classList.add('open');$('overlay').setAttribute('aria-hidden','false');$('drawer-close').focus()}
function closeDrawer(){drawerId=null;$('overlay').classList.remove('open');$('overlay').setAttribute('aria-hidden','true');}
function showEvent(id){const t=events.find(x=>x.id===id);if(!t)return toast('Transaction is outside the 65-event live window');drawerId=id;
  const reasons=Array.isArray(t.reasons)?t.reasons:[];
  openDrawer(`<div class="detail-score" style="color:${scoreColor(t.tier)}">${Number(t.score).toFixed(1)}<small>/ 100</small></div><p class="detail-sub"><span class="risk-tag ${h(t.tier)}">${h(t.tier)}</span> &nbsp; Model risk score · not a calibrated probability</p><div class="detail-grid"><div><small>TRANSACTION</small><strong>${h(t.txid)}</strong></div><div><small>TYPE</small><strong>${h(t.type)}</strong></div><div><small>AMOUNT</small><strong>${money(t.amount)}</strong></div><div><small>MODEL DECISION</small><strong>${h(t.decision)}</strong></div><div><small>ORIGIN BALANCE</small><strong>${money(t.old_balance)}</strong></div><div><small>REVIEW STATE</small><strong id="review-status">${h(t.reviewed_as)}</strong></div></div><div class="reason-heading">WHY THIS EVENT WAS SCORED</div>${reasons.map(x=>`<div class="reason-item">${h(x)}</div>`).join('')}<div class="reason-heading">ANALYST DISPOSITION</div><div class="review-actions"><button class="btn btn-secondary" data-disposition="INVESTIGATING">Investigating</button><button class="btn btn-secondary" data-disposition="FALSE_POSITIVE">False positive</button><button class="btn btn-primary" data-disposition="CONFIRMED_FRAUD">Confirm fraud</button></div><p class="drawer-note">${t.source==='synthetic'?'This event was generated for a demonstration. Ground truth labels are synthetic.':'This event was manually provided for scoring.'} Analysts can record a review disposition; this does not block a payment or make a real banking decision.</p>`);
}
function showManual(){drawerId=null;openDrawer(`<p class="drawer-note">Submit a PaySim-style transaction for an explainable model score. The event will be stored locally in the demo history.</p><form id="score-form"><div class="form-row"><label for="type">TRANSACTION TYPE</label><select name="type" id="type"><option>TRANSFER</option><option>CASH_OUT</option><option>PAYMENT</option><option>CASH_IN</option><option>DEBIT</option></select></div><div class="form-row"><label for="amount">AMOUNT</label><input name="amount" id="amount" type="number" min="0" max="1000000000000" step=".01" value="68000" required></div><div class="form-row"><label for="origin">ORIGIN BALANCE</label><input name="origin" id="origin" type="number" min="0" step=".01" value="72000" required></div><div class="form-row"><label for="destination">DESTINATION BALANCE</label><input name="destination" id="destination" type="number" min="0" step=".01" value="4000" required></div><button class="btn btn-primary" type="submit">Score and record transaction →</button></form>`,'Score a transaction')}
async function submitManual(form){const data=new FormData(form);try{const result=await api('/api/score','POST',{step:36,type:data.get('type'),amount:Number(data.get('amount')),oldbalanceOrg:Number(data.get('origin')),oldbalanceDest:Number(data.get('destination')),transactionId:'MANUAL-'+Date.now()});closeDrawer();await refresh();showEvent(result.id);toast('Transaction scored and recorded')}catch(err){toast(err.message)}}
async function disposition(id,value){try{await api('/api/review','POST',{id,disposition:value});closeDrawer();lastCount=-1;await refresh();toast('Analyst review saved in audit history')}catch(err){toast(err.message)}}
function attach(){
  $('replay-btn').addEventListener('click',async()=>{try{await api('/api/demo/start','POST',{count:85});toast('Synthetic replay started');await refresh()}catch(e){toast(e.message)}});
  $('reset-btn').addEventListener('click',async()=>{if(!confirm('Delete all LOCAL demo transaction and review records?'))return;try{await api('/api/demo/reset','POST',{});lastCount=-1;await refresh();toast('Demo history cleared')}catch(e){toast(e.message)}});
  $('manual-btn').addEventListener('click',showManual);$('drawer-close').addEventListener('click',closeDrawer);
  $('overlay').addEventListener('click',e=>{if(e.target.dataset.close)closeDrawer();if(e.target.dataset.disposition&&drawerId!==null)disposition(drawerId,e.target.dataset.disposition)});
  $('drawer-body').addEventListener('submit',e=>{if(e.target.id==='score-form'){e.preventDefault();submitManual(e.target)}});
  document.addEventListener('click',e=>{const tr=e.target.closest('[data-open-id]');if(tr)showEvent(Number(tr.dataset.openId))});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDrawer();if(e.key==='Enter'&&e.target.matches('.alert[data-open-id]'))showEvent(Number(e.target.dataset.openId))});
  document.querySelectorAll('.nav-link').forEach(a=>a.addEventListener('click',()=>{document.querySelectorAll('.nav-link').forEach(x=>x.classList.remove('active'));a.classList.add('active')}));
}
function clock(){const d=new Date();$('clock').textContent=d.toLocaleTimeString('en-IN',{hour12:false})}
attach();clock();setInterval(clock,1000);refresh();setInterval(refresh,1400);

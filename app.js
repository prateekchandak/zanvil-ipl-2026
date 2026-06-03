const cur=document.getElementById('cursor');
const ring=document.getElementById('cursor-ring');
let mx=0,my=0,rx=0,ry=0;
document.addEventListener('mousemove',e=>{mx=e.clientX;my=e.clientY;cur.style.left=mx+'px';cur.style.top=my+'px';});
(function animRing(){rx+=(mx-rx)*.12;ry+=(my-ry)*.12;ring.style.left=rx+'px';ring.style.top=ry+'px';requestAnimationFrame(animRing);})();
window.addEventListener('scroll',()=>{
document.getElementById('nav').classList.toggle('scrolled',scrollY>60);
},{passive:true});
setTimeout(()=>document.getElementById('hl1').classList.add('revealed'),100);
setTimeout(()=>document.getElementById('hl2').classList.add('revealed'),280);
setTimeout(()=>document.getElementById('hl3').classList.add('revealed'),460);
const cObs=new IntersectionObserver(entries=>{
entries.forEach(e=>{
if(!e.isIntersecting)return;
const el=e.target,target=+el.dataset.count,t0={v:null};
(function step(ts){
if(!t0.v)t0.v=ts;
const p=Math.min((ts-t0.v)/1200,1),ease=1-Math.pow(1-p,3);
el.textContent=Math.round(ease*target);
if(p<1)requestAnimationFrame(step);
})(performance.now());
cObs.unobserve(el);
});
},{threshold:.5});
document.querySelectorAll('[data-count]').forEach(el=>cObs.observe(el));
const rObs=new IntersectionObserver(entries=>{
entries.forEach(e=>{if(e.isIntersecting){e.target.classList.add('vis');rObs.unobserve(e.target);}});
},{threshold:.1});
document.querySelectorAll('.reveal').forEach(el=>rObs.observe(el));
const PORTFOLIO=[
{name:'NovaSilicon',ticker:'PRIVATE',layer:'Chips & Silicon',stage:'Series A',
desc:'Designing next-generation AI ASICs with 3x the FLOP/W of incumbent GPUs. Their sparse-compute architecture is purpose-built for transformer inference.',
value:4200000,cost:2000000,dailyChg:0.023,alloc:14},
{name:'MemScale',ticker:'PRIVATE',layer:'Memory & Storage',stage:'Seed',
desc:'CXL memory pooling fabric that decouples compute and memory, allowing AI clusters to share bandwidth dynamically. Addressing the memory wall at the system level.',
value:1800000,cost:1000000,dailyChg:-0.008,alloc:6},
{name:'NVIDIA',ticker:'NVDA',layer:'Chips & Silicon',stage:'Public',
desc:'The dominant AI accelerator franchise. NVDA\'s CUDA moat and H/B-series GPUs power the majority of global AI training workloads. Core long position.',
value:8500000,cost:5200000,dailyChg:0.018,alloc:28},
{name:'Marvell Technology',ticker:'MRVL',layer:'Networking & Interconnect',stage:'Public',
desc:'Leading custom ASIC and interconnect silicon for hyperscale AI infrastructure. Their co-packaged optics roadmap positions them as a key beneficiary of the optical interconnect transition.',
value:3100000,cost:2400000,dailyChg:0.011,alloc:10},
{name:'VoltAI Energy',ticker:'PRIVATE',layer:'Power & Energy',stage:'Series B',
desc:'Modular behind-the-meter power systems for AI data centers, combining small-scale gas turbines with battery storage. Solves the 18-month grid interconnect bottleneck.',
value:5600000,cost:3500000,dailyChg:0.004,alloc:18},
{name:'FabricOS',ticker:'PRIVATE',layer:'Systems Software',stage:'Series A',
desc:'Distributed training orchestration layer that abstracts heterogeneous AI accelerator clusters. Reduces model-to-cluster time from weeks to hours for frontier labs.',
value:2900000,cost:1500000,dailyChg:-0.012,alloc:9},
{name:'CryoLink',ticker:'PRIVATE',layer:'Data Center Infra',stage:'Seed',
desc:'Two-phase immersion cooling systems engineered for ultra-dense AI rack deployments (>100kW/rack). 40% lower PUE than air-cooled alternatives at equivalent density.',
value:1400000,cost:1000000,dailyChg:0.031,alloc:4},
{name:'Broadcom',ticker:'AVGO',layer:'Networking & Interconnect',stage:'Public',
desc:'Custom AI ASIC and networking silicon for the hyperscalers. Their XPU business and Ethernet switching portfolio are core AI infrastructure plays.',
value:4800000,cost:3600000,dailyChg:0.007,alloc:15},
{name:'LatticeAI',ticker:'PRIVATE',layer:'Chips & Silicon',stage:'Pre-Seed',
desc:'Photonic neural network inference chip using light instead of electricity for matrix multiplication — targeting 100x energy efficiency gains for edge AI inference.',
value:800000,cost:500000,dailyChg:-0.021,alloc:2},
{name:'GridNest',ticker:'PRIVATE',layer:'Power & Energy',stage:'Series A',
desc:'AI-native grid management software that optimizes power procurement and consumption across multi-site data center portfolios. SaaS model with utility partnerships.',
value:2200000,cost:1200000,dailyChg:0.009,alloc:7},
{name:'OpticCore',ticker:'PRIVATE',layer:'Networking & Interconnect',stage:'Seed',
desc:'Co-packaged optics chiplets for next-generation AI switch ASICs. Eliminates the copper bottleneck in rack-scale AI interconnects, enabling 10+ Tb/s per port.',
value:1100000,cost:800000,dailyChg:0.044,alloc:4},
{name:'CoreWeave Systems',ticker:'SMCI',layer:'Data Center Infra',stage:'Public',
desc:'GPU-optimized server systems and liquid-cooled rack solutions for AI data centers. Key supply-chain partner for NVDA-based cluster deployments.',
value:1500000,cost:1800000,dailyChg:-0.033,alloc:5},
];
const LAYER_BADGE_COLORS={
'Chips & Silicon':'rgba(0,229,255,0.15)',
'Memory & Storage':'rgba(91,124,250,0.15)',
'Data Center Infra':'rgba(139,92,246,0.15)',
'Power & Energy':'rgba(0,230,118,0.15)',
'Networking & Interconnect':'rgba(245,158,11,0.15)',
'Systems Software':'rgba(236,72,153,0.15)',
};
const grid=document.getElementById('portfolioGrid');
PORTFOLIO.forEach(p=>{
const totalRet=((p.value-p.cost)/p.cost*100).toFixed(1);
const card=document.createElement('div');
card.className='portfolio-card reveal';
card.innerHTML=`
<div class="pc-header">
<div>
<div class="pc-badge" style="background:${LAYER_BADGE_COLORS[p.layer]||'rgba(91,124,250,0.1)'};">${p.layer}</div>
<div class="pc-stage">${p.stage}</div>
</div>
<div class="pc-ticker">${p.ticker}</div>
</div>
<div class="pc-name">${p.name}</div>
<p class="pc-desc">${p.desc}</p>
<div class="pc-metrics">
<div>
<div class="pc-metric-label">Position Value</div>
<div class="pc-metric-value">$${(p.value/1e6).toFixed(1)}M</div>
</div>
<div>
<div class="pc-metric-label">Total Return</div>
<div class="pc-metric-value" style="color:${+totalRet>=0?'var(--green)':'var(--red)'}">
${+totalRet>=0?'+':''}${totalRet}%
</div>
</div>
</div>`;
grid.appendChild(card);
});
const totalVal=PORTFOLIO.reduce((s,p)=>s+p.value,0);
const totalCost=PORTFOLIO.reduce((s,p)=>s+p.cost,0);
const dailyDollar=PORTFOLIO.reduce((s,p)=>s+p.value*p.dailyChg,0);
const dailyPct=dailyDollar/totalVal*100;
const totalRetDollar=totalVal-totalCost;
const totalRetPct=(totalRetDollar/totalCost)*100;
function fmt(n){return(n>=0?'+':'')+n.toFixed(2)+'%';}
function fmtDollar(n){
const abs=Math.abs(n);
const s=n>=0?'+':'-';
if(abs>=1e6)return s+'$'+(abs/1e6).toFixed(2)+'M';
return s+'$'+(abs/1e3).toFixed(0)+'K';
}
document.getElementById('totalValue').textContent='$'+(totalVal/1e6).toFixed(2)+'M';
document.getElementById('totalChange').textContent=fmtDollar(dailyDollar)+' today';
document.getElementById('totalChange').className='po-change '+(dailyDollar>=0?'pos-up':'pos-down');
document.getElementById('dailyReturn').textContent=fmtDollar(dailyDollar);
document.getElementById('dailyReturn').style.color=dailyDollar>=0?'var(--green)':'var(--red)';
document.getElementById('dailyPct').textContent=fmt(dailyPct);
document.getElementById('dailyPct').className='po-change '+(dailyPct>=0?'pos-up':'pos-down');
document.getElementById('totalReturn').textContent=fmtDollar(totalRetDollar);
document.getElementById('totalReturn').style.color=totalRetDollar>=0?'var(--green)':'var(--red)';
document.getElementById('totalReturnPct').textContent=fmt(totalRetPct);
document.getElementById('totalReturnPct').className='po-change '+(totalRetPct>=0?'pos-up':'pos-down');
let prices=PORTFOLIO.map(p=>({...p}));
function genSparkline(history){
const mn=Math.min(...history),mx=Math.max(...history),range=mx-mn||1;
const pts=history.map((v,i)=>`${(i/(history.length-1)*76).toFixed(1)},${(28-(v-mn)/range*26).toFixed(1)}`).join(' ');
const isUp=history[history.length-1]>=history[0];
return `<svg class="sparkline" viewBox="0 0 80 32"><polyline points="${pts}" fill="none" stroke="${isUp?'var(--green)':'var(--red)'}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
const histories=PORTFOLIO.map(p=>{
const h=[];for(let i=0;i<14;i++)h.push(p.value*(1+(Math.random()-.48)*0.04));return h;
});
function renderTable(){
const tbl=document.getElementById('returnsTable');
tbl.innerHTML='';
prices.forEach((p,i)=>{
const dayChgDollar=p.value*p.dailyChg;
const isUp=p.dailyChg>=0;
const row=document.createElement('div');
row.className='returns-row';
row.innerHTML=`
<div><div class="rr-name">${p.name}</div><div class="rr-ticker">${p.ticker} · ${p.layer}</div></div>
<div class="rr-val">$${(p.value/1e6).toFixed(2)}M</div>
<div><span class="rr-change ${isUp?'rr-up':'rr-down'}">${isUp?'▲':'▼'} ${Math.abs(p.dailyChg*100).toFixed(2)}%</span>
<div style="font-size:11px;color:var(--muted);margin-top:4px">${fmtDollar(dayChgDollar)}</div></div>
<div class="alloc-col">
<div style="font-size:13px;font-weight:600">${p.alloc}%</div>
<div class="rr-bar"><div class="rr-bar-fill" style="width:${p.alloc*3}%;background:${isUp?'var(--green)':'var(--red)'}"></div></div>
</div>
<div>${genSparkline(histories[i])}</div>`;
tbl.appendChild(row);
});
}
renderTable();
setInterval(()=>{
prices=prices.map((p,i)=>{
const drift=(Math.random()-.49)*0.003;
const newVal=p.value*(1+drift);
const newChg=p.dailyChg+drift;
histories[i].push(newVal);histories[i].shift();
return{...p,value:newVal,dailyChg:newChg};
});
const newDaily=prices.reduce((s,p)=>s+p.value*p.dailyChg,0);
const newTotal=prices.reduce((s,p)=>s+p.value,0);
document.getElementById('totalValue').textContent='$'+(newTotal/1e6).toFixed(2)+'M';
document.getElementById('dailyReturn').textContent=fmtDollar(newDaily);
document.getElementById('dailyReturn').style.color=newDaily>=0?'var(--green)':'var(--red)';
const newDPct=newDaily/newTotal*100;
document.getElementById('dailyPct').textContent=fmt(newDPct);
document.getElementById('dailyPct').className='po-change '+(newDPct>=0?'pos-up':'pos-down');
document.getElementById('totalChange').textContent=fmtDollar(newDaily)+' today';
document.getElementById('totalChange').className='po-change '+(newDaily>=0?'pos-up':'pos-down');
document.getElementById('lastUpdated').textContent='Updated '+new Date().toLocaleTimeString();
renderTable();
},5000);
const tickerData=PORTFOLIO.filter(p=>p.ticker!=='PRIVATE').map(p=>({
name:p.name,ticker:p.ticker,chg:p.dailyChg
}));
function buildTicker(){
const track=document.getElementById('tickerTrack');
const all=[...tickerData,...tickerData,...tickerData,...tickerData];
track.innerHTML=all.map(t=>`
<div class="ticker-item">
<span class="name">${t.ticker}</span>
<span class="ticker-change ${t.chg>=0?'ticker-up':'ticker-down'}">${t.chg>=0?'▲':'▼'} ${Math.abs(t.chg*100).toFixed(2)}%</span>
</div>`).join('');
}
buildTicker();
document.querySelectorAll('.portfolio-card.reveal').forEach(el=>rObs.observe(el));
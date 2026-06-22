"""
POSCOPE 정적 HTML 내보내기
현재 DB의 프로젝트 데이터를 그대로 박아넣은, 서버 없이 파일만으로 열어볼 수 있는
읽기 전용 스냅샷(POSCOPE_정적공유.html)을 생성한다.
- 필터/카드/상세패널/AI요약/SF이력 보기는 그대로 동작
- 자동수집·수동입력·엑셀업로드·Teams공유처럼 서버가 필요한 기능은 안내 토스트로 대체
"""

import json
import os
from datetime import datetime

import db

BASE_DIR = os.path.dirname(__file__)
SRC = os.path.join(BASE_DIR, "index.html")
OUT = os.path.join(BASE_DIR, "POSCOPE.html")

STATIC_SCRIPT_TEMPLATE = """
function updateClock(){const n=new Date();document.getElementById('clock').textContent=n.toLocaleDateString('ko-KR')+' '+n.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'});}
updateClock();setInterval(updateClock,1000);
function switchTab(t){document.querySelectorAll('.tab-btn').forEach((b,i)=>b.classList.toggle('active',['dashboard','upload'][i]===t));document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));document.getElementById('tab-'+t).classList.add('active');}
function showToast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),3200);}

let DATA = __DATA_JSON__;
let selId=null,hist=[];
let flt={src:'all',div:'all',country:'all',sf:'all'};

const DIV_LABELS={steel:'철강본부',materials:'소재바이오본부',energy:'에너지사업본부',gas:'가스사업본부'};
function divLabel(d){return DIV_LABELS[d]||'철강본부';}

function renderCards(){
  const filtered=DATA.filter(p=>{
    if(flt.src==='auto'&&!p.isAuto)return false;
    if(flt.src==='manual'&&p.isAuto)return false;
    if(flt.div!=='all'&&p.div!==flt.div)return false;
    if(flt.country!=='all'&&p.country!==flt.country)return false;
    if(flt.sf==='y'&&p.sfHistory.length===0)return false;
    if(flt.sf==='n'&&p.sfHistory.length>0)return false;
    return true;
  });
  const tagCls={steel:'tc',energy:'te',materials:'ta',gas:'tg'};
  document.getElementById('card-list').innerHTML=filtered.map(p=>`
    <div class="card${selId===p.id?' selected':''}${!p.isAuto?' manual':''}" onclick="openDetail(${p.id})">
      ${p.isNew&&p.isAuto?'<div class="nbadge">NEW</div>':''}
      ${!p.isAuto?'<div class="mbadge">수동입력</div>':''}
      <div class="ct"><div class="ctitle">${p.title}</div>
        <span class="tag ${p.isAuto?(tagCls[p.div]||'tc'):'tm'}">${divLabel(p.div)}</span></div>
      <div class="cmeta">
        <span>🌍 ${p.region||p.country}</span>
        <span>⚖️ ${p.size||'-'}</span>
        <span>🔩 ${p.steel||p.item||'-'}</span>
        <span>${p.isAuto?'📡 '+p.source:'✏️ 수동'}</span>
      </div>
      <div class="cbottom">
        <div class="sfb${p.sfHistory.length===0?' none':''}">${p.sfHistory.length>0?`📋 SF이력 ${p.sfHistory.length}건`:'📋 신규 거래선'}</div>
        <div class="dl${p.urgency?' urg':''}">마감 ${p.deadline||'-'}${p.urgency?' ⚠️':''}</div>
      </div>
    </div>`).join('');
  document.getElementById('s-total').textContent=DATA.length;
  document.getElementById('s-auto').textContent=DATA.filter(x=>x.isAuto).length;
  document.getElementById('s-manual').textContent=DATA.filter(x=>!x.isAuto).length;
  document.getElementById('s-sf').textContent=DATA.filter(x=>x.sfHistory.length>0).length;
}

function openDetail(id){
  selId=id;const p=DATA.find(x=>x.id===id);
  document.getElementById('dpanel').classList.add('open');
  const sfHtml=p.sfHistory.length>0
    ?p.sfHistory.map(h=>`<div class="sfi"><div class="sd">${h.date}</div><div class="sw">👤 ${h.who}</div><div class="sm">${h.memo}</div></div>`).join('')
    :'<div class="sfempty">Salesforce 이력 없음<br>신규 개척 필요</div>';
  document.getElementById('dcontent').innerHTML=`
    <h2>${p.title}</h2>
    <div style="margin:7px 0 14px"><span class="tag ${p.isAuto?({steel:'tc',energy:'te',materials:'ta',gas:'tg'}[p.div]||'tc'):'tm'}">${divLabel(p.div)}</span>
    &nbsp;<span style="font-size:10px;color:var(--sub)">${p.isAuto?'📡 '+p.source+' · '+p.sourceDate:'✏️ 수동입력'}</span></div>
    ${p.aiSummary?`<div class="ais"><div class="al">🤖 AI 분석 요약</div><p>${p.aiSummary}</p></div>`:''}
    <div class="ds"><h4>프로젝트 정보</h4>
      <div class="dr"><span class="k">발주처</span><span class="v">${p.owner||'-'}</span></div>
      <div class="dr"><span class="k">EPC</span><span class="v">${p.epc||'-'}</span></div>
      <div class="dr"><span class="k">국가</span><span class="v">${p.region||p.country||'-'}</span></div>
      <div class="dr"><span class="k">규모</span><span class="v">${p.size||'-'}</span></div>
      <div class="dr"><span class="k">강재 품목</span><span class="v">${p.steel||p.item||'-'}</span></div>
      <div class="dr"><span class="k">예상 물량</span><span class="v">${p.tons||'-'}</span></div>
      <div class="dr"><span class="k">마감일</span><span class="v${p.urgency?' dl urg':''}">${p.deadline||'-'}${p.urgency?' ⚠️':''}</span></div>
      ${p.memo?`<div class="dr"><span class="k">메모</span><span class="v">${p.memo}</span></div>`:''}
      ${p.link?`<div class="dr"><span class="k">출처 링크</span><span class="v"><a href="${p.link}" target="_blank" rel="noopener">${p.link}</a></span></div>`:''}
    </div>
    <div class="ds"><h4>📋 Salesforce 이력 (${p.sfHistory.length}건)</h4>
      <div class="sfh">${sfHtml}</div>
    </div>
    <button class="tbtn" onclick="sendTeams(${p.id})">💬 Teams 채널에 공유</button>`;
  renderCards();
}
function closeDetail(){selId=null;document.getElementById('dpanel').classList.remove('open');renderCards();}
function setFilter(el,type,val){el.closest('.fg').querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));el.classList.add('active');flt[type]=val;renderCards();}

const CHART_COLORS=['#3b82f6','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4','#f97316','#84cc16','#ec4899','#14b8a6'];
let chartInstances={};
function renderCharts(){
  Object.values(chartInstances).forEach(c=>{try{c.destroy();}catch(e){}});chartInstances={};

  const regionMap={};DATA.forEach(p=>{const r=p.country||'기타';regionMap[r]=(regionMap[r]||0)+1;});
  chartInstances.region=new Chart(document.getElementById('chartRegion'),{
    type:'doughnut',
    data:{labels:Object.keys(regionMap),datasets:[{data:Object.values(regionMap),backgroundColor:CHART_COLORS,borderWidth:2,borderColor:'#fff'}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{font:{size:11},boxWidth:12}}}}
  });

  const stMap={'검토중':0,'오퍼제출':0,'협상중':0,'수주':0,'유찰':0};
  DATA.forEach(p=>{const s=p.status||'검토중';if(s in stMap)stMap[s]++;});
  chartInstances.status=new Chart(document.getElementById('chartStatus'),{
    type:'bar',
    data:{labels:Object.keys(stMap),datasets:[{data:Object.values(stMap),backgroundColor:['#3b82f6','#f59e0b','#f97316','#10b981','#9ca3af'],borderRadius:6}]},
    options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{beginAtZero:true,ticks:{stepSize:1}}}}
  });

  const divMap={'철강본부':0,'소재바이오본부':0,'에너지사업본부':0,'가스사업본부':0};
  DATA.forEach(p=>{divMap[divLabel(p.div)]++;});
  chartInstances.div=new Chart(document.getElementById('chartDiv'),{
    type:'bar',
    data:{labels:Object.keys(divMap),datasets:[{data:Object.values(divMap),backgroundColor:['#3b82f6','#10b981','#f59e0b','#6b46c1'],borderRadius:6}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,ticks:{stepSize:1}}}}
  });

  const srcMap={};DATA.forEach(p=>{const s=p.source||'기타';srcMap[s]=(srcMap[s]||0)+1;});
  chartInstances.source=new Chart(document.getElementById('chartSource'),{
    type:'doughnut',
    data:{labels:Object.keys(srcMap),datasets:[{data:Object.values(srcMap),backgroundColor:CHART_COLORS.slice(3),borderWidth:2,borderColor:'#fff'}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{font:{size:11},boxWidth:12}}}}
  });

  const today=new Date(),todayStr=today.toISOString().split('T')[0];
  const in60=new Date(Date.now()+60*86400000).toISOString().split('T')[0];
  const upcoming=DATA.filter(p=>p.deadline&&p.deadline>=todayStr&&p.deadline<=in60).sort((a,b)=>a.deadline.localeCompare(b.deadline));
  document.getElementById('deadlineList').innerHTML=upcoming.length
    ?upcoming.map(p=>{
        const days=Math.round((new Date(p.deadline)-today)/86400000);
        const cls=days<=7?'urgent':days<=30?'warn':'ok';
        return `<div class="dl-item"><div class="dl-days ${cls}">D-${days}</div><div class="dl-title">${p.title}</div><div class="dl-meta">${p.deadline} · ${p.region||p.country}</div></div>`;
      }).join('')
    :'<div style="font-size:12px;color:var(--sub);text-align:center;padding:14px;">60일 이내 마감 프로젝트가 없습니다.</div>';

  ['steel','materials','energy','gas'].forEach(div=>{
    const dp=DATA.filter(p=>p.div===div);
    const won=dp.filter(p=>p.status==='수주').length;
    const inprog=dp.filter(p=>['검토중','오퍼제출','협상중'].includes(p.status||'검토중')).length;
    const el=document.getElementById('dc-'+div);
    if(el){
      el.children[0].querySelector('.v').textContent=dp.length;
      el.children[1].querySelector('.v').textContent=won;
      el.children[2].querySelector('.v').textContent=inprog;
    }
  });
}

function sendTeams(id){showToast('⚠️ 정적 파일 버전입니다 — Teams 공유는 사내망 서버 링크에서만 동작합니다.');}
function runScan(){showToast('⚠️ 정적 파일 버전입니다 — 자동수집은 사내망 서버 링크에서만 동작합니다.');}
function onDrop(e){e.preventDefault();showToast('⚠️ 정적 파일 버전입니다 — 업로드는 사내망 서버 링크에서만 동작합니다.');}
function onFileSelect(e){showToast('⚠️ 정적 파일 버전입니다 — 업로드는 사내망 서버 링크에서만 동작합니다.');}
function importCards(){showToast('⚠️ 정적 파일 버전입니다 — 업로드는 사내망 서버 링크에서만 동작합니다.');}
function addManual(){showToast('⚠️ 정적 파일 버전입니다 — 추가 내용은 저장되지 않습니다. 사내망 서버 링크를 이용해주세요.');}

document.getElementById('hlist').innerHTML='<div style="font-size:12px;color:var(--sub);text-align:center;padding:14px;">정적 파일 버전에서는 업로드 이력이 표시되지 않습니다.</div>';
renderCards();
renderCharts();
"""


def main():
    db.init_db()
    projects = db.list_projects()

    with open(SRC, encoding="utf-8") as f:
        html = f.read()

    html = html.replace('src="/static_libs/', 'src="static_libs/')

    head, rest = html.split("<script>", 1)
    _old_script, tail = rest.split("</script>", 1)

    data_json = json.dumps(projects, ensure_ascii=False)
    new_script = STATIC_SCRIPT_TEMPLATE.replace("__DATA_JSON__", data_json)

    snapshot_note = (
        f'<div style="background:#fff3cd;color:#856404;padding:8px 32px;'
        f'font-size:12px;text-align:center;border-bottom:1px solid #ffe69c;">'
        f'📌 정적 보기 전용 스냅샷 — {datetime.now().strftime("%Y-%m-%d %H:%M")} 기준 데이터 '
        f'(이후 변경사항은 반영되지 않습니다. 최신 데이터·입력 기능은 사내망 서버 링크를 이용하세요)</div>'
    )
    head = head.replace("<body>", "<body>" + snapshot_note, 1)

    out_html = head + "<script>" + new_script + "</script>" + tail
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(out_html)

    print(f"생성 완료: {OUT} ({len(projects)}건 포함)")


if __name__ == "__main__":
    main()

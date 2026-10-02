import os, json, datetime as dt, secrets, concurrent.futures
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, String, Integer, Float, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler
from starlette.middleware.sessions import SessionMiddleware

DB=os.getenv('DATABASE_URL','sqlite:///./minion.db')
engine=create_engine(DB, connect_args={'check_same_thread':False} if DB.startswith('sqlite') else {}, pool_pre_ping=True)
class Base(DeclarativeBase): pass
class Agent(Base):
    __tablename__='agents'; id:Mapped[int]=mapped_column(Integer,primary_key=True); code:Mapped[str]=mapped_column(String(4),unique=True); name:Mapped[str]=mapped_column(String(100)); division:Mapped[str]=mapped_column(String(50)); mission:Mapped[str]=mapped_column(Text); status:Mapped[str]=mapped_column(String(20),default='idle'); score:Mapped[float]=mapped_column(Float,default=100)
class Workspace(Base):
    __tablename__='workspaces'; id:Mapped[int]=mapped_column(Integer,primary_key=True); agent_id:Mapped[int]=mapped_column(ForeignKey('agents.id'),unique=True); desk_notes:Mapped[str]=mapped_column(Text,default=''); current_task_id:Mapped[Optional[int]]=mapped_column(Integer,nullable=True); inbox:Mapped[str]=mapped_column(Text,default='[]'); outbox:Mapped[str]=mapped_column(Text,default='[]'); updated_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow)
class Warehouse(Base):
    __tablename__='warehouses'; id:Mapped[int]=mapped_column(Integer,primary_key=True); agent_id:Mapped[int]=mapped_column(ForeignKey('agents.id'),unique=True); products:Mapped[str]=mapped_column(Text,default='[]'); suppliers:Mapped[str]=mapped_column(Text,default='[]'); evidence:Mapped[str]=mapped_column(Text,default='[]'); opportunities:Mapped[str]=mapped_column(Text,default='[]'); inventory_proposals:Mapped[str]=mapped_column(Text,default='[]')
class Task(Base):
    __tablename__='tasks'; id:Mapped[int]=mapped_column(Integer,primary_key=True); title:Mapped[str]=mapped_column(String(200)); instructions:Mapped[str]=mapped_column(Text); assigned_agent:Mapped[Optional[int]]=mapped_column(ForeignKey('agents.id'),nullable=True); status:Mapped[str]=mapped_column(String(20),default='queued'); priority:Mapped[int]=mapped_column(Integer,default=50); result:Mapped[str]=mapped_column(Text,default=''); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); completed_at:Mapped[Optional[dt.datetime]]=mapped_column(DateTime,nullable=True)
class Opportunity(Base):
    __tablename__='opportunities'; id:Mapped[int]=mapped_column(Integer,primary_key=True); product:Mapped[str]=mapped_column(String(200)); source_agent:Mapped[int]=mapped_column(ForeignKey('agents.id')); buy_cost:Mapped[float]=mapped_column(Float,default=0); sell_price:Mapped[float]=mapped_column(Float,default=0); est_fees:Mapped[float]=mapped_column(Float,default=0); est_profit:Mapped[float]=mapped_column(Float,default=0); score:Mapped[float]=mapped_column(Float,default=0); approved:Mapped[bool]=mapped_column(Boolean,default=False); evidence:Mapped[str]=mapped_column(Text,default='')
class Treasury(Base):
    __tablename__='treasury'; id:Mapped[int]=mapped_column(Integer,primary_key=True); available_cash:Mapped[float]=mapped_column(Float,default=0); daily_limit:Mapped[float]=mapped_column(Float,default=500); spent_today:Mapped[float]=mapped_column(Float,default=0); spend_date:Mapped[str]=mapped_column(String(10),default=''); live_mode:Mapped[bool]=mapped_column(Boolean,default=False)
class Proposal(Base):
    __tablename__='proposals'; id:Mapped[int]=mapped_column(Integer,primary_key=True); agent_id:Mapped[int]=mapped_column(ForeignKey('agents.id')); title:Mapped[str]=mapped_column(String(200)); amount:Mapped[float]=mapped_column(Float,default=0); est_profit:Mapped[float]=mapped_column(Float,default=0); rationale:Mapped[str]=mapped_column(Text,default=''); status:Mapped[str]=mapped_column(String(20),default='pending'); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow)
class WorldEvent(Base):
    __tablename__='world_events'; id:Mapped[int]=mapped_column(Integer,primary_key=True); agent_id:Mapped[Optional[int]]=mapped_column(Integer,nullable=True); event:Mapped[str]=mapped_column(String(80)); detail:Mapped[str]=mapped_column(Text,default=''); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow)
class WorldStructure(Base):
    __tablename__='world_structures'; id:Mapped[int]=mapped_column(Integer,primary_key=True); key:Mapped[str]=mapped_column(String(40),unique=True); name:Mapped[str]=mapped_column(String(100)); kind:Mapped[str]=mapped_column(String(40)); level:Mapped[int]=mapped_column(Integer,default=1); progress:Mapped[float]=mapped_column(Float,default=0); x:Mapped[float]=mapped_column(Float,default=0); y:Mapped[float]=mapped_column(Float,default=0); workers:Mapped[int]=mapped_column(Integer,default=0); updated_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow)
Base.metadata.create_all(engine)
DIVISIONS=[('Market Intelligence',1,20,'Track demand, trends, categories, keywords, competitors and customer pain points.'),('Sourcing',21,40,'Find legitimate suppliers, manufacturers, wholesale pricing, MOQs, freight and lead times.'),('Product Underwriting',41,60,'Calculate landed cost, fees, margins, ROI, demand quality and opportunity scores.'),('Sales & Listings',61,75,'Prepare compliant listing research, positioning, pricing and merchandising recommendations.'),('Operations',76,90,'Monitor inventory proposals, replenishment, logistics, task throughput and performance.'),('Risk & Audit',91,100,'Audit evidence, duplicates, IP/policy risk, supplier risk, financial assumptions and agent quality.')]
def seed():
    with Session(engine) as s:
        if not s.query(Agent).count():
            c=Agent(code='000',name='Commander',division='Command',mission='Supervise all Minions, assign work, audit outputs, enforce risk limits, maintain task flow, and produce owner reports.'); s.add(c); s.flush(); s.add(Workspace(agent_id=c.id)); s.add(Warehouse(agent_id=c.id))
            for div,start,end,mission in DIVISIONS:
                for n in range(start,end+1):
                    a=Agent(code=f'{n:03}',name=f'Minion {n:03}',division=div,mission=f'{mission} Specialized worker #{n:03}. Store all work in your workspace and warehouse.'); s.add(a); s.flush(); s.add(Workspace(agent_id=a.id)); s.add(Warehouse(agent_id=a.id))
            s.commit()
        if not s.query(Treasury).first():
            s.add(Treasury(available_cash=0,daily_limit=500,spent_today=0,spend_date=dt.date.today().isoformat(),live_mode=False))
            s.commit()
        if not s.query(WorldStructure).count():
            starter=[('hq','COMMAND HQ','hq',44,40),('lab','RESEARCH LAB','lab',67,14),('warehouse','WAREHOUSE','warehouse',8,48),('market','MARKETPLACE','market',69,67),('power','POWER YARD','power',9,72),('homes','MINION VILLAGE','homes',45,72),('site','CITY EXPANSION','construction',35,12)]
            for key,name,kind,x,y in starter: s.add(WorldStructure(key=key,name=name,kind=kind,x=x,y=y,progress=25 if key=='site' else 100))
            s.commit()
seed()
app=FastAPI(title='MINION Command Center',version='1.1'); app.add_middleware(SessionMiddleware,secret_key=os.getenv('SESSION_SECRET',secrets.token_hex(32)),max_age=86400*7,https_only=False)
CSS='''<style>
*{box-sizing:border-box}body{margin:0;background:#061019;color:#e8f0f6;font-family:Inter,Arial,sans-serif}.top{padding:15px 22px;border-bottom:1px solid #21303c;display:flex;justify-content:space-between;align-items:center;background:#091721}.brand{font-weight:900;letter-spacing:2px}.wrap{max-width:1600px;margin:auto;padding:16px}.card,.metric{background:#0e1a24;border:1px solid #21303c;border-radius:12px;padding:14px}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:9px;margin:12px 0}.num{font-size:24px;font-weight:800}.muted{color:#91a5b5;font-size:12px}.pill{padding:4px 8px;border-radius:99px;background:#152633;font-size:10px}.btn{display:inline-block;padding:9px 13px;background:#e8f0f6;color:#071018;border-radius:8px;text-decoration:none;font-weight:800;border:0;cursor:pointer}.log{background:#08131c;padding:12px;border-radius:9px;white-space:pre-wrap;max-height:360px;overflow:auto}.row{display:flex;justify-content:space-between;gap:10px;align-items:center}.money{font-size:22px;font-weight:900}a{color:inherit;text-decoration:none}input{width:100%;padding:10px;background:#0b1720;color:white;border:1px solid #2a3b47;border-radius:8px;margin:7px 0 11px}
.city-layout{display:grid;grid-template-columns:minmax(700px,1fr) 300px;gap:12px}.city{position:relative;height:760px;overflow:hidden;border:1px solid #29404f;border-radius:14px;background:linear-gradient(145deg,#183c2b 0%,#102d23 48%,#0d251d 100%);box-shadow:inset 0 0 80px #0008}.road{position:absolute;background:#27333a;border:1px solid #3a474e;z-index:1}.road.h{height:8%;left:0;width:100%}.road.v{width:6%;top:0;height:100%}.road:after{content:'';position:absolute;left:0;top:48%;width:100%;border-top:1px dashed #9b8d54}.road.v:after{top:0;left:48%;height:100%;width:0;border-top:0;border-left:1px dashed #9b8d54}
.building{position:absolute;z-index:2;border:2px solid #415764;border-radius:8px;background:linear-gradient(135deg,#1b2c35,#0c1820);box-shadow:10px 12px 0 #07101899,0 0 20px #0007;padding:7px;overflow:hidden}.building:before{content:'';position:absolute;inset:7px;border:1px solid #6d849144;pointer-events:none}.building .roof{font-size:10px;font-weight:900;letter-spacing:.5px}.building .sub{font-size:8px;color:#8fa9b7}.building.hq{background:linear-gradient(135deg,#243642,#111d25);border-color:#d3aa39}.building.lab{background:linear-gradient(135deg,#163d4b,#0c1d28)}.building.warehouse{background:repeating-linear-gradient(90deg,#26333a 0 18px,#1b272d 18px 21px)}.building.market{background:linear-gradient(135deg,#402a1b,#1e1711)}.building.power{background:linear-gradient(135deg,#243b37,#10231f)}.building.homes{background:linear-gradient(135deg,#3b2c25,#1d1714)}.building.construction{border-style:dashed;background:repeating-linear-gradient(45deg,#3d3318,#3d3318 8px,#1d1b12 8px,#1d1b12 16px)}
.progress{height:5px;background:#08131c;border-radius:5px;margin-top:6px;overflow:hidden}.progress i{display:block;height:100%;background:#5ad987}.tree{position:absolute;z-index:2;width:16px;height:16px;border-radius:50%;background:#2d6a3d;box-shadow:0 8px 0 -5px #725139}.lamp{position:absolute;z-index:3;width:4px;height:4px;border-radius:50%;background:#ffd76a;box-shadow:0 0 10px #ffd76a}
.minion{position:absolute;width:18px;height:27px;border-radius:45% 45% 38% 38%;background:#f1c84b;border:1px solid #c99f22;color:#081018;font-size:5px;font-weight:900;text-align:center;padding-top:11px;z-index:8;transition:left 2.8s linear,top 2.8s linear;box-shadow:0 2px 4px #0008}.minion:before{content:'';position:absolute;left:3px;top:4px;width:10px;height:6px;border-radius:7px;background:#dce8ee;border:1px solid #26333a}.minion:after{content:'';position:absolute;left:2px;bottom:-4px;width:12px;height:8px;background:#315b91;border-radius:2px}.minion.sleeping{opacity:.45;filter:saturate(.6)}.minion.building{animation:hammer .55s infinite alternate}.minion.social{animation:bob .8s infinite alternate}.tool{position:absolute;right:-7px;top:10px;font-size:9px}.bubble{position:absolute;left:15px;top:-13px;background:#fff;color:#111;border-radius:7px;padding:2px 4px;font-size:6px;white-space:nowrap;display:none}.minion:hover .bubble{display:block}@keyframes hammer{to{transform:rotate(-7deg)}}@keyframes bob{to{transform:translateY(-2px)}}
.side{display:flex;flex-direction:column;gap:10px}.activity{max-height:360px;overflow:auto}.event{padding:8px 0;border-bottom:1px solid #1b2c36;font-size:11px}.event b{display:block}.legend{position:absolute;left:12px;bottom:12px;z-index:12;background:#071018dd;border:1px solid #29404f;border-radius:9px;padding:8px;font-size:9px}.city-title{position:absolute;left:12px;top:12px;z-index:12;background:#071018dd;border:1px solid #29404f;border-radius:9px;padding:8px 10px}.statusbar{position:absolute;right:12px;top:12px;z-index:12;background:#071018dd;border:1px solid #29404f;border-radius:9px;padding:8px 10px;font-size:9px}
@media(max-width:1000px){.city-layout{grid-template-columns:1fr}.city{height:680px}.metrics{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.wrap{padding:8px}.top{padding:12px}.city{height:600px;min-width:680px}.city-layout{overflow-x:auto}}
</style>'''
def page(title,body): return HTMLResponse(f'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>{CSS}</head><body>{body}</body></html>')
def authed(r): return r.session.get('owner') is True
@app.get('/login',response_class=HTMLResponse)
def login_get(request:Request):
    return page('MINION Login','<div class="wrap" style="max-width:430px;padding-top:12vh"><div class="card"><h1>MINION</h1><p class="muted">Owner Command Center</p><form method="post"><label>Password</label><input type="password" name="password" autofocus><button class="btn">ENTER COMMAND CENTER</button></form></div></div>')
@app.post('/login')
def login_post(request:Request,password:str=Form(...)):
    if password != os.getenv('OWNER_PASSWORD','minion-change-me'): return RedirectResponse('/login?error=1',303)
    request.session['owner']=True; return RedirectResponse('/command',303)
@app.get('/logout')
def logout(request:Request): request.session.clear(); return RedirectResponse('/login',303)
@app.get('/')
def root(): return RedirectResponse('/command')
@app.get('/command',response_class=HTMLResponse)
def command(request:Request):
    if not authed(request): return RedirectResponse('/login')
    with Session(engine) as s:
        agents=s.query(Agent).order_by(Agent.code).all(); treasury=s.query(Treasury).first()
        structures=s.query(WorldStructure).all(); proposals=s.query(Proposal).order_by(Proposal.id.desc()).limit(6).all()
        events=s.query(WorldEvent).order_by(WorldEvent.id.desc()).limit(18).all()
        working=sum(a.status=='working' for a in agents); sleeping=sum(a.status=='sleeping' for a in agents)
        queued=s.query(Task).filter(Task.status=='queued').count(); done=s.query(Task).filter(Task.status=='completed').count()
        roads='<div class="road h" style="top:30%"></div><div class="road h" style="top:61%"></div><div class="road v" style="left:30%"></div><div class="road v" style="left:62%"></div>'
        decor=''.join(f'<span class="tree" style="left:{(i*17)%96}%;top:{(i*29)%94}%"></span>' for i in range(22))
        buildings=''
        sizes={'hq':(18,16),'lab':(20,14),'warehouse':(19,15),'market':(20,14),'power':(17,13),'homes':(24,16),'construction':(22,18)}
        for b in structures:
            w,h=sizes.get(b.kind,(18,14)); label='BUILDING' if b.progress<100 else 'ACTIVE'
            buildings+=f'<div class="building {b.kind}" data-kind="{b.kind}" style="left:{b.x}%;top:{b.y}%;width:{w}%;height:{h}%"><div class="roof">{b.name}</div><div class="sub">{label} · LVL {b.level} · {int(b.progress)}%</div><div class="progress"><i style="width:{min(100,b.progress)}%"></i></div></div>'
        destinations={'Market Intelligence':(72,18),'Sourcing':(38,17),'Product Underwriting':(72,18),'Sales & Listings':(74,72),'Operations':(13,52),'Risk & Audit':(48,44),'Command':(49,46)}
        avatars=''
        for a in agents:
            n=int(a.code) if a.code!='000' else 0; dx,dy=destinations.get(a.division,(48,45))
            x=dx+((n%5)-2)*2; y=dy+(((n//5)%4)-2)*2
            activity='Working' if a.status=='working' else ('Sleeping' if a.status=='sleeping' else 'City duty')
            tool='🔨' if a.status!='sleeping' and n%4==0 else ('📦' if n%4==1 else ('💻' if n%4==2 else '🔧'))
            avatars+=f'<a href="/minion/{a.code}" class="minion {a.status}" data-code="{a.code}" data-status="{a.status}" data-division="{a.division}" style="left:{x}%;top:{y}%"><span class="tool">{tool}</span><span class="bubble">#{a.code} · {activity}</span>{a.code}</a>'
        feed=''.join(f'<div class="event"><b>{e.event.replace("_"," ").title()}</b>{e.detail}</div>' for e in events) or '<div class="muted">City systems starting...</div>'
        prop=''.join(f'<div class="event"><b>{p.title}</b>USD {p.amount:,.2f} proposal · est. profit USD {p.est_profit:,.2f}</div>' for p in proposals) or '<div class="muted">No spending proposals yet.</div>'
        body=f'''<div class="top"><div><div class="brand">MINION WORLD // AUTONOMOUS CITY</div><div class="muted">Commander #000 · persistent world simulation + AI workforce</div></div><a href="/logout" class="muted">Logout</a></div>
<div class="wrap"><div class="metrics"><div class="metric"><div class="num">101</div><div class="muted">POPULATION</div></div><div class="metric"><div class="num">{working}</div><div class="muted">AI WORKING</div></div><div class="metric"><div class="num">{sleeping}</div><div class="muted">SLEEPING</div></div><div class="metric"><div class="num">{queued}</div><div class="muted">JOBS QUEUED</div></div><div class="metric"><div class="num">{done}</div><div class="muted">JOBS COMPLETED</div></div></div>
<div class="city-layout"><div class="city" id="city">{roads}{decor}{buildings}{avatars}<div class="city-title"><b>LIVE CITY VIEW</b><div class="muted">The world keeps progressing while this page is closed.</div></div><div class="statusbar">AUTO SHIFTS: ON · CITY BUILD: ON</div><div class="legend">🔨 build · 📦 logistics · 💻 research · 🔧 maintenance<br>Green work continues server-side; movement is a live visualization of assigned activity.</div></div>
<div class="side"><div class="card"><h3 style="margin-top:0">TREASURY</h3><div class="money">USD {treasury.available_cash:,.2f}</div><div class="muted">Daily proposal ceiling USD {treasury.daily_limit:,.2f}</div><form method="post" action="/treasury"><input name="cash" type="number" min="0" step=".01" placeholder="Available cash"><input name="daily_limit" type="number" min="0" max="500" step=".01" value="{treasury.daily_limit}"><button class="btn">UPDATE</button></form></div><div class="card"><h3 style="margin-top:0">LIVE CITY ACTIVITY</h3><div class="activity">{feed}</div></div><div class="card"><h3 style="margin-top:0">OPPORTUNITIES</h3>{prop}</div><form method="post" action="/commander/bootstrap"><button class="btn" style="width:100%">ASSIGN BUSINESS MISSIONS</button></form></div></div></div>
<script>
const targets={{'Market Intelligence':[72,18],'Sourcing':[38,17],'Product Underwriting':[72,18],'Sales & Listings':[74,72],'Operations':[13,52],'Risk & Audit':[48,44],'Command':[49,46]}};
function moveLife(){{
 document.querySelectorAll('.minion').forEach((m,i)=>{{
  let s=m.dataset.status, d=targets[m.dataset.division]||[49,46], x=d[0], y=d[1];
  m.classList.remove('building','social');
  if(s==='sleeping'){{x=48+(i%7)*3;y=77+((i%3)*3);}}
  else if(s==='working'){{x+=Math.random()*12-6;y+=Math.random()*10-5;if(i%5===0)m.classList.add('building');}}
  else {{let mode=(Date.now()/6000+i)%3;if(mode<1){{x=39+Math.random()*18;y=36+Math.random()*18;m.classList.add('social')}}else if(mode<2){{x=34+Math.random()*24;y=66+Math.random()*18}}else{{x=20+Math.random()*55;y=33+Math.random()*30}}}}
  m.style.left=Math.max(3,Math.min(95,x))+'%';m.style.top=Math.max(5,Math.min(94,y))+'%';
 }});
}}
setInterval(moveLife,3000);setTimeout(moveLife,400);setTimeout(()=>location.reload(),20000);
</script>'''
        return page('MINION World',body)
@app.get('/minion/{code}',response_class=HTMLResponse)
def minion_view(code:str,request:Request):
    if not authed(request): return RedirectResponse('/login')
    with Session(engine) as s:
        a=s.query(Agent).filter(Agent.code==code).first()
        if not a: raise HTTPException(404,'Agent not found')
        w=s.query(Workspace).filter(Workspace.agent_id==a.id).first(); h=s.query(Warehouse).filter(Warehouse.agent_id==a.id).first(); t=s.get(Task,w.current_task_id) if w.current_task_id else None
        def count(x):
            try:return len(json.loads(x))
            except:return 0
        body=f'''<div class="top"><a href="/command">← COMMAND CENTER</a><div class="brand">MINION #{a.code}</div></div><div class="wrap"><div class="card"><div class="row"><div><h1 style="margin:0">{a.name}</h1><div class="muted">{a.division}</div></div><span class="pill"><span class="dot {a.status}"></span>{a.status.upper()}</span></div><p>{a.mission}</p></div><div class="metrics"><div class="metric"><div class="num">{count(h.products)}</div><div class="muted">PRODUCTS</div></div><div class="metric"><div class="num">{count(h.suppliers)}</div><div class="muted">SUPPLIERS</div></div><div class="metric"><div class="num">{count(h.evidence)}</div><div class="muted">EVIDENCE</div></div><div class="metric"><div class="num">{count(h.opportunities)}</div><div class="muted">OPPORTUNITIES</div></div></div><h2>Workspace</h2><div class="card"><b>Current mission</b><p>{t.title if t else 'Waiting for Commander assignment'}</p><div class="log">{w.desk_notes or 'Workspace ready. No completed notes yet.'}</div></div><h2>Warehouse</h2><div class="card"><div class="muted">Database-backed storage for this worker</div><p>Products: {count(h.products)} · Suppliers: {count(h.suppliers)} · Evidence: {count(h.evidence)} · Opportunities: {count(h.opportunities)} · Inventory proposals: {count(h.inventory_proposals)}</p></div></div><script>setTimeout(()=>location.reload(),8000)</script>'''
        return page(f'Minion {code}',body)
class TaskIn(BaseModel): title:str; instructions:str; assigned_code:Optional[str]=None; priority:int=50
@app.post('/tasks')
def create_task(x:TaskIn):
    with Session(engine) as s:
        aid=None
        if x.assigned_code:
            a=s.query(Agent).filter(Agent.code==x.assigned_code).first()
            if not a: raise HTTPException(404,'Agent not found')
            aid=a.id
        t=Task(title=x.title,instructions=x.instructions,assigned_agent=aid,priority=x.priority); s.add(t); s.commit(); s.refresh(t); return {'task_id':t.id,'status':t.status}
def choose_agent(s,t):
    if t.assigned_agent:return s.get(Agent,t.assigned_agent)
    words=(t.title+' '+t.instructions).lower(); division='Market Intelligence'
    if any(k in words for k in ['supplier','wholesale','manufacturer','source']):division='Sourcing'
    elif any(k in words for k in ['margin','profit','fee','roi','cost']):division='Product Underwriting'
    elif any(k in words for k in ['listing','price','keyword','sales']):division='Sales & Listings'
    elif any(k in words for k in ['inventory','reorder','logistics']):division='Operations'
    elif any(k in words for k in ['risk','policy','trademark','audit']):division='Risk & Audit'
    return s.query(Agent).filter(Agent.division==division,Agent.status=='idle').order_by(Agent.id).first()
def _worker_task(task_id:int,agent_id:int):
    key=os.getenv('OPENAI_API_KEY')
    if not key:return
    with Session(engine) as s:
        t=s.get(Task,task_id); a=s.get(Agent,agent_id); w=s.query(Workspace).filter(Workspace.agent_id==agent_id).first()
        if not t or not a:return
        try:
            client=OpenAI(api_key=key)
            system=f'''You are {a.name} ({a.code}) living inside MINION WORLD, division: {a.division}. Mission: {a.mission}
Work independently and evidence-first. Never invent live facts. Never execute purchases, transfers, trades, credentials, or external financial actions.
If you identify a potentially profitable opportunity, describe estimated cost, revenue, fees, profit, evidence needed and risks. Owner approval is mandatory before any spend.
Return compact JSON with summary, findings, evidence_needed, next_tasks, warehouse_items, and optional proposal with title, amount, est_profit, rationale.'''
            r=client.responses.create(model=os.getenv('MINION_MODEL','gpt-5-mini'),input=[{'role':'system','content':system},{'role':'user','content':t.instructions}])
            out=r.output_text; t.result=out; t.status='completed'; t.completed_at=dt.datetime.utcnow(); a.status='idle'; w.current_task_id=None; w.desk_notes=out[-5000:]; w.updated_at=dt.datetime.utcnow()
            box=json.loads(w.outbox or '[]'); box.append({'task_id':t.id,'result':out}); w.outbox=json.dumps(box[-100:])
            try:
                data=json.loads(out); p=data.get('proposal')
                if isinstance(p,dict) and float(p.get('amount',0) or 0)>0:
                    tr=s.query(Treasury).first(); amt=float(p.get('amount',0) or 0); profit=float(p.get('est_profit',0) or 0)
                    if amt<=tr.daily_limit: s.add(Proposal(agent_id=a.id,title=str(p.get('title','Opportunity'))[:200],amount=amt,est_profit=profit,rationale=str(p.get('rationale',''))[:4000],status='pending'))
            except Exception: pass
            s.add(WorldEvent(agent_id=a.id,event='task_completed',detail=t.title)); s.commit()
        except Exception as e:
            t.status='queued'; a.status='idle'; w.current_task_id=None; w.desk_notes=f'Last error: {e}'; s.commit()

def run_cycle():
    if not os.getenv('OPENAI_API_KEY'):return
    claimed=[]
    with Session(engine) as s:
        capacity=max(1,min(int(os.getenv('MINION_CONCURRENCY','12')),100))
        tasks=s.query(Task).filter(Task.status=='queued').order_by(Task.priority.desc(),Task.id).limit(capacity).all(); used=set()
        for t in tasks:
            a=choose_agent(s,t)
            if not a or a.id in used:continue
            used.add(a.id); t.assigned_agent=a.id; t.status='working'; a.status='working'
            w=s.query(Workspace).filter(Workspace.agent_id==a.id).first(); w.current_task_id=t.id; claimed.append((t.id,a.id))
        s.commit()
    if claimed:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(claimed)) as pool: list(pool.map(lambda pair:_worker_task(*pair),claimed))

@app.post('/treasury')
def update_treasury(request:Request,cash:float=Form(...),daily_limit:float=Form(...)):
    if not authed(request):return RedirectResponse('/login',303)
    with Session(engine) as s:
        tr=s.query(Treasury).first(); tr.available_cash=max(0,cash); tr.daily_limit=max(0,min(daily_limit,500)); tr.live_mode=tr.available_cash>0
        s.add(WorldEvent(event='treasury_updated',detail=f'Available cash {tr.available_cash:.2f}; proposal ceiling {tr.daily_limit:.2f}')); s.commit()
    return RedirectResponse('/command',303)

def world_tick():
    with Session(engine) as s:
        now=dt.datetime.utcnow(); slot=int(now.timestamp()//900)
        agents=s.query(Agent).filter(Agent.code!='000').all()
        busy={w.agent_id for w in s.query(Workspace).filter(Workspace.current_task_id.isnot(None)).all()}
        for a in agents:
            if a.id in busy: a.status='working'
            elif (int(a.code)+slot)%10<2: a.status='sleeping'
            else: a.status='idle'
        site=s.query(WorldStructure).filter(WorldStructure.kind=='construction').first()
        if site:
            active=sum(a.status!='sleeping' for a in agents)
            site.workers=max(8,min(24,active//4)); site.progress+=site.workers*0.08
            if site.progress>=100:
                site.progress=0; site.level+=1; site.name=f'CITY EXPANSION LVL {site.level}'
                s.add(WorldEvent(event='city_expanded',detail=f'Construction crew completed expansion level {site.level-1}.'))
            site.updated_at=now
        s.commit()

scheduler=BackgroundScheduler()
scheduler.add_job(run_cycle,'interval',seconds=5,max_instances=1,coalesce=True)
scheduler.add_job(world_tick,'interval',seconds=20,max_instances=1,coalesce=True)
scheduler.start()
@app.post('/commander/bootstrap')
def bootstrap(request:Request):
    if not authed(request):return RedirectResponse('/login',303)
    with Session(engine) as s:
        existing=s.query(Task).filter(Task.status.in_(['queued','working'])).count()
        if existing==0:
            for a in s.query(Agent).filter(Agent.code!='000').all():
                a.status='idle'; s.add(Task(title=f'World mission for Minion {a.code}',instructions=a.mission+' Build or improve your part of the digital headquarters while performing useful research. Identify data/tools needed, useful opportunities, risks, and next work. If an opportunity could require money, create only a proposal and never spend.',assigned_agent=a.id,priority=80))
            s.add(WorldEvent(event='world_wakeup',detail='Commander deployed all 100 Minions.')); s.commit()
    return RedirectResponse('/command',303)
@app.get('/api/status')
def status():
    with Session(engine) as s:
        tr=s.query(Treasury).first(); return {'agents':s.query(Agent).count(),'working':s.query(Agent).filter(Agent.status=='working').count(),'sleeping':s.query(Agent).filter(Agent.status=='sleeping').count(),'queued':s.query(Task).filter(Task.status=='queued').count(),'completed':s.query(Task).filter(Task.status=='completed').count(),'treasury':tr.available_cash,'daily_proposal_limit':tr.daily_limit,'pending_proposals':s.query(Proposal).filter(Proposal.status=='pending').count()}

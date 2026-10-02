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
seed()
app=FastAPI(title='MINION Command Center',version='1.1'); app.add_middleware(SessionMiddleware,secret_key=os.getenv('SESSION_SECRET',secrets.token_hex(32)),max_age=86400*7,https_only=False)
CSS='''<style>*{box-sizing:border-box}body{margin:0;background:#071018;color:#e8f0f6;font-family:Inter,Arial,sans-serif}.top{padding:20px 28px;border-bottom:1px solid #21303c;display:flex;justify-content:space-between;align-items:center}.brand{font-weight:900;letter-spacing:2px}.wrap{max-width:1400px;margin:auto;padding:24px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(185px,1fr));gap:12px}.card,.metric{background:#0e1a24;border:1px solid #21303c;border-radius:14px;padding:16px}.card:hover{border-color:#587184}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.num{font-size:28px;font-weight:800}.muted{color:#91a5b5;font-size:13px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#55d187;margin-right:7px}.working{background:#55d187}.idle{background:#e6bd52}.error{background:#ef6a6a}.pill{padding:4px 8px;border-radius:99px;background:#152633;font-size:11px}.btn{display:inline-block;padding:10px 14px;background:#e8f0f6;color:#071018;border-radius:9px;text-decoration:none;font-weight:700;border:0;cursor:pointer}.log{background:#08131c;padding:12px;border-radius:9px;white-space:pre-wrap;max-height:360px;overflow:auto}.row{display:flex;justify-content:space-between;gap:10px;align-items:center}.world{display:grid;grid-template-columns:2fr 1fr;gap:12px;margin:18px 0}.hq{min-height:260px;background:linear-gradient(180deg,#0d1b26,#08131c);border:1px solid #21303c;border-radius:14px;padding:16px}.zones{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.zone{background:#10212d;border:1px solid #29404f;border-radius:12px;padding:12px;min-height:92px}.avatar{display:inline-flex;width:30px;height:30px;border-radius:50%;align-items:center;justify-content:center;background:#e6bd52;color:#071018;font-size:10px;font-weight:900;margin:3px}.avatar.working{background:#55d187}.avatar.sleeping{background:#6f7fce}.money{font-size:22px;font-weight:900}a{color:inherit;text-decoration:none}input{width:100%;padding:12px;background:#0b1720;color:white;border:1px solid #2a3b47;border-radius:8px;margin:8px 0 14px}@media(max-width:700px){.metrics{grid-template-columns:1fr 1fr}.world{grid-template-columns:1fr}.zones{grid-template-columns:1fr 1fr}.wrap{padding:14px}.top{padding:16px}}</style>'''
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
        agents=s.query(Agent).order_by(Agent.code).all(); tasks=s.query(Task).order_by(Task.id.desc()).limit(12).all()
        treasury=s.query(Treasury).first(); proposals=s.query(Proposal).order_by(Proposal.id.desc()).limit(8).all()
        working=sum(a.status=='working' for a in agents); sleeping=sum(a.status=='sleeping' for a in agents)
        queued=s.query(Task).filter(Task.status=='queued').count(); done=s.query(Task).filter(Task.status=='completed').count()
        zones={}
        for a in agents:
            zone='Command Deck' if a.code=='000' else a.division
            zones.setdefault(zone,[]).append(a)
        zone_html=''
        for z,members in zones.items():
            icons=''.join(f'<a href="/minion/{a.code}" title="{a.name}: {a.status}" class="avatar {a.status}">{a.code}</a>' for a in members)
            zone_html+=f'<div class="zone"><b>{z}</b><div class="muted">{len(members)} residents</div><div style="margin-top:7px">{icons}</div></div>'
        feed=''.join(f'<div class="row" style="padding:8px 0;border-bottom:1px solid #182733"><span>#{t.id} {t.title}</span><span class="pill">{t.status}</span></div>' for t in tasks) or '<div class="muted">No tasks yet.</div>'
        prop=''.join(f'<div style="padding:10px 0;border-bottom:1px solid #182733"><b>{p.title}</b><div class="muted">Minion #{p.agent_id} · USD {p.amount:,.2f} proposed · est. profit USD {p.est_profit:,.2f} · {p.status}</div></div>' for p in proposals) or '<div class="muted">No spending proposals. Minions cannot spend automatically.</div>'
        live='LIVE MONEY DETECTED' if treasury.available_cash>0 else 'SIMULATION / ZERO TREASURY'
        body=f'''<div class="top"><div><div class="brand">MINION WORLD // DIGITAL HQ</div><div class="muted">Commander #000 + 100 autonomous research workers</div></div><a href="/logout" class="muted">Logout</a></div>
        <div class="wrap"><div class="metrics"><div class="metric"><div class="num">{working}</div><div class="muted">WORKING NOW</div></div><div class="metric"><div class="num">{sleeping}</div><div class="muted">SLEEPING</div></div><div class="metric"><div class="num">{queued}</div><div class="muted">QUEUED</div></div><div class="metric"><div class="num">{done}</div><div class="muted">COMPLETED</div></div></div>
        <div class="world"><div class="hq"><div class="row"><div><h2 style="margin:0">Minion Headquarters</h2><div class="muted">Every worker has a workspace, warehouse and home state.</div></div><form method="post" action="/commander/bootstrap"><button class="btn">WAKE & DEPLOY ALL</button></form></div><div class="zones" style="margin-top:14px">{zone_html}</div></div>
        <div class="card"><h2 style="margin-top:0">Treasury</h2><div class="money">USD {treasury.available_cash:,.2f}</div><div class="muted">{live}</div><p>Daily proposal ceiling: <b>USD {treasury.daily_limit:,.2f}</b></p><p class="muted">Agents may detect opportunities and prepare proposals. Actual purchases/transfers require owner approval.</p><form method="post" action="/treasury"><input name="cash" type="number" min="0" step="0.01" placeholder="Available cash"><input name="daily_limit" type="number" min="0" step="0.01" value="{treasury.daily_limit}"><button class="btn">UPDATE TREASURY</button></form></div></div>
        <h2>Opportunity / Spending Proposals</h2><div class="card">{prop}</div><h2>Live Activity</h2><div class="card">{feed}</div></div><script>setTimeout(()=>location.reload(),7000)</script>'''
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

scheduler=BackgroundScheduler();scheduler.add_job(run_cycle,'interval',seconds=5,max_instances=1,coalesce=True);scheduler.start()
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

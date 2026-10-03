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
class AgentWorldState(Base):
    __tablename__='agent_world_state'
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    agent_id:Mapped[int]=mapped_column(ForeignKey('agents.id'),unique=True)
    zone:Mapped[str]=mapped_column(String(40),default='homes')
    action:Mapped[str]=mapped_column(String(80),default='resting')
    activity_kind:Mapped[str]=mapped_column(String(30),default='life')
    task_id:Mapped[Optional[int]]=mapped_column(Integer,nullable=True)
    x:Mapped[float]=mapped_column(Float,default=50)
    y:Mapped[float]=mapped_column(Float,default=72)
    energy:Mapped[float]=mapped_column(Float,default=100)
    updated_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow)

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
        # Ensure persistent world state records exist for every worker.
        existing_states={r.agent_id for r in s.query(AgentWorldState).all()}
        for a in s.query(Agent).all():
            if a.id not in existing_states:
                s.add(AgentWorldState(agent_id=a.id,zone='hq' if a.code=='000' else 'homes',action='commanding' if a.code=='000' else 'resting',activity_kind='life',x=50 if a.code=='000' else 48+(int(a.code)%9)-4,y=42 if a.code=='000' else 75+(int(a.code)%7)-3,energy=100))
        s.commit()
seed()
app=FastAPI(title='MINION Command Center',version='1.1'); app.add_middleware(SessionMiddleware,secret_key=os.getenv('SESSION_SECRET',secrets.token_hex(32)),max_age=86400*7,https_only=False)
CSS='''<style>
*{box-sizing:border-box}body{margin:0;background:#061019;color:#e8f0f6;font-family:Inter,Arial,sans-serif}.top{padding:15px 22px;border-bottom:1px solid #21303c;display:flex;justify-content:space-between;align-items:center;background:#091721}.brand{font-weight:900;letter-spacing:2px}.wrap{max-width:1600px;margin:auto;padding:16px}.card,.metric{background:#0e1a24;border:1px solid #21303c;border-radius:12px;padding:14px}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:9px;margin:12px 0}.num{font-size:24px;font-weight:800}.muted{color:#91a5b5;font-size:12px}.pill{padding:4px 8px;border-radius:99px;background:#152633;font-size:10px}.btn{display:inline-block;padding:9px 13px;background:#e8f0f6;color:#071018;border-radius:8px;text-decoration:none;font-weight:800;border:0;cursor:pointer}.log{background:#08131c;padding:12px;border-radius:9px;white-space:pre-wrap;max-height:360px;overflow:auto}.row{display:flex;justify-content:space-between;gap:10px;align-items:center}.money{font-size:22px;font-weight:900}a{color:inherit;text-decoration:none}input,textarea{width:100%;padding:10px;background:#0b1720;color:white;border:1px solid #2a3b47;border-radius:8px;margin:7px 0 11px}textarea{min-height:100px;resize:vertical;background:#0b1720;color:white;border:1px solid #2a3b47;border-radius:8px}
.city-layout{display:grid;grid-template-columns:minmax(700px,1fr) 300px;gap:12px}.city{position:relative;height:760px;overflow:hidden;border:1px solid #29404f;border-radius:14px;background:linear-gradient(145deg,#183c2b 0%,#102d23 48%,#0d251d 100%);box-shadow:inset 0 0 80px #0008}.road{position:absolute;background:#27333a;border:1px solid #3a474e;z-index:1}.road.h{height:8%;left:0;width:100%}.road.v{width:6%;top:0;height:100%}.road:after{content:'';position:absolute;left:0;top:48%;width:100%;border-top:1px dashed #9b8d54}.road.v:after{top:0;left:48%;height:100%;width:0;border-top:0;border-left:1px dashed #9b8d54}
.building{appearance:none;color:inherit;text-align:left;cursor:pointer;position:absolute;z-index:2;border:2px solid #415764;border-radius:8px;background:linear-gradient(135deg,#1b2c35,#0c1820);box-shadow:10px 12px 0 #07101899,0 0 20px #0007;padding:7px;overflow:hidden}.building:before{content:'';position:absolute;inset:7px;border:1px solid #6d849144;pointer-events:none}.building .roof{font-size:10px;font-weight:900;letter-spacing:.5px}.building .sub{font-size:8px;color:#8fa9b7}.building.hq{background:linear-gradient(135deg,#243642,#111d25);border-color:#d3aa39}.building.lab{background:linear-gradient(135deg,#163d4b,#0c1d28)}.building.warehouse{background:repeating-linear-gradient(90deg,#26333a 0 18px,#1b272d 18px 21px)}.building.market{background:linear-gradient(135deg,#402a1b,#1e1711)}.building.power{background:linear-gradient(135deg,#243b37,#10231f)}.building.homes{background:linear-gradient(135deg,#3b2c25,#1d1714)}.building.construction{border-style:dashed;background:repeating-linear-gradient(45deg,#3d3318,#3d3318 8px,#1d1b12 8px,#1d1b12 16px)}
.progress{height:5px;background:#08131c;border-radius:5px;margin-top:6px;overflow:hidden}.progress i{display:block;height:100%;background:#5ad987}.tree{position:absolute;z-index:2;width:16px;height:16px;border-radius:50%;background:#2d6a3d;box-shadow:0 8px 0 -5px #725139}.lamp{position:absolute;z-index:3;width:4px;height:4px;border-radius:50%;background:#ffd76a;box-shadow:0 0 10px #ffd76a}
.minion{appearance:none;cursor:pointer;position:absolute;width:18px;height:27px;border-radius:45% 45% 38% 38%;background:#f1c84b;border:1px solid #c99f22;color:#081018;font-size:5px;font-weight:900;text-align:center;padding-top:11px;z-index:8;transition:left 2.8s linear,top 2.8s linear;box-shadow:0 2px 4px #0008}.minion:before{content:'';position:absolute;left:3px;top:4px;width:10px;height:6px;border-radius:7px;background:#dce8ee;border:1px solid #26333a}.minion:focus{outline:2px solid #fff;outline-offset:3px}.building:focus{outline:2px solid #fff;outline-offset:3px}.minion:after{content:'';position:absolute;left:2px;bottom:-4px;width:12px;height:8px;background:#315b91;border-radius:2px}.minion.sleeping{opacity:.45;filter:saturate(.6)}.minion.building{animation:hammer .55s infinite alternate}.minion.social{animation:bob .8s infinite alternate}.tool{position:absolute;right:-7px;top:10px;font-size:9px}.bubble{position:absolute;left:15px;top:-13px;background:#fff;color:#111;border-radius:7px;padding:2px 4px;font-size:6px;white-space:nowrap;display:none}.minion:hover .bubble{display:block}@keyframes hammer{to{transform:rotate(-7deg)}}@keyframes bob{to{transform:translateY(-2px)}}
.side{display:flex;flex-direction:column;gap:10px}.activity{max-height:360px;overflow:auto}.event{padding:8px 0;border-bottom:1px solid #1b2c36;font-size:11px}.event b{display:block}.legend{position:absolute;left:12px;bottom:12px;z-index:12;background:#071018dd;border:1px solid #29404f;border-radius:9px;padding:8px;font-size:9px}.city-title{position:absolute;left:12px;top:12px;z-index:12;background:#071018dd;border:1px solid #29404f;border-radius:9px;padding:8px 10px}.statusbar{position:absolute;right:12px;top:12px;z-index:12;background:#071018dd;border:1px solid #29404f;border-radius:9px;padding:8px 10px;font-size:9px}
@media(max-width:1000px){.city-layout{grid-template-columns:1fr}.city{height:680px}.metrics{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.wrap{padding:8px}.top{padding:12px}.city{height:600px;min-width:680px}.city-layout{overflow-x:auto}}
#ow{background:#050b10;min-height:100vh}.gamebar{height:58px;background:#08131b;border-bottom:1px solid #273945;display:flex;align-items:center;padding:0 18px;gap:24px}.gamebar b{letter-spacing:2px}.gamebar>div:first-child span{display:block;color:#79909e;font-size:9px}.game-stats{display:flex;gap:8px;margin-left:auto}.game-stats span{background:#101e27;border:1px solid #243845;border-radius:5px;padding:6px 8px;font-size:9px}.viewport{position:relative;max-width:1280px;margin:14px auto 0;border:1px solid #314651;background:#101820}.viewport>canvas{width:100%;height:auto;display:block;outline:none}.hud{position:absolute;background:#061018dd;border:1px solid #405663;border-radius:5px;padding:7px 9px;z-index:5;pointer-events:none}.hud b,.hud small{display:block}.hud small{font-size:9px;color:#9eb0bb;margin-top:3px}.top-left{left:12px;top:12px}.top-right{right:12px;top:12px}.bottom-left{left:12px;bottom:12px}.bottom-right{right:12px;bottom:12px;max-width:260px}.minimap{border:1px solid #42545e;margin-bottom:5px}.minimap canvas{display:block}.controlstrip{max-width:1280px;margin:8px auto 18px;display:grid;grid-template-columns:auto auto auto auto 1fr;gap:7px}.controlstrip>button,.controlstrip form button{background:#172731;color:#e8f0f6;border:1px solid #38505e;border-radius:5px;padding:8px;font-weight:800;cursor:pointer}.controlstrip form{display:grid;grid-template-columns:90px 160px 1fr auto;gap:5px}.controlstrip input{margin:0;padding:8px;border-radius:5px}.gamebar>a{font-size:10px;color:#8ca1ad}@media(max-width:900px){.game-stats span:nth-child(-n+3){display:none}.controlstrip{grid-template-columns:1fr 1fr}.controlstrip form{grid-column:1/-1;grid-template-columns:1fr}.viewport{overflow:hidden}}</style>'''
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
        treasury=s.query(Treasury).first()
        queued=s.query(Task).filter(Task.status=='queued').count(); done=s.query(Task).filter(Task.status=='completed').count()
        failed=s.query(Task).filter(Task.status=='failed').count(); working=s.query(Agent).filter(Agent.status=='working').count()
        api_state='ONLINE' if os.getenv('OPENAI_API_KEY') else 'OFFLINE'
        body=f"""<div id="mw3"><div class="mwbar"><div><b>MINION WORLD 3D</b><small>AUTONOMOUS OPERATIONS CITY</small></div><div class="mwstats"><span>AI {api_state}</span><span>{working} REAL WORK</span><span>{queued} QUEUED</span><span>{done} DONE</span><span>{failed} FAILED</span><span>USD {treasury.available_cash:,.2f}</span></div><a href="/logout">EXIT</a></div>
<div class="commander"><form method="post" action="/commander/mission"><input name="objective" required placeholder="Tell Commander #000 what you want the company to accomplish..."><button>DEPLOY</button></form><a href="/api/diagnostics" target="_blank">DIAGNOSTICS</a></div>
<div id="scene"><div id="loading">BUILDING MINION WORLD 3D...</div><div class="help">DRAG = LOOK · WHEEL = ZOOM · CLICK A WORKER = INSPECT</div><div id="inspect"><b>COMMANDER NETWORK</b><small>Select a worker to see their real assignment.</small></div></div>
<div class="mission"><form method="post" action="/missions/create"><input id="worker" name="assigned_code" placeholder="Worker #"><input name="title" required placeholder="Mission title"><input name="instructions" required placeholder="What should this worker accomplish?"><button>ASSIGN</button></form></div></div>
<style>
body{{overflow-x:hidden}}#mw3{{background:#050b10;min-height:100vh;color:#eaf2f6}}.mwbar{{height:58px;padding:10px 18px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #263844;background:#08131b}}.mwbar b{{letter-spacing:2px}}.mwbar small{{display:block;color:#7592a3;font-size:9px}}.mwbar a{{color:#9bb0bc}}.mwstats{{display:flex;gap:7px;flex-wrap:wrap}}.mwstats span{{font-size:10px;border:1px solid #29404e;border-radius:5px;padding:6px 8px;background:#0d1b24}}.commander,.mission{{max-width:1500px;margin:10px auto;display:flex;gap:8px;padding:0 10px}}.commander form,.mission form{{display:grid;grid-template-columns:1fr auto;gap:7px;flex:1}}.mission form{{grid-template-columns:120px 220px 1fr auto}}.commander input,.mission input{{margin:0;background:#0c1821;border:1px solid #314957;color:white;padding:10px;border-radius:5px}}.commander button,.mission button,.commander a{{background:#e7c343;color:#081018;border:0;border-radius:5px;padding:10px 14px;font-weight:900;text-decoration:none}}#scene{{position:relative;max-width:1500px;height:760px;margin:auto;border:1px solid #29404e;background:#071017;overflow:hidden}}#scene canvas{{width:100%!important;height:100%!important;display:block}}#loading{{position:absolute;inset:0;display:grid;place-items:center;z-index:5;letter-spacing:3px;background:#071017}}.help{{position:absolute;left:12px;bottom:12px;z-index:4;background:#061019dd;border:1px solid #36505e;padding:8px;font-size:10px}}#inspect{{position:absolute;right:12px;top:12px;z-index:4;width:300px;background:#061019e8;border:1px solid #36505e;padding:12px;border-radius:7px}}#inspect small{{display:block;color:#9eb0ba;margin-top:6px;line-height:1.45}}@media(max-width:800px){{.mwstats{{display:none}}#scene{{height:70vh}}.mission form{{grid-template-columns:1fr}}}}
</style>
<script type="module">
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js';
import {{ OrbitControls }} from 'https://cdn.jsdelivr.net/npm/three@0.180.0/examples/jsm/controls/OrbitControls.js';
const host=document.getElementById('scene'), loading=document.getElementById('loading');
const scene=new THREE.Scene();scene.background=new THREE.Color(0x86b7d5);scene.fog=new THREE.Fog(0x86b7d5,130,280);
const camera=new THREE.PerspectiveCamera(55,host.clientWidth/host.clientHeight,.1,600);camera.position.set(78,82,105);
const renderer=new THREE.WebGLRenderer({{antialias:true}});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setSize(host.clientWidth,host.clientHeight);renderer.shadowMap.enabled=true;host.appendChild(renderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,0,0);controls.enableDamping=true;controls.maxPolarAngle=Math.PI*.47;controls.minDistance=25;controls.maxDistance=190;
scene.add(new THREE.HemisphereLight(0xd7efff,0x28442c,2.1));const sun=new THREE.DirectionalLight(0xffffff,2.6);sun.position.set(70,110,40);sun.castShadow=true;scene.add(sun);
const ground=new THREE.Mesh(new THREE.PlaneGeometry(240,180),new THREE.MeshStandardMaterial({{color:0x315f38}}));ground.rotation.x=-Math.PI/2;ground.receiveShadow=true;scene.add(ground);
function box(x,z,w,d,h,color){{const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),new THREE.MeshStandardMaterial({{color}}));m.position.set(x,h/2,z);m.castShadow=m.receiveShadow=true;scene.add(m);return m}}
function road(x,z,w,d){{box(x,z,w,d,.12,0x30373b);for(let q=-w/2+5;q<w/2;q+=10)box(x+q,z,4,.18,.14,0xd8b94a)}}
road(0,0,240,15);road(0,55,240,13);box(-48,0,14,180,.13,0x30373b);box(48,0,14,180,.13,0x30373b);
const facilities={{
 hq:{{x:0,z:25,w:42,d:30,h:22,c:0x233b49,n:'COMMAND HQ'}},lab:{{x:72,z:-45,w:36,d:26,h:18,c:0x22566a,n:'RESEARCH CENTER'}},warehouse:{{x:-82,z:30,w:40,d:28,h:14,c:0x4a5155,n:'LOGISTICS DEPOT'}},market:{{x:76,z:69,w:38,d:25,h:13,c:0x6a4430,n:'MARKET DISTRICT'}},power:{{x:-83,z:70,w:34,d:22,h:11,c:0x365d52,n:'UTILITY YARD'}},homes:{{x:0,z:73,w:48,d:24,h:12,c:0x765546,n:'MINION VILLAGE'}},construction:{{x:0,z:-55,w:42,d:28,h:8,c:0x8a6d31,n:'ACTIVE DEVELOPMENT'}}
}};
for(const [k,b] of Object.entries(facilities)){{const m=box(b.x,b.z,b.w,b.d,b.h,b.c);m.userData={{kind:'building',key:k}};for(let xx=-b.w/2+5;xx<b.w/2-2;xx+=7)for(let yy=4;yy<b.h-2;yy+=6){{const win=box(b.x+xx,b.z+b.d/2+.08,3,.15,2.5,0x8cc7dc);win.position.y=yy}}}}
for(let i=0;i<55;i++){{let x=((i*37)%220)-110,z=((i*61)%165)-82;if(Math.abs(x)<10||Math.abs(z)<9)continue;const trunk=box(x,z,1,1,4,0x6b4a2b);const crown=new THREE.Mesh(new THREE.SphereGeometry(3,7,6),new THREE.MeshStandardMaterial({{color:0x2b6d3b}}));crown.position.set(x,6,z);scene.add(crown)}}
const workers=new Map(),targets=new Map();
function workerMesh(a){{const g=new THREE.Group();const body=new THREE.Mesh(new THREE.CapsuleGeometry(1.45,2.7,5,10),new THREE.MeshStandardMaterial({{color:0xf0cf38}}));body.position.y=3.4;body.castShadow=true;g.add(body);const bib=new THREE.Mesh(new THREE.BoxGeometry(2.5,1.7,1.65),new THREE.MeshStandardMaterial({{color:0x315c91}}));bib.position.set(0,2.35,.35);g.add(bib);const eye=new THREE.Mesh(new THREE.SphereGeometry(.52,10,8),new THREE.MeshStandardMaterial({{color:0xe9f4f5}}));eye.position.set(0,4.25,1.25);g.add(eye);const glass=new THREE.Mesh(new THREE.TorusGeometry(.7,.12,8,16),new THREE.MeshStandardMaterial({{color:0x30383d}}));glass.position.set(0,4.25,1.48);g.add(glass);g.scale.set(.72,.72,.72);g.userData={{kind:'worker',code:a.code}};scene.add(g);workers.set(a.code,g);return g}}
function zonePoint(a){{const b=facilities[a.zone]||facilities.hq;const n=parseInt(a.code||'0');return new THREE.Vector3(b.x+((n%7)-3)*2.2,0,b.z+((Math.floor(n/7)%5)-2)*2.1)}}
let state={{agents:[],structures:[],events:[]}},selected=null;
async function sync(){{try{{const r=await fetch('/api/world');if(!r.ok)return;state=await r.json();for(const a of state.agents){{let m=workers.get(a.code)||workerMesh(a);m.userData.agent=a;targets.set(a.code,zonePoint(a));if(selected===a.code)show(a)}}loading.style.display='none'}}catch(e){{loading.textContent='WORLD CONNECTION ERROR'}}}}
function show(a){{selected=a.code;document.getElementById('worker').value=a.code;document.getElementById('inspect').innerHTML='<b>'+a.name+' #'+a.code+'</b><small>'+a.division+'<br><strong>'+(a.activity_kind==='real_work'?'REAL AI WORK':'CITY LIFE')+'</strong><br>'+a.action+(a.task_title?'<br><br>Task: '+a.task_title:'')+'<br>Energy: '+Math.round(a.energy)+'%</small>'}}
const ray=new THREE.Raycaster(),mouse=new THREE.Vector2();renderer.domElement.addEventListener('pointerdown',e=>{{const r=renderer.domElement.getBoundingClientRect();mouse.x=((e.clientX-r.left)/r.width)*2-1;mouse.y=-((e.clientY-r.top)/r.height)*2+1;ray.setFromCamera(mouse,camera);const hits=ray.intersectObjects([...workers.values()],true);if(hits.length){{let o=hits[0].object;while(o.parent&&!o.userData.code)o=o.parent;if(o.userData.code)show(o.userData.agent)}}}});
let last=performance.now();function animate(t){{requestAnimationFrame(animate);const dt=Math.min(.05,(t-last)/1000);last=t;for(const [code,m] of workers){{const q=targets.get(code);if(!q)continue;const d=q.clone().sub(m.position);d.y=0;if(d.length()>.5){{m.position.addScaledVector(d.normalize(),dt*5);m.rotation.y=Math.atan2(d.x,d.z)}}const a=m.userData.agent;if(a?.activity_kind==='real_work')m.position.y=.12+Math.sin(t*.006+parseInt(code))*.08;else m.position.y=Math.sin(t*.002+parseInt(code))*.03}}controls.update();renderer.render(scene,camera)}}requestAnimationFrame(animate);sync();setInterval(sync,2500);
addEventListener('resize',()=>{{camera.aspect=host.clientWidth/host.clientHeight;camera.updateProjectionMatrix();renderer.setSize(host.clientWidth,host.clientHeight)}});
</script>"""
        return page('Minion World 3D',body)

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
            err=str(e)[:1800]
            t.status='failed'; t.result='ERROR: '+err; a.status='idle'; w.current_task_id=None; w.desk_notes='Last error: '+err; w.updated_at=dt.datetime.utcnow(); s.add(WorldEvent(agent_id=a.id,event='task_failed',detail=f'{t.title}: {err[:500]}')); s.commit()

def run_cycle():
    if not os.getenv('OPENAI_API_KEY'):return
    claimed=[]
    with Session(engine) as s:
        capacity=max(1,min(int(os.getenv('MINION_CONCURRENCY','3')),8))
        tasks=s.query(Task).filter(Task.status=='queued').order_by(Task.priority.desc(),Task.id).limit(max(capacity*8,100)).all(); used=set()
        for t in tasks:
            a=choose_agent(s,t)
            if not a or a.id in used:continue
            used.add(a.id); t.assigned_agent=a.id; t.status='working'; a.status='working'
            w=s.query(Workspace).filter(Workspace.agent_id==a.id).first(); w.current_task_id=t.id; claimed.append((t.id,a.id))
        s.commit()
    if claimed:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(claimed)) as pool: list(pool.map(lambda pair:_worker_task(*pair),claimed))

@app.post('/missions/create')
def create_mission_ui(request:Request,title:str=Form(...),instructions:str=Form(...),assigned_code:str=Form('')):
    if not authed(request): return RedirectResponse('/login',303)
    title=title.strip()[:200]; instructions=instructions.strip()[:5000]; assigned_code=assigned_code.strip()
    if not title or not instructions: return RedirectResponse('/command',303)
    with Session(engine) as s:
        aid=None
        if assigned_code:
            a=s.query(Agent).filter(Agent.code==assigned_code).first()
            if a: aid=a.id
        t=Task(title=title,instructions=instructions,assigned_agent=aid,priority=90)
        s.add(t); s.add(WorldEvent(agent_id=aid,event='mission_created',detail=f'{title} assigned to #{assigned_code}' if assigned_code else title)); s.commit()
    return RedirectResponse('/command',303)

@app.post('/commander/mission')
def commander_mission(request:Request,objective:str=Form(...)):
    if not authed(request): return RedirectResponse('/login',303)
    objective=objective.strip()[:6000]
    if not objective: return RedirectResponse('/command',303)
    plans=[
      ('Market Intelligence','Research demand, competitors, trends, customer pain points and evidence relevant to the owner objective.'),
      ('Sourcing','Research legitimate suppliers, tools, resources, pricing, lead times and implementation options relevant to the objective.'),
      ('Product Underwriting','Analyze economics, costs, revenue potential, ROI assumptions and rank viable approaches using evidence.'),
      ('Sales & Listings','Develop positioning, go-to-market, outreach, listing or presentation work relevant to the objective.'),
      ('Operations','Create an execution plan, workflow, logistics requirements, milestones and operating requirements for the objective.'),
      ('Risk & Audit','Audit the objective and other likely outputs for legal, financial, supplier, evidence, duplication and execution risks.')
    ]
    with Session(engine) as s:
        commander=s.query(Agent).filter(Agent.code=='000').first()
        root=Task(title='COMMANDER: '+objective[:185],instructions='Owner objective: '+objective+'\nAct as Commander. Synthesize specialist outputs as they complete. Never spend money or take consequential external actions without owner approval.',assigned_agent=commander.id,priority=60)
        s.add(root)
        for division,instruction in plans:
            workers=s.query(Agent).filter(Agent.division==division).order_by(Agent.id).limit(1).all()
            for a in workers:
                s.add(Task(title=division+': '+objective[:150],instructions='Owner objective: '+objective+'\nYour specialist assignment: '+instruction+'\nProduce useful work, cite evidence needed, and identify concrete next steps. Do not pretend simulated city activity is real work.',assigned_agent=a.id,priority=100))
        s.add(WorldEvent(agent_id=commander.id,event='commander_delegated',detail='Commander created a cross-division work program: '+objective[:500]))
        s.commit()
    return RedirectResponse('/command',303)

@app.get('/api/world')
def world_api(request:Request):
    if not authed(request): raise HTTPException(401,'login required')
    with Session(engine) as s:
        states={r.agent_id:r for r in s.query(AgentWorldState).all()}
        workspaces={w.agent_id:w for w in s.query(Workspace).all()}
        rows=[]
        for a in s.query(Agent).order_by(Agent.code).all():
            st=states.get(a.id); w=workspaces.get(a.id); task=s.get(Task,w.current_task_id) if w and w.current_task_id else None
            rows.append({'id':a.id,'code':a.code,'name':a.name,'division':a.division,'status':a.status,'zone':st.zone if st else 'homes','action':st.action if st else a.status,'activity_kind':st.activity_kind if st else 'life','task_id':task.id if task else None,'task_title':task.title if task else None,'x':st.x if st else 50,'y':st.y if st else 72,'energy':st.energy if st else 100})
        structures=[{'key':z.key,'name':z.name,'kind':z.kind,'level':z.level,'progress':z.progress,'workers':z.workers} for z in s.query(WorldStructure).all()]
        events=[{'event':e.event,'detail':e.detail,'agent_id':e.agent_id,'time':e.created_at.isoformat()} for e in s.query(WorldEvent).order_by(WorldEvent.id.desc()).limit(20).all()]
        return {'agents':rows,'structures':structures,'events':events}

@app.post('/treasury')
def update_treasury(request:Request,cash:float=Form(...),daily_limit:float=Form(...)):
    if not authed(request):return RedirectResponse('/login',303)
    with Session(engine) as s:
        tr=s.query(Treasury).first(); tr.available_cash=max(0,cash); tr.daily_limit=max(0,min(daily_limit,500)); tr.live_mode=tr.available_cash>0
        s.add(WorldEvent(event='treasury_updated',detail=f'Available cash {tr.available_cash:.2f}; proposal ceiling {tr.daily_limit:.2f}')); s.commit()
    return RedirectResponse('/command',303)

def world_tick():
    zones={'Market Intelligence':('lab',67,22),'Sourcing':('warehouse',17,58),'Product Underwriting':('lab',72,26),'Sales & Listings':('market',76,73),'Operations':('warehouse',22,63),'Risk & Audit':('hq',52,47),'Command':('hq',50,43)}
    with Session(engine) as s:
        now=dt.datetime.utcnow(); slot=int(now.timestamp()//900)
        agents=s.query(Agent).all()
        workspaces={w.agent_id:w for w in s.query(Workspace).all()}
        states={r.agent_id:r for r in s.query(AgentWorldState).all()}
        for a in agents:
            st=states.get(a.id)
            if not st:
                st=AgentWorldState(agent_id=a.id); s.add(st); states[a.id]=st
            w=workspaces.get(a.id); task=s.get(Task,w.current_task_id) if w and w.current_task_id else None
            if task:
                zone,x,y=zones.get(a.division,('hq',50,45)); st.zone=zone; st.x=x+(a.id%7)-3; st.y=y+(a.id%5)-2
                st.action='REAL AI WORK: '+task.title[:55]; st.activity_kind='real_work'; st.task_id=task.id; st.energy=max(20,st.energy-1); a.status='working'
            elif a.code=='000':
                st.zone='hq'; st.x=50; st.y=43; st.action='supervising workforce'; st.activity_kind='command'; st.task_id=None; a.status='idle'
            elif (int(a.code)+slot)%10<2 or st.energy<18:
                st.zone='homes'; st.x=48+(int(a.code)%9)-4; st.y=76+(int(a.code)%7)-3; st.action='sleeping / recharging'; st.activity_kind='life'; st.task_id=None; st.energy=min(100,st.energy+8); a.status='sleeping'
            else:
                # Non-working characters maintain the simulated city; this is deliberately labeled life/city activity, not AI work.
                choices=[('construction','building city',40,18),('market','getting supplies',76,73),('power','maintaining utilities',17,78),('homes','eating / socializing',50,76)]
                zone,action,x,y=choices[(int(a.code)+slot)%len(choices)]; st.zone=zone; st.action=action; st.activity_kind='city_life'; st.task_id=None; st.x=x+(a.id%9)-4; st.y=y+(a.id%7)-3; st.energy=max(18,st.energy-0.4); a.status='idle'
            st.updated_at=now
        site=s.query(WorldStructure).filter(WorldStructure.kind=='construction').first()
        if site:
            builders=sum(1 for st in states.values() if st.zone=='construction' and st.activity_kind=='city_life')
            site.workers=builders; site.progress+=builders*0.05
            if site.progress>=100:
                site.progress=0; site.level+=1; site.name=f'CITY EXPANSION LVL {site.level}'
                s.add(WorldEvent(event='city_expanded',detail=f'City simulation completed expansion level {site.level-1}.'))
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
            commander=s.query(Agent).filter(Agent.code=='000').first()
            s.add(Task(title='Commander daily review',instructions='Review the current Minion World operation. Produce a compact owner briefing: useful work to prioritize, evidence needed, risks, and no more than six specialist assignments. Never spend money or take external consequential actions.',assigned_agent=commander.id,priority=100))
            s.add(WorldEvent(event='world_wakeup',detail='Commander activated in cost-controlled mode. Specialist workers are deployed only for useful assignments.')); s.commit()
    return RedirectResponse('/command',303)
@app.get('/api/diagnostics')
def diagnostics(request:Request):
    if not authed(request): raise HTTPException(401,'login required')
    with Session(engine) as s:
        failed=s.query(Task).filter(Task.status=='failed').order_by(Task.id.desc()).limit(25).all()
        ws=s.query(Workspace).all()
        workspace_errors=[{'agent_id':w.agent_id,'error':(w.desk_notes or '')[:1000]} for w in ws if (w.desk_notes or '').startswith('Last error:')]
        return {'openai_key_present':bool(os.getenv('OPENAI_API_KEY')),'model':os.getenv('MINION_MODEL','gpt-5-mini'),'failed_count':s.query(Task).filter(Task.status=='failed').count(),'failed_tasks':[{'id':t.id,'title':t.title,'agent_id':t.assigned_agent,'error':t.result[:1200]} for t in failed],'workspace_errors':workspace_errors[:25]}

@app.post('/tasks/retry-failed')
def retry_failed(request:Request):
    if not authed(request): return RedirectResponse('/login',303)
    with Session(engine) as s:
        # Cost safety: retry at most 3 failures per click, never all failed tasks.
        failed=s.query(Task).filter(Task.status=='failed').order_by(Task.id.desc()).limit(3).all()
        for t in failed:
            t.status='queued'; t.result=''; t.completed_at=None
            if t.assigned_agent:
                a=s.get(Agent,t.assigned_agent)
                if a: a.status='idle'
                w=s.query(Workspace).filter(Workspace.agent_id==t.assigned_agent).first()
                if w: w.current_task_id=None
        s.add(WorldEvent(event='failed_tasks_retried',detail=f'Owner retried {len(failed)} failed AI tasks in cost-controlled mode.')); s.commit()
    return RedirectResponse('/command',303)

@app.get('/api/status')
def status():
    with Session(engine) as s:
        tr=s.query(Treasury).first(); return {'agents':s.query(Agent).count(),'working':s.query(Agent).filter(Agent.status=='working').count(),'sleeping':s.query(Agent).filter(Agent.status=='sleeping').count(),'queued':s.query(Task).filter(Task.status=='queued').count(),'completed':s.query(Task).filter(Task.status=='completed').count(),'treasury':tr.available_cash,'daily_proposal_limit':tr.daily_limit,'pending_proposals':s.query(Proposal).filter(Proposal.status=='pending').count()}

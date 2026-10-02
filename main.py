import os, json, secrets, datetime as dt
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from app import engine, Agent, Workspace, Task, Treasury, Proposal, WorldEvent, WorldStructure

app=FastAPI(title='Minion World Operations',version='2.0')
app.add_middleware(SessionMiddleware,secret_key=os.getenv('SESSION_SECRET',secrets.token_hex(32)),max_age=86400*7,https_only=False)

def authed(r): return r.session.get('owner') is True

def shell(body):
    return HTMLResponse('''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Minion World</title><style>
*{box-sizing:border-box}html,body{margin:0;background:#05080b;color:#e8edf0;font-family:Inter,Arial,sans-serif}button,input,textarea{font:inherit}.bar{height:54px;background:#091117;border-bottom:1px solid #263944;display:flex;align-items:center;padding:0 16px;gap:14px}.brand{font-weight:900;letter-spacing:2px}.brand small{display:block;font-size:8px;color:#8195a1;letter-spacing:1px}.stats{display:flex;gap:7px;margin-left:auto}.stat{padding:6px 8px;background:#101c24;border:1px solid #263a45;border-radius:5px;font-size:9px}.world-wrap{position:relative;max-width:1500px;margin:auto;background:#020405}.world{height:760px}.hud{position:absolute;z-index:8;background:#071017e8;border:1px solid #40545e;border-radius:7px;padding:9px;box-shadow:0 4px 18px #0008}.tl{top:12px;left:12px}.tr{top:12px;right:12px;width:280px}.bl{bottom:12px;left:12px}.br{bottom:12px;right:12px;width:310px}.hud b,.hud small{display:block}.hud small{color:#93a5ae;font-size:10px;margin-top:4px;line-height:1.4}.tag{display:inline-block;padding:3px 6px;border-radius:4px;background:#172832;margin:3px 3px 0 0;font-size:8px}.controls{max-width:1500px;margin:8px auto 20px;display:grid;grid-template-columns:auto auto auto 1fr;gap:7px;padding:0 8px}.controls button,.mission button{background:#1a2a34;color:#fff;border:1px solid #3b5360;border-radius:5px;padding:9px 12px;font-weight:800;cursor:pointer}.mission{display:grid;grid-template-columns:80px 180px 1fr auto;gap:5px}.mission input{background:#0b151c;color:#fff;border:1px solid #314650;border-radius:5px;padding:9px}.panel-title{font-size:10px;letter-spacing:1px;color:#9fb0b9}.progress{height:6px;background:#111e25;border-radius:5px;overflow:hidden;margin-top:5px}.progress i{display:block;height:100%;background:#62c987}.feed{max-height:150px;overflow:auto;margin-top:7px;font-size:9px;color:#a9b6bd}.feed div{border-top:1px solid #1c2a31;padding:5px 0}.login{max-width:420px;margin:12vh auto;background:#0c171e;border:1px solid #263944;border-radius:12px;padding:24px}.login input{width:100%;padding:12px;margin:10px 0;background:#081117;color:white;border:1px solid #344953;border-radius:6px}@media(max-width:900px){.world{height:620px}.stats .stat:nth-child(n+4){display:none}.controls{grid-template-columns:1fr 1fr}.mission{grid-column:1/-1;grid-template-columns:1fr}.tr{width:220px}.br{width:230px}}</style></head><body>'''+body+'''</body></html>''')

@app.get('/')
def root(request:Request): return RedirectResponse('/command' if authed(request) else '/login')
@app.get('/login')
def login(): return shell('<div class="login"><div class="brand">MINION WORLD<small>OWNER OPERATIONS NETWORK</small></div><form method="post"><input name="password" type="password" autofocus placeholder="Owner password"><button>ENTER WORLD</button></form></div>')
@app.post('/login')
def login_post(request:Request,password:str=Form(...)):
    if password!=os.getenv('OWNER_PASSWORD','minion-change-me'): return RedirectResponse('/login',303)
    request.session['owner']=True; return RedirectResponse('/command',303)
@app.get('/logout')
def logout(request:Request): request.session.clear(); return RedirectResponse('/login',303)

@app.get('/api/world')
def world(request:Request):
    if not authed(request): return JSONResponse({'error':'auth'},401)
    with Session(engine) as s:
        agents=[]
        for a in s.query(Agent).order_by(Agent.code).all():
            w=s.query(Workspace).filter(Workspace.agent_id==a.id).first(); t=s.get(Task,w.current_task_id) if w and w.current_task_id else None
            agents.append({'code':a.code,'name':a.name,'division':a.division,'status':a.status,'task':t.title if t else None,'task_id':t.id if t else None})
        structures=[{'key':x.key,'name':x.name,'kind':x.kind,'level':x.level,'progress':x.progress,'workers':x.workers} for x in s.query(WorldStructure).all()]
        events=[{'event':e.event,'detail':e.detail,'time':e.created_at.isoformat()} for e in s.query(WorldEvent).order_by(WorldEvent.id.desc()).limit(15).all()]
        tr=s.query(Treasury).first()
        return {'agents':agents,'structures':structures,'events':events,'treasury':tr.available_cash if tr else 0,'queued':s.query(Task).filter(Task.status=='queued').count(),'working':s.query(Task).filter(Task.status=='working').count(),'done':s.query(Task).filter(Task.status=='completed').count(),'ai':bool(os.getenv('OPENAI_API_KEY'))}

@app.post('/missions/create')
def mission(request:Request,title:str=Form(...),instructions:str=Form(...),assigned_code:str=Form('')):
    if not authed(request): return RedirectResponse('/login',303)
    with Session(engine) as s:
        aid=None
        if assigned_code.strip():
            a=s.query(Agent).filter(Agent.code==assigned_code.strip()).first(); aid=a.id if a else None
        t=Task(title=title.strip()[:200],instructions=instructions.strip()[:5000],assigned_agent=aid,priority=95);s.add(t);s.add(WorldEvent(agent_id=aid,event='owner_mission',detail=title[:200]));s.commit()
    return RedirectResponse('/command',303)

@app.post('/commander/mission')
def commander(request:Request,goal:str=Form(...)):
    if not authed(request): return RedirectResponse('/login',303)
    goal=goal.strip()[:4000]
    with Session(engine) as s:
        commander=s.query(Agent).filter(Agent.code=='000').first()
        plan=[
          ('Market Intelligence','RESEARCH',f'Research the market and demand relevant to this owner goal: {goal}. Return evidence, findings, unknowns, and useful next actions.'),
          ('Sourcing','SOURCE',f'Investigate legitimate suppliers, tools, resources, or inputs relevant to this owner goal: {goal}. Do not buy anything.'),
          ('Product Underwriting','UNDERWRITE',f'Analyze costs, margins, feasibility, risks, and assumptions for this owner goal: {goal}.'),
          ('Sales & Listings','POSITION',f'Develop sales, positioning, customer, pricing, or presentation research relevant to this owner goal: {goal}.'),
          ('Operations','OPERATE',f'Design an execution workflow, logistics plan, and measurable next steps for this owner goal: {goal}.'),
          ('Risk & Audit','AUDIT',f'Audit this owner goal for weak assumptions, policy/IP/supplier/financial risks and evidence gaps: {goal}.')]
        for div,label,inst in plan:
            workers=s.query(Agent).filter(Agent.division==div).order_by(Agent.id).limit(3).all()
            for i,a in enumerate(workers): s.add(Task(title=f'{label} · Commander mission',instructions=inst+f' You are specialist {i+1}; focus on a distinct angle.',assigned_agent=a.id,priority=100-i))
        s.add(WorldEvent(agent_id=commander.id if commander else None,event='commander_deployed',detail=f'18-agent operation: {goal[:240]}'));s.commit()
    return RedirectResponse('/command',303)

@app.get('/command')
def command(request:Request):
    if not authed(request): return RedirectResponse('/login')
    with Session(engine) as s:
        tr=s.query(Treasury).first(); working=s.query(Task).filter(Task.status=='working').count(); queued=s.query(Task).filter(Task.status=='queued').count(); done=s.query(Task).filter(Task.status=='completed').count()
    body=f'''<div class="bar"><div class="brand">MINION WORLD<small>AUTONOMOUS OPERATIONS CITY</small></div><div class="stats"><span class="stat" id="ai">AI</span><span class="stat">{working} REAL JOBS</span><span class="stat">{queued} QUEUED</span><span class="stat">{done} DONE</span><span class="stat">USD {tr.available_cash if tr else 0:,.2f}</span></div><a href="/logout">EXIT</a></div>
<div class="world-wrap"><div id="world" class="world"></div><div class="hud tl"><b id="clock">08:00</b><small>LIVE CITY · drag to orbit · wheel to zoom</small></div><div class="hud tr"><div class="panel-title">COMMANDER #000</div><form method="post" action="/commander/mission"><input name="goal" required style="width:100%;margin:7px 0;padding:8px;background:#0a141a;color:#fff;border:1px solid #344b56" placeholder="Give the company a goal..."><button style="width:100%">DEPLOY TEAM</button></form><small>Commander breaks one goal into specialist research, sourcing, underwriting, sales, operations and audit jobs.</small></div><div class="hud bl"><b>WORLD MAP</b><canvas id="mini" width="180" height="115"></canvas><small>Workers physically travel to the facility matching their real backend job.</small></div><div class="hud br" id="inspect"><b>SELECT A WORKER</b><small>Click a character to inspect real task state.</small><div class="feed" id="feed"></div></div></div>
<div class="controls"><button id="follow">FOLLOW</button><button id="home">CITY VIEW</button><button id="pause">PAUSE VISUALS</button><form class="mission" method="post" action="/missions/create"><input id="worker" name="assigned_code" placeholder="Worker #"><input name="title" required placeholder="Specific mission"><input name="instructions" required placeholder="What should this worker actually do?"><button>ASSIGN</button></form></div>
<script type="module">
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js';
import {{OrbitControls}} from 'https://cdn.jsdelivr.net/npm/three@0.180.0/examples/jsm/controls/OrbitControls.js';
const root=document.getElementById('world'), scene=new THREE.Scene();scene.background=new THREE.Color(0x87a9b8);scene.fog=new THREE.Fog(0x87a9b8,70,210);
const camera=new THREE.PerspectiveCamera(55,root.clientWidth/root.clientHeight,.1,500);camera.position.set(58,62,78);
const renderer=new THREE.WebGLRenderer({{antialias:true}});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setSize(root.clientWidth,root.clientHeight);renderer.shadowMap.enabled=true;root.appendChild(renderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,0,0);controls.enableDamping=true;controls.maxPolarAngle=1.48;controls.minDistance=16;controls.maxDistance=145;
scene.add(new THREE.HemisphereLight(0xd8efff,0x36502c,2.2));const sun=new THREE.DirectionalLight(0xfff1c9,2.8);sun.position.set(45,80,30);sun.castShadow=true;scene.add(sun);
const ground=new THREE.Mesh(new THREE.PlaneGeometry(190,150),new THREE.MeshStandardMaterial({{color:0x376c3f,roughness:1}}));ground.rotation.x=-Math.PI/2;ground.receiveShadow=true;scene.add(ground);
const roads=[];function road(x,z,w,d){{let m=new THREE.Mesh(new THREE.BoxGeometry(w,.08,d),new THREE.MeshStandardMaterial({{color:0x30383d}}));m.position.set(x,.04,z);scene.add(m);roads.push(m)}}road(0,0,190,11);road(0,44,190,11);road(0,-44,190,11);road(-45,0,11,150);road(45,0,11,150);
const spots={{hq:[0,18],lab:[65,-25],warehouse:[-67,20],market:[67,57],power:[-68,58],homes:[0,58],construction:[0,-48]}};
const colors={{hq:0x243844,lab:0x285e70,warehouse:0x48555b,market:0x76503a,power:0x3e5c52,homes:0x705548,construction:0x9a7936}};const buildings={{}};
function building(kind,name,x,z,w=24,d=18,h=11){{let g=new THREE.Group(),base=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),new THREE.MeshStandardMaterial({{color:colors[kind]||0x45545c,roughness:.75}}));base.position.y=h/2;base.castShadow=true;g.add(base);for(let ix=-w/2+3;ix<w/2-2;ix+=5)for(let iy=3;iy<h-1;iy+=4){{let win=new THREE.Mesh(new THREE.PlaneGeometry(2.2,1.5),new THREE.MeshBasicMaterial({{color:0x9bd6e8}}));win.position.set(ix,iy,d/2+.01);g.add(win)}}g.position.set(x,0,z);g.userData={{kind,name}};scene.add(g);buildings[kind]=g;return g}}
building('hq','COMMAND HQ',0,18,29,23,17);building('lab','RESEARCH CENTER',65,-25,28,20,13);building('warehouse','LOGISTICS DEPOT',-67,20,30,23,10);building('market','MARKET DISTRICT',67,57,30,22,12);building('power','UTILITY YARD',-68,58,26,20,9);building('homes','RESIDENTIAL BLOCK',0,58,36,20,12);building('construction','ACTIVE DEVELOPMENT',0,-48,32,23,4);
for(let i=0;i<65;i++){{let t=new THREE.Mesh(new THREE.CylinderGeometry(0,2.3,6,7),new THREE.MeshStandardMaterial({{color:0x28613a}}));t.position.set(-90+(i*29)%180,3,-70+(i*47)%140);scene.add(t)}}
const people=new Map(),ray=new THREE.Raycaster(),mouse=new THREE.Vector2();let state=null,selected=null,paused=false,follow=false;
function makePerson(a,i){{let g=new THREE.Group();let body=new THREE.Mesh(new THREE.CapsuleGeometry(.65,1.3,4,8),new THREE.MeshStandardMaterial({{color:0xf1c842}}));body.position.y=1.6;let legs=new THREE.Mesh(new THREE.BoxGeometry(1.2,.8,.75),new THREE.MeshStandardMaterial({{color:0x315b91}}));legs.position.y=.65;let eye=new THREE.Mesh(new THREE.SphereGeometry(.35,8,8),new THREE.MeshStandardMaterial({{color:0xdce9ef}}));eye.position.set(0,2.1,.6);g.add(body,legs,eye);g.scale.set(.75,.75,.75);g.userData={{agent:a}};scene.add(g);people.set(a.code,{{g,a,target:new THREE.Vector3(),phase:'travel',wait:0}});return g}}
function destination(a){{if(a.status==='sleeping')return 'homes';if(a.task){{let d=a.division;return d==='Market Intelligence'||d==='Product Underwriting'?'lab':d==='Sourcing'||d==='Operations'?'warehouse':d==='Sales & Listings'?'market':'hq'}}return Math.random()<.22?'construction':Math.random()<.45?'homes':Math.random()<.65?'market':'hq'}}
function setTarget(p){{let k=destination(p.a),s=spots[k];p.dest=k;p.target.set(s[0]+(Math.random()-.5)*14,0,s[1]+(Math.random()-.5)*10);p.phase='travel';p.wait=0}}
function sync(data){{state=data;document.getElementById('ai').textContent=data.ai?'AI ONLINE':'AI OFFLINE';data.agents.forEach((a,i)=>{{let p=people.get(a.code);if(!p){{makePerson(a,i);p=people.get(a.code);let h=spots.homes;p.g.position.set(h[0]+(Math.random()-.5)*20,0,h[1]+(Math.random()-.5)*12);setTarget(p)}}else{{let changed=p.a.task_id!==a.task_id||p.a.status!==a.status;p.a=a;p.g.userData.agent=a;if(changed)setTarget(p)}}}});let site=data.structures.find(x=>x.kind==='construction');if(site){{let b=buildings.construction;b.scale.y=Math.max(.25,site.progress/100);b.userData.progress=site.progress}}document.getElementById('feed').innerHTML=data.events.slice(0,7).map(e=>'<div><b>'+e.event.replaceAll('_',' ')+'</b><br>'+e.detail+'</div>').join('')}}
async function refresh(){{try{{let r=await fetch('/api/world');if(r.ok)sync(await r.json())}}catch(e){{}}}}refresh();setInterval(refresh,5000);
function tick(dt){{if(paused)return;people.forEach(p=>{{if(p.phase==='travel'){{let d=p.target.clone().sub(p.g.position),len=d.length();if(len>.6){{d.normalize();p.g.position.addScaledVector(d,dt*(p.a.status==='working'?4.2:3));p.g.rotation.y=Math.atan2(d.x,d.z)}}else{{p.phase=p.a.task?'real_work':'life';p.wait=p.a.task?999999:3+Math.random()*7}}}}else{{p.wait-=dt;if(p.wait<=0)setTarget(p)}}}});if(follow&&selected){{let q=selected.g.position;controls.target.lerp(new THREE.Vector3(q.x,1,q.z),.08)}}}}
renderer.domElement.addEventListener('pointerdown',e=>{{let r=renderer.domElement.getBoundingClientRect();mouse.x=((e.clientX-r.left)/r.width)*2-1;mouse.y=-((e.clientY-r.top)/r.height)*2+1;ray.setFromCamera(mouse,camera);let meshes=[];people.forEach(p=>p.g.children.forEach(c=>meshes.push(c)));let hit=ray.intersectObjects(meshes)[0];if(hit){{let g=hit.object.parent,p=people.get(g.userData.agent.code);selected=p;document.getElementById('worker').value=p.a.code;document.getElementById('inspect').innerHTML='<b>'+p.a.name+' #'+p.a.code+'</b><small>'+p.a.division+' · '+p.a.status+'<br>'+(p.a.task?'<b>REAL TASK:</b> '+p.a.task:'Life activity: '+p.phase)+'<br>Location: '+p.dest+'</small><div class="feed" id="feed"></div>';if(state)document.getElementById('feed').innerHTML=state.events.slice(0,5).map(e=>'<div>'+e.detail+'</div>').join('')}}}});
document.getElementById('follow').onclick=()=>follow=!follow;document.getElementById('home').onclick=()=>{{follow=false;camera.position.set(58,62,78);controls.target.set(0,0,0)}};document.getElementById('pause').onclick=()=>paused=!paused;
let last=performance.now();function frame(t){{let dt=Math.min(.05,(t-last)/1000);last=t;tick(dt);controls.update();renderer.render(scene,camera);requestAnimationFrame(frame)}}requestAnimationFrame(frame);addEventListener('resize',()=>{{camera.aspect=root.clientWidth/root.clientHeight;camera.updateProjectionMatrix();renderer.setSize(root.clientWidth,root.clientHeight)}});
</script>'''
    return shell(body)

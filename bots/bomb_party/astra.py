"""Astra: temporal navigation, counterfactual bomb safety, territory control."""
import heapq
import time
import itertools

_NAMES = ('up', 'down', 'left', 'right', 'stay')
_memory = {}

class Arena:
    def __init__(self, s):
        self.started=time.process_time()
        self.s = s
        self.w = w = s['width']
        self.h = h = s['height']
        self.n = n = w*h
        self.turn = s['turn']
        self.g = list(''.join(s['grid']))
        self.me = next(p for p in s['players'] if p['id'] == s['you'])
        self.p = self.me['y']*w+self.me['x']
        self.enemies = [p for p in s['players'] if p['id'] != s['you']]
        self.ep = {p['y']*w+p['x'] for p in self.enemies}
        self.occ = sum(1 << p for p in self.ep)
        self.items = {i['y']*w+i['x']:i['kind'] for i in s['items']}
        self.limits={p['id']:p['bomb_limit'] for p in s['players']}
        self.deltas = (-w,w,-1,1)
        self.full = (1<<n)-1
        self.left = sum(1 << (y*w) for y in range(h))
        self.right = self.left << (w-1)
        self.neigh = []
        for p in range(n):
            x,y=p%w,p//w
            self.neigh.append([q for q in (p-w,p+w,p-1,p+1) if 0<=q<n and abs(q%w-x)+abs(q//w-y)==1])
        self.bombs = [(b['y']*w+b['x'],b['fuse'],b['radius'],_NAMES.index(b['direction']) if b.get('direction') in _NAMES[:4] else -1,b['owner'],b['id']) for b in s['bombs']]
        self.bp = {b[0] for b in self.bombs}
        self.crush = _memory.get('crush')
        if self.crush is None or s['turn'] == 1:
            cells=[]
            lo,hi=0,w-1
            while lo<=hi:
                cells.extend((x,lo) for x in range(lo,hi+1))
                cells.extend((hi,y) for y in range(lo+1,hi+1))
                if lo<hi:
                    cells.extend((x,hi) for x in range(hi-1,lo-1,-1))
                    cells.extend((lo,y) for y in range(hi-1,lo,-1))
                lo+=1; hi-=1
            for _ in range(s['crush_rotation']): cells=[(w-1-y,x) for x,y in cells]
            old={y*w+x for x,y in s.get('crushed',[])}
            cells=[y*w+x for x,y in cells if self.g[y*w+x]!='@' or y*w+x in old]
            self.crush={p:s['crush_start']+i for i,p in enumerate(cells)}
            _memory['crush']=self.crush
        self.life=[self.crush.get(p,10000)-self.turn for p in range(n)]
        self.crush_at={t:p for p,t in self.crush.items()}
        self.open=sum(1<<i for i,c in enumerate(self.g) if c=='.')
        self.history=_memory.setdefault('visits',{})
        self.history[self.p]=self.history.get(self.p,0)*.94+1
        if self.turn%8==0:
            for p in self.history: self.history[p]*=.75
        self.horizon=min(max(8,s['bomb_fuse']+3), max(1, max(self.crush.values(), default=self.turn+20)-self.turn))

    def expand(self, bits):
        return ((bits<<self.w)|(bits>>self.w)|((bits&~self.right)<<1)|((bits&~self.left)>>1))&self.full

    def blast(self, p, radius, grid=None, bombs=None):
        g=self.g if grid is None else grid
        result=1<<p
        for d in self.deltas:
            q=p
            for _ in range(radius):
                nq=q+d
                if nq<0 or nq>=self.n or (abs(d)==1 and nq//self.w!=q//self.w):break
                q=nq
                if g[q]=='@':break
                result|=1<<q
                if g[q]=='#' or bombs is not None and q in bombs:break
        return result

    def forecast(self, bombs=None, own=None, kick=None, mobile=False, horizon=None, scheduled=None):
        # Each layer describes terrain and bombs BEFORE movement, then terminal fire.
        H=self.horizon if horizon is None else horizon
        g=self.g.copy()
        bs=list(self.bombs if bombs is None else bombs)
        if kick is not None:
            bp,di=kick
            bs=[(p,f,r,di if p==bp else d,o,i) for p,f,r,d,o,i in bs]
        items=set(self.items)
        if own is not None:items.discard(own)
        floors=[]; blocks=[]; fires=[]; endfloors=[]; broken=[]
        floor=self.open
        for t in range(H):
            if scheduled is not None and t==1:
                occupied={b[0] for b in bs}
                bs.extend(b for b in scheduled if g[b[0]]=='.' and b[0] not in occupied and sum(old[4]==b[4] for old in bs)<self.limits.get(b[4],6))
            floors.append(floor)
            bmap={b[0]:j for j,b in enumerate(bs)}
            blocks.append(sum(1<<p for p in bmap))
            # Future trajectories assume free movement. First tick has actual blockers.
            blocked=set(bmap)|items
            if t==0:
                if not mobile:blocked|=self.ep
                if own is not None:blocked.add(own)
            targets={}
            counts={}
            for j,(p,f,r,d,o,i) in enumerate(bs):
                if d>=0:
                    q=p+self.deltas[d]
                    if q in self.neigh[p] and g[q]=='.' and q not in blocked:
                        targets[j]=q; counts[q]=counts.get(q,0)+1
            moved=[]
            for j,(p,f,r,d,o,i) in enumerate(bs):
                if j in targets and counts[targets[j]]==1:p=targets[j]
                elif d>=0:d=-1
                moved.append((p,f-1,r,d,o,i))
            bs=moved
            bmap={b[0]:j for j,b in enumerate(bs)}
            queue=[j for j,b in enumerate(bs) if b[1]<=0]
            seen=set(); fire=0
            for j in queue:
                if j in seen:continue
                seen.add(j)
                p,f,r,d,o,i=bs[j]
                fire|=1<<p
                for delta in self.deltas:
                    q=p
                    for _ in range(r):
                        nq=q+delta
                        if nq not in self.neigh[q]:break
                        q=nq
                        if g[q]=='@':break
                        fire|=1<<q
                        if g[q]=='#':break
                        if q in bmap:
                            queue.append(bmap[q]);break
            destroyed=[]
            b=fire
            while b:
                bit=b&-b; p=bit.bit_length()-1; b-=bit
                if g[p]=='#':
                    g[p]='.'; floor|=bit; destroyed.append(p)
                items.discard(p)
            bs=[b for j,b in enumerate(bs) if j not in seen]
            cp=self.crush_at.get(self.turn+t)
            if cp is not None:
                g[cp]='@'; floor&=~(1<<cp); fire|=1<<cp
                items.discard(cp);bs=[b for b in bs if b[0]!=cp]
            fires.append(fire); endfloors.append(floor);broken.append(destroyed)
        return (floors,blocks,fires,endfloors,broken)

    def reach(self, fc, p, start=0, hold_enemies=1, need_layers=False, avoid=None):
        floors,blocks,fires,ends,_=fc
        R=1<<p
        layers=[]
        depth=0
        for t in range(start,len(fires)):
            if t>start:
                R=R | (self.expand(R)&~blocks[t])
                if t<=hold_enemies:R &= ~self.occ | (1<<p if p in self.ep else 0)
            R &= floors[t] & ~fires[t] & ends[t]
            if avoid is not None and t>start and t<len(avoid):R &= ~avoid[t]
            if not R:break
            depth+=1;layers.append(R)
        if need_layers:return depth,R,layers
        return depth,R

    def enemy_areas(self,fc):
        areas=[0]*self.horizon
        for e in self.ep:
            R=1<<e
            for t in range(min(4,self.horizon)):
                R=(R|(self.expand(R)&~fc[1][t]))&fc[0][t]&~fc[2][t]&fc[3][t]
                if t+1<self.horizon:areas[t+1]|=R
        # Adversarial body blocking matters most during the next two moves.
        for t in range(3,len(areas)):areas[t]=0
        return areas

    def newbomb(self,p,player):
        return (p,self.s['bomb_fuse']+1,player['radius'],-1,player['id'],100000+player['id'])

    def distance(self, starts, grid=None, through=False):
        g=self.g if grid is None else grid
        ds=[999.]*self.n;heap=[]
        for p,v in starts:
            ds[p]=v; heapq.heappush(heap,(v,p))
        while heap:
            d,p=heapq.heappop(heap)
            if d!=ds[p]:continue
            for q in self.neigh[p]:
                if g[q]=='@' or (g[q]=='#' and not through):continue
                if self.life[q]<d+3:continue
                nd=d+(6 if g[q]=='#' else 1)
                if nd<ds[q]:ds[q]=nd;heapq.heappush(heap,(nd,q))
        return ds

    def tile_values(self, fc):
        g=self.g; w=self.w; me=self.me
        # Assess the future open board after already committed explosions.
        future=g.copy()
        destroyed=set()
        for cells in fc[4]:destroyed.update(cells)
        for p in destroyed:future[p]='.'
        late=self.turn>self.s['crush_start']+25
        quality=[-1000.]*self.n
        crates=[0.]*self.n
        center_targets=[(p,0.) for p in self.crush if self.life[p]>35 and abs(p%w-(w-1)/2)+abs(p//w-(self.h-1)/2)<=3]
        if self.turn>self.s['crush_start']-15:
            best=max((self.life[p] for p in self.crush if g[p]!='@'),default=0)
            center_targets=[(p,0.) for p in self.crush if self.life[p]>=best and g[p]!='@']
        if not center_targets:
            best=max((self.life[p] for p in self.crush if g[p]!='@'),default=0)
            center_targets=[(p,0.) for p in self.crush if self.life[p]>=best-2 and g[p]!='@']
        centerd=self.distance(center_targets,through=True)
        pressure=min(2.0,max(.15,(self.turn-self.s['crush_start']+45)/35))
        for p in range(self.n):
            if future[p]!='.':continue
            degree=sum(future[q]=='.' and self.life[q]>6 for q in self.neigh[p])
            quality[p]=.35*degree-.06*self.history.get(p,0)
            if degree<2:quality[p]-=1.3
            quality[p]-=pressure*min(centerd[p],30)*.3
            remain=self.life[p]
            if remain<20:quality[p]-=(20-remain)*.32
            if remain<8:quality[p]-=(8-remain)*1.1
            if late:quality[p]+=min(35,max(0,remain))*.07
            if g[p]=='.':
                ray=self.blast(p,me['radius'])
                cr=0.
                while ray:
                    bit=ray&-ray;q=bit.bit_length()-1;ray-=bit
                    if g[q]=='#' and q not in destroyed:
                        cr+=1.0 + .45*(centerd[q]<centerd[p])
                crates[p]=cr
        # Reward reaching a useful future planting square, with travel cost.
        targets=[]
        for p,c in enumerate(crates):
            if c>0 and self.life[p]>10:
                v=2.0+min(c,4)*1.55
                if late:v*=.6
                targets.append((p,-v))
        potential=self.distance(targets, future)
        for p in range(self.n):
            if quality[p]>-999 and potential[p]<0:quality[p]+=-potential[p]*.75
        # Loot is worth more than one more speculative crate, especially kick.
        itemtargets=[]
        for p,kind in self.items.items():
            if kind=='kick':v=10. if not me['can_kick'] else 1.0
            elif kind=='bomb':v=8. if me['bomb_limit']==1 else (5. if me['bomb_limit']<3 else 1.2)
            else:v=7.5 if me['radius']<4 else (3.5 if me['radius']<6 else 1.)
            if any(f>>p&1 for f in fc[2][:2]):v*=.2
            itemtargets.append((p,-v))
        ip=self.distance(itemtargets,future)
        for p in range(self.n):
            if quality[p]>-999 and ip[p]<0:quality[p]+=-ip[p]*1.2
        # Do not stand in a narrow corridor directly beside an armed rival.
        for enemy in self.enemies:
            e=enemy['y']*w+enemy['x']
            ds=self.distance([(e,0)],future)
            ray=self.blast(e,enemy['radius'],future)
            for p in range(self.n):
                if quality[p]<-999:continue
                d=ds[p]
                if d<5:
                    quality[p]-=(5-d)*.28
                    if ray>>p&1 and enemy['can_bomb']:quality[p]-=(.35 if self.turn>self.s['crush_start']+20 else .8)*(5-d)
        return quality,crates

    def attack(self, fc, base, action):
        value=0.
        for enemy in self.enemies:
            e=enemy['y']*self.w+enemy['x']
            if abs(e%self.w-self.p%self.w)+abs(e//self.w-self.p//self.w)>self.me['radius']+5:continue
            # Enemy gets a move on the planting turn, unlike the planter.
            choices=[e]+[q for q in self.neigh[e] if self.g[q]=='.' and q not in self.bp and q!=self.p and q not in self.ep]
            alive=0;alivebase=0;end=0;endbase=0
            for q in choices:
                d,r=self.reach(fc,q,hold_enemies=0)
                db,rb=self.reach(base,q,hold_enemies=0)
                if d==len(fc[2]):alive+=1;end|=r
                if db==len(base[2]):alivebase+=1;endbase|=rb
            if alivebase:
                if not alive:value+=70. if not enemy['can_kick'] else 20.
                else:
                    reduction=max(0,1-end.bit_count()/max(1,endbase.bit_count()))
                    value+=reduction*5+(alivebase-alive)/alivebase*5
                    if action=='bomb' and self.blast(self.p,self.me['radius'])>>e&1:value+=.8
        return value

    def decide(self):
        p=self.p
        base=self.forecast(own=p)
        quality,crates=self.tile_values(base)
        actions=[('stay',p,None)]
        for d,q in enumerate((p-self.w,p+self.w,p-1,p+1)):
            if q not in self.neigh[p]:continue
            if q in self.bp:
                if self.me['can_kick']:actions.append((_NAMES[d],p,(q,d)))
            elif self.g[q]=='.' and q not in self.ep:actions.append((_NAMES[d],q,None))
        if self.me['can_bomb'] and p not in self.bp:
            actions.append(('bomb',p,None))
        slides=any(b[3]>=0 for b in self.bombs)
        contenders=[]
        enemybombs=[self.newbomb(e['y']*self.w+e['x'],e) for e in self.enemies if e['can_bomb'] and e['y']*self.w+e['x'] not in self.bp and abs(e['x']-p%self.w)+abs(e['y']-p//self.w)<9]
        for act,q,kick in actions:
            bs=self.bombs+[self.newbomb(p,self.me)] if act=='bomb' else self.bombs
            fc=self.forecast(bs,own=q,kick=kick) if act=='bomb' or kick is not None or slides else base
            depth,R,layers=self.reach(fc,q,need_layers=True)
            score=-10000+(depth*500)+quality[q]*.1
            if layers:score+=max((self.life[i] for i in range(self.n) if layers[-1]>>i&1),default=0)*.01
            if depth==self.horizon:
                score=0.
                # Best reachable utility, discounted by time so it actually travels.
                best=-1000.
                for t,layer in enumerate(layers):
                    while layer:
                        bit=layer&-layer; pos=bit.bit_length()-1;layer-=bit
                        v=quality[pos]-.65*t
                        if v>best:best=v
                score+=best+.07*min(R.bit_count(),35)
                score+=.15*quality[q]

                if act=='stay':score-=.13
                if q in self.bp:score-=.75
                if any(f>>q&1 for f in fc[2][1:3]):score-=.35
                if kick is not None:score-=.3
                # A move contested by another player can fail. Reject lethal conflicts.
                conflict=any(q in self.neigh[e] for e in self.ep) if q!=p else False
                if conflict:
                    fd,_=self.reach(fc,p)
                    score-=.7 if fd==self.horizon else 180.
                # Counterfactual: rivals may plant simultaneously. All such bombs
                # together form a useful conservative certificate against traps.
                if enemybombs:
                    ef=self.forecast(bs+enemybombs,own=q,kick=kick)
                    ed,er=self.reach(ef,q,hold_enemies=2)
                    if ed<self.horizon:score-=230.+(self.horizon-ed)*20
                    else:score+=.03*min(er.bit_count(),20)
                if slides:
                    ff=self.forecast(bs,own=q,kick=kick,mobile=True)
                    fd,fr=self.reach(ff,q)
                    if fd<self.horizon:score-=300.+(self.horizon-fd)*20
                if act=='bomb':
                    attack=self.attack(fc,base,act)
                    reward=crates[p]*2.4
                    if self.turn>self.s['crush_start']+25:reward*=.6
                    score+=reward+attack-1.6
                    if not crates[p] and attack<.5:score-=6
                    # Prefer several different routes out over a single brittle path.
                    early=layers[min(self.s['bomb_fuse'],len(layers)-1)].bit_count()
                    if early<3:score-=3.5
                    # A rival can move now, then plant a relay bomb next tick.
                    # Check these delayed chains before committing our own fuse.
                    relaybad=False
                    for e in self.enemies:
                        ep=e['y']*self.w+e['x']
                        if abs(e['x']-p%self.w)+abs(e['y']-p//self.w)>11:continue
                        spots=[ep]+[z for z in self.neigh[ep] if self.g[z]=='.' and z not in self.bp and z not in self.ep and z!=p]
                        for z in spots:
                            ef=self.forecast(bs,own=q,scheduled=[self.newbomb(z,e)])
                            ed,er=self.reach(ef,q,hold_enemies=2)
                            if ed<self.horizon:
                                relaybad=True;break
                        if relaybad:break
                    if relaybad:score-=420
            contenders.append((score,act,q,depth))
        contenders.sort(reverse=True)
        _memory['last']=(self.turn,p,contenders)
        if time.process_time()-self.started>.036:return contenders[0][1]
        if len(self.enemies)==1 and (self.turn>self.s['crush_start']+50 or abs(self.enemies[0]['x']-p%self.w)+abs(self.enemies[0]['y']-p//self.w)<=7):
            budget=max(.004,.039-(time.process_time()-self.started))
            tactical=Duel(self,budget).choose(contenders)
            if tactical is not None:return tactical
        if len(self.enemies)>1:
            nearby=min(abs(e['x']-p%self.w)+abs(e['y']-p//self.w) for e in self.enemies)
            if nearby<=7 or slides:
                budget=max(.004,.038-(time.process_time()-self.started))
                if len(self.enemies)<=3 and (self.open.bit_count()<=18 or len(self.bombs)>=2 and sum(abs(e['x']-p%self.w)+abs(e['y']-p//self.w)<=5 for e in self.enemies)>=2):
                    return Council(self,budget).choose(contenders)
                return Multi(self,budget).choose(contenders)
        return contenders[0][1]

class SearchTimeout(Exception):pass

class Duel:
    """Small exact simultaneous-action game tree, with a temporal leaf evaluator."""
    def __init__(self,a,budget):
        self.a=a; self.end=time.process_time()+budget
        self.nodes=0; self.simcache={};self.tt={};self.ecache={};self.graphcache={}
        self.players=[a.me]+a.enemies
        self.ids={p['id']:i for i,p in enumerate(self.players)}
        self.order=sorted(range(len(self.players)),key=lambda i:self.players[i]['id'])
        ps=tuple((p['y']*a.w+p['x'],p['radius'],p['bomb_limit'],int(p['can_kick']),p['kills'],0) for p in self.players)
        steel=sum(1<<p for p,c in enumerate(a.g) if c=='@')
        bricks=sum(1<<p for p,c in enumerate(a.g) if c=='#')
        bs=tuple((p,f,r,d,self.ids.get(o,-1)) for p,f,r,d,o,i in sorted(a.bombs,key=lambda b:b[-1]))
        items=tuple(sorted((p,('fire','bomb','kick').index(k)) for p,k in a.items.items()))
        self.root=(0,steel,bricks,items,ps,bs)
        self.last=max(a.crush.values(),default=a.turn+100)
        self.rays=[]
        for p in range(a.n):
            rr=[]
            for d in a.deltas:
                arr=[];q=p
                for _ in range(a.s['max_radius']):
                    nq=q+d
                    if nq not in a.neigh[q]:break
                    q=nq;arr.append(q)
                rr.append(tuple(arr))
            self.rays.append(rr)
        self.target=sorted(a.crush,key=lambda p:a.crush[p],reverse=True)[:4]

    def moves(self,s,i):
        t,steel,brick,items,ps,bs=s
        p,r,cap,k,kill=ps[i][:5]
        if p<0:return (4,)
        bombpos={b[0] for b in bs}
        moves=[]
        for d,q in enumerate((p-self.a.w,p+self.a.w,p-1,p+1)):
            if q not in self.a.neigh[p]:continue
            if q in bombpos:
                if k:moves.append(d)
            elif not ((steel|brick)>>q&1) and q not in {v[0] for j,v in enumerate(ps) if j!=i}:moves.append(d)
        if p not in bombpos and sum(b[4]==i for b in bs)<cap:moves.append(5)
        moves.append(4)
        # Last safe cells and contact bombs first for alpha-beta ordering.
        enemy=min((v[0] for j,v in enumerate(ps) if j!=i and v[0]>=0),key=lambda q:abs(q%self.a.w-p%self.a.w)+abs(q//self.a.w-p//self.a.w),default=-1)
        def key(m):
            q=p+self.a.deltas[m] if m<4 and p+self.a.deltas[m] not in bombpos else p
            v=self.a.life[q]*.05
            if m==5:v+=2 if enemy>=0 and abs(enemy%self.a.w-p%self.a.w)+abs(enemy//self.a.w-p//self.a.w)<5 else -2
            return v
        moves.sort(key=key,reverse=True)
        return tuple(moves)

    def step(self,s,*moves):
        key=(s,moves)
        got=self.simcache.get(key)
        if got is not None:return got
        offset,steel,brick,items,ps,oldbs=s
        ps=[list(p) for p in ps]
        bs=[list(b) for b in oldbs]
        bm={b[0]:j for j,b in enumerate(bs)}
        want=[p[0] for p in ps];kicks={}
        n=len(ps)
        for i,m in enumerate(moves):
            p=ps[i][0]
            if p<0:continue
            if m<4:
                q=p+self.a.deltas[m]
                if q in bm:
                    if ps[i][3]:kicks.setdefault(bm[q],[]).append(m)
                elif q in self.a.neigh[p] and not ((steel|brick)>>q&1) and q not in {v[0] for j,v in enumerate(ps) if j!=i}:want[i]=q
        for i,q in enumerate(want):
            if q>=0 and want.count(q)==1:ps[i][0]=q
        for j,ds in kicks.items():bs[j][3]=ds[0] if len(ds)==1 else -1
        keepitems=[]
        for p,k in items:
            collector=next((i for i in range(n) if ps[i][0]==p),None)
            if collector is None:keepitems.append((p,k))
            elif k==0:ps[collector][1]=min(self.a.s['max_radius'],ps[collector][1]+1)
            elif k==1:ps[collector][2]=min(self.a.s['max_bombs'],ps[collector][2]+1)
            else:ps[collector][3]=1
        oldcount=len(bs)
        for i in self.order:
            p,r,cap,k,kill=ps[i][:5]
            if moves[i]==5 and p>=0 and p not in bm and sum(b[4]==i for b in bs)<cap:
                bm[p]=len(bs);bs.append([p,self.a.s['bomb_fuse'],r,-1,i])
        blocked=set(bm)|{p[0] for p in ps}|{p for p,k in keepitems}
        targets={};counts={}
        for j,(p,f,r,d,o) in enumerate(bs):
            if d>=0:
                q=p+self.a.deltas[d]
                if q in self.a.neigh[p] and not ((steel|brick)>>q&1) and q not in blocked:
                    targets[j]=q;counts[q]=counts.get(q,0)+1
        for j,b in enumerate(bs):
            if j in targets and counts[targets[j]]==1:b[0]=targets[j]
            else:b[3]=-1
            if j<oldcount:b[1]-=1
        bm={b[0]:j for j,b in enumerate(bs)}
        queue=[j for j,b in enumerate(bs) if b[1]<=0]
        hits={};flame=0
        for j in queue:
            if j in hits:continue
            p,f,r,d,o=bs[j]; hit=1<<p
            for ray in self.rays[p]:
                for q in ray[:r]:
                    bit=1<<q
                    if steel&bit:break
                    hit|=bit
                    if brick&bit:break
                    if q in bm:queue.append(bm[q]);break
            hits[j]=hit;flame|=hit
        brick&=~flame
        keepitems=tuple((p,k) for p,k in keepitems if not (flame>>p&1))
        # Credit is oldest bomb, regardless of chain order.
        for i in range(n):
            p=ps[i][0]
            if p>=0 and flame>>p&1:
                by=next(bs[j][4] for j in sorted(hits) if hits[j]>>p&1)
                if by>=0 and by!=i:ps[by][4]+=1
                ps[i][0]=-1;ps[i][5]=offset+1
        bs=[tuple(b) for j,b in enumerate(bs) if j not in hits]
        cp=self.a.crush_at.get(self.a.turn+offset)
        if cp is not None:
            bit=1<<cp;steel|=bit;brick&=~bit
            bs=[b for b in bs if b[0]!=cp]
            keepitems=tuple((p,k) for p,k in keepitems if p!=cp)
            for i in range(n):
                if ps[i][0]==cp:ps[i][0]=-1;ps[i][5]=offset+1
            flame|=bit
        out=((offset+1,steel,brick,keepitems,tuple(tuple(p) for p in ps),tuple(bs)),flame)
        self.simcache[key]=out
        return out

    def terminal(self,s):
        t,steel,brick,items,ps,bs=s
        p0,p1=ps[0][0],ps[1][0]
        if p0<0 or p1<0 or self.a.turn+t>self.a.s['max_turns']:
            if p0>=0 and p1<0:return 20000-t*10
            if p1>=0 and p0<0:return -20000+t*10
            diff=ps[0][4]-ps[1][4]
            return (19000-t*10 if diff>0 else -19000+t*10 if diff<0 else 0)
        return None

    def evaluate(self,s):
        got=self.ecache.get(s)
        if got is not None:return got
        tv=self.terminal(s)
        if tv is not None:return tv
        off,steel,brick,items,ps,bs=s
        H=min(5,max(1,self.last-self.a.turn-off))
        # Forward propagate all legal escape routes through scheduled detonations.
        R=[1<<p[0] for p in ps];depth=[0,0];counts=[0,0]
        f=s
        earliest=[None,None]
        for t in range(H):
            floor=self.a.full&~(f[1]|f[2]);block=sum(1<<b[0] for b in f[5])
            after,fire=self.step(f,4,4)
            for i in range(2):
                R[i]=(R[i]|(self.a.expand(R[i])&~block))&floor&~fire
                if t==0:R[i]&=~(1<<ps[1-i][0])
                if R[i]:depth[i]+=1;counts[i]=R[i].bit_count()
                elif earliest[i] is None:earliest[i]=t
            f=after
        val=0.
        if depth[0]<H or depth[1]<H:
            val+=(depth[0]-depth[1])*650
            if depth[0]==H:val+=2500
            elif depth[1]==H:val-=2500
        val+=4*(min(counts[0],25)-min(counts[1],25))
        # Accessible late terrain with the opponent holding their present square.
        floor=self.a.full&~(steel|brick)
        vals=[]
        for i in range(2):
            p=ps[i][0];allowed=floor&~(1<<ps[1-i][0])
            rr=1<<p;seen=rr;best=-1000.;targetval=-1000.
            for d in range(15):
                if not rr:break
                bits=rr
                while bits:
                    bit=bits&-bits;q=bit.bit_length()-1;bits-=bit
                    life=self.a.life[q]-off
                    if life>d:
                        v=min(life,45)*.7-d*.65
                        if v>best:best=v
                        if q in self.target:targetval=max(targetval,22-d*1.6+(life)*.12)
                rr=self.a.expand(rr)&allowed&~seen;seen|=rr
            # The final basin is strategic before it becomes compulsory.
            factor=max(0,min(1,(self.a.turn+off-self.a.s['crush_start']-35)/35))
            vals.append(best+factor*max(-10,targetval))
        val+=3*(vals[0]-vals[1])
        val+=.3*(ps[0][4]-ps[1][4])
        self.ecache[s]=val
        return val

    def solve(self,s,depth,alpha,beta):
        self.nodes+=1
        if self.nodes&15==0 and time.process_time()>self.end:raise SearchTimeout
        tv=self.terminal(s)
        if tv is not None:return tv
        if depth==0:return self.evaluate(s)
        key=(s,depth)
        if key in self.tt:return self.tt[key]
        acts=self.moves(s,0);opps=self.moves(s,1)
        best=-1e9;complete=True
        for act in acts:
            worst=1e9
            for opp in opps:
                nxt,_=self.step(s,act,opp)
                val=self.solve(nxt,depth-1,alpha,min(beta,worst))
                if val<worst:worst=val
                if worst<=alpha:
                    complete=False;break
            if worst>best:best=worst
            alpha=max(alpha,best)
            if best>=beta:
                complete=False;break
        if complete:self.tt[key]=best
        return best

    def choose(self,prior):
        names=_NAMES+('bomb',)
        allowed=set(self.moves(self.root,0))
        acts=[names.index(v[1]) for v in prior if names.index(v[1]) in allowed]
        opps=self.moves(self.root,1)
        result=None;lastscores=[]
        for depth in range(1,9):
            scores=[];best=-1e9
            try:
                for act in acts:
                    worst=1e9
                    priorval=next((v[0] for v in prior if v[1]==names[act]),0)
                    bonus=max(-1000,min(30,priorval))*.015
                    cut=False
                    for opp in opps:
                        nxt,_=self.step(self.root,act,opp)
                        val=self.solve(nxt,depth-1,best-bonus,worst)
                        if val<worst:worst=val
                        if worst+bonus<=best:
                            cut=True;break
                    score=worst+bonus
                    # A pruned upper bound is not an exact tie with the incumbent.
                    if cut:score=min(score,best-.00001)
                    scores.append((score,act))
                    best=max(best,score)
                scores.sort(reverse=True)
                result=names[scores[0][1]];lastscores=scores
                acts=[act for v,act in scores]
                if abs(scores[0][0])>15000:break
            except SearchTimeout:break
        _memory['search']=(self.nodes,result,lastscores)
        return result

class Multi(Duel):
    def future(self,s):
        off,steel,brick,items,ps,bs=s
        key=(off,steel,brick,items,bs)
        if key in self.fcache:return self.fcache[key]
        ghost=tuple((-1,v[1],v[2],v[3],v[4],v[5]) for v in ps)
        f=(off,steel,brick,items,ghost,bs)
        layers=[]
        for t in range(self.a.horizon-1):
            floor=self.a.full&~(f[1]|f[2]);block=sum(1<<b[0] for b in f[5])
            after,fire=self.step(f,*([4]*len(ps)))
            layers.append((floor,block,fire))
            f=after
        self.fcache[key]=layers
        return layers

    def safety(self,s):
        off,steel,brick,items,ps,bs=s
        p=ps[0][0]
        if p<0:
            alive=sum(v[0]>=0 for v in ps[1:])
            if alive==0:
                rank=1+sum(v[4]>ps[0][4] for v in ps[1:])
                if rank==1:return 1000.,0
            return -8000.-alive*200,0
        if not any(v[0]>=0 for v in ps[1:]):return 1000.,1
        blocked=sum(1<<v[0] for v in ps[1:] if v[0]>=0)
        R=1<<p
        layers=self.future(s)
        for t,(floor,bombs,fire) in enumerate(layers):
            R=(R|(self.a.expand(R)&~bombs))&floor&~fire
            if t<2:R &= ~blocked
            if not R:return -300.-(len(layers)-t)*40,0
        # Follow possible enemy movement as well as their current body blocks.
        persistent=1<<p
        robust=1<<p
        enemy=[1<<v[0] for v in ps[1:] if v[0]>=0]
        for t,(floor,bombs,fire) in enumerate(layers):
            persistent=(persistent|(self.a.expand(persistent)&~bombs))&floor&~fire&~blocked
            area=0
            for e in enemy:area|=e
            nextenemy=[(e|(self.a.expand(e)&~bombs))&floor&~fire for e in enemy]
            for e in nextenemy:area|=e
            robust=(robust|(self.a.expand(robust)&~bombs&~area))&floor&~fire
            enemy=nextenemy
        penalty=-6. if not persistent else 0.
        ownnew=sum(b[4]==0 for b in bs)>sum(b[4]==0 for b in self.root[5])
        if not persistent and ownnew:penalty-=900
        if not robust and bs:penalty-=45
        return penalty,R.bit_count()

    def choose(self,prior):
        self.fcache={}
        n=len(self.players)
        names=_NAMES+('bomb',)
        legal=set(self.moves(self.root,0))
        candidates=[(names.index(x[1]),x[0]) for x in prior if names.index(x[1]) in legal]
        options=[]
        for i in range(1,n):
            p=self.root[4][i][0];me=self.root[4][0][0]
            distance=abs(p%self.a.w-me%self.a.w)+abs(p//self.a.w-me//self.a.w)
            options.append(self.moves(self.root,i) if distance<=9 or any(b[3]>=0 for b in self.root[5]) else (4,))
        scenarios=[tuple([4]*(n-1))]
        scenarios.append(tuple(5 if 5 in opt else 4 for opt in options))
        for i,opt in enumerate(options):
            for m in opt:
                sc=[4]*(n-1);sc[i]=m;scenarios.append(tuple(sc))
        scenarios.extend(itertools.islice(itertools.product(*options),256))
        scenarios=list(dict.fromkeys(scenarios))
        worst={m:0. for m,v in candidates};total={m:0. for m,v in candidates};cnt=0
        for sc in scenarios:
            if cnt>2 and time.process_time()>self.end:break
            for m,v in candidates:
                s,fire=self.step(self.root,m,*sc)
                penalty,area=self.safety(s)
                worst[m]=min(worst[m],penalty)
                total[m]+=min(area,20)*.01
            cnt+=1
        values=[]
        for m,v in candidates:
            # The policy's existing explosion certificate remains authoritative.
            values.append((v+worst[m]+total[m]/max(1,cnt),m))
        values.sort(reverse=True)
        _memory['multi']=(cnt,values)
        return names[values[0][1]]

class Council(Multi):
    def __init__(self,a,budget):
        super().__init__(a,budget)
        self.fcache={};self.jcache={}

    def terminal(self,s):
        off,steel,brick,items,ps,bs=s
        me=ps[0]
        alive=[v for v in ps if v[0]>=0]
        if me[0]<0:
            key=(me[5],me[4])
            rank=1+sum((10000 if v[0]>=0 else v[5],v[4])>key for v in ps[1:])
            return (20000 if rank==1 else -5000 if rank==2 else -12000 if rank==3 else -19000)+off*3
        if len(alive)==1:return 20000-off*10
        return None

    def joint(self,s):
        if s not in self.jcache:
            self.jcache[s]=tuple(itertools.product(*(self.moves(s,i) for i in range(1,len(self.players)))))
        return self.jcache[s]

    def evaluate(self,s):
        if s in self.ecache:return self.ecache[s]
        tv=self.terminal(s)
        if tv is not None:return tv
        off,steel,brick,items,ps,bs=s
        layers=self.future(s)
        floor=self.a.full&~(steel|brick)
        vals=[]
        for i,v in enumerate(ps):
            p=v[0]
            if p<0:vals.append(-5000.);continue
            block=sum(1<<u[0] for j,u in enumerate(ps) if i!=j and u[0]>=0)
            R=1<<p;depth=0;counts=0
            for t,(fl,bm,fire) in enumerate(layers):
                R=(R|(self.a.expand(R)&~bm))&fl&~fire
                if t<2:R&=~block
                if not R:break
                depth+=1;counts=R.bit_count()
            score=0.
            if depth<len(layers):score-=3000+(len(layers)-depth)*600
            score+=min(counts,20)*2
            rr=1<<p;seen=rr;best=-100.;target=-10.
            for d in range(14):
                if not rr:break
                bits=rr
                while bits:
                    bit=bits&-bits;q=bit.bit_length()-1;bits-=bit
                    life=self.a.life[q]-off
                    if life>d:
                        best=max(best,min(life,40)*1.2-d*.8)
                        if q in self.target[:2]:target=max(target,25-d*2+life*.1)
                rr=self.a.expand(rr)&floor&~block&~seen;seen|=rr
            score+=best*3+target*2+v[4]*.2
            vals.append(score)
        others=[vals[i] for i in range(1,len(ps)) if ps[i][0]>=0]
        result=vals[0]-max(others)+.15*(vals[0]-sum(others)/len(others))
        result+=sum(v[0]<0 for v in ps[1:])*100
        self.ecache[s]=result
        return result

    def solve(self,s,depth,alpha,beta):
        self.nodes+=1
        if self.nodes&7==0 and time.process_time()>self.end:raise SearchTimeout
        tv=self.terminal(s)
        if tv is not None:return tv
        if depth==0:return self.evaluate(s)
        key=(s,depth)
        if key in self.tt:return self.tt[key]
        best=-1e9;complete=True
        for act in self.moves(s,0):
            worst=1e9
            for sc in self.joint(s):
                nxt,_=self.step(s,act,*sc)
                value=self.solve(nxt,depth-1,alpha,min(beta,worst))
                worst=min(worst,value)
                if worst<=alpha:complete=False;break
            best=max(best,worst);alpha=max(alpha,best)
            if best>=beta:complete=False;break
        if complete:self.tt[key]=best
        return best

    def choose(self,prior):
        names=_NAMES+('bomb',)
        legal=set(self.moves(self.root,0))
        acts=[names.index(v[1]) for v in prior if names.index(v[1]) in legal]
        result=prior[0][1];lastscores=[]
        for depth in range(1,7):
            scores=[];best=-1e9
            try:
                for act in acts:
                    worst=1e9;cut=False
                    priorval=next((v[0] for v in prior if v[1]==names[act]),0)
                    bonus=max(-1000,min(30,priorval))*.015
                    for sc in self.joint(self.root):
                        nxt,_=self.step(self.root,act,*sc)
                        val=self.solve(nxt,depth-1,best-bonus,worst)
                        worst=min(worst,val)
                        if worst+bonus<=best:cut=True;break
                    score=worst+bonus
                    if cut:score=min(score,best-.00001)
                    scores.append((score,act));best=max(best,score)
                scores.sort(reverse=True);lastscores=scores
                acts=[act for v,act in scores];result=names[acts[0]]
                if best>15000:break
            except SearchTimeout:break
        _memory['council']=(self.nodes,result,lastscores)
        return result

def decide(state):
    return Arena(state).decide()

"""Refine the existing hood silhouette, preserving the rig and facial features.

Usage: python tools/refine_head.py INPUT_FOLDER OUTPUT_FOLDER
Input is a V4.4 author/model folder with layout.json and editable models.
"""
from pathlib import Path
import copy, json, math, shutil, sys, uuid


def uv_for(cube, template):
    dims = [b-a for a,b in zip(cube['lo'],cube['hi'])]
    spans = {'north':(dims[0],dims[1]),'south':(dims[0],dims[1]),
             'east':(dims[2],dims[1]),'west':(dims[2],dims[1]),
             'up':(dims[0],dims[2]),'down':(dims[0],dims[2])}
    # Sample the same hood material island at 16 pixels per model unit.
    for face,(w,h) in spans.items():
        x,y,_,_=template['uv'][face]
        cube['uv'][face]=[x,y,x+w*16,y+h*16]


def refine(data):
    d=copy.deepcopy(data)
    byname={c['name']:c for c in d['cubes']}
    template=byname['Hood back shell']
    removed={'Hood back shell'}
    d['cubes']=[c for c in d['cubes'] if c['name'] not in removed]
    for c in d['cubes']:
        if c['name']=='Head core':c['hi'][2]=2.20
        if c['name']=='Hair volume':c['hi'][2]=2.45
        if c['name']=='Hood crown':
            old=copy.deepcopy(c);c['hi'][1]=32.20;c['hi'][2]=1.25;uv_for(c,old)
        if c['name']=='Rear hood lower lining':
            c['lo']=[-2.6,25.15,1.12];c['hi']=[2.6,26.8,2.12]
            uv_for(c,template)
        if 'Hood lower shell' in c['name']:
            old=copy.deepcopy(c);c['hi'][2]=2.3;uv_for(c,old)
        if 'Hood jaw return' in c['name']:
            old=copy.deepcopy(c);c['hi'][2]=2.18;uv_for(c,old)
        if 'Hood rear corner lining' in c['name']:
            old=copy.deepcopy(c);c['hi'][2]=2.45;uv_for(c,old)
        if 'Hood upper bevel' in c['name']:
            old=copy.deepcopy(c);c['hi'][2]=2.18;uv_for(c,old)

    # Concealed lining joins curved panels to the existing side shell.
    liner=copy.deepcopy(template)
    liner.update(name='Hood continuous rear lining',lo=[-2.68,27.15,1.12],
                 hi=[2.68,30.70,3.40],pivot=[0,28.3,1.6],rot=[0,0,0])
    uv_for(liner,template);d['cubes'].append(liner)
    # (height, rear surface centre): shoulder to occiput to crown.
    profile=[(25.20,2.12),(26.50,2.95),(28.0,3.80),
             (29.50,4.05),(31.0,3.55),(31.95,2.45),(32.20,1.05)]
    widths=[2.55,2.68,2.68,2.68,2.35,1.92]
    for i,((y0,z0),(y1,z1)) in enumerate(zip(profile,profile[1:])):
        cy,cz=(y0+y1)/2,(z0+z1)/2
        length=math.hypot(y1-y0,z1-z0)+.035
        tilt=math.degrees(math.atan2(z1-z0,y1-y0))
        # Profile describes the OUTER surface. Place the thickness inwards;
        # neighbouring outward faces then meet without protruding end caps.
        cy+=math.sin(math.radians(tilt))*.08
        cz-=math.cos(math.radians(tilt))*.08
        w=widths[i]
        c=copy.deepcopy(template)
        c.update(name=f'Hood occipital curve {i}',lo=[-w,cy-length/2,cz-.08],
                 hi=[w,cy+length/2,cz+.08],pivot=[0,cy,cz],rot=[tilt,0,0])
        uv_for(c,template)
        for face in ('north','south'):
            u=c['uv'][face]
            start=template['uv'][face][1]+(31.8-y1)*14
            c['uv'][face]=[u[0],start,u[2],start+length*14]
        d['cubes'].append(c)
    # Interior fill follows the same rounded contour; shallow exterior facets
    # provide the surface, without the protruding end faces of deep panels.
    for i,((y0,z0),(y1,z1)) in enumerate(zip(profile,profile[1:])):
        steps=math.ceil((y1-y0)/.18)
        for j in range(steps):
            low=y0+(y1-y0)*j/steps
            high=y0+(y1-y0)*(j+1)/steps
            depth=min(z0+(z1-z0)*j/steps,z0+(z1-z0)*(j+1)/steps)-.10
            if depth<=1.15:continue
            c=copy.deepcopy(template)
            w=widths[i]-.025
            c.update(name=f'Hood concealed fill {i} {j}',lo=[-w,low,1.10],
                     hi=[w,high+.002,depth],pivot=[0,low,1.10],rot=[0,0,0])
            uv_for(c,template);d['cubes'].append(c)
    return d


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def apply(src,dest):
    if src.resolve()==dest.resolve():raise ValueError('Use a preserved input folder')
    dest.mkdir(parents=True,exist_ok=True)
    for path in src.iterdir():
        if path.is_file():shutil.copy2(path,dest/path.name)
    before=json.loads((src/'layout.json').read_text(encoding='utf-8'))
    data=refine(before);write(dest/'layout.json',data)
    changed={c['name']:c for c in data['cubes'] if c['bone']=='Head'}
    for path in src.glob('*.bbmodel'):
        bb=json.loads(path.read_text(encoding='utf-8'))
        groups={}
        def visit(children):
            for child in children:
                if isinstance(child,dict):groups[child['name']]=child;visit(child['children'])
        visit(bb['outliner'])
        old_head_names={c['name'] for c in before['cubes'] if c['bone']=='Head'}
        old_ids={e['uuid'] for e in bb['elements'] if e['name'] in old_head_names}
        old_byname={e['name']:e for e in bb['elements']}
        replacements={}
        for name,c in changed.items():
            e=copy.deepcopy(old_byname.get(name,{}))
            uid=e.get('uuid',str(uuid.uuid5(uuid.NAMESPACE_URL,'mercer-v45/'+name)))
            e.update(name=name,type='cube',uuid=uid,origin=c['pivot'],rotation=c['rot'],box_uv=False,
                **{'from':c['lo'],'to':c['hi']},faces={f:{'uv':u,'texture':0} for f,u in c['uv'].items()})
            replacements[name]=e
        old_names=set(old_byname)
        bb['elements']=[replacements.get(e['name'],e) for e in bb['elements']
                        if e['name'] not in old_head_names or e['name'] in replacements]
        bb['elements'].extend(e for name,e in replacements.items() if name not in old_names)
        kept={e['uuid'] for e in replacements.values()}
        groups['Head']['children']=[x for x in groups['Head']['children']
                                   if not isinstance(x,str) or x not in old_ids or x in kept]
        groups['Head']['children'].extend(e['uuid'] for name,e in replacements.items() if name not in old_names)
        bb['name']='Alex Mercer V4.5 / rounded hood and natural occiput'
        write(dest/path.name,bb)
    geo=json.loads((src/'main.json').read_text(encoding='utf-8'))
    head=next(b for b in geo['minecraft:geometry'][0]['bones'] if b['name']=='Head')
    head['cubes']=[]
    for c in changed.values():
        a,h,p,r=c['lo'],c['hi'],c['pivot'],c['rot'];uv={}
        for f,(x,y,x1,y1) in c['uv'].items():
            key={'east':'west','west':'east'}.get(f,f)
            uv[key]={'uv':[x,y],'uv_size':[x1-x,y1-y]}
            if f in ('up','down'):uv[key]={'uv':[x1,y1],'uv_size':[x-x1,y-y1]}
        q={'origin':[-h[0],a[1],a[2]],'size':[v-u for u,v in zip(a,h)],'uv':uv}
        if any(r):q.update(pivot=[-p[0],p[1],p[2]],rotation=[-r[0],-r[1],r[2]])
        head['cubes'].append(q)
    write(dest/'main.json',geo)
    config=json.loads((src/'ysm.json').read_text(encoding='utf-8'))
    config['metadata']['name']=config['metadata']['name'].replace('V4.4','V4.5')
    write(dest/'ysm.json',config)
    assert data['pivots']==before['pivots'] and data['parents']==before['parents']
    assert [c for c in data['cubes'] if c['bone']!='Head']==[c for c in before['cubes'] if c['bone']!='Head']
    print(f'{dest}: {len(before["cubes"])} -> {len(data["cubes"])} cubes; rig/body unchanged')


if __name__=='__main__':apply(Path(sys.argv[1]),Path(sys.argv[2]))

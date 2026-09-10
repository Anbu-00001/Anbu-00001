#!/usr/bin/env python3
"""Composite the six frames exactly as the SVG stacks them, readout and all."""
import base64, io, json, os, re
import numpy as np
from PIL import Image
ROOT='../..'
js=open(f'{ROOT}/lib/plague-frames.js').read()
W=int(re.search(r'ART_W = (\d+)',js).group(1)); H=int(re.search(r'ART_H = (\d+)',js).group(1))
L=json.loads(re.search(r'LAYERS = (\[.*\]);',js,re.S).group(1))
f=open(f'{ROOT}/lib/pixelfont7.js').read()
tbl=f[f.index('const G = {'):f.index('};',f.index('const G = {'))]
G={}
for m in re.finditer(r"(?:'(.)'|\b([A-Z])):\s*\[([^\]]*)\]",tbl):
    G[m.group(1) or m.group(2)]=[r.strip().strip("'") for r in m.group(3).split(',')]
def cells(t):
    gs=[G[c] for c in t.upper() if c in G]
    return sum(len(g[0]) for g in gs)+max(0,len(gs)-1)
def stamp(img,t,cx,y,cell,fill):
    gs=[G[c] for c in t.upper() if c in G]; x=int(round(cx-(cells(t)*cell)/2)); px=img.load()
    for g in gs:
        for ry,row in enumerate(g):
            for rx,ch in enumerate(row):
                if ch=='1':
                    for dy in range(cell):
                        for dx in range(cell):
                            X,Y=x+rx*cell+dx,y+ry*cell+dy
                            if 0<=X<img.width and 0<=Y<img.height: px[X,Y]=fill
        x+=(len(g[0])+1)*cell
def compose(n):
    c=Image.new('RGB',(W,H))
    for i in range(n+1):
        if L[i]: c.paste(Image.open(io.BytesIO(base64.b64decode(L[i]['data']))).convert('RGB'),(L[i]['x'],L[i]['y']))
    return c
SC=W/512.0
Z={'x':278,'y':31,'w':101,'h':72}; CX=int(round((Z['x']+Z['w']/2)*SC))
lab,num=int(round(1*SC)),int(round(3*SC))
labH,numH=7*lab,7*num
inner,lead,between=int(round(2*SC)),max(1,int(round(1*SC))),int(round(4*SC))
bA=labH+inner+numH; bB=labH+lead+labH+inner+numH
top=int(round(Z['y']*SC)); bT=top+bA+between
INK,INK_LABEL=(12,5,16),(30,16,42)
frames=[]
for n in range(6):
    im=compose(n)
    stamp(im,'DAYS UNBROKEN',CX,top,lab,INK_LABEL)
    stamp(im,'195',CX,top+labH+inner,num,INK)
    stamp(im,'GIT DEEDS',CX,bT,lab,INK_LABEL)
    stamp(im,'COMMITTED',CX,bT+labH+lead,lab,INK_LABEL)
    stamp(im,'1,158',CX,bT+labH+lead+labH+inner,num,INK)
    frames.append(im)
import imagequant
pal=imagequant.quantize_pil_image(frames[2],dithering_level=0.0,max_colors=256,min_quality=0,max_quality=100)
q=[x.quantize(palette=pal,dither=Image.NONE) for x in frames]
q[0].save('dist/animation.gif',save_all=True,append_images=q[1:],duration=500,loop=0,disposal=1,optimize=True)
print('dist/animation.gif  %.0f KB  6 frames, 3.0s'%(os.path.getsize('dist/animation.gif')/1024))
frames[2].resize((W*2,H*2),Image.NEAREST).save('dist/still@2x.png')
frames[2].crop((266,18,392,108)).resize((504,360),Image.NEAREST).save('dist/readout@2x.png')

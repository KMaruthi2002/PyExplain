/* =======================================================================
   engine.js — PyExplain motion-graphics engine.

   * Regions (code / visual / headline) MORPH between per-scene layouts so the
     composition changes with the explanation (full-screen code, full-screen
     metaphor, big kinetic statement, terminal …).
   * A library of animated metaphor COMPONENTS (variable box, if/else road,
     concat puzzle, loop cycle, compare stamp, function machine, terminal).
   * Everything is a pure function of the global clock `t` → the exported MP4
     is identical to the live preview.
   ======================================================================= */

/* ----------------------------- easing ------------------------------- */
const E = {
  clamp:(x,a=0,b=1)=>Math.max(a,Math.min(b,x)),
  out:x=>1-Math.pow(1-E.clamp(x),3),
  inOut:x=>{x=E.clamp(x);return x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2;},
  back:x=>{x=E.clamp(x);const c=1.70158*1.4;return 1+(c+1)*Math.pow(x-1,3)+c*Math.pow(x-1,2);},
  pop:x=>{x=E.clamp(x);if(x>=1)return 1;const c=2.2;return 1+(c+1)*Math.pow(x-1,3)+c*Math.pow(x-1,2);},
  lerp:(a,b,t)=>a+(b-a)*t,
};

/* --------------------------- refined themes ------------------------- */
const THEMES = {
  cartoon: { label:'Vivid', av:'🤖', orbs:['#ff7eb6','#7c5cff','#39d0d8'],
    vars:{ '--bg':'#0f1220','--ink':'#f3f5ff','--muted':'#9aa3c4','--accent':'#7c5cff',
      '--accent-strong':'#a899ff','--accent-soft':'rgba(124,92,255,.18)','--accent-ink':'#fff','--track':'rgba(255,255,255,.10)',
      '--card-border':'1px solid rgba(255,255,255,.08)','--shadow':'0 30px 70px rgba(0,0,0,.45)','--hair':'rgba(255,255,255,.07)',
      '--code-bg':'#151933','--panel':'#141731','--lineno':'#5a628c',
      '--spot':'rgba(124,92,255,.16)','--spot-shadow':'inset 0 0 0 2px #7c5cff, 0 0 30px rgba(124,92,255,.45)',
      '--cap-bg':'rgba(20,23,49,.78)','--cap-border':'1px solid rgba(255,255,255,.08)',
      '--t-kw':'#ff7eb6','--t-str':'#9be59b','--t-num':'#ffcf6b','--t-com':'#6b7196',
      '--t-fn':'#a899ff','--t-bi':'#39d0d8','--t-op':'#aab0d4','--t-def':'#a899ff','--orb-op':'.5' } },
  classroom: { label:'Studio Light', av:'👩‍🏫', orbs:['#9fd6b4','#bcd0ff','#ffe2a8'],
    vars:{ '--bg':'#f4f6fb','--ink':'#1d2433','--muted':'#7c879c','--accent':'#3b6cf6',
      '--accent-strong':'#2a55d6','--accent-soft':'rgba(59,108,246,.12)','--accent-ink':'#fff','--track':'rgba(0,0,0,.08)',
      '--card-border':'1px solid #e3e8f1','--shadow':'0 24px 60px rgba(20,30,60,.10)','--hair':'#eef1f7',
      '--code-bg':'#0f1426','--panel':'#ffffff','--lineno':'#5b6party'.replace('party','a8'),
      '--spot':'rgba(110,150,255,.16)','--spot-shadow':'inset 0 0 0 2px #6e96ff, 0 0 26px rgba(110,150,255,.4)',
      '--cap-bg':'rgba(255,255,255,.92)','--cap-border':'1px solid #e3e8f1',
      '--t-kw':'#c25ea8','--t-str':'#86d39a','--t-num':'#e6b15a','--t-com':'#6b7290',
      '--t-fn':'#8aa6ff','--t-bi':'#4cc6d6','--t-op':'#9aa3c4','--t-def':'#8aa6ff','--orb-op':'.5' } },
  neon: { label:'Neon', av:'👾', orbs:['#22e3c3','#ff6ad5','#5b8cff'],
    vars:{ '--bg':'#080612','--ink':'#eaf6ff','--muted':'#8aa0c8','--accent':'#22e3c3',
      '--accent-strong':'#5cf0ff','--accent-soft':'rgba(34,227,195,.16)','--accent-ink':'#04121a','--track':'rgba(255,255,255,.08)',
      '--card-border':'1px solid rgba(120,140,200,.22)','--shadow':'0 0 60px rgba(34,227,195,.12)','--hair':'rgba(255,255,255,.06)',
      '--code-bg':'#0b0d1d','--panel':'#0c0e20','--lineno':'#465178',
      '--spot':'rgba(92,240,255,.12)','--spot-shadow':'inset 0 0 0 2px #22e3c3, 0 0 30px rgba(34,227,195,.5)',
      '--cap-bg':'rgba(11,13,29,.8)','--cap-border':'1px solid rgba(92,240,255,.25)',
      '--t-kw':'#ff6ad5','--t-str':'#7dffb0','--t-num':'#ffd166','--t-com':'#5e6a92',
      '--t-fn':'#5cf0ff','--t-bi':'#22e3c3','--t-op':'#aab6d8','--t-def':'#5cf0ff','--orb-op':'.45' } },
  minimal: { label:'Mono', av:'•', orbs:['#dddddd','#cccccc','#eeeeee'],
    vars:{ '--bg':'#0d0d0f','--ink':'#f2f2f2','--muted':'#8a8a8a','--accent':'#ffffff',
      '--accent-strong':'#ffffff','--accent-soft':'rgba(255,255,255,.12)','--accent-ink':'#000','--track':'rgba(255,255,255,.1)',
      '--card-border':'1px solid rgba(255,255,255,.12)','--shadow':'0 24px 60px rgba(0,0,0,.5)','--hair':'rgba(255,255,255,.08)',
      '--code-bg':'#151517','--panel':'#141416','--lineno':'#5a5a5a',
      '--spot':'rgba(255,255,255,.08)','--spot-shadow':'inset 0 0 0 2px #fff',
      '--cap-bg':'rgba(20,20,22,.82)','--cap-border':'1px solid rgba(255,255,255,.12)',
      '--t-kw':'#ffffff','--t-str':'#bdbdbd','--t-num':'#e6e6e6','--t-com':'#6a6a6a',
      '--t-fn':'#dcdcdc','--t-bi':'#cfcfcf','--t-op':'#9a9a9a','--t-def':'#ffffff','--orb-op':'.18' } },
};
// fix accidental token in classroom lineno
THEMES.classroom.vars['--lineno']='#5b6aa8';

/* ------------------- python syntax highlighter ---------------------- */
const PY_KW=new Set(('False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case').split(' '));
const PY_BI=new Set(('print len range int str float list dict set tuple bool input sum min max abs sorted enumerate zip map filter type isinstance open round any all').split(' '));
function esc(s){return (s==null?'':String(s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
// normalize fancy operator glyphs / dashes that the AI sometimes emits
function nop(s){return String(s==null?'':s).replace(/≥/g,'>=').replace(/≤/g,'<=').replace(/≠/g,'!=').replace(/[—–]/g,'-');}
function trunc(s,m){s=String(s==null?'':s);return s.length>m?s.slice(0,m-1)+'…':s;}
function normVisual(v){ if(!v||typeof v!=='object')return v; const out=Array.isArray(v)?[]:{};
  for(const k in v){ const val=v[k];
    out[k]= typeof val==='string'?nop(val): Array.isArray(val)?val.map(x=>typeof x==='string'?nop(x):x): val; }
  return out; }
function highlightPython(line){
  let out='',i=0;const n=line.length;
  while(i<n){const c=line[i];
    if(c==='#'){out+='<span class="tk-com">'+esc(line.slice(i))+'</span>';break;}
    if(c==='"'||c==="'"){let j=i+1;while(j<n&&line[j]!==c){if(line[j]==='\\')j++;j++;}
      out+='<span class="tk-str">'+esc(line.slice(i,Math.min(j+1,n)))+'</span>';i=j+1;continue;}
    if(/[0-9]/.test(c)&&(i===0||/[^A-Za-z0-9_]/.test(line[i-1]))){let j=i;while(j<n&&/[0-9_.]/.test(line[j]))j++;
      out+='<span class="tk-num">'+esc(line.slice(i,j))+'</span>';i=j;continue;}
    if(/[A-Za-z_]/.test(c)){let j=i;while(j<n&&/[A-Za-z0-9_]/.test(line[j]))j++;const w=line.slice(i,j);
      const prev=line.slice(0,i).trimEnd();let cls='';
      if(PY_KW.has(w))cls='tk-kw';else if(prev.endsWith('def')||prev.endsWith('class'))cls='tk-def';
      else if(line[j]==='('&&PY_BI.has(w))cls='tk-bi';else if(line[j]==='(')cls='tk-fn';else if(PY_BI.has(w))cls='tk-bi';
      out+=cls?'<span class="'+cls+'">'+esc(w)+'</span>':esc(w);i=j;continue;}
    if('+-*/%=<>!&|^~:,.'.includes(c)){out+='<span class="tk-op">'+esc(c)+'</span>';i++;continue;}
    out+=esc(c);i++;}
  return out||'&nbsp;';
}

/* ----------------------------- SVG helpers -------------------------- */
const SVGNS='http://www.w3.org/2000/svg';
function S(tag,attrs,txt){const e=document.createElementNS(SVGNS,tag);
  if(attrs)for(const k in attrs)e.setAttribute(k,attrs[k]);
  if(txt!=null)e.textContent=txt;return e;}
function setA(e,attrs){for(const k in attrs)e.setAttribute(k,attrs[k]);}

/* ----------------------- layout presets (rects) --------------------- */
// content band keeps clear of the top bar (96) and the caption (~y 900+)
const R={
  codeBig:{x:300,y:128,w:1320,h:716},
  codeLeft:{x:60,y:128,w:884,h:716},
  visRight:{x:984,y:128,w:876,h:716},
  visBig:{x:300,y:120,w:1320,h:744},
  headFull:{x:140,y:120,w:1640,h:760},
};
const LAYOUTS={
  title:    {code:null, vis:null, head:R.headFull, cap:false},
  statement:{code:null, vis:null, head:R.headFull, cap:true},
  code:     {code:R.codeBig, vis:null, head:null, cap:true},
  split:    {code:R.codeLeft, vis:R.visRight, head:null, cap:true},
  metaphor: {code:null, vis:R.visBig, head:null, cap:true},
  terminal: {code:null, vis:R.visBig, head:null, cap:true},
};

/* =======================================================================
   COMPONENTS — each: build(svg, v, T) -> draw(lt,dur,p)
   Drawn in a 900x640 viewBox; text is SVG so it scales with the region.
   ======================================================================= */
function txt(x,y,s,fill,opts){return S('text',Object.assign({x,y,'font-size':s,fill,
  'font-family':"'Inter',sans-serif",'font-weight':'700','text-anchor':'middle','dominant-baseline':'middle'},opts||{}));}
function mono(x,y,s,fill,opts){return txt(x,y,s,fill,Object.assign({'font-family':"'JetBrains Mono',monospace"},opts||{}));}

const COMPONENTS={
  /* a value drops into a labeled box */
  variable_box(svg,v,T){
    const name=v.name||'x', val=String(v.value==null?'':v.value);
    const box=S('rect',{x:300,y:300,width:300,height:150,rx:22,fill:'none',stroke:T.accent,'stroke-width':4});
    const nameTag=S('rect',{x:300,y:255,width:Math.max(120,name.length*20+40),height:54,rx:14,fill:T.accent});
    const nameT=mono(0,282,30,T.accentInk,{'text-anchor':'start'}); nameT.setAttribute('x',320); nameT.textContent=name;
    const valT=mono(450,375,Math.min(46, 520/Math.max(4,val.length)),T.ink); valT.textContent=val;
    const drop=S('g',{}); drop.appendChild(valT);
    svg.appendChild(nameTag);svg.appendChild(box);svg.appendChild(nameT);svg.appendChild(drop);
    return (lt,dur,p)=>{
      const a=E.pop(E.clamp(lt/420));
      setA(box,{transform:`translate(450 375) scale(${a}) translate(-450 -375)`});
      nameTag.setAttribute('opacity',E.clamp(lt/300)); nameT.setAttribute('opacity',E.clamp(lt/300));
      const d=E.out(E.clamp((lt-350)/550)); const y=E.lerp(-140,0,d);
      drop.setAttribute('transform',`translate(0 ${y})`); drop.setAttribute('opacity',E.clamp((lt-350)/250));
      const fl=Math.sin(E.clamp((lt-850)/350)*Math.PI);
      box.setAttribute('stroke-width',4+fl*4);
    };
  },
  /* left  op  right  ->  TRUE / FALSE stamp */
  compare(svg,v,T){
    const expr=`${v.left} ${v.op||'≥'} ${v.right}`;
    const e=mono(450,250,52,T.ink); e.textContent=expr;
    const res=(v.result===true||v.result==='true'||v.result==='True');
    const col=res?'#27c46b':'#ff5d6c';
    const stamp=txt(450,440,96,col,{'font-weight':'900','stroke':col,'stroke-width':2});
    stamp.textContent=res?'TRUE':'FALSE';
    svg.appendChild(e);svg.appendChild(stamp);
    return (lt,dur,p)=>{
      e.setAttribute('opacity',E.clamp(lt/300));
      const s=E.clamp((lt-450)/300); const sc=E.lerp(2.4,1,E.back(s)); const rot=E.lerp(-12,0,E.out(s));
      stamp.setAttribute('opacity',E.clamp((lt-450)/180));
      stamp.setAttribute('transform',`translate(450 440) rotate(${rot}) scale(${sc}) translate(-450 -440)`);
    };
  },
  /* a path splits; the taken branch lights up */
  if_else(svg,v,T){
    const taken=(v.taken==='yes'||v.taken==='if'||v.taken===true);
    const cond=v.condition||'condition'; const yes=v.yes_label||'do this'; const no=v.no_label||'do that';
    const stem=S('path',{d:'M450 130 L450 300',stroke:T.muted,'stroke-width':8,fill:'none','stroke-linecap':'round'});
    const left=S('path',{d:'M450 300 C 350 380, 250 400, 200 470',stroke:taken?'#27c46b':T.muted,'stroke-width':8,fill:'none','stroke-linecap':'round',opacity:taken?1:.35});
    const right=S('path',{d:'M450 300 C 550 380, 650 400, 700 470',stroke:!taken?'#27c46b':T.muted,'stroke-width':8,fill:'none','stroke-linecap':'round',opacity:!taken?1:.35});
    const q=mono(450,100,30,T.ink); q.textContent=cond+' ?';
    const yA=txt(45,545,22,taken?'#27c46b':T.muted,{'text-anchor':'start'}); yA.textContent='✔ '+trunc(yes,30);
    const nA=txt(855,545,22,!taken?'#27c46b':T.muted,{'text-anchor':'end'}); nA.textContent=trunc(no,30)+' ✘';
    const tok=S('circle',{r:16,fill:T.accent,cx:450,cy:130});
    [stem,left,right,q,yA,nA,tok].forEach(x=>svg.appendChild(x));
    return (lt,dur,p)=>{
      q.setAttribute('opacity',E.clamp(lt/250));
      const d=E.inOut(E.clamp((lt-300)/900));
      // token travels down the taken branch
      const path=taken?left:right; let pt={x:450,y:130};
      try{const L=path.getTotalLength(); const seg= d<0.45? null: path.getPointAtLength(L*E.clamp((d-0.45)/0.55));
        const stemY=E.lerp(130,300,E.clamp(d/0.45)); pt = seg?seg:{x:450,y:stemY};}catch(e){}
      tok.setAttribute('cx',pt.x); tok.setAttribute('cy',pt.y);
      const glow=E.clamp((d-0.45)/0.3);
      (taken?left:right).setAttribute('stroke-width',8+glow*4);
      [yA,nA].forEach(a=>a.setAttribute('opacity',E.clamp((lt-500)/400)));
    };
  },
  /* text chips pop into a row joined by +, then the joined result reveals below */
  concat(svg,v,T){
    const parts=(v.parts&&v.parts.length?v.parts:['"Hi "','name','"!"']).slice(0,4).map(String);
    const result=v.result!=null?String(v.result):parts.join('');
    const cw=parts.map(s=>Math.max(70,Math.min(220,s.length*14+34)));
    const plusW=46; const total=cw.reduce((a,b)=>a+b,0)+(parts.length-1)*plusW;
    let x=450-total/2; const chips=[]; const pluses=[];
    parts.forEach((pp,i)=>{ const w=cw[i]; const bx=x+w/2;
      const g=S('g',{transform:`translate(${bx} 250)`});
      const r=S('rect',{x:-w/2,y:-34,width:w,height:68,rx:14,fill:T.accentSoft,stroke:T.accent,'stroke-width':2});
      const tx=mono(0,4,Math.min(26,(w-20)/Math.max(2,pp.length)*1.75),T.ink); tx.textContent=pp;
      g.appendChild(r); g.appendChild(tx); svg.appendChild(g); chips.push({g,bx});
      x+=w; if(i<parts.length-1){ const ps=txt(x+plusW/2,250,40,T.accentStrong,{'font-weight':'900'}); ps.textContent='+';
        ps.setAttribute('opacity',0); svg.appendChild(ps); pluses.push(ps); x+=plusW; } });
    const rw=Math.min(700,result.length*13+70);
    const obox=S('rect',{x:450-rw/2,y:418,width:rw,height:84,rx:16,fill:'none',stroke:'#27c46b','stroke-width':3,opacity:0});
    const out=mono(450,463,Math.min(34,(rw-40)/Math.max(6,result.length)*1.7),'#27c46b'); out.textContent=result; out.setAttribute('opacity',0);
    svg.appendChild(obox); svg.appendChild(out);
    return (lt,dur,p)=>{
      chips.forEach((c,i)=>{ const a=E.pop(E.clamp((lt-150-i*200)/430));
        c.g.setAttribute('transform',`translate(${c.bx} 250) scale(${a.toFixed(3)})`);
        c.g.setAttribute('opacity',E.clamp((lt-150-i*200)/250).toFixed(3)); });
      pluses.forEach((ps,i)=>ps.setAttribute('opacity',E.clamp((lt-300-i*200)/250).toFixed(3)));
      const revAt=150+parts.length*200+200; const r=E.out(E.clamp((lt-revAt)/500));
      obox.setAttribute('opacity',(r*0.9).toFixed(3)); out.setAttribute('opacity',r.toFixed(3));
    };
  },
  /* a row of items; a ring cycles across them */
  loop(svg,v,T){
    const items=(v.items&&v.items.length?v.items:['10','20','5']).slice(0,8).map(String);
    const n=items.length; const gap=820/n; const y=320; const boxes=[];
    items.forEach((it,i)=>{ const cx=60+gap*i+gap/2;
      const r=S('rect',{x:cx-gap*0.38,y:y-40,width:gap*0.76,height:80,rx:14,fill:T.panelSoft,stroke:T.muted,'stroke-width':2});
      const tx=mono(cx,y+4,Math.min(30,gap*0.5),T.ink); tx.textContent=it; svg.appendChild(r); svg.appendChild(tx); boxes.push({r,cx}); });
    const ring=S('rect',{x:0,y:y-50,width:gap*0.9,height:100,rx:18,fill:'none',stroke:T.accent,'stroke-width':5});
    svg.appendChild(ring);
    const lbl=txt(450,150,30,T.muted); lbl.textContent=v.label||'for each item …'; svg.appendChild(lbl);
    return (lt,dur,p)=>{
      lbl.setAttribute('opacity',E.clamp(lt/300));
      const prog=E.clamp((lt-300)/(dur-500))*n; const idx=Math.min(n-1,Math.floor(prog));
      const f=prog-idx; const cx=boxes[idx]?boxes[idx].cx:boxes[0].cx;
      ring.setAttribute('x',cx-ring.getAttribute('width')/2);
      ring.setAttribute('opacity',E.clamp(lt/300));
      boxes.forEach((b,i)=>b.r.setAttribute('stroke',i<=idx?T.accent:T.muted));
      ring.setAttribute('transform',`translate(0 ${Math.sin(f*Math.PI)*-6})`);
    };
  },
  /* a machine: input -> [func] -> output */
  function_machine(svg,v,T){
    const name=v.name||'f', inp=trunc(String(v.input==null?'':v.input),10), outp=trunc(String(v.output==null?'':v.output),10);
    const defs=S('defs',{}); const mk=S('marker',{id:'ar',markerWidth:9,markerHeight:9,refX:5,refY:3,orient:'auto'});
    mk.appendChild(S('path',{d:'M0 0 L6 3 L0 6 Z',fill:T.muted}));
    const mk2=S('marker',{id:'ar2',markerWidth:9,markerHeight:9,refX:5,refY:3,orient:'auto'});
    mk2.appendChild(S('path',{d:'M0 0 L6 3 L0 6 Z',fill:'#27c46b'})); defs.appendChild(mk); defs.appendChild(mk2);
    const m=S('rect',{x:365,y:255,width:170,height:150,rx:20,fill:T.accentSoft,stroke:T.accent,'stroke-width':4});
    const mt=mono(450,335,32,T.ink); mt.textContent=name+'()';
    const ina=S('path',{d:'M170 330 L358 330',stroke:T.muted,'stroke-width':6,'marker-end':'url(#ar)',fill:'none'});
    const outa=S('path',{d:'M542 330 L700 330',stroke:'#27c46b','stroke-width':6,'marker-end':'url(#ar2)',fill:'none'});
    const inChip=mono(170,292,28,T.ink); inChip.textContent=inp;
    const outChip=mono(735,292,30,'#27c46b'); outChip.textContent=outp;
    [defs,ina,outa,m,mt,inChip,outChip].forEach(x=>svg.appendChild(x));
    return (lt,dur,p)=>{
      m.setAttribute('opacity',E.clamp(lt/300)); mt.setAttribute('opacity',E.clamp(lt/300));
      ina.setAttribute('opacity',E.clamp((lt-150)/300));
      const d=E.out(E.clamp((lt-350)/520)); inChip.setAttribute('transform',`translate(${E.lerp(0,185,d).toFixed(1)} 0)`);
      inChip.setAttribute('opacity',(1-E.clamp((d-0.65)/0.35)).toFixed(3));
      outa.setAttribute('opacity',E.clamp((lt-800)/300));
      const o=E.out(E.clamp((lt-950)/520)); outChip.setAttribute('transform',`translate(${E.lerp(-185,0,o).toFixed(1)} 0)`);
      outChip.setAttribute('opacity',E.clamp((lt-950)/250).toFixed(3));
    };
  },
  /* items pop into a list */
  list(svg,v,T){
    const items=(v.items&&v.items.length?v.items:['a','b','c']).slice(0,8).map(String);
    const name=v.name||'list'; const lbl=mono(450,140,30,T.accentStrong); lbl.textContent=name+' = [ … ]'; svg.appendChild(lbl);
    const n=items.length; const cols=Math.min(n,4); const cw=760/cols; const chips=[];
    items.forEach((it,i)=>{ const col=i%cols, row=Math.floor(i/cols);
      const cx=70+cw*col+cw/2, cy=260+row*110;
      const g=S('g',{}); const r=S('rect',{x:cx-cw*0.4,y:cy-38,width:cw*0.8,height:76,rx:14,fill:T.accentSoft,stroke:T.accent,'stroke-width':2});
      const tx=mono(cx,cy+4,Math.min(30,cw*0.4),T.ink); tx.textContent=it; g.appendChild(r); g.appendChild(tx); svg.appendChild(g); chips.push({g,cx,cy}); });
    return (lt,dur,p)=>{ lbl.setAttribute('opacity',E.clamp(lt/300));
      chips.forEach((c,i)=>{ const a=E.pop(E.clamp((lt-200-i*120)/420));
        c.g.setAttribute('transform',`translate(${c.cx} ${c.cy}) scale(${a}) translate(${-c.cx} ${-c.cy})`);
        c.g.setAttribute('opacity',E.clamp((lt-200-i*120)/250)); }); };
  },
  /* a terminal window with text typing in green */
  terminal(svg,v,T){
    const text=String(v.text||'');
    const win=S('rect',{x:80,y:150,width:740,height:340,rx:16,fill:'#0b0e16',stroke:'rgba(255,255,255,.12)','stroke-width':1.5});
    const bar=S('rect',{x:80,y:150,width:740,height:46,rx:16,fill:'#11151f'});
    const d1=S('circle',{cx:112,cy:173,r:7,fill:'#ff5f57'});const d2=S('circle',{cx:136,cy:173,r:7,fill:'#febc2e'});const d3=S('circle',{cx:160,cy:173,r:7,fill:'#28c840'});
    [win,bar,d1,d2,d3].forEach(x=>svg.appendChild(x));
    const lines=text.split('\n'); const lineEls=lines.map((ln,i)=>{const t=mono(110,250+i*46,28,'#7dffb0',{'text-anchor':'start'});svg.appendChild(t);return t;});
    const total=text.length;
    return (lt,dur,p)=>{ const rev=E.clamp((lt-300)/Math.min(1600,dur-400)); let shown=Math.floor(total*rev); let used=0;
      lines.forEach((ln,i)=>{ const take=Math.max(0,Math.min(ln.length,shown-used)); lineEls[i].textContent='› '+ln.slice(0,take); used+=ln.length+1; });
    };
  },
  /* a question bubble; the user's answer types in below */
  input_prompt(svg,v,T){
    const q=String(v.question||'Type something:'); const ans=String(v.answer==null?'':v.answer);
    const bub=S('rect',{x:130,y:140,width:640,height:120,rx:26,fill:T.accentSoft,stroke:T.accent,'stroke-width':3});
    const qt=txt(450,200,30,T.ink); qt.textContent=q;
    const tail=S('path',{d:'M260 258 L260 308 L320 258 Z',fill:T.accentSoft,stroke:T.accent,'stroke-width':3});
    const box=S('rect',{x:170,y:370,width:560,height:96,rx:16,fill:T.panelSoft,stroke:T.muted,'stroke-width':2});
    const at=mono(200,422,34,T.ink,{'text-anchor':'start'}); at.textContent='';
    const caret=S('rect',{x:200,y:396,width:4,height:50,fill:T.accent});
    [bub,tail,qt,box,at,caret].forEach(x=>svg.appendChild(x));
    return (lt,dur,p)=>{
      const a=E.pop(E.clamp(lt/420));
      bub.setAttribute('transform',`translate(450 200) scale(${a}) translate(-450 -200)`);
      qt.setAttribute('opacity',E.clamp((lt-200)/300)); tail.setAttribute('opacity',E.clamp((lt-150)/300));
      box.setAttribute('opacity',E.clamp((lt-550)/300));
      const rev=E.clamp((lt-850)/Math.min(1300,Math.max(400,dur-1100)));
      at.textContent=ans.slice(0,Math.floor(ans.length*rev));
      let w=0; try{w=at.getComputedTextLength();}catch(e){w=at.textContent.length*18;}
      caret.setAttribute('x',205+w); caret.setAttribute('opacity',(lt>700&&Math.floor(lt/300)%2===0)?1:.2);
    };
  },
  /* running tally: items fly into a total box that counts up each pass */
  accumulator(svg,v,T){
    const items=(v.items&&v.items.length?v.items:['10','20','5']).slice(0,8).map(String);
    const nums=items.map(s=>parseFloat(s)); const label=v.label||'total';
    const result=v.result!=null?String(v.result):String(nums.reduce((a,b)=>a+(isFinite(b)?b:0),0));
    const n=items.length;
    const tbox=S('rect',{x:330,y:118,width:240,height:120,rx:20,fill:'none',stroke:T.accent,'stroke-width':4});
    const tlab=S('rect',{x:330,y:86,width:Math.max(120,label.length*18+40),height:46,rx:12,fill:T.accent});
    const tlt=mono(0,120,26,T.accentInk,{'text-anchor':'start'}); tlt.setAttribute('x',348); tlt.textContent=label;
    const tval=mono(450,182,48,T.ink); tval.textContent='0';
    const gap=820/n; const chips=[];
    items.forEach((it,i)=>{ const cx=60+gap*i+gap/2; const g=S('g',{});
      const r=S('rect',{x:-gap*0.36,y:-34,width:gap*0.72,height:68,rx:12,fill:T.accentSoft,stroke:T.accent,'stroke-width':2});
      const tx=mono(0,4,Math.min(28,gap*0.45),T.ink); tx.textContent=it; g.appendChild(r); g.appendChild(tx);
      g.setAttribute('transform',`translate(${cx} 478)`); svg.appendChild(g); chips.push({g,cx}); });
    [tlab,tbox,tlt,tval].forEach(x=>svg.appendChild(x));
    return (lt,dur,p)=>{
      tlab.setAttribute('opacity',E.clamp(lt/300)); tlt.setAttribute('opacity',E.clamp(lt/300));
      const start=450, span=Math.max(800,dur-start-300), per=span/n;
      let landed=0;
      for(let i=0;i<n;i++){ const t0=start+i*per, local=E.clamp((lt-t0)/per), g=chips[i].g;
        if(lt>=t0){ const fly=E.inOut(local); const x=E.lerp(chips[i].cx,450,fly), y=E.lerp(478,182,fly);
          g.setAttribute('transform',`translate(${x} ${y}) scale(${E.lerp(1,0.55,fly)})`);
          g.setAttribute('opacity',(1-Math.max(0,fly-0.7)/0.3).toFixed(3));
          if(local>=1) landed+=isFinite(nums[i])?nums[i]:0;
        } else { g.setAttribute('transform',`translate(${chips[i].cx} 478)`); g.setAttribute('opacity',E.clamp((lt-i*60)/300).toFixed(3)); } }
      tval.textContent=(lt>start+span-60)?result:String(Math.round(landed));
      const fl=Math.sin(E.clamp((lt-(start+span-60))/300)*Math.PI); tbox.setAttribute('stroke-width',(4+(fl>0?fl*5:0)).toFixed(1));
    };
  },
  none(svg,v,T){ const t=txt(450,320,46,T.ink,{'font-weight':'800'}); t.textContent=v.text||''; svg.appendChild(t);
    return (lt)=>t.setAttribute('opacity',E.clamp(lt/400)); },
};

/* ------------------------------ Engine ------------------------------ */
class Engine{
  constructor(stage,script,opts){
    this.stage=stage; this.opts=opts||{}; this.S=script; this.scenes=script.scenes||[]; this.meta=script.meta||{};
    this.theme=THEMES[opts.theme||this.meta.style||'cartoon']||THEMES.cartoon;
    this.audio=opts.audio||null; this._audioEls=[]; this._curAudio=-1; this._built=-1; this._capScene=-1;
    this._build();
    this._playing=false; this._t=0; this._startWall=0;
    this.totalMs=this.scenes.reduce((a,s)=>a+(s.durationMs||1500),0);
    window.__ready=true; this._emit('ready',{total:this.totalMs});
    if(!opts.manual) this.play(); else this.renderAt(0);
  }
  _emit(type,data){ try{ if(window.parent&&window.parent!==window) window.parent.postMessage(Object.assign({type:'engine-'+type},data),'*'); }catch(e){} }

  _build(){
    const root=this.stage; const th=this.theme;
    Object.entries(th.vars).forEach(([k,v])=>root.style.setProperty(k,v));
    // convenience color refs for components
    this.C={accent:gv('--accent'),accentInk:gv('--accent-ink'),accentSoft:gv('--accent-soft'),
      accentStrong:gv('--accent-strong'),ink:gv('--ink'),muted:gv('--muted'),panel:gv('--panel'),
      panelSoft:'rgba(127,127,150,.12)'};
    function gv(n){return getComputedStyle(root).getPropertyValue(n).trim()||'#888';}

    root.querySelector('#brand-t').textContent=this.meta.title? '': 'PyExplain';
    root.querySelector('#brand-t').textContent='PyExplain';
    root.querySelector('#file').textContent=slug(this.meta.title)+'.py';
    root.querySelector('#cap .av').textContent=th.av;

    // background orbs
    const bg=root.querySelector('#bg'); bg.innerHTML='';
    this._orbs=[];
    for(let i=0;i<3;i++){ const o=document.createElement('div'); o.className='orb';
      const sz=620+i*180; o.style.width=sz+'px'; o.style.height=sz+'px'; o.style.background=th.orbs[i%th.orbs.length];
      bg.appendChild(o); this._orbs.push({el:o,x:(i*700)%1700,y:(i*430)%900,sp:.05+i*.02,ph:i*2}); }

    // code lines
    this._codeLines=[]; const wrap=root.querySelector('#lines');
    const hl=root.querySelector('#hl'); wrap.innerHTML=''; wrap.appendChild(hl); this._hl=hl;
    this._codeFull=[]; this._codePlain=[];
    const src=(this.meta.code||'').replace(/\n$/,'').split('\n');
    src.forEach((ln,idx)=>{ const row=document.createElement('div'); row.className='cl';
      const num=document.createElement('span'); num.className='ln'; num.textContent=idx+1;
      const code=document.createElement('span'); code.className='code'; code.innerHTML=highlightPython(ln);
      row.appendChild(num); row.appendChild(code); wrap.appendChild(row);
      this._codeLines.push({row,code}); this._codeFull.push(highlightPython(ln)); this._codePlain.push(ln); });

    this.$={rcode:root.querySelector('#rcode'),rvis:root.querySelector('#rvis'),rhead:root.querySelector('#rhead'),
      cap:root.querySelector('#cap'),captx:root.querySelector('#captx'),badge:root.querySelector('#badge'),
      prog:root.querySelector('#prog>div'),vtitle:root.querySelector('#vtitle'),vcanvas:root.querySelector('#vcanvas'),
      cam:root.querySelector('#cam'),lines:wrap,codeView:root.querySelector('#code-view'),
      connector:root.querySelector('#connector'),cPath:root.querySelector('#cPath')};

    this._prep();
  }

  _prep(){
    // find first scene that shows code (for the typing reveal)
    this._revealScene=-1;
    const lastRect={code:R.codeBig,vis:R.visRight,head:R.headFull};
    this._st=this.scenes.map((sc,i)=>{
      const layout=this._layoutFor(sc);
      const L=LAYOUTS[layout]||LAYOUTS.split;
      if(this._revealScene<0 && L.code) this._revealScene=i;
      const rects={};
      for(const reg of ['code','vis','head']){
        if(L[reg]){ rects[reg]={r:L[reg],show:true}; lastRect[reg]=L[reg]; }
        else rects[reg]={r:lastRect[reg],show:false};
      }
      return {layout,rects,cap:L.cap, words:(sc.narration||'').split(/\s+/).filter(Boolean), hl:null};
    });
  }

  _layoutFor(sc){
    const vt=sc.visual&&sc.visual.type; const hasVis=!!(vt&&vt!=='none');
    const hasHl=!!(sc.highlight&&sc.highlight.length);
    let lay=(sc.layout&&LAYOUTS[sc.layout])?sc.layout:null;
    if(!lay){
      if(sc.kind==='intro'||sc.kind==='outro') lay='title';
      else if(sc.kind==='statement') lay='statement';
      else if(vt==='terminal'||(sc.output&&!hasVis)) lay='terminal';
      else if(hasVis) lay=hasHl?'split':'metaphor';
      else if(hasHl) lay='code';
      else lay='statement';
    }
    // validate so we never show an empty panel
    if((lay==='split'||lay==='metaphor')&&!hasVis) lay=hasHl?'code':'statement';
    if(lay==='terminal'&&!(hasVis||sc.output)) lay=hasHl?'code':'statement';
    if(lay==='code'&&!hasHl) lay='statement';
    return lay;
  }

  /* timing */
  _locate(t){let acc=0;for(let i=0;i<this.scenes.length;i++){const d=this.scenes[i].durationMs||1500;
    if(t<acc+d||i===this.scenes.length-1)return{i,lt:t-acc,dur:d,p:E.clamp((t-acc)/d)};acc+=d;}return{i:0,lt:0,dur:1,p:0};}
  _sceneStart(i){let a=0;for(let k=0;k<i;k++)a+=this.scenes[k].durationMs||1500;return a;}

  /* build per-scene DOM (component, headline, code font, hl rect) on change */
  _buildScene(i){
    const sc=this.scenes[i], st=this._st[i];
    // badge
    this.$.badge.textContent=(sc.badge||'').toUpperCase();
    // code font: fit to this scene's code region width.
    // Force the code region visible + sized so measurements are accurate even
    // if the previous scene had it hidden (display:none).
    const codeRect = st.rects.code.r;
    this.$.rcode.style.display=''; this.$.rcode.style.opacity='1';
    this.$.rcode.style.width=codeRect.w+'px'; this.$.rcode.style.height=codeRect.h+'px';
    this.$.rcode.style.transform='none';
    // restore full code FIRST so line heights are final, then measure
    if(i!==this._revealScene) this._codeLines.forEach((o,k)=>o.code.innerHTML=this._codeFull[k]);
    this._setCodeFont(codeRect.w);
    this._lineTops=this._codeLines.map(o=>o.row.offsetTop);
    this._lineH=this._codeLines.length>1?(this._lineTops[1]-this._lineTops[0]):46;
    st.hl=this._hlRect(sc.highlight);
    // visual component
    this.$.vcanvas.innerHTML=''; this._draw=null; this.$.vtitle.textContent='';
    if(st.rects.vis.show){
      const v=normVisual(sc.visual||{type:(sc.output?'terminal':'none'),text:sc.caption||''});
      if(v.type==='terminal'&&!v.text&&sc.output) v.text=sc.output;
      const comp=COMPONENTS[v.type]||COMPONENTS.none;
      const svg=S('svg',{viewBox:'0 0 900 640',preserveAspectRatio:'xMidYMid meet'});
      this.$.vcanvas.appendChild(svg);
      this.$.vtitle.textContent=sc.caption||'';
      try{ this._draw=comp(svg,v,this.C); }catch(e){ this._draw=null; }
    }
    // headline content
    this.$.rhead.innerHTML='';
    if(st.rects.head.show){
      if(sc.kind==='intro'||sc.kind==='outro'){
        add(this.$.rhead,'kick',(sc.kind==='outro'?'WRAP UP':'PYTHON EXPLAINER'));
        add(this.$.rhead,'emoji',sc.kind==='outro'?'🎉':'🐍');
        const big=document.createElement('div'); big.className='big'; big.innerHTML=words(sc.title||''); this.$.rhead.appendChild(big);
        add(this.$.rhead,'sub',sc.subtitle||'');
        this._headWords=big.querySelectorAll('.w');
      } else {
        const st2=document.createElement('div'); st2.className='stmt'; st2.innerHTML=words(sc.caption||sc.narration||'');
        this.$.rhead.appendChild(st2); this._headWords=st2.querySelectorAll('.w');
      }
    } else this._headWords=[];
    function add(host,cls,t){const d=document.createElement('div');d.className=cls;d.textContent=t;host.appendChild(d);}
    function words(t){return t.split(/\s+/).filter(Boolean).map(w=>'<span class="w">'+esc(w)+'</span>').join(' ');}
    this._built=i;
  }

  _setCodeFont(regionW){
    const wrap=this.$.lines; wrap.style.fontSize='26px';
    const avail=regionW-110;
    let maxW=0; this._codeLines.forEach(o=>maxW=Math.max(maxW,o.code.scrollWidth));
    if(maxW>avail&&avail>0){ const fs=Math.max(13,Math.floor(26*avail/maxW)); wrap.style.fontSize=fs+'px'; }
  }
  _hlRect(highlight){ if(!highlight||!highlight.length||!this._codeLines.length)return{show:false,top:0,height:0};
    const ls=highlight.filter(n=>n>=1&&n<=this._codeLines.length); if(!ls.length)return{show:false,top:0,height:0};
    const f=Math.min.apply(null,ls),l=Math.max.apply(null,ls);
    const r1=this._codeLines[f-1].row, r2=this._codeLines[l-1].row;
    const top=r1.offsetTop-3, bottom=r2.offsetTop+r2.offsetHeight+3;
    return{show:true,top,height:bottom-top}; }

  /* ---------- the deterministic frame ---------- */
  renderAt(t){
    t=E.clamp(t,0,this.totalMs); this._t=t;
    const loc=this._locate(t), sc=this.scenes[loc.i], st=this._st[loc.i];
    if(this._built!==loc.i) this._buildScene(loc.i);

    this.$.prog.style.width=(t/this.totalMs*100).toFixed(2)+'%';
    // orbs
    const ts=t/1000; this._orbs.forEach(o=>{ const x=o.x+Math.sin(ts*o.sp+o.ph)*90, y=o.y+Math.cos(ts*o.sp*.8+o.ph)*70;
      o.el.style.transform=`translate(${x}px,${y}px)`; });

    // region morph
    const k=E.inOut(E.clamp(loc.lt/640));
    const prev=loc.i>0?this._st[loc.i-1]:st;
    this._morph(this.$.rcode,prev.rects.code,st.rects.code,k);
    this._morph(this.$.rvis,prev.rects.vis,st.rects.vis,k);
    this._morph(this.$.rhead,prev.rects.head,st.rects.head,k);

    // caption show/hide
    const capOp=E.lerp(prev.cap?1:0, st.cap?1:0, k);
    this.$.cap.style.opacity=capOp.toFixed(3);
    this.$.cap.style.pointerEvents='none';

    // code internals (only meaningful when shown, cheap anyway)
    this._renderCode(sc,st,loc);
    // visual
    if(this._draw && st.rects.vis.show){ try{ this._draw(loc.lt,loc.dur,loc.p); }catch(e){} }
    // headline kinetic
    this._renderHead(loc, st);
    // connector arrow (code -> metaphor) in split layout
    this._renderConnector(st,loc);
    // caption words
    this._renderCaption(sc,st,loc);
    // badge
    this._renderBadge(sc,st,loc);
  }

  _renderConnector(st,loc){
    const con=this.$.connector, cp=this.$.cPath;
    if(st.layout==='split' && st.rects.code.show && st.rects.vis.show && this._draw){
      const c=st.rects.code.r, w=st.rects.vis.r;
      const cx=c.x+c.w-4, cy=c.y+c.h*0.40, vx=w.x+4, vy=w.y+w.h*0.40;
      cp.setAttribute('d',`M ${cx} ${cy} C ${cx+90} ${cy}, ${vx-90} ${vy}, ${vx} ${vy}`);
      const appear=E.out(E.clamp((loc.lt-500)/520));
      con.style.opacity=(appear*0.9).toFixed(3);
      const len=Math.abs(vx-cx)+Math.abs(vy-cy)+180;
      cp.setAttribute('stroke-dasharray',len);
      cp.setAttribute('stroke-dashoffset',(len*(1-appear)).toFixed(1));
    } else con.style.opacity=0;
  }

  _morph(el,prev,cur,k){
    const r={x:E.lerp(prev.r.x,cur.r.x,k),y:E.lerp(prev.r.y,cur.r.y,k),
      w:E.lerp(prev.r.w,cur.r.w,k),h:E.lerp(prev.r.h,cur.r.h,k)};
    const op=E.lerp(prev.show?1:0, cur.show?1:0, k);
    el.style.left=r.x+'px'; el.style.top=r.y+'px'; el.style.width=r.w+'px'; el.style.height=r.h+'px';
    el.style.opacity=op.toFixed(3);
    el.style.display = op<0.01 ? 'none':'';
    const sc=E.lerp(prev.show?1:0.965, cur.show?1:0.965, k);
    el.style.transform=`scale(${sc.toFixed(3)})`;
    el.style.transformOrigin='center center';
  }

  _renderCode(sc,st,loc){
    // typing reveal on the first code scene
    if(loc.i===this._revealScene){
      const rev=E.clamp(loc.lt/Math.min(loc.dur*0.8,2600)); const n=this._codeLines.length;
      const prog=rev*n; const cur=Math.floor(prog);
      this._codeLines.forEach((o,k)=>{ if(k<cur) o.code.innerHTML=this._codeFull[k];
        else if(k===cur){ const ln=this._codePlain[k]; const ch=Math.floor((prog-cur)*Math.max(1,ln.length));
          o.code.innerHTML=highlightPython(ln.slice(0,ch))+(rev<1?'<span class="caret">&nbsp;</span>':''); }
        else o.code.innerHTML='&nbsp;'; });
    }
    // highlight + camera (use accurate tops for current font)
    const hl=st.hl||{show:false};
    const prevHl=(loc.i>0&&this._st[loc.i-1].hl&&this._st[loc.i-1].hl.show)?this._st[loc.i-1].hl:hl;
    const g=E.inOut(E.clamp(loc.lt/Math.min(540,loc.dur*0.6)));
    if(hl.show){ const top=E.lerp(prevHl.top,hl.top,g), h=E.lerp(prevHl.height,hl.height,g);
      this._hl.style.transform=`translateY(${top}px)`; this._hl.style.height=h+'px';
      this._hl.style.opacity=(E.out(E.clamp(loc.lt/300))*(0.94+0.06*Math.sin(loc.lt/300))).toFixed(3);
    } else this._hl.style.opacity=0;
    // dim non-active
    const set=new Set(sc.highlight||[]); const dim=(sc.highlight&&sc.highlight.length&&loc.i!==this._revealScene)?0.32:1;
    this._codeLines.forEach((o,idx)=>o.row.style.opacity=set.has(idx+1)?1:dim);
    // camera: scroll active line toward centre + a subtle push-in zoom
    const H=this.$.codeView.clientHeight||700;
    const content=this._codeLines.length*this._lineH+44;
    const zoomT=(st.layout==='code'&&hl.show)?1.05:1.0;
    const zoom=1+(zoomT-1)*E.out(E.clamp(loc.lt/900));
    const center=hl.show?(hl.top+hl.height/2):(this._lineH*2);
    const target=E.clamp(H*0.5-center*zoom, Math.min(0,H-content*zoom), 0);
    if(this._camScene!==loc.i){ this._camFrom=(this._camCur==null?target:this._camCur); this._camScene=loc.i; }
    this._camCur=E.lerp(this._camFrom==null?target:this._camFrom,target,g);
    this.$.cam.style.transformOrigin='0 0';
    this.$.cam.style.transform=`translateY(${this._camCur}px) scale(${zoom.toFixed(3)})`;
  }

  _renderHead(loc, st){
    if(!st.rects.head.show||!this._headWords||!this._headWords.length) return;
    this._headWords.forEach((w,i)=>{ const a=E.back(E.clamp((loc.lt-120-i*70)/520));
      w.style.opacity=E.clamp((loc.lt-120-i*70)/300).toFixed(3);
      w.style.transform=`translateY(${(1-a)*26}px)`; });
  }

  _renderCaption(sc,st,loc){
    if(this._capScene!==loc.i){ this._capScene=loc.i;
      this.$.captx.innerHTML=st.words.map(w=>'<span class="w">'+esc(w)+'</span>').join(' ');
      this._capW=Array.from(this.$.captx.querySelectorAll('.w')); }
    const audioMs=this.audio&&this.audio[loc.i]?this.audio[loc.i].ms:null;
    const span=audioMs?Math.min(audioMs,loc.dur):loc.dur*0.92;
    const n=st.words.length||1;
    this._capW.forEach((w,i)=>{ const act=(i/n)*span; const on=loc.lt>=act;
      w.classList.toggle('on',on);
      const s=on?0.86+0.14*E.pop(E.clamp((loc.lt-act)/200)):1;
      w.style.transform=`scale(${s.toFixed(3)})`; });
  }

  _renderBadge(sc,st,loc){ const b=this.$.badge;
    if(!sc.badge||st.layout==='title'){ b.style.opacity=0; return; }
    const a=E.pop(E.clamp(loc.lt/420)); b.style.opacity=E.clamp(loc.lt/220).toFixed(3);
    b.style.transform=`scale(${(0.85+0.15*a).toFixed(3)})`; }

  /* ---------- playback ---------- */
  play(){ if(this._playing)return; this._playing=true; this._startWall=performance.now()-this._t; this._syncAudio(true); this._loop(); }
  pause(){ this._playing=false; this._pauseAudio(); }
  seek(ms){ this._t=E.clamp(ms,0,this.totalMs); this._startWall=performance.now()-this._t; this.renderAt(this._t);
    this._emit('tick',{t:this._t,total:this.totalMs}); if(this._playing)this._syncAudio(true,true); }
  restart(){ this.seek(0); this.play(); }
  control(a,v){ if(a==='play')this.play();else if(a==='pause')this.pause();else if(a==='seek')this.seek(v);
    else if(a==='restart')this.restart();else if(a==='theme')this.setTheme(v); }
  setTheme(name){ const th=THEMES[name]; if(!th)return; this.theme=th;
    Object.entries(th.vars).forEach(([k,v])=>this.stage.style.setProperty(k,v));
    this._build(); this._built=-1; this._capScene=-1; this.renderAt(this._t); }
  _loop(){ if(!this._playing)return; const t=performance.now()-this._startWall;
    if(t>=this.totalMs){ this.renderAt(this.totalMs); this._playing=false; this._pauseAudio();
      this._emit('tick',{t:this.totalMs,total:this.totalMs}); this._emit('ended',{}); return; }
    const loc=this._locate(t); if(loc.i!==this._curAudio)this._syncAudio(true);
    this.renderAt(t); this._emit('tick',{t,total:this.totalMs}); requestAnimationFrame(()=>this._loop()); }

  _ensureAudio(){ if(!this.audio||this._audioEls.length)return; this.audio.forEach(a=>{const el=a&&a.url?new Audio(a.url):null;if(el)el.preload='auto';this._audioEls.push(el);}); }
  _syncAudio(force,restart){ if(!this.audio)return; this._ensureAudio(); const loc=this._locate(this._t),i=loc.i;
    if(i!==this._curAudio||restart){ this._pauseAudio(); this._curAudio=i; const el=this._audioEls[i];
      if(el){try{el.currentTime=Math.max(0,loc.lt/1000);el.play().catch(()=>{});}catch(e){}} } }
  _pauseAudio(){ this._audioEls.forEach(el=>{if(el){try{el.pause();}catch(e){}}}); }
}

function slug(s){ return String(s||'program').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'').slice(0,22)||'program'; }
window.Engine=Engine; window.THEMES=THEMES;

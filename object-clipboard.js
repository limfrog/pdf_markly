/* Shared with PDF Markly. Horizon object clipboard v1; coordinates are canvas pixels. */
globalThis.HorizonClipboard = (() => {
  const FORMAT = 'horizon.objects';
  const clone = o => JSON.parse(JSON.stringify(o, (key, value) =>
    ['img', '_imgObj', 'id', 'layerId', 'isBackground', '_copiedAt'].includes(key) ? undefined : value));
  const colorParts = value => {
    const match = /^rgba\(\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)$/.exec(value || '');
    return match ? {color:`rgb(${match[1]},${match[2]},${match[3]})`,alpha:Number(match[4])} : {color:value,alpha:1};
  };
  function encodeObject(obj, app) {
    const o=clone(obj);
    if(o.type==='image') {
      o.src=obj.img?.src || obj._src || obj.src;
      delete o._src;
    }
    if(o.type==='shape') {
      const epp=app==='easy-paint-pad', fill=colorParts(epp?o.fillColor:(o.fill==='bg'?o.bgColor:o.color));
      o.strokeColor=epp?o.strokeColor:o.color;
      o.fillColor=epp?fill.color:(o.fill&&o.fill!=='none'?fill.color:null);
      o.fillAlpha=epp?(o._horizonFillAlpha??(o.alpha??1)*fill.alpha):(o.fill==='bg'?(o.bgAlpha??1):(o.alpha??1));
      o.measureBars=epp?!!o.measureBars:!!o.barlines;
      o.geometry=o._horizonGeometry || {origin:app};
      delete o._horizonGeometry;
    }
    if(o.type==='text'&&app==='pdf-markly') {
      o.box=!!o.boxed;o.boxBorder=o.boxStrokeWidth??1.5;
      o.boxPad=o.boxPad??8;o.boxBgColor=o.bgColor;o.boxBgAlpha=o.bgAlpha??1;
    }
    return o;
  }
  function decodeObject(obj, app) {
    const o=clone(obj);
    if(o.type==='image'){o._src=o.src;delete o.src;}
    if(o.type==='shape') {
      o._horizonGeometry=o.geometry;delete o.geometry;
      if(app==='pdf-markly') {
        o.color=o.strokeColor;o.fill=o.fillColor&&o.fillColor!=='transparent'?'bg':'none';
        o.bgColor=o.fillColor;o.bgAlpha=o.fillAlpha;o.barlines=!!o.measureBars;
      } else if(o.fillColor&&o.fillColor!=='transparent') {
        // Keep an independent fill opacity for the shared renderer.
        o._horizonFillAlpha=o.fillAlpha;
      }
    }
    if(o.type==='text'&&app==='pdf-markly') {
      o.boxed=!!o.box;o.boxStrokeWidth=o.boxBorder??1;o.bgColor=o.boxBgColor;o.bgAlpha=o.boxBgAlpha??1;
    }
    return o;
  }
  function stringify(objects, app, copiedAt=Date.now()) {
    return JSON.stringify({format:FORMAT,version:1,source:app,copiedAt,units:'canvas-px',objects:objects.map(o=>encodeObject(o,app))});
  }
  function parse(text, app) {
    let data;try{data=JSON.parse(text);}catch(_){return null;}
    if(data?.format!==FORMAT||data.version!==1||data.units!=='canvas-px'||!Array.isArray(data.objects)||!data.objects.length)return null;
    if(data.objects.length>10000)return null;
    for(const o of data.objects){
      if(!o||!['text','shape','stroke','image'].includes(o.type))return null;
      const keys=o.type==='shape'?['x1','y1','x2','y2']:o.type==='stroke'?[]:['x','y'];
      if(keys.some(k=>!Number.isFinite(o[k])))return null;
      if(o.type==='shape'&&!['line','rect','ellipse','arrow','staff'].includes(o.shape))return null;
      if(o.type==='stroke'&&(!Array.isArray(o.points)||!o.points.length||o.points.some(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y))))return null;
      if(o.type==='image'&&(!/^data:image\/(png|jpeg|webp|gif);base64,/i.test(o.src||'')||!Number.isFinite(o.w)||!Number.isFinite(o.h)||o.w<=0||o.h<=0))return null;
    }
    return {objects:data.objects.map(o=>decodeObject(o,app)),copiedAt:Number(data.copiedAt)||Date.now()};
  }
  async function loadImages(objects) {
    await Promise.all(objects.map(o=>o.type!=='image'?null:new Promise((resolve,reject)=>{
      const img=new Image();img.onload=()=>{o.img=img;delete o._src;resolve();};img.onerror=()=>reject(new Error('이미지를 불러올 수 없습니다.'));img.src=o._src;
    })));
    return objects;
  }
  function drawShape(c,obj,app) {
    const o=encodeObject(obj,app),sw=o.strokeWidth||1,epp=o.geometry?.origin==='easy-paint-pad';
    const x=Math.min(o.x1,o.x2),y=Math.min(o.y1,o.y2),w=Math.abs(o.x2-o.x1),h=Math.abs(o.y2-o.y1);
    c.save();c.strokeStyle=o.strokeColor;c.fillStyle=o.fillColor||'transparent';c.lineWidth=sw;c.lineCap='round';c.lineJoin='round';
    const stroke=()=>{c.globalAlpha=o.alpha??1;c.stroke();};
    if(o.shape==='rect'||o.shape==='ellipse'){
      c.beginPath();if(o.shape==='rect')c.rect(x,y,w,h);else c.ellipse(x+w/2,y+h/2,w/2,h/2,0,0,Math.PI*2);
      if(o.fillColor&&o.fillColor!=='transparent'){c.globalAlpha=app==='easy-paint-pad'?(obj._horizonFillAlpha??o.fillAlpha):o.fillAlpha;c.fill();}stroke();
    }else if(o.shape==='arrow'){
      const dx=o.x2-o.x1,dy=o.y2-o.y1,d=Math.hypot(dx,dy)||1,ux=dx/d,uy=dy/d;
      const len=6+Math.max(sw,1)*2,hl=epp?len*Math.cos(Math.PI/6):Math.max(12,sw*5),hw=epp?len/2:Math.max(8,sw*3);
      c.beginPath();c.moveTo(o.x1,o.y1);c.lineTo(o.x2-ux*hl,o.y2-uy*hl);c.lineCap='butt';stroke();
      c.beginPath();c.moveTo(o.x2,o.y2);c.lineTo(o.x2-ux*hl+uy*hw,o.y2-uy*hl-ux*hw);c.lineTo(o.x2-ux*hl-uy*hw,o.y2-uy*hl+ux*hw);c.closePath();c.fillStyle=o.strokeColor;c.fill();
    }else{
      c.beginPath();
      const sh=epp?h:Math.max(h,sw*8);
      if(o.shape==='staff'){c.lineWidth=epp?Math.max(.5,sw*.5):sw;for(let i=0;i<5;i++){c.moveTo(x,y+sh*i/4);c.lineTo(x+w,y+sh*i/4);}}
      else{c.moveTo(o.x1,o.y1);c.lineTo(o.x2,o.y2);}stroke();
      if(o.measureBars){c.lineWidth=sw;c.beginPath();const dx=o.x2-o.x1,dy=o.y2-o.y1,d=Math.hypot(dx,dy)||1,half=epp?Math.max(8,Math.min(18,10+sw*1.5)):Math.max(8,sw*3);
        for(const f of [.25,.5,.75,1]){if(o.shape==='staff'){c.moveTo(x+w*f,y);c.lineTo(x+w*f,y+sh);}else{const bx=o.x1+dx*f,by=o.y1+dy*f;c.moveTo(bx-dy/d*half,by+dx/d*half);c.lineTo(bx+dy/d*half,by-dx/d*half);}}stroke();}
    }
    c.restore();
  }
  return {stringify,parse,loadImages,drawShape};
})();

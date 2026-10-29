const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const sandbox={};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../object-clipboard.js'),'utf8'),sandbox);
const codec=sandbox.HorizonClipboard;
const source=[{id:1,layerId:'old',type:'shape',shape:'rect',x1:10,y1:20,x2:100,y2:80,strokeColor:'#123456',strokeWidth:3,alpha:.8,fillColor:'rgba(10,20,30,0.5)'},
 {type:'text',x:20,y:90,text:'Hello',box:true,boxBorder:2,boxPad:7,richLines:[[{text:'Hello',fontFamily:'Arial',fontSize:21,bold:true,color:'#333333'}]]}];
const received=codec.parse(codec.stringify(source,'easy-paint-pad',123),'pdf-markly');
assert.equal(received.copiedAt,123);assert.equal(received.objects.length,2);assert.equal(received.objects[0].color,'#123456');assert.equal(received.objects[0].bgAlpha,.4);assert.equal(received.objects[0].id,undefined);assert.equal(received.objects[1].boxed,true);
const returned=codec.parse(codec.stringify(received.objects,'pdf-markly'),'easy-paint-pad').objects;
assert.equal(returned[0].strokeColor,'#123456');assert.equal(returned[0]._horizonFillAlpha,.4);assert.equal(returned[1].boxBorder,2);assert.equal(returned[1].richLines[0][0].bold,true);assert.equal(source[0].id,1);
assert.equal(codec.parse('not JSON','pdf-markly'),null);
assert.equal(codec.parse(JSON.stringify({format:'horizon.objects',version:2,units:'canvas-px',objects:source}),'pdf-markly'),null);
for(const src of ['https://example.com/x.png','data:image/svg+xml;base64,PHN2Zz4='])assert.equal(codec.parse(codec.stringify([{type:'image',x:0,y:0,w:10,h:10,src}],'easy-paint-pad'),'pdf-markly'),null);
console.log('PASS: mixed object round trip, independent fills, rich text, no source mutation, invalid/untrusted payload rejection');

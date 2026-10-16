const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// Exercise the shipped preview code without a physical camera or browser.
const app = fs.readFileSync(path.join(__dirname, '../ocrbench/static/app.js'), 'utf8');
const code = app.slice(app.indexOf('function renderSourceFrame()'), app.indexOf('async function startRun()'));
function fixture() {
  const elements = new Map(), loads = [];
  function element() {
    const classes = new Set();
    return {textContent:'', src:'', style:{}, lastElementChild:{textContent:''}, classList:{
      add: name => classes.add(name), remove: name => classes.delete(name),
      contains: name => classes.has(name), toggle(name, value) {value ? classes.add(name) : classes.delete(name);}
    }, append(child) {elements.set(child.id, child);}};
  }
  const context = {$: id => elements.get(id) || (elements.set(id, element()), elements.get(id)),
    document: {createElement: () => element(), querySelectorAll: () => []},
    Image: class {constructor() {this.naturalWidth=1280;this.naturalHeight=720;loads.push(this);}},
    currentRun:{id:'run-one', config:{mode:'live'}, progress:'Initializing'},
    candidateIndex:0, frameIndex:0, followLive:true, sourceRequest:0, sourceKey:'',
    displayedSource:null, displayedRecord:null, record:null, running:true,
    currentRecord:() => context.record, busy:() => context.running,
    currentCandidate:() => context.candidate || {records:[]},
    renderEvidence:()=>{}, decorateTerms:()=>{},
    renderOverlay:() => {context.overlayFrame=context.displayedRecord?.frame_id;},
    selectSample:() => {context.restored=true;}, sampleId:'pivi-pro', encodeURIComponent, esc:String};
  vm.createContext(context);vm.runInContext(code,context);
  return {context, loads, show(record) {context.record=record;context.renderSourceFrame();}};
}
const frame = n => ({frame_id:`camera-${n}`, sample_id:`capture-camera-${n}`, predictions:[{text:`frame ${n}`} ]});

test('camera preview starts empty and swaps each decoded frame with its own detections', () => {
  const {context:c, loads, show}=fixture();
  show(null);
  assert(c.$('source-image').classList.contains('hidden'));
  assert.match(c.$('source-waiting').textContent,/Waiting/);
  show(frame(1));loads[0].onload();
  assert.equal(c.displayedRecord.frame_id,'camera-1');
  assert.equal(c.overlayFrame,'camera-1');
  assert.equal(c.$('source-image').src,'/api/samples/capture-camera-1/image');
  show(frame(2));
  assert.equal(c.overlayFrame,'camera-1');
  loads[1].onload();
  assert.equal(c.overlayFrame,'camera-2');
  assert.equal(c.$('source-image').src,'/api/samples/capture-camera-2/image');
  show(frame(2));assert.equal(loads.length,2);
});

test('late image loads cannot replace a newer frame or a different run', () => {
  const {context:c, loads, show}=fixture();
  show(frame(1));show(frame(2));loads[1].onload();loads[0].onload();
  assert.equal(c.overlayFrame,'camera-2');
  show(frame(3));c.currentRun={id:'other-run', config:{mode:'live'}};
  loads[2].onload();assert.equal(c.overlayFrame,'camera-2');
});

test('inspection and stop preserve the selected frame, failed image loads retry', () => {
  const {context:c, loads, show}=fixture();
  show(frame(1));loads[0].onerror();assert.equal(c.sourceKey,'');
  show(frame(1));loads[1].onload();c.followLive=false;
  show(frame(1));assert.match(c.$('source-status').textContent,/paused for inspection/);
  c.running=false;show(frame(1));assert.match(c.$('source-status').textContent,/Camera stopped/);
  assert.equal(loads.length,2);
  c.currentRun.config.mode='saved';c.renderSourceFrame();assert.equal(c.restored,true);
});

test('completed runs stop following and previous/next preserve the chosen frame', () => {
  const {context:c, loads}=fixture();
  c.candidate={records:[frame(0),frame(1),frame(2)]};c.currentRun.candidates=[];
  c.currentRecord=()=>c.candidate.records[c.frameIndex];c.running=false;
  vm.runInContext(app.slice(app.indexOf('function renderRun()'),app.indexOf('function renderEvidence()')),c);
  c.renderRun();assert.equal(c.frameIndex,2);assert.equal(c.followLive,false);
  loads.at(-1).onload();assert.equal(c.overlayFrame,'camera-2');
  c.chooseCameraFrame(0);loads.at(-1).onload();
  assert.equal(c.frameIndex,0);assert.equal(c.overlayFrame,'camera-0');
  c.renderRun();assert.equal(c.frameIndex,0);
  assert.equal(c.$('previous-camera-frame').disabled,true);
  assert.equal(c.$('next-camera-frame').disabled,false);
  c.chooseCameraFrame(1);loads.at(-1).onload();assert.equal(c.overlayFrame,'camera-1');
});

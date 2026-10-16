const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names = {rapidocr:'RapidOCR',paddleocr:'PaddleOCR',easyocr:'EasyOCR',tesseract:'Tesseract'};
const fmt = (n, digits=1) => n == null ? '—' : Number(n).toFixed(digits);
const pct = n => n == null ? '—' : fmt(n*100,1)+'%';
let samples=[], system={}, runs=[], currentRun=null, sampleId='pivi-pro', mode='saved', candidateIndex=0, frameIndex=0, evidenceTab='text', pollTimer;
let envs={};try{envs=JSON.parse(localStorage.getItem('ocrbench-environments')||'{}')}catch{}
let annotationDraft=null, annotationJsonMode=false, dragStart=null, pendingPolygon=null;
let historySelected=new Set(), historyCompare=false, historySort={key:'created',direction:-1};
let followLive=true, displayedSource=null, displayedRecord=null, sourceRequest=0, sourceKey='';

async function api(path, options={}){
  const response=await fetch('/api'+path,{...options,headers:{'X-OCRBench':'local',...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...options.headers}});
  if(!response.ok){let error;try{error=await response.json()}catch{throw Error(await response.text())}throw Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail||error));}
  return response.json();
}
function toast(message,error=false){$('toast').textContent=message;$('toast').className='toast'+(error?' error':'');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.add('hidden'),error?9000:4500);}
function guard(fn){return async(...args)=>{try{await fn(...args)}catch(e){toast(e.message,true)}}}
function icon(name){return `<svg><use href="#${name}"/></svg>`}
function currentSample(){return samples.find(s=>s.id===sampleId)}
function currentCandidate(){return currentRun?.candidates[candidateIndex]}
function currentRecord(){return currentCandidate()?.records[frameIndex]}
function engineInterpreter(engine){
  const info=system.engines.find(e=>e.id===engine);
  return ($('device').value==='gpu'?(envs[engine+'-gpu']||info?.gpu_python_path):null)||envs[engine]||info?.python_path||null;
}
function busy(){return currentRun&&['queued','running'].includes(currentRun.status)}

async function init(){
  [system,samples,runs]=await Promise.all([api('/system'),api('/samples'),api('/runs')]);
  $('server-status').textContent='Workspace connected';
  renderEngines();renderSamples();renderEnvironments();renderHistory();
  if(runs.length){await loadRun(runs[0].id)}
  if(system.active_run&&system.active_run!==currentRun?.id){await loadRun(system.active_run)}
}
function renderEngines(){
  const previous=[...document.querySelectorAll('#engine-list input')], selected=new Set(previous.filter(i=>i.checked).map(i=>i.value));
  $('engine-list').innerHTML=system.engines.map(e=>`<label class="engine-choice ${e.installed?'':'not-installed'}"><input type="checkbox" value="${e.id}" ${(previous.length?selected.has(e.id):e.id==='rapidocr')?'checked':''}><span><strong>${names[e.id]}</strong><small>${e.installed?'Ready for preflight':envs[e.id]?'Custom interpreter':'Separate environment'}</small></span><span class="engine-dot"></span></label>`).join('');
  $('ready-count').textContent=system.engines.filter(e=>e.installed).length;
  refreshDeviceOptions();
}
function refreshDeviceOptions(){
  const gpu=$('device').value==='gpu';
  document.querySelectorAll('#engine-list input').forEach(input=>{
    const info=system.engines.find(e=>e.id===input.value);
    input.disabled=gpu&&!info.gpu;
    if(input.disabled)input.checked=false;
    input.closest('label').title=input.disabled?'This engine supports CPU only':'';
    input.closest('label').style.opacity=input.disabled?'0.5':'';
    input.closest('label').querySelector('small').textContent=gpu?(info.gpu?(info.gpu_python_path||envs[info.id+'-gpu']?'GPU runtime · preflight':'GPU runtime required'):'CPU only'):(info.installed?'Ready for preflight':envs[info.id]?'Custom interpreter':'Separate environment');
  });
}
function renderSamples(){
  if(!samples.some(s=>s.id===sampleId))sampleId=samples[0]?.id;
  $('sample-select').innerHTML=samples.map(s=>`<option value="${s.id}" ${s.id===sampleId?'selected':''}>${esc(s.name)}</option>`).join('');
  $('sample-count').textContent=samples.length;$('dataset-count').textContent=samples.length;
  $('dataset-grid').innerHTML=samples.map(s=>`<article class="dataset-card"><img src="${s.url}" alt="${esc(s.name)}"><div><h3>${esc(s.name)}</h3><p>${s.width} × ${s.height} · ${s.annotation.regions.length} text regions · development</p><span class="badge ${s.annotation.reviewed&&s.annotation.complete?'success':'warning'}">${s.annotation.reviewed&&s.annotation.complete?'Reviewed & complete':'Draft annotations'}</span><br><button class="button secondary" data-open-sample="${s.id}">Open capture ${icon('arrow')}</button><button class="button secondary" data-annotate="${s.id}">Annotate</button></div></article>`).join('');
  document.querySelectorAll('[data-open-sample]').forEach(b=>b.onclick=()=>{selectSample(b.dataset.openSample);showView('workbench')});
  document.querySelectorAll('[data-annotate]').forEach(b=>b.onclick=()=>{selectSample(b.dataset.annotate);openAnnotation()});
  selectSample(sampleId);
}
function selectSample(id){
  sampleId=id;const s=currentSample();if(!s)return;
  sourceRequest++;sourceKey='';displayedSource=s;displayedRecord=null;
  $('camera-preview-option')?.remove();$('sample-select').disabled=false;$('source-heading').textContent='Source image';
  $('source-image').classList.remove('hidden');$('source-waiting').classList.add('hidden');
  $('source-status').textContent='';$('annotate-button').disabled=false;$('annotation-state').disabled=false;
  $('sample-select').value=id;$('source-image').src=s.url;$('source-image').alt=s.name;
  $('image-stage').style.aspectRatio=`${s.width}/${s.height}`;
  $('image-dimensions').textContent=`${s.width} × ${s.height}`;$('capture-group').textContent=s.capture_group;
  const reviewed=s.annotation.reviewed&&s.annotation.complete;
  $('annotation-state').textContent=reviewed?'Reviewed & complete ↗':'Draft · review required ↗';
  $('annotation-state').classList.toggle('reviewed',reviewed);
  renderOverlay();
}
function renderOverlay(){
  const s=displayedSource||currentSample(), r=displayedSource?.stream?displayedRecord:currentRecord();if(!s)return;
  const matching=r?.sample_id===s.id;
  const predictions=matching?r.predictions||[]:[], placed=[], labels=[];
  const scale=s.width/($('image-stage').clientWidth||s.width), font=9*scale, height=14*scale, gap=2*scale;
  const canvas=document.createElement('canvas'), ctx=canvas.getContext('2d');ctx.font=`500 ${font}px Segoe UI, sans-serif`;
  $('overlay').setAttribute('viewBox',`0 0 ${s.width} ${s.height}`);
  $('overlay').innerHTML=$('show-boxes').checked?predictions.map((p,i)=>{
    const full=`${p.text} · ${p.confidence==null?'confidence unavailable':pct(p.confidence)}`, maxWidth=s.width-2*gap;
    let label=full;
    // Fit labels to the image; the title and accessible name keep the complete text.
    while(ctx.measureText(label).width+8*scale>maxWidth&&label.length>2)label=label.slice(0,-2)+'…';
    const width=Math.min(maxWidth,ctx.measureText(label).width+8*scale);
    const xs=p.polygon.map(pt=>pt[0]),ys=p.polygon.map(pt=>pt[1]),left=Math.min(...xs),top=Math.min(...ys),bottom=Math.max(...ys);
    const clampX=x=>Math.max(gap,Math.min(x,s.width-width-gap)), clamp=y=>Math.max(gap,Math.min(y,s.height-height-gap));
    const anchorX=clampX(left), anchorY=clamp(top-height-gap);
    const positions=[clamp(top-height-gap),clamp(bottom+gap)];
    for(let step=1;step<Math.ceil(s.height/height);step++)positions.push(clamp(top-height-gap-step*(height+gap)),clamp(bottom+gap+step*(height+gap)));
    const horizontal=[left,Math.max(...xs)-width,(left+Math.max(...xs)-width)/2,left-width-gap,Math.max(...xs)+gap].map(clampX);
    const choices=positions.flatMap(y=>horizontal.map(x=>({x,y,distance:Math.abs(x-anchorX)+Math.abs(y-anchorY)}))).sort((a,b)=>a.distance-b.distance);
    const {x,y}=choices.find(({x,y})=>!placed.some(b=>x<b.x+b.width+gap&&x+width+gap>b.x&&y<b.y+height+gap&&y+height+gap>b.y))??choices[0];
    if($('show-labels').checked)placed.push({x,y,width});
    const labelSvg=$('show-labels').checked?`<line class="overlay-connector" x1="${left}" y1="${top}" x2="${x+Math.min(width/2,8*scale)}" y2="${y+height/2}"/><rect class="overlay-label-bg" x="${x}" y="${y}" width="${width}" height="${height}" rx="${2*scale}"/><text class="overlay-label" x="${x+4*scale}" y="${y+height/2}" font-size="${font}">${esc(label)}</text>`:'';
    if(labelSvg)labels.push(`<g data-polygon="${i}" aria-hidden="true">${labelSvg}</g>`);
    return `<g data-polygon="${i}" role="button" tabindex="0" aria-label="${esc(full)}"><title>${esc(full)}</title><polygon points="${p.polygon.map(pt=>pt.join(',')).join(' ')}"/></g>`;
  }).join('')+labels.join(''):'';
  $('overlay-legend').textContent=matching?`${predictions.length} OCR predictions`:'OCR predictions';
  document.querySelectorAll('[data-polygon]').forEach(p=>{p.onclick=()=>highlightPrediction(Number(p.dataset.polygon));p.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();highlightPrediction(Number(p.dataset.polygon))}}});
}
function highlightPrediction(i){
  document.querySelectorAll('[data-polygon]').forEach(p=>p.classList.toggle('highlight',Number(p.dataset.polygon)===i));
  document.querySelectorAll('[data-prediction]').forEach(p=>p.style.background=Number(p.dataset.prediction)===i?'#eff7e9':'');
}
function showView(view){
  document.querySelectorAll('.view').forEach(v=>v.classList.toggle('hidden',v.id!=='view-'+view));
  document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  $('breadcrumb').textContent={workbench:'Workbench',dataset:'Dataset',history:'Run history',environments:'Environments'}[view];
  if(view==='history')refreshHistory().catch(e=>toast(e.message,true));
}
function setMode(value){
  mode=value;document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('selected',b.dataset.mode===value));
  $('stream-options').classList.toggle('hidden',value==='saved');document.querySelectorAll('.live-only').forEach(e=>e.classList.toggle('hidden',value!=='live'));
  $('source-type').textContent=value==='saved'?'SAVED IMAGE':value==='replay'?'TIMED REPLAY':'LIVE CAMERA';
  if(value!=='live'&&currentRun?.config.mode==='live'&&!busy()){
    followLive=false;selectSample(sampleId);$('live-follow-control').classList.add('hidden');
  }
}
function renderSourceFrame(){
  const live=currentRun?.config.mode==='live', record=currentRecord();
  $('live-follow-control').classList.toggle('hidden',!live);$('follow-live').checked=followLive;
  $('camera-frame-navigation').classList.toggle('hidden',!live);
  const count=currentCandidate()?.records.length||0;
  $('camera-frame-position').textContent=count?`Frame ${frameIndex+1} / ${count}`:'No frames yet';
  $('previous-camera-frame').disabled=!count||frameIndex===0;
  $('next-camera-frame').disabled=!count||frameIndex>=count-1;
  if(!live){if(displayedSource?.stream||$('source-image').classList.contains('hidden'))selectSample(sampleId);return}
  $('source-heading').textContent='Camera stream';$('sample-select').disabled=true;
  if(!$('camera-preview-option')){const option=document.createElement('option');option.id='camera-preview-option';option.value='__camera__';option.textContent='Camera stream · processed frames';$('sample-select').append(option)}
  $('sample-select').value='__camera__';
  $('source-type').textContent=busy()?'LIVE CAMERA':'CAMERA RECORDING';
  $('annotate-button').disabled=true;$('annotation-state').disabled=true;
  if(!record){
    sourceRequest++;sourceKey='';displayedSource=null;displayedRecord=null;
    $('source-image').classList.add('hidden');$('overlay').innerHTML='';
    $('source-waiting').classList.remove('hidden');
    $('source-waiting').textContent=busy()?'Waiting for the first camera detection…':'No camera frames were processed.';
    $('source-status').textContent=busy()?currentRun.progress:'Camera stopped';
    $('capture-group').textContent='Live camera';$('image-dimensions').textContent='';return;
  }
  const key=`${currentRun.id}:${candidateIndex}:${record.frame_id}`;
  if(key===sourceKey){updateSourceStatus();return}
  sourceKey=key;const request=++sourceRequest, runId=currentRun.id, image=new Image();
  image.onload=()=>{
    if(request!==sourceRequest||currentRun?.id!==runId)return;
    // Swap the decoded frame and its own predictions together. Never paint old
    // detections onto a newer camera frame while it is still loading.
    displayedSource={id:record.sample_id,width:image.naturalWidth,height:image.naturalHeight,stream:true};displayedRecord=record;
    $('source-image').src=image.src;$('source-image').alt=`Camera frame ${record.frame_id}`;
    $('source-image').classList.remove('hidden');$('source-waiting').classList.add('hidden');
    $('image-stage').style.aspectRatio=`${image.naturalWidth}/${image.naturalHeight}`;
    $('image-dimensions').textContent=`${image.naturalWidth} × ${image.naturalHeight}`;
    $('capture-group').textContent=record.frame_id;
    $('annotation-state').textContent='Camera frame · unreviewed';$('annotation-state').classList.remove('reviewed');
    renderOverlay();updateSourceStatus();
  };
  image.onerror=()=>{
    if(request!==sourceRequest)return;
    sourceKey='';displayedSource=null;displayedRecord=null;$('overlay').innerHTML='';
    $('source-image').classList.add('hidden');$('source-waiting').classList.remove('hidden');
    $('source-waiting').textContent=record.frame_storage==='session'||record.sample_id.startsWith('session-')?'This temporary camera frame is no longer available. Enable saving before a future run to keep frames.':'Camera frame could not be loaded.';
    $('source-status').textContent='Frame unavailable';
  };
  image.src=`/api/samples/${encodeURIComponent(record.sample_id)}/image`;
}
function updateSourceStatus(){
  if(!displayedSource?.stream)return;
  const state=busy()?(followLive?'Live · following detections':'Live · paused for inspection'):'Camera stopped';
  const storage=displayedRecord.frame_storage==='session'||displayedRecord.sample_id.startsWith('session-')?' · session only':'';
  $('source-status').textContent=`${state} · ${displayedRecord.frame_id} · ${displayedRecord.predictions?.length||0} text regions${storage}`;
}
function chooseCameraFrame(index){
  const count=currentCandidate()?.records.length||0;
  if(!count)return;
  frameIndex=Math.max(0,Math.min(Number(index),count-1));followLive=false;renderRun();
}
function configuration(){
  const engineOptions=JSON.parse($('engine-options').value||'{}');
  if(!engineOptions||Array.isArray(engineOptions)||typeof engineOptions!=='object')throw Error('Engine options must be a JSON object');
  const selected=[...document.querySelectorAll('#engine-list input:checked')].map(e=>e.value);
  if(!selected.length)throw Error('Select at least one OCR engine');
  return {samples:$('all-samples').checked?samples.map(s=>s.id):[sampleId],mode,
    engines:selected.map(engine=>({engine,device:$('device').value,languages:$('languages').value.split(',').map(s=>s.trim()).filter(Boolean),threads:Number($('threads').value),python_path:engineInterpreter(engine),options:engineOptions})),
    preprocessing:$('preprocessing').value,track:$('track').value,warmups:Number($('warmups').value),repetitions:Number($('repetitions').value),timeout_s:Number($('timeout').value),iou_threshold:Number($('iou').value),
    replay_fps:Number($('stream-fps').value),queue_policy:$('queue-policy').value,camera_index:Number($('camera-index').value),duration_s:Number($('duration').value),
    save_camera_frames:$('save-camera-frames').checked,
    max_p95_ms:$('gate-latency').value?Number($('gate-latency').value):null,min_e2e_f1:$('gate-f1').value?Number($('gate-f1').value):null};
}
async function startRun(){
  const config=configuration();
  if(mode==='live'&&config.engines.length!==1)throw Error('Select one engine for live camera capture. Use replay for a paired comparison.');
  $('run-button').disabled=true;
  try{currentRun=await api('/runs',{method:'POST',body:JSON.stringify(config)});candidateIndex=0;frameIndex=0;followLive=true;selectSample(sampleId);renderRun();pollRun();toast('Benchmark started. Engines run in isolated workers.')}finally{if(!busy())$('run-button').disabled=false}
}
async function pollRun(){
  clearTimeout(pollTimer);if(!currentRun)return;
  try{currentRun=await api('/runs/'+currentRun.id);renderRun();if(busy())pollTimer=setTimeout(pollRun,currentRun.config.mode==='live'?250:1000);else{refreshHistory();toast(currentRun.status==='completed'?'Benchmark complete. Results saved.':`Benchmark ${currentRun.status.replaceAll('_',' ')}. Inspect run details.`,currentRun.status==='error')}}catch(e){toast(e.message,true);pollTimer=setTimeout(pollRun,3000)}
}
async function loadRun(id){
  clearTimeout(pollTimer);currentRun=await api('/runs/'+id);candidateIndex=0;frameIndex=currentRun.config.mode==='live'?Math.max(0,(currentCandidate()?.records.length||0)-1):0;followLive=busy();selectSample(sampleId);renderRun();if(busy())pollRun();
}
function renderRun(){
  if(!currentRun)return;const running=busy();
  $('run-button').disabled=running;$('cancel-button').classList.toggle('hidden',!running);$('run-progress').classList.toggle('hidden',!running);
  $('run-progress').lastElementChild.textContent=currentRun.progress;
  $('run-caption').textContent=running?currentRun.progress:'Cold start and warm measurements are recorded separately.';
  $('run-subtitle').textContent=`${currentRun.id} · ${new Date(currentRun.created_at).toLocaleString()} · ${currentRun.config.preprocessing} · ${currentRun.config.mode} · ${currentRun.config.track==='full'?'full image':'known crops'}`;
  $('export-toggle').disabled=false;
  $('export-menu').innerHTML=['csv','json','jsonl','html'].map(format=>`<a href="/api/runs/${currentRun.id}/export/${format}" download>${{csv:'Comparison CSV',json:'Complete JSON',jsonl:'Raw records JSONL',html:'HTML report'}[format]}</a>`).join('');
  if(currentRun.candidates.length){
    candidateIndex=Math.min(candidateIndex,currentRun.candidates.length-1);
    $('comparison-body').innerHTML=currentRun.candidates.map((c,i)=>{
      const s=c.summary||{}, ram=c.resources?.peak_process_tree_rss_mb;
      const style=c.status==='completed'?'success':['initializing','running'].includes(c.status)?'warning':'error';
      return `<tr data-candidate="${i}" class="${i===candidateIndex?'selected':''}"><td><strong>${names[c.config.engine]}</strong><small>${esc(c.identity?.observed_device||c.config.device.toUpperCase())} · ${esc(c.config.languages.join(', '))}</small></td><td><span class="badge ${style}">${esc(c.status)}</span></td><td class="mono">${pct(s.e2e?.f1)}</td><td class="mono">${pct(s.cer)}</td><td class="mono">${fmt(s.latency_ms?.p95)}${s.latency_ms?.p95!=null?' ms':''}</td><td class="mono">${fmt(s.completed_fps,2)}</td><td class="mono">${fmt(ram,0)}${ram!=null?' MB':''}</td><td class="mono">${s.failures??'—'}</td></tr>`
    }).join('');
    document.querySelectorAll('[data-candidate]').forEach(b=>b.onclick=()=>{candidateIndex=Number(b.dataset.candidate);frameIndex=0;renderRun()});
  }
  $('candidate-select').innerHTML=currentRun.candidates.map((c,i)=>`<option value="${i}" ${i===candidateIndex?'selected':''}>${names[c.config.engine]} · ${c.config.device.toUpperCase()}</option>`).join('');
  const records=currentCandidate()?.records||[];frameIndex=Math.min(frameIndex,Math.max(0,records.length-1));
  if(currentRun.config.mode==='live'&&followLive){frameIndex=Math.max(0,records.length-1);if(!running)followLive=false}
  $('frame-select').innerHTML=records.length?records.map((r,i)=>`<option value="${i}" ${i===frameIndex?'selected':''}>${currentRun.config.mode==='live'?`Frame ${i+1} · ${esc(r.frame_id)}`:`${esc(r.sample_id)} · #${r.repetition+1}`}</option>`).join(''):'<option>No frames yet</option>';
  const c=currentCandidate();
  $('result-note').textContent=c?.summary?.quality_scored_attempts?`Strict Unicode · ${c.summary.unique_samples} unique samples · ${c.summary.quality_scored_attempts} scored attempts. Repetition does not add independent scene diversity.`:'Quality scores require reviewed, complete annotations. Latency and throughput use measured calls only.';
  renderEvidence();renderSourceFrame();renderOverlay();
}
function renderEvidence(){
  const c=currentCandidate(), r=currentRecord();
  document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===evidenceTab);b.setAttribute('aria-selected',b.dataset.tab===evidenceTab)});
  $('detection-count').textContent=r?.predictions?.length||0;
  if(!c){$('evidence-content').innerHTML='<div class="empty-evidence">Text, confidence, and source positions will appear here after a run.</div>';return}
  if(evidenceTab==='details'){
    const s=c.summary||{};
    $('evidence-content').innerHTML=`<div class="details-grid"><div class="detail-card"><span>WORKER INITIALIZATION</span><strong>${fmt(c.initialization_ms)} ms</strong></div><div class="detail-card"><span>FIRST RESULT · FROM WORKER START</span><strong>${fmt(c.first_result_ms)} ms</strong></div><div class="detail-card"><span>WARM MEDIAN / P99</span><strong>${fmt(s.latency_ms?.median)} / ${fmt(s.latency_ms?.p99)} ms</strong></div><div class="detail-card"><span>MEASURED ATTEMPTS</span><strong>${s.attempts??0} · ${s.unique_samples??0} unique samples</strong></div><div class="detail-card"><span>RECEIVED / QUEUE DROPS</span><strong>${c.stream?`${c.stream.received} / ${c.stream.queue_drops}`:'Saved-image track'}</strong></div><div class="detail-card"><span>ACCEPTANCE GATES</span><strong>${Object.keys(s.acceptance||{}).length?esc(JSON.stringify(s.acceptance)):'Not configured'}</strong></div>${c.error?`<div class="error-message">${esc(c.error)}</div>`:''}<a href="/api/runs/${currentRun.id}/logs/${c.name}" target="_blank" rel="noopener">Open worker log ↗</a><pre>${esc(JSON.stringify({identity:c.identity,resources:c.resources,stream:c.stream,summary:c.summary,frame_timing:r?.timing,quality:r?.quality,crop_recognition:r?.crop_recognition,host:currentRun.host,config:currentRun.config,config_sha256:currentRun.config_sha256,source_sha256:currentRun.source_sha256},null,2))}</pre></div>`;
    return;
  }
  if(!r){$('evidence-content').innerHTML=c.error?`<div class="error-message">${esc(c.error)}<br>Configure the engine in Environments, then run again. <a href="/api/runs/${currentRun.id}/logs/${c.name}" target="_blank">Worker log ↗</a></div>`:'<div class="empty-evidence">Waiting for measured frames…</div>';return}
  if(evidenceTab==='text'){
    if(r.status!=='success'){$('evidence-content').innerHTML=`<div class="error-message">${esc(r.status)}: ${esc(r.error)}</div>`;return}
    $('evidence-content').innerHTML=r.predictions.length?`<table class="evidence-table"><thead><tr><th>#</th><th>RECOGNIZED TEXT</th><th>CONFIDENCE</th><th>SOURCE POSITION (X, Y)</th></tr></thead><tbody>${r.predictions.map((p,i)=>`<tr data-prediction="${i}"><td class="mono">${String(i+1).padStart(2,'0')}</td><td class="text-cell">${esc(p.text)}</td><td><div class="confidence"><span class="confidence-track"><i style="width:${p.confidence==null?0:p.confidence*100}%"></i></span>${pct(p.confidence)}</div></td><td class="mono">${p.polygon.map(p=>`(${fmt(p[0],0)}, ${fmt(p[1],0)})`).join(' ')}</td></tr>`).join('')}</tbody></table>`:'<div class="empty-evidence">No text regions detected. This is a recorded empty output.</div>';
    document.querySelectorAll('[data-prediction]').forEach(el=>{el.onmouseenter=()=>highlightPrediction(Number(el.dataset.prediction));el.onclick=()=>highlightPrediction(Number(el.dataset.prediction))});
  }else if(evidenceTab==='labels'){
    const labels=r.application?.labels||[];
    $('evidence-content').innerHTML=labels.length?`<table class="evidence-table"><thead><tr><th>EXPECTED LABEL</th><th>EXPECTED STATE</th><th>OBSERVED</th><th>OUTCOME</th><th>EVIDENCE</th></tr></thead><tbody>${labels.map(l=>`<tr><td>${esc(l.text)}</td><td>${l.present?'Present':'Absent'}</td><td>${esc(l.state)}</td><td><span class="badge ${l.correct===null?'warning':l.correct?'success':'error'}">${l.correct===null?'Uncertain':l.correct?'Correct':'Incorrect'}</span></td><td>${esc(l.evidence.map(p=>p.text).join(', ')||'—')}</td></tr>`).join('')}</tbody></table>`:'<div class="empty-evidence">Add expected labels in the annotation JSON to verify text and location.</div>';
  }else{
    const fields=r.application?.fields||[];
    $('evidence-content').innerHTML=fields.length?`<table class="evidence-table"><thead><tr><th>FIELD</th><th>RAW OCR TEXT</th><th>PARSED VALUE / UNIT</th><th>STRICT EXPECTED MATCH</th></tr></thead><tbody>${fields.map(f=>`<tr><td>${esc(f.name)}</td><td>${esc(f.raw||'—')}</td><td>${esc(f.parse_error||[f.value,f.unit].filter(v=>v!=null).join(' '))}</td><td><span class="badge ${f.correct===null?'warning':f.correct?'success':'error'}">${f.correct===null?'No reference':f.correct?'Exact':'Mismatch'}</span></td></tr>`).join('')}</tbody></table>`:'<div class="empty-evidence">Add named regions and parsing rules in the annotation JSON to extract values.</div>';
  }
}
async function refreshHistory(){runs=await api('/runs');renderHistory()}
function renderHistory(){
  $('run-count').textContent=runs.length;
  historySelected=new Set([...historySelected].filter(id=>runs.some(r=>r.id===id)));
  if(historySelected.size<2)historyCompare=false;
  const engine=$('history-engine').value,device=$('history-device').value,completed=$('history-completed').checked;
  const rows=runs.flatMap(r=>(r.candidates?.length?r.candidates:r.config.engines.map(config=>({config,status:r.status}))).map((c,index)=>({r,c,index})));
  const visible=rows.filter(({r,c})=>(!historyCompare||historySelected.has(r.id))&&(!engine||c.config.engine===engine)&&(!device||c.config.device===device)&&(!completed||c.status==='completed'));
  const value=({r,c},key)=>({created:r.created_at,engine:names[c.config.engine],device:c.config.device,status:c.status,p95:c.summary?.latency_ms?.p95,fps:c.summary?.completed_fps,f1:c.summary?.e2e?.f1,cer:c.summary?.cer,ram:c.resources?.peak_process_tree_rss_mb,failures:c.summary?.failures})[key];
  visible.sort((a,b)=>{const av=value(a,historySort.key),bv=value(b,historySort.key);if(av==null)return bv==null?0:1;if(bv==null)return -1;return (typeof av==='number'?av-bv:String(av).localeCompare(String(bv)))*historySort.direction});
  const columns=[['created','RUN / TIME'],['engine','ENGINE / DEVICE'],['status','STATUS'],['p95','P95 ↓ · MS'],['fps','FPS ↑'],['f1','F1 ↑'],['cer','CER ↓'],['ram','RAM · MB'],['failures','FAILURES']];
  $('history-list').innerHTML=`<table class="history-table"><thead><tr><th aria-label="Select runs"></th>${columns.map(([key,label])=>`<th aria-sort="${historySort.key===key?(historySort.direction===1?'ascending':'descending'):'none'}"><button data-history-sort="${key}">${label} <span>${historySort.key===key?(historySort.direction===1?'▴':'▾'):'↕'}</span></button></th>`).join('')}<th>SETUP / SOURCE</th><th>ACTIONS</th></tr></thead><tbody>${visible.length?visible.map(({r,c,index})=>{
    const s=c.summary||{},cfg=r.config,e=c.config,style=c.status==='completed'?'success':['queued','running','initializing'].includes(c.status)?'warning':'error';
    return `<tr class="${historySelected.has(r.id)?'selected':''}" data-history-row="${r.id}"><td><input type="checkbox" data-compare-run="${r.id}" aria-label="Select run ${r.id}, ${names[e.engine]} ${index+1}" ${historySelected.has(r.id)?'checked':''}></td><td><strong class="mono">${r.id}</strong><small>${esc(new Date(r.created_at).toLocaleString())}</small></td><td><strong>${names[e.engine]} <span class="device-badge">${e.device.toUpperCase()}</span></strong><small title="${esc(c.observed_device||'Observed device unavailable')}">${esc(c.observed_device||'Observed device unavailable')}</small></td><td><span class="badge ${style}" title="${esc(c.error||'')}">${esc(c.status)}</span></td><td class="mono">${fmt(s.latency_ms?.p95)}</td><td class="mono">${fmt(s.completed_fps,2)}</td><td class="mono">${pct(s.e2e?.f1)}</td><td class="mono">${pct(s.cer)}</td><td class="mono">${fmt(c.resources?.peak_process_tree_rss_mb,0)}</td><td class="mono">${s.failures??'—'}<small>${s.completed??0} completed</small></td><td class="history-setup"><strong>${esc(cfg.samples.join(', '))}</strong><small>${esc(cfg.mode)} · ${esc(cfg.preprocessing)} · ${cfg.track==='full'?'full image':'known crops'}</small><small>${cfg.repetitions} reps · ${cfg.warmups} warmups · ${esc(e.languages.join(', '))} · ${e.threads} threads</small></td><td><div class="history-actions"><button class="button secondary compact" data-open-run="${r.id}" data-open-candidate="${index}">Open results</button><button class="text-button" data-rerun="${r.id}">Load setup</button></div></td></tr>`;
  }).join(''):`<tr><td colspan="12" class="empty-table">${runs.length?'No results match these filters.':'No saved runs yet. Start a benchmark in the workbench.'}</td></tr>`}</tbody></table>`;
  $('history-selection').textContent=`${historySelected.size} runs selected`;
  $('compare-selected').disabled=historySelected.size<2;$('compare-selected').textContent=historyCompare?'Show all runs':'Compare selected';
  $('history-note').textContent=`${historyCompare?'Selected comparison · ':''}${visible.length} engine results from ${new Set(visible.map(row=>row.r.id)).size} runs. Click a column heading to sort. Select any engine row to include its whole run.`;
  document.querySelectorAll('[data-history-sort]').forEach(b=>b.onclick=()=>{const key=b.dataset.historySort;historySort={key,direction:historySort.key===key?-historySort.direction:key==='created'?-1:1};renderHistory()});
  document.querySelectorAll('[data-compare-run]').forEach(b=>b.onchange=()=>{b.checked?historySelected.add(b.dataset.compareRun):historySelected.delete(b.dataset.compareRun);renderHistory()});
  document.querySelectorAll('[data-open-run]').forEach(b=>b.onclick=guard(async()=>{await loadRun(b.dataset.openRun);candidateIndex=Number(b.dataset.openCandidate);frameIndex=currentRun.config.mode==='live'?Math.max(0,(currentCandidate()?.records.length||0)-1):0;const r=currentRecord();if(r&&samples.some(s=>s.id===r.sample_id))selectSample(r.sample_id);renderRun();showView('workbench')}));
  document.querySelectorAll('[data-rerun]').forEach(b=>b.onclick=guard(async()=>{const r=await api('/runs/'+b.dataset.rerun);applyConfig(r.config);showView('workbench');toast('Configuration loaded. Start a new run when ready.')}));
}
function applyConfig(c){
  setMode(c.mode);if(c.samples.length)selectSample(c.samples[0]);
  $('save-camera-frames').checked=c.save_camera_frames===true;
  document.querySelectorAll('#engine-list input').forEach(e=>e.checked=c.engines.some(x=>x.engine===e.value));
  for(const [id,key] of Object.entries({preprocessing:'preprocessing',track:'track',warmups:'warmups',repetitions:'repetitions',timeout:'timeout_s',iou:'iou_threshold','stream-fps':'replay_fps','queue-policy':'queue_policy','camera-index':'camera_index',duration:'duration_s','gate-latency':'max_p95_ms','gate-f1':'min_e2e_f1'}))$(id).value=c[key]??'';
  const e=c.engines[0];$('device').value=e.device;$('languages').value=e.languages.join(',');$('threads').value=e.threads;$('engine-options').value=JSON.stringify(e.options);
  c.engines.forEach(e=>{
    if(!e.python_path)return;
    const info=system.engines.find(x=>x.id===e.engine), key=e.engine+(e.device==='gpu'?'-gpu':'');
    const normalized=p=>String(p||'').replaceAll('\\','/').toLowerCase();
    // Old GPU runs stored the automatically selected CPU interpreter. Loading
    // their setup should discover the newly provisioned GPU environment.
    if(e.device==='gpu'&&[info?.python_path,system.interpreter].filter(Boolean).some(p=>normalized(p)===normalized(e.python_path))){
      if(normalized(envs[key])===normalized(e.python_path))delete envs[key];
    }else envs[key]=e.python_path;
  });saveEnvs();$('all-samples').checked=c.samples.length>1;refreshDeviceOptions();
}
function renderEnvironments(){
  $('environment-list').innerHTML=system.engines.map(e=>`<section class="panel environment-card"><h3>${names[e.id]} <span class="badge ${e.installed?'success':'warning'}">${e.installed?'Installed in app environment':'Optional environment'}</span></h3><p>${e.id==='rapidocr'?'ONNX Runtime · CPU or CUDA. Record model ancestry when comparing with PaddleOCR.':e.id==='paddleocr'?'PaddlePaddle · CPU or CUDA. Configure one language/model per candidate.':e.id==='easyocr'?'PyTorch · CPU or CUDA. Compatible multilingual combinations depend on the model.':'Native Tesseract executable required, plus pytesseract. CPU baseline.'}</p><label>Python interpreter (leave blank to use app environment)<input data-env="${e.id}" value="${esc(envs[e.id]||'')}" placeholder="${esc(e.environment)}" spellcheck="false"></label><p>Create with <code>.\scripts\setup-engine.ps1 -Engine ${e.id} -Python C:\path\to\python.exe</code></p></section>`).join('');
  system.engines.forEach(e=>{
    const input=document.querySelector(`[data-env="${e.id}"]`), label=input.parentElement, card=label.parentElement;
    label.firstChild.textContent='CPU / shared Python interpreter (blank uses automatic selection)';
    input.placeholder=e.python_path||system.interpreter;
    card.querySelector('.badge').textContent=e.installed?'Installed · preflight required':'Optional environment';
    if(e.gpu){
      const gpuLabel=document.createElement('label');gpuLabel.style.marginTop='14px';
      gpuLabel.innerHTML=`GPU Python interpreter (blank uses automatic selection)<input data-env="${e.id}-gpu" value="${esc(envs[e.id+'-gpu']||'')}" placeholder="${esc(e.gpu_python_path||'No dedicated GPU environment detected')}" spellcheck="false">`;
      label.insertAdjacentElement('afterend',gpuLabel);
      const hint=document.createElement('p');hint.textContent=e.gpu_python_path?'Dedicated GPU environment detected. GPU runs select it automatically unless overridden.':'GPU runs require a CUDA-enabled runtime.';
      gpuLabel.insertAdjacentElement('afterend',hint);
    }
    card.lastElementChild.innerHTML=`Create with <code>${esc(String.raw`.\scripts\setup-engine.ps1 -Engine ${e.id} -Python C:\path\to\python.exe`)}</code>${e.gpu?' (add <code>-Device gpu</code> for CUDA)':''}`;
  });
  document.querySelectorAll('[data-env]').forEach(input=>input.onchange=()=>{envs[input.dataset.env]=input.value.trim();saveEnvs();renderEngines();toast('Interpreter path saved')});
}
function saveEnvs(){localStorage.setItem('ocrbench-environments',JSON.stringify(envs))}
async function uploadFiles(){
  const files=[...$('upload-input').files];if(!files.length)return;
  let last;for(const file of files){const form=new FormData();form.append('file',file);last=await api('/samples',{method:'POST',body:form})}
  samples=await api('/samples');sampleId=last.id;renderSamples();$('upload-input').value='';toast(`${files.length} image${files.length>1?'s':''} imported`);
}
function openAnnotation(){
  const s=currentSample();if(!s)return;
  annotationDraft=structuredClone(s.annotation);annotationJsonMode=false;pendingPolygon=null;
  $('ann-reviewed').checked=annotationDraft.reviewed;$('ann-complete').checked=annotationDraft.complete;
  $('annotation-image').src=s.url;$('annotation-image').parentElement.style.aspectRatio=`${s.width}/${s.height}`;
  $('ann-error').textContent='';$('new-region').classList.add('hidden');
  setAnnotationMode(false);renderAnnotation();$('annotation-dialog').showModal();
}
function renderAnnotation(){
  const s=currentSample();$('annotation-overlay').setAttribute('viewBox',`0 0 ${s.width} ${s.height}`);
  $('annotation-overlay').innerHTML=annotationDraft.regions.map((r,i)=>`<polygon points="${r.polygon.map(p=>p.join(',')).join(' ')}"><title>${i+1}: ${esc(r.text)}</title></polygon>`).join('');
  $('annotation-rows').innerHTML=annotationDraft.regions.map((r,i)=>`<div class="annotation-row"><span>${i+1}</span><input data-ann-text="${i}" aria-label="Text region ${i+1}" value="${esc(r.text)}"><button data-ann-remove="${i}" aria-label="Remove region ${i+1}">×</button></div>`).join('');
  document.querySelectorAll('[data-ann-text]').forEach(e=>e.oninput=()=>annotationDraft.regions[Number(e.dataset.annText)].text=e.value);
  document.querySelectorAll('[data-ann-remove]').forEach(e=>e.onclick=()=>{annotationDraft.regions.splice(Number(e.dataset.annRemove),1);renderAnnotation()});
  $('annotation-json').value=JSON.stringify(annotationDraft,null,2);
}
function setAnnotationMode(json){
  if(annotationJsonMode&&!json){try{annotationDraft=JSON.parse($('annotation-json').value);if(!Array.isArray(annotationDraft.regions))throw Error('regions must be an array');renderAnnotation()}catch(e){toast('Invalid annotation JSON: '+e.message,true);return}}
  if(json&&!annotationJsonMode)$('annotation-json').value=JSON.stringify(annotationDraft,null,2);
  annotationJsonMode=json;$('annotation-rows').classList.toggle('hidden',json);$('annotation-json').classList.toggle('hidden',!json);
  $('ann-json-button').classList.toggle('selected',json);$('ann-table-button').classList.toggle('selected',!json);
}
function sourcePoint(e){const rect=$('annotation-overlay').getBoundingClientRect(),s=currentSample();return [Math.max(0,Math.min(s.width,(e.clientX-rect.left)/rect.width*s.width)),Math.max(0,Math.min(s.height,(e.clientY-rect.top)/rect.height*s.height))]}
$('annotation-overlay').addEventListener('pointerdown',e=>{if(annotationJsonMode){toast('Switch to Text regions to draw a region');return}dragStart=sourcePoint(e);$('annotation-overlay').setPointerCapture(e.pointerId)});
$('annotation-overlay').addEventListener('pointermove',e=>{if(!dragStart)return;const p=sourcePoint(e);let preview=$('drag-preview');if(!preview){preview=document.createElementNS('http://www.w3.org/2000/svg','rect');preview.id='drag-preview';preview.style.stroke='#f5d093';$('annotation-overlay').append(preview)}preview.setAttribute('x',Math.min(dragStart[0],p[0]));preview.setAttribute('y',Math.min(dragStart[1],p[1]));preview.setAttribute('width',Math.abs(p[0]-dragStart[0]));preview.setAttribute('height',Math.abs(p[1]-dragStart[1]))});
$('annotation-overlay').addEventListener('pointerup',e=>{if(!dragStart)return;const p=sourcePoint(e);let [x,y]=dragStart;dragStart=null;const l=Math.round(Math.min(x,p[0])),t=Math.round(Math.min(y,p[1])),r=Math.round(Math.max(x,p[0])),b=Math.round(Math.max(y,p[1]));if(r-l<3||b-t<3){$('drag-preview')?.remove();return}pendingPolygon=[[l,t],[r,t],[r,b],[l,b]];$('new-region').classList.remove('hidden');$('new-region-text').value='';$('new-region-text').focus()});
$('add-region').onclick=()=>{if(!pendingPolygon)return;annotationDraft.regions.push({text:$('new-region-text').value,polygon:pendingPolygon,language:$('languages').value.split(',')[0]||'en',ignore:false});pendingPolygon=null;$('new-region').classList.add('hidden');renderAnnotation()};
$('save-annotation').onclick=async()=>{try{if(annotationJsonMode)annotationDraft=JSON.parse($('annotation-json').value);annotationDraft.reviewed=$('ann-reviewed').checked;annotationDraft.complete=$('ann-complete').checked;await api('/samples/'+sampleId+'/annotation',{method:'PUT',body:JSON.stringify(annotationDraft)});samples=await api('/samples');renderSamples();$('annotation-dialog').close();toast('Annotations saved. Start a new run to use this ground truth.')}catch(e){$('ann-error').textContent=e.message}};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>showView(b.dataset.view));
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>setMode(b.dataset.mode));
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{evidenceTab=b.dataset.tab;renderEvidence()});
$('sample-select').onchange=e=>{if(currentRun?.config.mode==='live'){followLive=false;$('follow-live').checked=false}selectSample(e.target.value)};$('show-boxes').onchange=renderOverlay;$('fit-button').onclick=()=>highlightPrediction(-1);
$('follow-live').onchange=e=>{followLive=e.target.checked;if(followLive)frameIndex=Math.max(0,(currentCandidate()?.records.length||0)-1);renderRun()};
$('previous-camera-frame').onclick=()=>chooseCameraFrame(frameIndex-1);
$('next-camera-frame').onclick=()=>chooseCameraFrame(frameIndex+1);
$('show-labels').onchange=renderOverlay;new ResizeObserver(()=>renderOverlay()).observe($('image-stage'));
for(const id of ['history-engine','history-device','history-completed'])$(id).onchange=renderHistory;
$('compare-selected').onclick=()=>{historyCompare=!historyCompare;renderHistory()};
$('clear-comparison').onclick=()=>{historySelected.clear();historyCompare=false;historySort={key:'created',direction:-1};$('history-engine').value='';$('history-device').value='';$('history-completed').checked=false;renderHistory()};
$('device').onchange=refreshDeviceOptions;
$('run-button').onclick=guard(startRun);$('cancel-button').onclick=guard(async()=>{await api('/runs/'+currentRun.id+'/cancel',{method:'POST'});toast('Stopping worker and capture')});
$('candidate-select').onchange=e=>{candidateIndex=Number(e.target.value);frameIndex=0;renderRun()};
$('frame-select').onchange=async e=>{frameIndex=Number(e.target.value);const r=currentRecord();if(currentRun?.config.mode==='live'){chooseCameraFrame(frameIndex);return}if(r&&!samples.some(s=>s.id===r.sample_id)){samples=await api('/samples');renderSamples()}if(r&&samples.some(s=>s.id===r.sample_id))selectSample(r.sample_id);renderRun()};
for(const id of ['import-button','dataset-import'])$(id).onclick=()=>$('upload-input').click();$('upload-input').onchange=guard(uploadFiles);
$('export-toggle').onclick=()=>$('export-menu').classList.toggle('hidden');document.addEventListener('click',e=>{if(!e.target.closest('.export-wrap'))$('export-menu').classList.add('hidden')});
$('annotate-button').onclick=openAnnotation;$('annotation-state').onclick=openAnnotation;$('close-annotation').onclick=()=>$('annotation-dialog').close();$('ann-table-button').onclick=()=>setAnnotationMode(false);$('ann-json-button').onclick=()=>setAnnotationMode(true);$('refresh-history').onclick=guard(refreshHistory);
guard(init)();

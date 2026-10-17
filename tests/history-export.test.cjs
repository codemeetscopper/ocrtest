const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../ocrbench/static/app.js'),'utf8');
const code=app.slice(app.indexOf('async function refreshHistory()'),app.indexOf('function applyConfig('));
function fixture(){
  const elements=new Map(),downloads=[],requests=[];
  const config={samples:['pivi-pro'],mode:'saved',preprocessing:'raw',track:'full',repetitions:5,warmups:1};
  const engine=(name,device,p95)=>({config:{engine:name,device,languages:['en'],threads:2},status:'completed',summary:{latency_ms:{p95}}});
  const c={runs:[{id:'aaaaaaaaaaaa',created_at:'2026-10-15',config,candidates:[engine('rapidocr','cpu',20),engine('easyocr','gpu',10)]},
                 {id:'bbbbbbbbbbbb',created_at:'2026-10-16',config,candidates:[engine('rapidocr','cpu',30)]}],
    historySelected:new Set(),historyCompare:false,historySort:{key:'p95',direction:1},
    historyAllRows:[],historyVisibleRows:[],historyExportBusy:false,
    names:{rapidocr:'RapidOCR',easyocr:'EasyOCR'},fmt:String,pct:String,esc:String,
    tesseractBinding:()=>'',decorateTerms:()=>{},toast:()=>{},
    $:id=>{if(!elements.has(id))elements.set(id,{value:'',checked:false,disabled:false});return elements.get(id)},
    document:{querySelectorAll:()=>[],createElement:()=>({click(){downloads.push(this.download)},remove(){}}),body:{appendChild(){}}},
    URL:{createObjectURL:()=> 'blob:history',revokeObjectURL:()=>{}},setTimeout:fn=>fn(),
    fetch:async(url,options)=>{requests.push({url,options});return {ok:true,headers:{get:()=> 'attachment; filename="history.xlsx"'},blob:async()=>({})}}
  };
  c.$('history-export-scope').value='visible';
  vm.createContext(c);vm.runInContext(code,c);
  return {c,requests,downloads};
}
function refs(c){return JSON.parse(JSON.stringify(c.historyExportRows().map(({r,index})=>[r.id,index])))}
test('visible export respects filters, comparison selection and sort order',()=>{
  const {c}=fixture();c.renderHistory();
  assert.deepEqual(refs(c),[['aaaaaaaaaaaa',1],['aaaaaaaaaaaa',0],['bbbbbbbbbbbb',0]]);
  c.$('history-device').value='cpu';c.renderHistory();
  assert.deepEqual(refs(c),[['aaaaaaaaaaaa',0],['bbbbbbbbbbbb',0]]);
  c.historySelected=new Set(['aaaaaaaaaaaa','bbbbbbbbbbbb']);c.historyCompare=true;c.renderHistory();
  assert.equal(c.historyExportRows().length,2);
});
test('selected-run export includes hidden engines and supports a single selected run',()=>{
  const {c}=fixture();c.$('history-device').value='cpu';
  c.historySelected.add('aaaaaaaaaaaa');c.$('history-export-scope').value='selected';c.renderHistory();
  assert.deepEqual(refs(c),[['aaaaaaaaaaaa',1],['aaaaaaaaaaaa',0]]);
  assert.equal(c.$('history-export-csv').disabled,false);
  c.historySelected.clear();c.updateHistoryExport();
  assert.equal(c.$('history-export-csv').disabled,true);
});
test('download sends ordered references with the local header and clears busy state',async()=>{
  const {c,requests,downloads}=fixture();c.renderHistory();await c.exportHistory('xlsx');
  assert.equal(requests[0].url,'/api/history/export/xlsx');
  assert.equal(requests[0].options.headers['X-OCRBench'],'local');
  assert.deepEqual(JSON.parse(requests[0].options.body).rows,[
    {run_id:'aaaaaaaaaaaa',candidate_index:1},{run_id:'aaaaaaaaaaaa',candidate_index:0},{run_id:'bbbbbbbbbbbb',candidate_index:0}]);
  assert.deepEqual(downloads,['history.xlsx']);assert.equal(c.historyExportBusy,false);
});
test('a failed export reports the server error and restores controls',async()=>{
  const {c}=fixture();c.renderHistory();c.fetch=async()=>({ok:false,json:async()=>({detail:'Refresh history and retry.'})});
  await assert.rejects(c.exportHistory('csv'),/Refresh history/);
  assert.equal(c.historyExportBusy,false);assert.equal(c.$('history-export-xlsx').disabled,false);
});

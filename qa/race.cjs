/* Browser-only controlled fixtures. Never writes or publishes synthetic prices. */
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const gate=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve}};
const bounded=(promise)=>{let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Controlled request did not reach expected boundary')),20000)})]).finally(()=>clearTimeout(timer))};
let browser;
(async()=>{
 const base=(process.argv[2]||'http://127.0.0.1:4173/').replace(/\/?$/,'/');
 const real=await (await fetch(base+'data/history/us-spy.json')).json();
 const expected=((real.bars.at(-1).close/real.bars[0].close-1)*100).toFixed(2);
 browser=await chromium.launch({channel:'msedge',headless:true});
 const results=[];
 for(const lateError of [false,true]){
  const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'});
  const p=await context.newPage();
  const started=gate(),release=gate(),settled=gate();let requests=0;
  await p.route('**/data/history/us-spy.json*',async route=>{
   requests++;
   if(requests===1){started.resolve();await release.promise;try{if(lateError){await route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:'deliberately stale test failure'})})}else{const fixture=structuredClone(real);for(const key of ['open','high','low','close'])if(fixture.bars[0][key]!=null)fixture.bars[0][key]*=2;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(fixture),headers:{'Cache-Control':'no-store'}})}}catch{/* Abort is also a valid ownership barrier. */}finally{settled.resolve()}return;}
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(real),headers:{'Cache-Control':'no-store'}});
  });
  await p.goto(base,{waitUntil:'networkidle'});await p.getByLabel('Country',{exact:true}).waitFor();
  await p.getByLabel('Chart period ALL',{exact:true}).click();
  await p.getByLabel('Compare SPY',{exact:true}).check();await bounded(started.promise);
  await p.getByLabel('Compare SPY',{exact:true}).uncheck();await p.getByLabel('Compare VHY.AX',{exact:true}).check();await p.getByTestId('comparison-end-au-vhy').waitFor({timeout:60000});
  await p.getByLabel('Compare VHY.AX',{exact:true}).uncheck();await p.getByLabel('Compare SPY',{exact:true}).check();
  await p.getByTestId('comparison-end-us-spy').waitFor({timeout:60000});assert.equal(await p.getByTestId('comparison-end-us-spy').innerText(),'+'+expected+'%');
  release.resolve();await bounded(settled.promise);
  assert.equal(await p.getByTestId('comparison-end-us-spy').innerText(),'+'+expected+'%');assert.equal(await p.locator('[data-testid^="comparison-end-"]').count(),1);
  await p.getByLabel('Compare SPY',{exact:true}).uncheck();await p.getByLabel('Compare SPY',{exact:true}).check();await p.getByTestId('comparison-end-us-spy').waitFor();
  assert.equal(await p.getByTestId('comparison-end-us-spy').innerText(),'+'+expected+'%');assert.equal(requests,2,'stale response must not poison cache or trigger a third fetch');assert.equal(p.url(),base);
  results.push({scenario:lateError?'A→B→A late rejection':'A→B→A late distinguishable payload',requests,cacheReopen:'newest',passed:true});await context.close();
 }
 const context=await browser.newContext({serviceWorkers:'block'}),p=await context.newPage();await p.route('**/data/market.json*',r=>r.fulfill({status:503,body:'deliberate initial-load failure'}));await p.goto(base,{waitUntil:'networkidle'});await p.getByRole('alert').waitFor();assert.equal(await p.getByLabel('Country',{exact:true}).count(),0);assert(await p.getByLabel('Retry market data',{exact:true}).count());await context.close();
 console.log(JSON.stringify({browserRaces:'PASS',fixtures:'isolated test context only; real published dataset unchanged',results,initialFailureGated:true},null,2));await browser.close();
})().catch(async e=>{console.error(e);await browser?.close();process.exitCode=1});

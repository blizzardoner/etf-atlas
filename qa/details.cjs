/* Real downloads, dividend details and chart zoom acceptance in Edge. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');let browser;
(async()=>{
 const base=(process.argv[2]||'http://127.0.0.1:4173/').replace(/\/?$/,'/');
 const market=await (await fetch(base+'data/market.json')).json();
 const out=path.resolve('artifacts');fs.mkdirSync(out,{recursive:true});browser=await chromium.launch({channel:'msedge',headless:true});
 const p=await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});await p.goto(base,{waitUntil:'networkidle'});await p.getByLabel('Country',{exact:true}).waitFor();
 const downloads=[];
 for(const id of ['au-vhy','cn-510500','us-index-gspc']){
  const item=market.instruments.find(i=>i.id===id),real=await (await fetch(base+item.historyUrl)).json();
  await p.getByLabel('Details '+item.symbol,{exact:true}).click();await p.getByRole('dialog').waitFor();
  const received=p.waitForEvent('download',{timeout:60000});await p.getByLabel('Download full history JSON',{exact:true}).click();const download=await received;
  const file=path.join(out,id+'-browser-download.json');await download.saveAs(file);const actual=JSON.parse(fs.readFileSync(file,'utf8'));assert.deepEqual(actual,real,'download must contain complete original history and provenance');
  assert.equal(await p.getByRole('dialog').locator('.dividend-table tbody tr').count(),real.dividends?.length??0);
  if(id==='au-vhy'){assert((await p.getByRole('dialog').innerText()).includes('抵税比例未知'));await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(out,'iphone-dividends.png'),fullPage:false});assert(await p.getByRole('dialog').evaluate(e=>e.scrollWidth<=e.clientWidth));await p.setViewportSize({width:1440,height:1000});}
  if(id==='cn-510500')assert(actual.bars.some(b=>b.rawClose!==b.close),'post-listing split history must preserve nominal prices');
  if(id==='us-index-gspc')assert(actual.bars[0].date<'1970-01-01','all available index history cannot be epoch truncated');
  await p.keyboard.press('Escape');assert.equal(await p.getByRole('dialog').count(),0);downloads.push({id,bars:actual.bars.length,dividends:actual.dividends?.length??null,first:actual.bars[0].date});
 }
 await p.getByLabel('Compare SPY',{exact:true}).check();await p.getByTestId('comparison-end-us-spy').waitFor({timeout:60000});
 const selector='[aria-label="Performance comparison chart"] .chart-container svg text';
 await p.locator(selector).first().waitFor({state:'visible'});
 const initial=await p.locator(selector).evaluateAll(es=>JSON.stringify(es.map(e=>e.textContent).sort()));await p.getByLabel('Zoom in',{exact:true}).click();
 await p.waitForFunction(({selector,initial})=>JSON.stringify(Array.from(document.querySelectorAll(selector)).map(e=>e.textContent).sort())!==initial,{selector,initial});
 await p.getByLabel('Reset zoom',{exact:true}).click();await p.waitForFunction(({selector,initial})=>JSON.stringify(Array.from(document.querySelectorAll(selector)).map(e=>e.textContent).sort())===initial,{selector,initial});
 await p.setViewportSize({width:390,height:844});
 const targets=await p.evaluate(()=>({smallCheckboxLabels:Array.from(document.querySelectorAll('input[type=checkbox]')).map(e=>e.closest('label')).filter(Boolean).filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.width<43||r.height<43)}).map(e=>e.textContent),smallInputFonts:Array.from(document.querySelectorAll('input:not([type=checkbox]),select')).filter(e=>parseFloat(getComputedStyle(e).fontSize)<16).map(e=>e.getAttribute('aria-label'))}));
 assert.deepEqual(targets.smallCheckboxLabels,[]);assert.deepEqual(targets.smallInputFonts,[]);
 console.log(JSON.stringify({detailsAndDownloads:'PASS',downloads,zoom:true,resetZoom:true,touchTargets:targets},null,2));await browser.close();
})().catch(async e=>{console.error(e);await browser?.close();process.exitCode=1});

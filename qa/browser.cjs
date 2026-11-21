/* Black-box functional acceptance using real deployed data and Microsoft Edge. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
let browser;
(async()=>{
 const base=(process.argv[2]||'http://127.0.0.1:4173/').replace(/\/?$/,'/');
 const market=await (await fetch(base+'data/market.json')).json();
 const out=path.resolve('artifacts');fs.mkdirSync(out,{recursive:true});
 const b=await chromium.launch({channel:'msedge',headless:true});
 browser=b;
 const context=await b.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});
 const p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(base,{waitUntil:'networkidle',timeout:90000});
 await p.getByLabel('Country',{exact:true}).waitFor();
 const country=p.getByLabel('Country',{exact:true}),kind=p.getByLabel('Instrument kind',{exact:true});
 const sort=p.getByLabel('Ranking period',{exact:true});
 const symbols=()=>p.locator('tbody tr input[type=checkbox]').evaluateAll(es=>es.map(e=>e.getAttribute('aria-label').replace(/^Compare /,'')));
 const sortItems=(items,key,mode,direction)=>[...items].sort((a,b)=>{const av=key==='cashYield'?a.cashYield:a.returns[mode][key],bv=key==='cashYield'?b.cashYield:b.returns[mode][key];if(av==null&&bv==null)return a.symbol.localeCompare(b.symbol);if(av==null)return 1;if(bv==null)return -1;return (av-bv)*(direction==='desc'?-1:1)||a.symbol.localeCompare(b.symbol)}).map(i=>i.symbol);
 for(const c of ['CN','US','AU']){await country.selectOption(c);assert.deepEqual(new Set(await symbols()),new Set(market.instruments.filter(i=>i.country===c).map(i=>i.symbol)));}
 await country.selectOption('all');await kind.selectOption('etf');assert.equal((await symbols()).length,market.instruments.filter(i=>i.kind==='etf').length);await kind.selectOption('all');
 const periods=['1m','3m','6m','1y','3y','5y','10y'];
 for(const period of periods){await sort.selectOption(period);if(await p.getByLabel('Sort descending',{exact:true}).count())await p.getByLabel('Sort descending',{exact:true}).click();assert.deepEqual(await symbols(),sortItems(market.instruments,period,'price','desc'),period+' desc');await p.getByLabel('Sort ascending',{exact:true}).click();assert.deepEqual(await symbols(),sortItems(market.instruments,period,'price','asc'),period+' asc');}
 const min=p.getByLabel('Minimum cash yield (%)',{exact:true}),max=p.getByLabel('Maximum cash yield (%)',{exact:true});await min.fill('3');await max.fill('6');await sort.selectOption('cashYield');
 if(await p.getByLabel('Sort descending',{exact:true}).count())await p.getByLabel('Sort descending',{exact:true}).click();
 const filtered=market.instruments.filter(i=>i.cashYield!==null&&i.cashYield>=.03&&i.cashYield<=.06);assert.deepEqual(await symbols(),sortItems(filtered,'cashYield','price','desc'));
 await min.fill('');await max.fill('');
 const chosen=['cn-510300','us-spy','au-vhy'].map(id=>market.instruments.find(i=>i.id===id));assert(chosen.every(Boolean));
 for(const item of chosen)await p.getByLabel('Compare '+item.symbol,{exact:true}).check();
 await p.getByTestId('comparison-end-us-spy').waitFor({timeout:90000});
 assert.equal(await p.locator('[data-testid^="comparison-end-"]').count(),3);
 assert(await p.locator('[aria-label="Performance comparison chart"] canvas,[aria-label="Performance comparison chart"] svg').count(),'real chart renderer missing');
 for(const period of [...periods,'all']){await p.getByLabel('Chart period '+period.toUpperCase(),{exact:true}).click();await p.getByTestId('comparison-end-us-spy').waitFor();assert.equal(await p.getByLabel('Chart period '+period.toUpperCase(),{exact:true}).getAttribute('aria-pressed'),'true');}
 await p.getByLabel('Chart period 1Y',{exact:true}).click();
 await p.screenshot({path:path.join(out,'desktop-functional.png'),fullPage:true});
 await p.locator('[aria-label="Return basis"] button').nth(1).click();
 await p.locator('#comparison [role="alert"]').waitFor();
 assert.equal(await p.locator('[data-testid^="comparison-end-"]').count(),0,'unknown CN total return must not become a partial or guessed chart');
 await p.getByLabel('Remove 510300 from comparison',{exact:true}).click();
 await p.getByTestId('comparison-end-us-spy').waitFor();assert.equal(await p.locator('[data-testid^="comparison-end-"]').count(),2);
 for(const period of periods){await sort.selectOption(period);if(await p.getByLabel('Sort descending',{exact:true}).count())await p.getByLabel('Sort descending',{exact:true}).click();assert.deepEqual(await symbols(),sortItems(market.instruments,period,'total','desc'),period+' total desc');await p.getByLabel('Sort ascending',{exact:true}).click();assert.deepEqual(await symbols(),sortItems(market.instruments,period,'total','asc'),period+' total asc');}
 await p.reload({waitUntil:'networkidle'});await p.getByTestId('comparison-end-us-spy').waitFor();assert(await p.getByLabel('Compare SPY',{exact:true}).isChecked());assert(await p.getByLabel('Compare VHY.AX',{exact:true}).isChecked());
 for(const width of [320,390,768]){await p.setViewportSize({width,height:844});await p.screenshot({path:path.join(out,'mobile-'+width+'.png'),fullPage:true});const sizes=await p.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert(sizes.scroll<=sizes.width,'page horizontal overflow '+width);}
 await p.setViewportSize({width:390,height:844});
 const worker=await p.evaluate(async()=>{if(!('serviceWorker' in navigator))return false;await Promise.race([navigator.serviceWorker.ready,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Service worker readiness timeout')),15000))]);return !!navigator.serviceWorker.controller});
 assert(worker,'production service worker not controlling page');
 await context.setOffline(true);await p.reload({waitUntil:'networkidle'});await p.getByTestId('comparison-end-us-spy').waitFor({timeout:30000});assert.equal(await p.locator('tbody tr').count(),market.instruments.length);await context.setOffline(false);
 assert.deepEqual(errors,[],'browser runtime errors');
 console.log(JSON.stringify({acceptance:'PASS',base,instruments:market.instruments.length,rankings:periods,countryFilters:['CN','US','AU'],yieldRange:[3,6],multichart:chosen.map(i=>i.symbol),totalMode:true,persistence:true,offline:true,mobileWidths:[320,390,768],errors},null,2));
 await b.close();
})().catch(async e=>{console.error(e);await browser?.close();process.exitCode=1});

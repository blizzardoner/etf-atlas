/* Real Edge browser inspection; PLAYWRIGHT_MODULE may point at a local install. */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const base = process.argv[2] || 'http://127.0.0.1:4173/';
  const out = path.resolve('artifacts');
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(base, { waitUntil: 'networkidle', timeout: 90000 });
  await page.screenshot({ path: path.join(out, 'desktop.png'), fullPage: true });
  const inspection = await page.evaluate(() => ({ title: document.title, text: document.body.innerText.slice(0, 12000), controls: Array.from(document.querySelectorAll('button,input,select')).map(e => ({ tag: e.tagName, text: e.textContent, label: e.getAttribute('aria-label'), type: e.getAttribute('type'), value: e.value })) }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(out, 'iphone.png'), fullPage: true });
  const mobile = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, smallTargets: Array.from(document.querySelectorAll('button,input:not([type=checkbox]),select')).filter(e => {const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&(r.height<43||r.width<43)}).map(e => ({ text: e.textContent, label:e.getAttribute('aria-label'), width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height })) }));
  console.log(JSON.stringify({base, errors, inspection, mobile}, null, 2));
  await browser.close();
  if (errors.length || mobile.scrollWidth > mobile.width) process.exitCode = 1;
})().catch(e => { console.error(e); process.exitCode = 1; });

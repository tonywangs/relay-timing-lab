/* Optional validation dependency: Playwright 1.56.1 + Chromium 141. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');
(async () => {
  const report = path.resolve(process.argv[2] || 'results/evaluation/report.html');
  const browser = await chromium.launch({headless:true,args:['--disable-background-networking','--no-sandbox']});
  try {
    const context = await browser.newContext({offline:true});
    let requests = [], errors = [];
    await context.route('**/*',route=>{const url=route.request().url();if(url.startsWith('file:'))return route.continue();requests.push(url);return route.abort();});
    const page = await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(pathToFileURL(report).href);
    await page.locator('#aggregate tbody tr').first().waitFor();
    const data = await page.locator('#data').textContent().then(JSON.parse);
    const count = Math.min(50,data.rows.length);
    assert.equal(await page.locator('#trials tbody tr').count(),count);
    assert.equal(await page.locator('#aggregate tbody tr').count(),Math.min(100,data.groups.length));
    await page.selectOption('#family',data.rows[0].family);
    await page.selectOption('#candidates',String(data.rows[0].candidates));
    await page.selectOption('#policy','padded');
    const expected = data.rows.filter(r=>r.family===data.rows[0].family && r.candidates===data.rows[0].candidates && r.policy==='padded');
    assert.equal(await page.locator('#trials tbody tr').count(),Math.min(50,expected.length));
    const cells=await page.locator('#trials tbody tr').first().locator('td').allTextContents();
    assert.equal(Number(cells[4]),Number(expected[0].top1.toFixed(3)));
    assert.equal(Number(cells[9].replaceAll(',','')),expected[0].transmitted_bytes);
    const aggregate = data.groups.find(r=>r.family===data.rows[0].family && r.candidates===data.rows[0].candidates && r.policy==='padded');
    const agCells=await page.locator('#aggregate tbody tr').first().locator('td').allTextContents();
    assert.ok(agCells[1].startsWith(aggregate.metrics.top1.mean.toLocaleString('en-US',{maximumFractionDigits:3})));
    // Native selects and buttons work entirely from keyboard.
    await page.locator('#reset').focus();await page.keyboard.press('Enter');
    assert.equal(await page.locator('#family').inputValue(),'');
    await page.locator('#family').focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
    assert.equal(await page.locator('#family').inputValue(),data.rows[0].family);
    await page.locator('#reset').focus();await page.keyboard.press('Space');
    if(data.rows.length>50){await page.locator('#next').focus();await page.keyboard.press('Enter');assert.ok((await page.locator('#page').textContent()).startsWith('Page 2'));await page.locator('#prev').focus();await page.keyboard.press('Enter');}
    // Construct hostile labels and an oversized row set in a local copy of the
    // real report. Escape data as the Python renderer does; no HTTP is used.
    const hostile='</script><img src="https://example.invalid/leak" onerror="globalThis.pwned=1">';
    const large=structuredClone(data);large.rows=Array.from({length:12000},(_,i)=>({...data.rows[i%data.rows.length],family:hostile}));
    large.groups=Array.from({length:120},()=>({...data.groups[0],family:hostile}));large.paired=Array.from({length:120},()=>({...data.paired[0],family:hostile}));
    const code='import json,sys; sys.path.insert(0,sys.argv[1]); from relay_timing_lab.report import render; print(render(json.load(sys.stdin)))';
    const html=require('node:child_process').execFileSync('python3',['-c',code,path.resolve(__dirname,'../src')],{input:JSON.stringify(large),encoding:'utf8',maxBuffer:32*1024*1024});
    await page.goto('about:blank');
    await page.setContent(html);
    assert.equal(await page.locator('#trials tbody tr').count(),50);
    assert.equal(await page.locator('#aggregate tbody tr').count(),100);
    assert.equal(await page.locator('#paired tbody tr').count(),100);
    assert.equal(await page.locator('.bar-row').count(),90);
    assert.ok((await page.locator('#trials tbody tr').first().textContent()).includes(hostile));
    assert.equal(await page.locator('img').count(),0);
    assert.equal(await page.evaluate(()=>globalThis.pwned),undefined);
    assert.deepEqual(errors,[]);
    assert.deepEqual(requests,[]);
    console.log(JSON.stringify({status:'passed',browser:await browser.version(),playwright:require('playwright/package.json').version,network:'offline + abort all requests; zero requests observed',checks:['filters','numeric tables','keyboard selects/buttons','pagination','hostile labels','12000-row bounded rendering'],report},null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

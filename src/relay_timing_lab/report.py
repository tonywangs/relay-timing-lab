"""Self-contained report; no external assets, bounded DOM, no label HTML parsing."""
import json


def render(summary):
    # JSON embedded as inert data. Escape HTML delimiter even for hostile labels.
    data = json.dumps(summary, sort_keys=True, separators=(',', ':'), allow_nan=False)
    data = data.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    return TEMPLATE.replace('__DATA__', data)


TEMPLATE = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>Relay timing lab · frozen synthetic experiment</title>
<style>
:root{color-scheme:light;--ink:#142a38;--muted:#4d6371;--line:#ced8dc;--accent:#126e72}
*{box-sizing:border-box}body{margin:0;background:#f4f6f5;color:var(--ink);font:16px/1.6 system-ui,sans-serif}
main{max-width:1260px;margin:auto;padding:38px 24px}h1{font-size:clamp(28px,4vw,48px);line-height:1.15;margin:12px 0}
h2{font-size:22px;margin-top:32px}.eyebrow{font-weight:750;text-transform:uppercase;letter-spacing:.14em;color:var(--accent);font-size:12px}
p{max-width:850px}.muted{color:var(--muted)}.notice{border-left:4px solid #b36523;background:#fff4e7;padding:14px 20px}
.controls{display:flex;gap:18px;flex-wrap:wrap;margin:24px 0}label{display:flex;flex-direction:column;font-size:14px;font-weight:650}
select,button{font:inherit;border:1px solid #879da6;background:white;border-radius:5px;padding:8px 12px;color:var(--ink)}
button{cursor:pointer}button:disabled{opacity:.45;cursor:default}:focus-visible{outline:3px solid #0a858d;outline-offset:3px}
.table-wrap{overflow:auto;border:1px solid var(--line);background:white}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:10px 12px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}th:first-child,td:first-child{text-align:left}
th{background:#e8efef}caption{text-align:left;padding:12px;font-weight:650}.plots{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px}
.card{border:1px solid var(--line);background:white;padding:18px}.bar-row{display:grid;grid-template-columns:100px 1fr 70px;gap:8px;align-items:center;font-size:13px;margin:12px 0}
.track{background:#e8eeee;height:16px}.bar{height:100%;background:var(--accent)}.bar-row span:last-child{text-align:right}
code{overflow-wrap:anywhere;font-size:12px}footer{margin-top:40px;border-top:1px solid var(--line);padding-top:16px}.pager{display:flex;gap:16px;align-items:center;margin:15px 0}
</style></head><body><main>
<header><div class="eyebrow">Offline experiment / synthetic traffic</div><h1>What timing protection costs</h1>
<p class="muted">Compare immediate forwarding, bounded batching, and constant-rate padding under a passive observer who sees timestamps and wire sizes at both boundaries.</p></header>
<p class="notice"><strong>Matcher performance is not anonymity.</strong> These are synthetic, independently shaped, one-way streams with synchronized clocks. Fixed-rate candidates have identical observed schedules by construction. This is not a Tor evaluation or a secure communication protocol.</p>
<p id="provenance" class="muted"></p>
<div class="controls"><label>Traffic family<select id="family" aria-label="Traffic family"></select></label>
<label>Candidate set<select id="candidates" aria-label="Candidate set"></select></label>
<label>Policy<select id="policy" aria-label="Policy"></select></label><button id="reset">Reset filters</button></div>
<section aria-labelledby="trade-title"><h2 id="trade-title">Matching and cost</h2><p class="muted">Means across independent seeds; bars follow the current filters. Exact values and 95% bootstrap intervals appear below.</p><div id="plots" class="plots"></div></section>
<section><h2>Numeric results</h2><p class="muted">Latency is the mean of each run’s delivered-event quantile, not a pooled packet quantile. Byte ratio includes dummy and size padding. Dropped and queued events have no measured delivery delay.</p>
<div class="table-wrap"><table id="aggregate"><caption>Independent-run estimates, 95% percentile bootstrap intervals</caption><thead><tr><th>Family / candidates / policy</th><th>Top-one [95% CI]</th><th>Mean rank</th><th>p95 delay ms</th><th>Wire/input bytes</th><th>Wire bytes</th><th>Dummy bytes</th><th>Size pad bytes</th><th>Horizon backlog</th><th>Max queue/flow</th><th>Undelivered</th></tr></thead><tbody></tbody></table></div>
<h2>Paired changes from immediate forwarding</h2><p class="muted">Each difference uses the same traffic and seed. Intervals resample run differences, preserving pairing. These are descriptive intervals without multiple-comparison adjustment.</p>
<div class="table-wrap"><table id="paired"><caption>Policy minus immediate; same independent seeds</caption><thead><tr><th>Family / candidates / policy</th><th>Top-one change [95% CI]</th><th>p95 delay change ms [95% CI]</th><th>Byte ratio change [95% CI]</th></tr></thead><tbody></tbody></table></div></section>
<section><h2>Per-run measurements</h2><p id="count" aria-live="polite"></p><div class="table-wrap"><table id="trials"><caption>At most 50 rows per page</caption><thead><tr><th>Family</th><th>Seed</th><th>Candidates</th><th>Policy</th><th>Top-one</th><th>Rank</th><th>p50 ms</th><th>p95 ms</th><th>p99 ms</th><th>Wire bytes</th><th>Dummy bytes</th><th>Dropped</th><th>Queued</th></tr></thead><tbody></tbody></table></div>
<div class="pager"><button id="prev">Previous page</button><span id="page" aria-live="polite"></span><button id="next">Next page</button></div></section>
<footer><p>Observer: closed candidate set, exact clocks, full observation, no payloads or dummy labels. Matching uses normalized byte histograms, a frozen causal lag search, and exact L1 distance. Ties receive expected uniform top-one credit and midrank. Random-ranking is an analytical control; unmodified traces are a diagnostic control.</p>
<p>Generated inputs, raw event accounting, exact scores, hashes, and the protocol accompany this report. No network resources are required.</p><code id="hash"></code></footer>
</main><script type="application/json" id="data">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent);
const el=id=>document.getElementById(id);let page=0;const pageSize=50;
const fmt=x=>x===null||x===undefined?'—':Number(x).toLocaleString('en-US',{maximumFractionDigits:3});
const ci=x=>x?`${fmt(x.mean)} [${fmt(x.low)}, ${fmt(x.high)}]`:'—';
function options(id,values){const all=document.createElement('option');all.value='';all.textContent='All';el(id).append(all);for(const value of [...new Set(values)]){const o=document.createElement('option');o.value=String(value);o.textContent=String(value);el(id).append(o);}}
options('family',data.rows.map(r=>r.family));options('candidates',data.rows.map(r=>r.candidates));options('policy',data.rows.map(r=>r.policy));
function selected(r){return ['family','candidates','policy'].every(k=>!el(k).value||String(r[k])===el(k).value);}
function fill(id,rows){const body=el(id).querySelector('tbody');body.replaceChildren();for(const values of rows){const tr=document.createElement('tr');for(const v of values){const td=document.createElement('td');td.textContent=String(v);tr.append(td);}body.append(tr);}}
function label(r){return `${r.family} / ${r.candidates} / ${r.policy}`;}
function draw(){const groups=data.groups.filter(selected).slice(0,100);fill('aggregate',groups.map(r=>[label(r),ci(r.metrics.top1),fmt(r.metrics.rank.mean),fmt(r.metrics.delay_p95_ms.mean),fmt(r.metrics.byte_ratio.mean),fmt(r.metrics.transmitted_bytes.mean),fmt(r.metrics.dummy_bytes.mean),fmt(r.metrics.size_padding_bytes.mean),fmt(r.metrics.backlog_horizon.mean),fmt(r.metrics.max_backlog_per_flow.mean),fmt(r.metrics.undelivered.mean)]));
fill('paired',data.paired.filter(selected).slice(0,100).map(r=>[label(r),ci(r.metrics.top1),ci(r.metrics.delay_p95_ms),ci(r.metrics.byte_ratio)]));
const rows=data.rows.filter(selected);const pages=Math.max(1,Math.ceil(rows.length/pageSize));page=Math.min(page,pages-1);fill('trials',rows.slice(page*pageSize,(page+1)*pageSize).map(r=>[r.family,r.seed,r.candidates,r.policy,fmt(r.top1),fmt(r.rank),fmt(r.delay_p50_ms),fmt(r.delay_p95_ms),fmt(r.delay_p99_ms),fmt(r.transmitted_bytes),fmt(r.dummy_bytes),fmt(r.dropped),fmt(r.queued)]));el('count').textContent=`${rows.length} run-policy rows match. Aggregate tables are capped at 100 rows.`;el('page').textContent=`Page ${page+1} of ${pages}`;el('prev').disabled=page===0;el('next').disabled=page>=pages-1;
el('plots').replaceChildren();for(const [key,title] of [['top1','Top-one matching accuracy'],['delay_p95_ms','Delivered p95 delay (ms)'],['byte_ratio','Transmitted / input bytes']]){const card=document.createElement('div');card.className='card';const h=document.createElement('h3');h.textContent=title;card.append(h);const values=groups.slice(0,30);const max=key==='top1'?1:Math.max(1,...values.map(r=>r.metrics[key].mean||0));for(const r of values){const line=document.createElement('div');line.className='bar-row';line.title=label(r);const name=document.createElement('span');name.textContent=`${r.family} ${r.candidates} ${r.policy}`;const track=document.createElement('div');track.className='track';const bar=document.createElement('div');bar.className='bar';bar.style.width=`${Math.max(0,Math.min(100,100*(r.metrics[key].mean||0)/max))}%`;track.append(bar);const value=document.createElement('span');value.textContent=fmt(r.metrics[key].mean);line.append(name,track,value);card.append(line);}el('plots').append(card);}}
for(const id of ['family','candidates','policy'])el(id).addEventListener('change',()=>{page=0;draw();});el('reset').addEventListener('click',()=>{for(const id of ['family','candidates','policy'])el(id).value='';page=0;draw();});el('prev').addEventListener('click',()=>{page--;draw();});el('next').addEventListener('click',()=>{page++;draw();});
el('provenance').textContent=`${data.seeds.length} independent seeds per family/candidate setting · ${data.rows.length} run-policy rows · all times in milliseconds`;
el('hash').textContent=`Frozen protocol SHA-256: ${data.config_sha256}`;draw();
</script></body></html>'''

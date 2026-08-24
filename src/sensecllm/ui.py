from __future__ import annotations

from fastapi.responses import HTMLResponse


def dashboard() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SenseCLLM Harness</title>
<style>
:root{color-scheme:dark;--bg:#08111d;--panel:#101d2d;--line:#29415e;--a:#56d6c9;--warn:#f4c56a}
*{box-sizing:border-box}body{margin:0;font:14px system-ui;background:linear-gradient(135deg,#07101c,#12243a);color:#e9f2fa}
header,main{max-width:1200px;margin:auto;padding:22px}header h1{margin:0;font-size:28px}header p{color:#9eb2c8}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.panel{background:#0d1928e8;border:1px solid var(--line);border-radius:14px;padding:18px}
button,input,select,textarea{background:#07111e;color:#e9f2fa;border:1px solid #35516f;border-radius:8px;padding:9px}button{cursor:pointer;background:#174b55}.runs button{display:block;width:100%;text-align:left;margin:7px 0;background:#102338}
.graph{display:flex;flex-wrap:wrap;gap:7px}.node{padding:10px;border:1px solid #42617f;border-radius:20px}.completed{border-color:var(--a);color:var(--a)}.failed,.rejected{border-color:#ff7d7d;color:#ff9c9c}.running{border-color:var(--warn);color:var(--warn)}
pre{white-space:pre-wrap;max-height:380px;overflow:auto;background:#07111e;padding:12px;border-radius:8px}.wide{grid-column:1/-1}a{color:#68cbed}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
</style></head><body><header><h1>SenseCLLM Agent Harness</h1><p>物理约束多 Agent · 文献 RAG · Episodic Memory · Critic</p></header>
<main class="grid"><section class="panel"><h2>新建分析</h2><input id="file" type="file" accept=".pdf,.md,.txt"><select id="model"><option>deepseek-v3.2</option></select> <button onclick="upload()">上传并运行</button><p id="uploadState"></p></section>
<section class="panel runs"><h2>运行与对比</h2><button onclick="compareRuns()">对比勾选项</button><div id="runs"></div><pre id="comparison"></pre></section>
<section class="panel wide"><h2>Agent 执行图</h2><div id="status"></div><div class="graph" id="graph"></div></section>
<section class="panel"><h2>物理路径 / 证据 / 产物</h2><div id="artifacts"></div><pre id="evidence">选择一个运行查看结果</pre></section>
<section class="panel"><h2>案例记忆与验证反馈</h2><div id="cases"></div></section>
<section class="panel wide"><h2>基于报告的对话</h2><input id="question" style="width:75%" placeholder="该结论由哪些路径和证据支持？"><button onclick="ask()">提问</button><pre id="answer"></pre></section>
</main><script>
let selected='';const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function json(url,opt){let r=await fetch(url,opt);if(!r.ok)throw Error(await r.text());return r.json()}
async function load(){let rs=await json('/v1/runs');runs.innerHTML=rs.map(r=>`<label><input class="cmp" type="checkbox" value="${r.run_id}"></label><button onclick="show('${r.run_id}')"><b>${r.run_id.slice(0,8)}</b> · ${r.status} · ${r.model}</button>`).join('')||'暂无运行';let cs=await json('/v1/memory/cases');cases.innerHTML=cs.map(c=>`<p><b>${esc(c.device_model||c.sensor_type||c.id.slice(0,8))}</b><br>${esc(c.summary)} · 验证 ${c.verification_count} <button onclick="verify('${c.id}')">录入验证</button></p>`).join('')||'暂无历史案例'}
async function upload(){let f=file.files[0];if(!f)return;uploadState.textContent='上传中…';let bytes=new Uint8Array(await f.arrayBuffer()),bin='';for(let i=0;i<bytes.length;i+=8192)bin+=String.fromCharCode(...bytes.subarray(i,i+8192));let r=await json('/v1/uploads',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({filename:f.name,content_base64:btoa(bin),model:model.value})});uploadState.textContent='运行 '+r.run_id;selected=r.run_id;await load();await show(selected)}
async function show(id){selected=id;let r=await json('/v1/runs/'+id);status.textContent=`${r.status} · ${r.metadata?.usage?.total_tokens||0} tokens · ${r.metadata?.usage?.execution_seconds||0}s`;graph.innerHTML=Object.values(r.stages).map(s=>`<span class="node ${s.status}">${esc(s.name)} · ${esc(s.status)}</span>`).join('');artifacts.innerHTML=Object.entries(r.artifacts||{}).map(([n,p])=>`<a href="/v1/runs/${id}/artifacts/${encodeURIComponent(n)}">${esc(n)}</a> `).join('');let p=r.artifacts?.step2_mechanism_paths;if(p){let d=await fetch(`/v1/runs/${id}/artifacts/step2_mechanism_paths`);evidence.textContent=await d.text()}if(['running','pending'].includes(r.status))setTimeout(()=>show(id),2000)}
async function ask(){if(!selected)return;answer.textContent='生成中…';let r=await json(`/v1/runs/${selected}/chat`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({question:question.value})});answer.textContent=r.answer+'\n\n'+JSON.stringify(r.citations,null,2)}
async function compareRuns(){let ids=[...document.querySelectorAll('.cmp:checked')].map(x=>x.value);if(ids.length<2)return;comparison.textContent=JSON.stringify(await json('/v1/compare?run_ids='+ids.join(',')),null,2)}
async function verify(id){let vulnerability=prompt('漏洞名称');if(!vulnerability)return;let outcome=prompt('结果：confirmed / rejected / inconclusive / not_tested','confirmed');if(!outcome)return;await json(`/v1/memory/cases/${id}/verification`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({vulnerability_name:vulnerability,outcome})});await load()}
load();</script></body></html>"""
    )

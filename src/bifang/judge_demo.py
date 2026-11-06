"""Static public judge page. Provider credentials never enter this document."""

import base64
import hashlib

_STYLE = """
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:#090c12;color:#f7f7f7}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 20% 0,#37201666,transparent 55%)}
a{color:inherit}button,select,textarea{font:inherit}button,a,select,textarea{outline-offset:5px}
.wrap{width:min(1120px,100%);margin:auto;padding:32px 24px}nav{display:flex;align-items:center;justify-content:space-between;gap:16px}
.brand{font-weight:800;letter-spacing:.22em;text-decoration:none}.brand span{color:#ff8a3d}.links{display:flex;gap:20px;font-size:.85rem;color:#b9c0cf}
.hero{padding:64px 0 32px;max-width:800px}.eyebrow{color:#ffad69;text-transform:uppercase;letter-spacing:.18em;font-size:.75rem}
h1{font-size:clamp(2.5rem,7vw,4.8rem);line-height:1.04;letter-spacing:-.055em;margin:16px 0 24px}h1 span{color:#ff8a3d}
.intro{max-width:650px;color:#b9c0cf;line-height:1.7;font-size:1.08rem}.grid{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:24px}
.panel{border:1px solid #293245;border-radius:20px;background:#101725;padding:24px;min-width:0}.panel h2{font-size:1.05rem;margin:0 0 18px}
.controls{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:16px}
label{font-size:.85rem;color:#c5ccda}select,textarea{border:1px solid #354057;background:#090f1b;color:#f7f7f7;border-radius:10px;padding:12px;max-width:100%}
textarea{display:block;width:100%;resize:vertical;min-height:120px;line-height:1.6;margin:8px 0 14px}.actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
button,.download{border:0;border-radius:10px;padding:12px 18px;font-weight:650;cursor:pointer;background:linear-gradient(110deg,#ff7034,#ffad42);color:#16100c}
button:disabled{opacity:.5;cursor:wait}.secondary{background:#222d40;color:#e9edf5}.badge{font-size:.75rem;border:1px solid #354057;border-radius:30px;padding:6px 10px;color:#b9c0cf}
#status{font-size:.8rem;color:#b9c0cf}#response{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.65;font:14px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;margin:24px 0 0;max-height:560px;overflow:auto}
.aside p,.aside li{color:#b9c0cf;font-size:.88rem;line-height:1.7}.aside ul{padding-left:18px}.download{display:block;text-decoration:none;text-align:center;margin:18px 0}
code{font:12px/1.7 ui-monospace,monospace;overflow-wrap:anywhere}.api{margin-top:24px;padding-top:18px;border-top:1px solid #293245}.api p{font-size:.78rem;color:#b9c0cf}
footer{padding:28px 0;color:#8792a8;font-size:.76rem;line-height:1.7}.hint{font-size:.76rem;color:#98a4b9;margin-top:16px}
@media(max-width:760px){.wrap{padding:24px 16px}.hero{padding:38px 0 20px}.grid{grid-template-columns:1fr}.panel{padding:18px}.links{gap:12px}.badge{display:none}}
"""

_SCRIPT = """
const form=document.querySelector('#prompt-form'), picker=document.querySelector('#model');
const prompt=document.querySelector('#prompt'), response=document.querySelector('#response');
const status=document.querySelector('#status'), send=document.querySelector('#send'), stop=document.querySelector('#stop');
let controller=null;
document.querySelector('#api-url').textContent=location.origin+'/v1';
function label(id){return /nano/i.test(id)?'Nano · fast':/super/i.test(id)?'Super · balanced':/ultra/i.test(id)?'Ultra · reasoning':id;}
async function models(){
 try{
  const result=await fetch('/v1/models',{cache:'no-store'});
  if(!result.ok)throw new Error('catalog');
  const catalog=await result.json();
  for(const row of catalog.data||[]){if(typeof row.id!=='string')continue;const option=document.createElement('option');option.value=row.id;option.textContent=label(row.id);picker.append(option);}
  const fast=Array.from(picker.options).find(option=>/nano/i.test(option.value));
  if(fast)picker.value=fast.value;
  send.disabled=picker.options.length===0;status.textContent=send.disabled?'Models are temporarily unavailable.':'Ready · no login required';
 }catch{status.textContent='Models are temporarily unavailable. Please try again shortly.';}
}
form.addEventListener('submit',async event=>{
 event.preventDefault();if(controller||!prompt.value.trim()||!picker.value)return;
 controller=new AbortController();send.disabled=true;picker.disabled=true;stop.hidden=false;response.textContent='';status.textContent='Working on Nebius Token Factory…';
 try{
  const result=await fetch('/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({model:picker.value,messages:[{role:'user',content:prompt.value.trim()}],max_tokens:2048,stream:false})});
  if(!result.ok)throw new Error('HTTP '+result.status);
  const answer=await result.json(), text=answer.choices?.[0]?.message?.content;
  if(typeof text!=='string'||!text.trim())throw new Error('No final text was returned. Try another model.');
  response.textContent=text;
  const tokens=answer.usage?.total_tokens;status.textContent='Complete'+(typeof answer.model==='string'?' · '+label(answer.model):'')+(Number.isInteger(tokens)?' · '+tokens+' reported tokens':'');
 }catch(error){status.textContent=error.name==='AbortError'?'Request stopped.':'Request could not complete. '+error.message;}
 finally{controller=null;picker.disabled=false;send.disabled=picker.options.length===0;stop.hidden=true;}
});
stop.addEventListener('click',()=>controller?.abort());
document.querySelector('#example').addEventListener('click',()=>{prompt.value='Write a Python function that parses CSV receipt lines correctly, including quoted commas. Use the standard library and include three unit tests.';prompt.focus();});
void models();
"""


def _hash(value: str) -> str:
    return base64.b64encode(hashlib.sha256(value.encode()).digest()).decode()


PUBLIC_DEMO_CSP = (
    "default-src 'none'; "
    f"script-src 'sha256-{_hash(_SCRIPT)}'; style-src 'sha256-{_hash(_STYLE)}'; "
    "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)

PUBLIC_DEMO_HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Try Bifang's NVIDIA coding models on Nebius Token Factory. Public judge demo, no login required.">
<title>Bifang · Build. Run. Verify.</title><style>{_STYLE}</style></head>
<body><main class="wrap">
<nav><a class="brand" href="/">BI<span>F</span>ANG</a><div class="links"><a href="https://github.com/Protocol-X-01/Bifang">Source</a><a href="https://github.com/Protocol-X-01/Bifang/releases/tag/v0.3.2">Downloads</a></div></nav>
<header class="hero"><p class="eyebrow">Nebius × NVIDIA · Public judge demo</p><h1>Build. Run.<br><span>Verify.</span></h1>
<p class="intro">Try the coding models behind Bifang. Choose Nano, Super or Ultra, then take the full inspect, edit, test and review workflow into the open-source IDE.</p></header>
<div class="grid"><section class="panel" aria-labelledby="demo-title">
<div class="controls"><h2 id="demo-title">Code with Bifang</h2><span class="badge">No account or API key needed</span></div>
<form id="prompt-form"><label for="model">Model</label> <select id="model" aria-label="Model"></select>
<p><label for="prompt">Coding request</label><textarea id="prompt" maxlength="16000" placeholder="Ask for a function, a test or help with a bug…" required></textarea></p>
<div class="actions"><button id="send" type="submit" disabled>Send request</button><button id="stop" type="button" class="secondary" hidden>Stop</button><button id="example" type="button" class="secondary">Try a coding prompt</button></div>
</form><p id="status" role="status" aria-live="polite">Connecting to the model catalog…</p><pre id="response" aria-label="Model response" tabindex="0"></pre>
<p class="hint">Requests run on Nebius Token Factory. Share only the code or text you want the selected model to receive.</p></section>
<aside class="panel aside"><h2>The full coding workspace</h2><p>Bifang's desktop and terminal clients keep the project, tool approvals, checks and patch review together.</p>
<ul><li>Start with a blank workspace or an existing repository.</li><li>Review edits and commands as the agent works.</li><li>Inspect the diff and decide when to apply.</li></ul>
<a class="download" href="https://github.com/Protocol-X-01/Bifang/releases/tag/v0.3.2">Download Bifang</a>
<div class="api"><h2>Use your own client</h2><p>OpenAI-compatible API base</p><code id="api-url"></code><p>No secret is required for this public demo. Clients that require a key field can use <code>bifang-public-demo</code>.</p></div></aside></div>
<footer>Built for the Coding and Agentic Engineering track. NVIDIA Nemotron models, served through Nebius Token Factory.<br>Source and installation instructions are on GitHub.</footer>
</main><script>{_SCRIPT}</script></body></html>"""

"""MedLocal Web UI — mobile-first single-page interface."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from .api import app

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#0f172a">
<title>MedLocal</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0f172a;--surface:#1e293b;--surface2:#334155;--border:#475569;--text:#e2e8f0;--text2:#94a3b8;--accent:#3b82f6;--green:#22c55e;--red:#ef4444;--yellow:#eab308;--orange:#f97316}
body{font-family:-apple-system,system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100dvh;display:flex;flex-direction:column;font-size:16px}
header{background:var(--surface);padding:12px 16px;display:flex;align-items:center;gap:12px;border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100}
header h1{font-size:18px;font-weight:700}
.offline-badge{background:var(--green);color:#000;font-size:10px;padding:2px 8px;border-radius:99px;font-weight:700;letter-spacing:1px}
nav{display:flex;background:var(--surface);border-bottom:1px solid var(--border);overflow-x:auto;position:sticky;top:49px;z-index:99}
nav button{flex:1;padding:10px 4px;background:none;border:none;color:var(--text2);font-size:12px;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap;min-width:60px}
nav button.active{color:var(--accent);border-bottom-color:var(--accent)}
main{flex:1;padding:16px;max-width:640px;margin:0 auto;width:100%}
.tab{display:none}
.tab.active{display:block}
textarea,input[type=text],select{width:100%;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:16px;resize:vertical}
textarea{min-height:80px}
button.primary{width:100%;padding:14px;background:var(--accent);color:#fff;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer;margin-top:12px}
button.primary:disabled{opacity:.5;cursor:not-allowed}
button.primary.emergency{background:var(--red)}
button.primary.green{background:var(--green);color:#000}
.result{margin-top:16px;padding:16px;background:var(--surface);border-radius:8px;border:1px solid var(--border);line-height:1.6;white-space:pre-wrap;word-wrap:break-word}
.result h3{margin-bottom:8px}
.result strong{color:var(--accent)}
.sources{margin-top:8px;font-size:13px;color:var(--text2)}
.sources a:hover .source-tag{filter:brightness(1.3)}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;margin:2px}
.badge.high{background:#166534;color:#bbf7d0}
.badge.medium{background:#854d0e;color:#fef08a}
.badge.low{background:#991b1b;color:#fecaca}
.badge.emergency{background:var(--red);color:#fff;font-size:13px;padding:4px 12px}
.badge.flag{background:var(--orange);color:#000}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px}
.card-label{font-size:12px;color:var(--text2);margin-bottom:4px}
.card-question{font-size:15px;line-height:1.5}
.rating{font-size:14px;font-weight:700;padding:4px 12px;border-radius:4px;display:inline-block;margin:4px 0}
.rating.again{background:#991b1b;color:#fecaca}
.rating.hard{background:#854d0e;color:#fef08a}
.rating.good{background:#166534;color:#bbf7d0}
.rating.easy{background:#164e63;color:#a5f3fc}
.loading{color:var(--text2);font-style:italic;padding:16px 0}
.empty{color:var(--text2);text-align:center;padding:40px 16px}
.stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:16px}
.stat{background:var(--surface);border-radius:8px;padding:12px;text-align:center}
.stat-value{font-size:24px;font-weight:700;color:var(--accent)}
.stat-label{font-size:11px;color:var(--text2);margin-top:2px}
.chat-messages{max-height:60vh;overflow-y:auto;margin-bottom:12px}
.msg{padding:10px 14px;border-radius:12px;margin-bottom:8px;max-width:85%;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}
.msg.user{background:var(--accent);margin-left:auto;color:#fff}
.msg.assistant{background:var(--surface2)}
.source-tag{font-size:10px;padding:1px 6px;border-radius:3px;font-weight:600}
.source-tag.core{background:#164e63;color:#a5f3fc}
.source-tag.local{background:#713f12;color:#fef08a}
footer{background:var(--surface);padding:8px;text-align:center;font-size:11px;color:var(--text2);border-top:1px solid var(--border)}
</style>
</head>
<body>
<header>
  <h1>MedLocal</h1>
  <span class="offline-badge">OFFLINE</span>
</header>
<nav>
  <button onclick="showTab('consult')" id="nav-consult" class="active">Consult</button>
  <button onclick="showTab('train')" id="nav-train">Train</button>
  <button onclick="showTab('search')" id="nav-search">Search</button>
  <button onclick="showTab('admin')" id="nav-admin">Admin</button>
</nav>
<main>

<!-- CONSULT TAB (unified: text + vision + follow-ups) -->
<div id="tab-consult" class="tab active" style="display:flex;flex-direction:column;height:calc(100dvh - 145px)">
  <div id="consult-messages" style="flex:1;overflow-y:auto;padding-bottom:8px"></div>
  <div style="flex-shrink:0;padding-top:8px;border-top:1px solid var(--border)">
    <input type="file" id="vision-file" accept="image/*" capture="environment" style="display:none" onchange="onImageSelected(this)">
    <div id="img-preview-bar" style="display:none;margin-bottom:8px;position:relative">
      <img id="vision-preview" style="height:60px;border-radius:6px;border:1px solid var(--border)">
      <select id="vision-mode" style="padding:6px;background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:6px;font-size:12px;margin-left:8px">
        <option value="triage">Wound / Rash</option>
        <option value="medication">Medication ID</option>
        <option value="scan">Scan Document</option>
      </select>
      <button onclick="clearImage()" style="position:absolute;top:-6px;right:-6px;background:var(--red);color:#fff;border:none;border-radius:50%;width:20px;height:20px;font-size:12px;cursor:pointer;line-height:20px">x</button>
    </div>
    <textarea id="consult-q" placeholder="Describe symptoms or ask a follow-up..." rows="2" style="min-height:48px"></textarea>
    <div style="display:flex;gap:8px;margin-top:8px">
      <button onclick="document.getElementById('vision-file').click()" style="width:44px;height:44px;background:var(--surface2);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:20px;cursor:pointer;flex-shrink:0" title="Take photo">📷</button>
      <button class="primary" onclick="doConsult()" id="btn-consult" style="flex:1;margin:0">Send</button>
      <button class="primary" onclick="clearConsult()" style="width:60px;margin:0;background:var(--surface2);font-size:12px">New</button>
    </div>
  </div>
</div>

<!-- TRAIN TAB -->
<div id="tab-train" class="tab">
  <h3 style="margin-bottom:12px">Training</h3>
  <div id="train-stats" class="stats"></div>
  <div id="train-card"></div>
  <div id="train-controls" style="display:none">
    <textarea id="train-answer" placeholder="Type your answer..." rows="3"></textarea>
    <button class="primary green" onclick="submitAnswer()">Submit Answer</button>
    <button class="primary" onclick="skipCard()" style="background:var(--surface2);margin-top:8px">Skip</button>
  </div>
  <div id="train-feedback"></div>
  <button class="primary" onclick="loadSession()" id="btn-load-session">Start Session</button>
</div>

<!-- SEARCH TAB -->
<div id="tab-search" class="tab">
  <h3 style="margin-bottom:12px">Search Protocols</h3>
  <input type="text" id="search-q" placeholder="Search the knowledge base...">
  <button class="primary" onclick="doSearch()">Search</button>
  <div id="search-results"></div>
</div>

<!-- ADMIN TAB -->
<div id="tab-admin" class="tab">
  <h3 style="margin-bottom:12px">Administration</h3>
  <div class="card">
    <div class="card-label">Add Local Protocol</div>
    <input type="text" id="admin-source" placeholder="File path or URL" style="margin-top:8px">
    <button class="primary" onclick="doIngest()" style="background:var(--surface2)">Ingest to Local</button>
  </div>
  <div class="card" style="margin-top:12px">
    <div class="card-label">Generate Training Cards</div>
    <input type="text" id="admin-topic" placeholder="Topic (e.g. malaria, pneumonia)" style="margin-top:8px">
    <button class="primary" onclick="doGenerate()" style="background:var(--surface2)">Generate Cards</button>
  </div>
  <div id="admin-result"></div>
</div>

</main>
<!-- Source Modal -->
<div id="source-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:200;padding:16px;overflow-y:auto" onclick="if(event.target===this)this.style.display='none'">
  <div style="background:var(--surface);border-radius:12px;padding:20px;max-width:600px;margin:40px auto;border:1px solid var(--border)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h3>Source Protocol</h3>
      <button onclick="document.getElementById('source-modal').style.display='none'" style="background:none;border:none;color:var(--text);font-size:20px;cursor:pointer">x</button>
    </div>
    <div id="source-content" style="line-height:1.7;white-space:pre-wrap;font-size:14px"></div>
  </div>
</div>
<footer>MedLocal v0.1 &mdash; Works without internet. Fits in your pocket. Backed by benchmarks.</footer>

<script>
const API = '';
let chatHistory = [];
let trainQueue = [];
let trainIdx = 0;

function showTab(id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.getElementById('nav-'+id).classList.add('active');
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function renderAnswer(r) {
  let html = '<div class="result">';
  if (r.emergency) html += '<span class="badge emergency">EMERGENCY</span> ';
  html += '<span class="badge '+r.confidence.toLowerCase()+'">'+r.confidence+'</span>';
  if (r.safety_flags) r.safety_flags.forEach(f => {
    html += ' <span class="badge flag">'+f+'</span>';
  });
  html += '<div style="margin-top:12px;white-space:pre-wrap">'+formatMd(r.answer)+'</div>';
  if (r.sources && r.sources.length) {
    const srcId = 'src-'+Math.random().toString(36).substr(2,6);
    html += '<div class="sources"><a onclick="document.getElementById(\\''+srcId+'\\').style.display=document.getElementById(\\''+srcId+'\\').style.display===\\'none\\'?\\'block\\':\\'none\\'" style="cursor:pointer;color:var(--text2);font-size:12px">View retrieved protocols</a>';
    html += '<div id="'+srcId+'" style="display:none;margin-top:6px">';
    r.sources.slice(0,3).forEach(s => {
      const tag = s.profile === 'core' ? 'core' : 'local';
      const cid = s.chunk_id || 0;
      html += '<a onclick="viewSource('+cid+',\\''+s.profile+'\\')" style="cursor:pointer;text-decoration:none;display:inline-block;margin:2px 4px 2px 0"><span class="source-tag '+tag+'">'+s.profile.toUpperCase()+'</span> '+esc(s.title)+'</a>';
    });
    html += '</div></div>';
  }
  html += '</div>';
  return html;
}

function formatMd(text) {
  return esc(text)
    .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
    .replace(/\\n/g, '<br>')
    // Highlight alerts: IMPORTANTE, URGENT, WARNING, EMERGENCY, REFER, PELIGRO
    // Highlight alerts
    .replace(/<strong>(IMPORTANT[EO]?:?|URGENT[EO]?:?|WARNING:?|EMERGENCY:?|PELIGRO:?|DANGER:?)<.strong>/gi,
      '<span style="background:var(--red);color:#fff;padding:2px 8px;border-radius:4px;font-weight:700;font-size:13px">$1</span>')
    // Highlight "Refer if:" and "Ask also:" headers
    .replace(/<strong>(Refer if:|Referir si:|Ask also:|Pregunte tambi.n:)<.strong>/gi,
      '<strong style="color:var(--yellow)">$1</strong>')
    // Clean LaTeX artifacts from small models
    .replace(/[$]\\\\geq[$]/g, '>=')
    .replace(/[$]\\\\leq[$]/g, '<=')
    .replace(/[$]([^$]+)[$]/g, '$1');
}

async function doConsult() {
  const input = document.getElementById('consult-q');
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  input.style.height = 'auto';
  const btn = document.getElementById('btn-consult');
  const box = document.getElementById('consult-messages');

  // Show user message
  box.innerHTML += '<div class="msg user">'+esc(q)+'</div>';
  box.innerHTML += '<div class="msg assistant loading" id="consult-loading">Searching protocols...</div>';
  box.scrollTop = box.scrollHeight;
  btn.disabled = true;

  try {
    const res = await fetch(API+'/api/consult', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({question:q, history:chatHistory})
    });
    const r = await res.json();
    chatHistory.push({role:'user',content:q});
    chatHistory.push({role:'assistant',content:r.answer});

    document.getElementById('consult-loading').remove();
    box.innerHTML += '<div class="msg assistant">'+renderAnswer(r)+'</div>';
    box.scrollTop = box.scrollHeight;
  } catch(e) {
    document.getElementById('consult-loading').remove();
    box.innerHTML += '<div class="msg assistant" style="border-color:var(--red)">Error: '+esc(e.message)+'</div>';
  }
  btn.disabled = false;
  input.focus();
}

function clearConsult() {
  chatHistory = [];
  document.getElementById('consult-messages').innerHTML =
    '<div class="empty" style="padding:20px;font-size:14px">Ask any clinical question. You can follow up for more details.</div>';
  document.getElementById('consult-q').focus();
}
clearConsult();

async function loadSession() {
  const out = document.getElementById('train-card');
  out.innerHTML = '<div class="loading">Loading cards...</div>';
  document.getElementById('btn-load-session').style.display = 'none';
  try {
    const res = await fetch(API+'/api/train/session');
    const r = await res.json();
    trainQueue = r.cards;
    trainIdx = 0;
    document.getElementById('train-stats').innerHTML =
      '<div class="stat"><div class="stat-value">'+r.due_count+'</div><div class="stat-label">Due</div></div>'+
      '<div class="stat"><div class="stat-value">'+r.new_count+'</div><div class="stat-label">New</div></div>'+
      '<div class="stat"><div class="stat-value">'+r.cards.length+'</div><div class="stat-label">Total</div></div>';
    if (trainQueue.length === 0) {
      out.innerHTML = '<div class="empty">No cards to review. Generate cards in Admin tab first.</div>';
      document.getElementById('btn-load-session').style.display = 'block';
      return;
    }
    showCard();
  } catch(e) {
    out.innerHTML = '<div class="result" style="border-color:var(--red)">Error: '+esc(e.message)+'</div>';
    document.getElementById('btn-load-session').style.display = 'block';
  }
}

function showCard() {
  const out = document.getElementById('train-card');
  const controls = document.getElementById('train-controls');
  const feedback = document.getElementById('train-feedback');
  feedback.innerHTML = '';
  if (trainIdx >= trainQueue.length) {
    out.innerHTML = '<div class="empty">Session complete!</div>';
    controls.style.display = 'none';
    document.getElementById('btn-load-session').style.display = 'block';
    return;
  }
  const c = trainQueue[trainIdx];
  out.innerHTML = '<div class="card"><div class="card-label">'+esc(c.level_label)+' &mdash; '+esc(c.topic)+' ('+(trainIdx+1)+'/'+trainQueue.length+')</div>'+
    '<div class="card-question" style="margin-top:8px">'+esc(c.question)+'</div></div>';
  if (c.is_read_only) {
    out.innerHTML += '<div class="card" style="border-color:var(--accent)"><div class="card-label">Key Concept</div>'+
      '<div style="margin-top:8px;line-height:1.5">'+esc(c.answer)+'</div></div>';
    controls.style.display = 'none';
    out.innerHTML += '<button class="primary" onclick="trainIdx++;showCard()">Next</button>';
  } else {
    controls.style.display = 'block';
    document.getElementById('train-answer').value = '';
    document.getElementById('train-answer').focus();
  }
}

function skipCard() { trainIdx++; showCard(); }

async function submitAnswer() {
  const c = trainQueue[trainIdx];
  const answer = document.getElementById('train-answer').value.trim();
  if (!answer) return;
  const feedback = document.getElementById('train-feedback');
  feedback.innerHTML = '<div class="loading">Evaluating...</div>';
  try {
    const res = await fetch(API+'/api/train/answer', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({card_id:c.id, answer:answer})
    });
    const r = await res.json();
    feedback.innerHTML = '<div class="card">'+
      '<span class="rating '+r.rating+'">'+r.rating.toUpperCase()+'</span>'+
      '<div style="margin-top:8px;color:var(--text2)">'+esc(r.feedback)+'</div>'+
      '<div style="margin-top:8px"><strong>Correct answer:</strong><br>'+esc(r.correct_answer)+'</div>'+
      '<div style="margin-top:8px;font-size:12px;color:var(--text2)">Next review in '+r.next_review_days+' days</div>'+
      '</div>';
    document.getElementById('train-controls').style.display = 'none';
    feedback.innerHTML += '<button class="primary" onclick="trainIdx++;showCard()">Next Card</button>';
  } catch(e) {
    feedback.innerHTML = '<div class="result" style="border-color:var(--red)">Error: '+esc(e.message)+'</div>';
  }
}

async function doSearch() {
  const q = document.getElementById('search-q').value.trim();
  if (!q) return;
  const out = document.getElementById('search-results');
  out.innerHTML = '<div class="loading">Searching...</div>';
  try {
    const res = await fetch(API+'/api/search?q='+encodeURIComponent(q));
    const results = await res.json();
    if (!results.length) { out.innerHTML = '<div class="empty">No results found.</div>'; return; }
    out.innerHTML = results.map((r,i) =>
      '<div class="card"><div class="card-label">'+
      '<span class="source-tag '+(r.profile==='core'?'core':'local')+'">'+r.profile.toUpperCase()+'</span> '+
      esc(r.title)+' (score: '+r.score+')</div>'+
      '<div style="margin-top:8px;font-size:14px;line-height:1.5;color:var(--text2)">'+esc(r.text)+'</div></div>'
    ).join('');
  } catch(e) {
    out.innerHTML = '<div class="result" style="border-color:var(--red)">Error: '+esc(e.message)+'</div>';
  }
}

async function doIngest() {
  const source = document.getElementById('admin-source').value.trim();
  if (!source) return;
  const out = document.getElementById('admin-result');
  out.innerHTML = '<div class="loading">Ingesting...</div>';
  try {
    const res = await fetch(API+'/api/ingest', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({source:source, profile:'local'})
    });
    const r = await res.json();
    if (res.ok) {
      out.innerHTML = '<div class="result" style="border-color:var(--green)">Ingested '+r.chunks+' chunks into '+r.profile+' profile</div>';
    } else {
      out.innerHTML = '<div class="result" style="border-color:var(--red)">'+esc(r.detail)+'</div>';
    }
  } catch(e) {
    out.innerHTML = '<div class="result" style="border-color:var(--red)">Error: '+esc(e.message)+'</div>';
  }
}

async function doGenerate() {
  const topic = document.getElementById('admin-topic').value.trim();
  if (!topic) return;
  const out = document.getElementById('admin-result');
  out.innerHTML = '<div class="loading">Generating cards for "'+esc(topic)+'"... (this may take a minute)</div>';
  try {
    const res = await fetch(API+'/api/train/generate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({topic:topic})
    });
    const r = await res.json();
    if (res.ok) {
      out.innerHTML = '<div class="result" style="border-color:var(--green)">Created '+r.cards_created+' training cards for "'+esc(r.topic)+'"</div>';
    } else {
      out.innerHTML = '<div class="result" style="border-color:var(--red)">'+esc(r.detail)+'</div>';
    }
  } catch(e) {
    out.innerHTML = '<div class="result" style="border-color:var(--red)">Error: '+esc(e.message)+'</div>';
  }
}

// Enter key handlers
document.getElementById('consult-q').addEventListener('keydown', e => {
  if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); doConsult(); }
});
document.getElementById('search-q').addEventListener('keydown', e => {
  if (e.key==='Enter') { doSearch(); }
});

// Source viewer
async function viewSource(chunkId, profile) {
  const modal = document.getElementById('source-modal');
  const content = document.getElementById('source-content');
  content.textContent = 'Loading...';
  modal.style.display = 'block';
  try {
    const res = await fetch(API+'/api/chunk/'+chunkId+'?profile='+profile);
    const r = await res.json();
    content.textContent = r.text;
  } catch(e) {
    content.textContent = 'Error loading source: '+e.message;
  }
}

// Vision (integrated into consult)
let pendingImage = null;
function onImageSelected(input) {
  if (input.files && input.files[0]) {
    pendingImage = input.files[0];
    const reader = new FileReader();
    reader.onload = e => {
      document.getElementById('vision-preview').src = e.target.result;
      document.getElementById('img-preview-bar').style.display = 'flex';
    };
    reader.readAsDataURL(input.files[0]);
  }
}
function clearImage() {
  pendingImage = null;
  document.getElementById('img-preview-bar').style.display = 'none';
  document.getElementById('vision-file').value = '';
}

// Override doConsult to handle images
const _origConsult = doConsult;
doConsult = async function() {
  if (!pendingImage) { return _origConsult(); }
  // Image flow
  const file = pendingImage;
  const mode = document.getElementById('vision-mode').value;
  const textQ = document.getElementById('consult-q').value.trim();
  const box = document.getElementById('consult-messages');
  const btn = document.getElementById('btn-consult');
  const imgSrc = document.getElementById('vision-preview').src;

  // Show user message with image thumbnail
  box.innerHTML += '<div class="msg user"><img src="'+imgSrc+'" style="max-height:120px;border-radius:6px;display:block;margin-bottom:6px">'+
    (textQ ? esc(textQ) : '<em style="color:rgba(255,255,255,.6)">'+{triage:'Analyze wound/rash',medication:'Identify medication',scan:'Scan document'}[mode]+'</em>')+'</div>';
  box.innerHTML += '<div class="msg assistant loading" id="consult-loading">Analyzing image...</div>';
  box.scrollTop = box.scrollHeight;
  btn.disabled = true;
  clearImage();
  document.getElementById('consult-q').value = '';

  const endpoints = {triage:'/api/vision/triage', medication:'/api/vision/medication', scan:'/api/vision/scan'};
  const formData = new FormData();
  const bytes = await file.arrayBuffer();
  formData.append('file', new Blob([bytes]), file.name);
  if (textQ) formData.append('context', textQ);

  try {
    const res = await fetch(API+endpoints[mode], {method:'POST', body:formData});
    const r = await res.json();
    document.getElementById('consult-loading').remove();
    let html = '';
    if (mode==='triage') {
      html = '<div class="card" style="margin-bottom:8px"><div class="card-label">Visual Findings</div><div style="margin-top:6px">'+esc(r.description)+'</div></div>'+renderAnswer(r);
      chatHistory.push({role:'user',content:'[Image: visual triage] '+(textQ||'')});
      chatHistory.push({role:'assistant',content:r.answer});
    } else if (mode==='medication') {
      html = '<div class="result">'+formatMd(r.identification)+'</div>';
    } else {
      html = '<div class="card"><div class="card-label">Scanned Text ('+r.chunks+' chunks ingested)</div><div style="margin-top:6px;font-size:13px;white-space:pre-wrap">'+esc(r.text.substring(0,500))+(r.text.length>500?'...':'')+'</div></div>';
    }
    box.innerHTML += '<div class="msg assistant">'+html+'</div>';
    box.scrollTop = box.scrollHeight;
  } catch(e) {
    document.getElementById('consult-loading').remove();
    box.innerHTML += '<div class="msg assistant" style="border-color:var(--red)">Error: '+esc(e.message)+'</div>';
  }
  btn.disabled = false;
  document.getElementById('consult-q').focus();
};
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def serve_ui(request: Request):
    """Serve the mobile-first web interface."""
    return HTMLResponse(content=_HTML)

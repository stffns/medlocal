const API = '';

export async function consultAPI(question, history = []) {
  const res = await fetch(`${API}/api/consult`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function searchAPI(query, topK = 5) {
  const res = await fetch(`${API}/api/search?q=${encodeURIComponent(query)}&top_k=${topK}`);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function getChunkAPI(chunkId, profile = 'core') {
  const res = await fetch(`${API}/api/chunk/${chunkId}?profile=${profile}`);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function trainGenerateAPI(topic, maxChunks = 20) {
  const res = await fetch(`${API}/api/train/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, max_chunks: maxChunks }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function trainSessionAPI(topic = null, newLimit = 10) {
  const params = new URLSearchParams();
  if (topic) params.set('topic', topic);
  params.set('new_limit', newLimit);
  const res = await fetch(`${API}/api/train/session?${params}`);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function trainAnswerAPI(cardId, answer) {
  const res = await fetch(`${API}/api/train/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card_id: cardId, answer }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function trainTopicsAPI() {
  const res = await fetch(`${API}/api/train/topics`);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function visionTriageAPI(file, context = '') {
  const form = new FormData();
  form.append('file', file);
  form.append('context', context);
  const res = await fetch(`${API}/api/vision/triage`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function visionMedicationAPI(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API}/api/vision/medication`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function visionScanAPI(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API}/api/vision/scan`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

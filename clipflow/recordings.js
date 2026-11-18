const recordingsView = document.createElement('section');
recordingsView.id = 'recordings';
recordingsView.className = 'card section';
recordingsView.style.marginTop = '20px';
recordingsView.innerHTML = `<div class="sectionhead"><div><h2>Analisar gravação</h2><p>Encontre até cinco momentos antes de renderizar.</p></div><span>✦</span></div>
<p class="hint">As lives monitoradas geram blocos automáticos de até uma hora para análise pela IA. Você também pode colocar um vídeo em <strong>input/</strong>. A transcrição é enviada ao provedor selecionado em Edição e pode gerar custo de API.</p><p class="hint">O original automático será excluído permanentemente quando todas as sugestões forem rejeitadas ou seus cortes renderizados forem aprovados/rejeitados. Gravações sem sugestões ou com falha são mantidas. Vídeos adicionados manualmente não são excluídos.</p>
<label class="label" for="recording-file">Gravação local</label><select id="recording-file" class="editor-input"><option value="">Carregando...</option></select>
<div class="controls"><button class="primary" id="recording-start">Analisar gravação</button><button class="secondary" id="recording-refresh">Atualizar lista</button></div>
<p class="hint" id="recording-message" role="status"></p><div id="recording-results"></div>`;
document.querySelector('.foot').before(recordingsView);
views.push(recordingsView);
menus.push(['recordings', '▣', 'Gravações', recordingsView]);
headings.recordings = ['Gravações', 'Analise uma hora e revise os melhores momentos.'];
navigation.insertAdjacentHTML('beforeend', '<a href="#recordings" data-view="recordings"><span>▣</span><span>Gravações</span></a>');
showView();
const recordingFile = document.getElementById('recording-file');
const recordingMessage = document.getElementById('recording-message');
let recordingsData = null;
let recordingDirty = false;
recordingFile.addEventListener('change', () => recordingDirty = true);
function timestamp(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  return `${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;
}
async function loadRecordings() {
  try {
    const r = await fetch('/api/recordings'); if (!r.ok) throw Error();
    const data = await r.json(); recordingsData = data;
    const previous = recordingFile.value;
    recordingFile.innerHTML = data.files.length ? data.files.map(f => `<option value="${esc(f)}">${esc(f)}</option>`).join('') : '<option value="">Nenhum vídeo encontrado em input/</option>';
    if (previous && data.files.includes(previous)) recordingFile.value = previous;
    document.getElementById('recording-start').disabled = data.busy || !data.files.length;
    const results = document.getElementById('recording-results');
    if (results.querySelector('video')) return;
    results.innerHTML = data.analyses.length ? data.analyses.map(a => `<div class="recording-analysis"><div class="sectionhead"><div><h2>${esc(a.filename)}</h2><p>${esc(a.created.replace('T',' '))} · ${esc(a.provider)} · ${esc(a.progress)}</p></div><span class="count">${esc(a.status)}</span></div>${a.error ? `<p class="job-error">${esc(a.error)}</p>${a.original_status === 'disponivel' ? `<button class="smallbtn" data-retry="${a.id}">Tentar análise novamente</button>` : ''}` : ''}${a.original_status ? `<p class="hint">Original automático: ${a.original_status === 'excluido' ? 'excluído após revisão' : 'guardado até todas as sugestões serem revisadas'}${a.original_error ? ' · ' + esc(a.original_error) : ''}</p>` : ''}${a.candidates.map(c => `<article class="clip"><div><h3>${esc(c.title)}</h3><p>${timestamp(c.start)} – ${timestamp(c.end)} · ${esc(c.clip_status || c.status)}<br>${esc(c.reason)}</p><div class="clip-actions"><button class="smallbtn" data-review="${c.id}" ${a.original_status === 'excluido' ? 'disabled' : ''}>▷ Rever trecho</button><button class="smallbtn" data-render="${c.id}" ${data.busy || !['sugerido','erro'].includes(c.status) ? 'disabled' : ''}>✦ ${c.status === 'erro' ? 'Tentar novamente' : c.status === 'pronto' ? 'Renderizado' : c.status === 'renderizando' ? 'Renderizando' : 'Renderizar corte'}</button>${['sugerido','erro'].includes(c.status) ? `<button class="smallbtn" data-discard="${c.id}">✕ Rejeitar sugestão</button>` : ''}${c.status === 'pronto' ? '<a class="smallbtn" href="#clips">Revisar corte em Cortes</a>' : ''}</div></div><div class="score">${esc(c.score)}<small> /100</small></div></article>`).join('')}${a.status === 'concluido' && !a.candidates.length ? '<p class="hint">Nenhum momento sugerido nesta análise.</p>' : ''}</div>`).join('') : '<p class="hint">Suas análises de gravações aparecerão aqui.</p>';
  } catch (_) { recordingMessage.textContent = 'Não foi possível carregar as gravações.'; }
}
async function recordingAction(path, data) {
  try {
    const response = await fetch(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result = await response.json(); if (!response.ok) throw Error(result.error);
    recordingMessage.textContent = 'Solicitação iniciada. Acompanhe o progresso abaixo.';
    await loadRecordings();
  } catch (error) { recordingMessage.textContent = error.message || 'Não foi possível iniciar.'; }
}
document.getElementById('recording-refresh').onclick = loadRecordings;
document.getElementById('recording-start').onclick = () => recordingAction('/api/recordings/analyze', {filename:recordingFile.value});
document.getElementById('recording-results').addEventListener('click', event => {
  const retry = event.target.closest('[data-retry]');
  if (retry) { recordingAction('/api/recordings/retry', {id:Number(retry.dataset.retry)}); return; }
  const discard = event.target.closest('[data-discard]');
  if (discard) { recordingAction('/api/recordings/discard', {id:Number(discard.dataset.discard)}); return; }
  const render = event.target.closest('[data-render]');
  if (render) { recordingAction('/api/recordings/render', {id:Number(render.dataset.render)}); return; }
  const review = event.target.closest('[data-review]'); if (!review) return;
  for (const analysis of recordingsData.analyses) {
    const candidate = analysis.candidates.find(c => c.id === Number(review.dataset.review));
    if (!candidate) continue;
    const existing = document.querySelector('#recording-results video'); if (existing) existing.remove();
    const video = document.createElement('video'); video.controls = true; video.preload = 'metadata';
    video.src = '/api/recording-video/' + encodeURIComponent(analysis.filename) + '#t=' + candidate.start + ',' + candidate.end;
    review.parentElement.after(video); break;
  }
});
loadRecordings(); setInterval(loadRecordings, 5000);

const queueSection = document.createElement('section');
queueSection.className = 'card section';
queueSection.style.marginTop = '20px';
queueSection.id = 'queue';
queueSection.innerHTML = '<div class="sectionhead"><div><h2>Fila de processamento</h2><p>Veja cada momento desde a detecção até o envio.</p></div><span class="count" id="queue-count">—</span></div><div id="queue-list" aria-live="polite">Carregando...</div>';
document.querySelector('.layout').before(queueSection);
document.querySelector('.nav').insertAdjacentHTML('beforeend', '<a href="#queue">◷ &nbsp; Fila de cortes</a>');
const jobLabels = {detectado:'Pico detectado', extraindo:'Salvando trecho', na_fila:'Na fila', transcrevendo:'Transcrevendo', analisando:'Analisando', renderizando:'Renderizando', gerando_previa:'Gerando prévia', enviando:'Enviando ao Telegram', enviado:'Enviado', erro:'Erro'};
async function refreshQueue() {
  try {
    const response = await fetch('/api/jobs');
    if (!response.ok) throw Error();
    const jobs = await response.json();
    document.getElementById('queue-count').textContent = jobs.filter(j => !['enviado','erro'].includes(j.status)).length + ' em andamento';
    document.getElementById('queue-list').innerHTML = jobs.length ? jobs.slice(0, 20).map(j => `<div class="job-row"><div><strong>${esc(jobLabels[j.status] || j.status)}</strong><small>@${esc(j.channel)} · ${esc(j.created.replace('T',' '))}</small>${j.error ? `<small class="job-error">${esc(j.error)}</small>` : ''}</div><span class="job-pill ${j.status === 'erro' ? 'error' : ''}">${j.status === 'enviado' ? '✓ Concluído' : j.status === 'erro' ? 'Falhou' : 'Em andamento'}</span></div>`).join('') : '<p class="hint">Os novos picos aparecerão aqui. Os cortes anteriores continuam disponíveis em Cortes recentes.</p>';
  } catch (_) { document.getElementById('queue-list').textContent = 'Não foi possível carregar a fila.'; }
}
refreshQueue();
setInterval(refreshQueue, 5000);

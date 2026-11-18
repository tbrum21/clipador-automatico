// As secoes existentes permanecem montadas para preservar formulario e player.
const contentRoot = document.querySelector('.content');
const contentHeading = document.querySelector('.heading');
const metrics = document.querySelector('.grid');
const clipsSection = document.getElementById('clips');
const monitorSection = document.getElementById('monitor');
const logsSection = document.getElementById('logs');
const editingSection = document.getElementById('editor');
const queueView = document.getElementById('queue');
const oldLayout = document.querySelector('.layout');
const views = [metrics, clipsSection, monitorSection, logsSection, editingSection, queueView];
oldLayout.before(clipsSection, monitorSection, logsSection);
oldLayout.remove();
const menus = [
  ['overview', '◫', 'Visão geral', metrics], ['clips', '▷', 'Cortes', clipsSection],
  ['monitor', '◉', 'Monitoramento', monitorSection], ['queue', '◷', 'Fila de cortes', queueView],
  ['editor', '✦', 'Edição', editingSection], ['logs', '≡', 'Logs da atividade', logsSection]
];
const navigation = document.querySelector('.nav');
navigation.innerHTML = menus.map(([id, icon, label]) => `<a href="#${id}" data-view="${id}"><span>${icon}</span><span>${label}</span></a>`).join('');
const headings = {overview:['Visão geral', 'Tudo o que acontece nas suas lives, em um só lugar.'],
  clips:['Cortes', 'Revise os momentos gerados e as avaliações de IA.'],
  monitor:['Monitoramento', 'Escolha e controle o canal acompanhado.'],
  queue:['Fila de cortes', 'Acompanhe cada etapa do processamento.'],
  editor:['Estúdio de edição', 'Ajuste o estilo dos próximos cortes.'],
  logs:['Logs da atividade', 'Acompanhe o funcionamento e os envios.']};
function showView() {
  const id = location.hash.slice(1) || 'overview';
  const current = menus.find(item => item[0] === id) || menus[0];
  views.forEach(view => { view.hidden = view !== current[3]; });
  navigation.querySelectorAll('a').forEach(a => { a.classList.toggle('active', a.dataset.view === current[0]); if (a.dataset.view === current[0]) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  contentHeading.querySelector('h1').textContent = headings[current[0]][0];
  contentHeading.querySelector('.sub').textContent = headings[current[0]][1];
  document.querySelector('.crumb b').textContent = headings[current[0]][0];
}
window.addEventListener('hashchange', showView);
showView();

function addDecisionDetails() {
  if (!state || !state.clips) return;
  document.querySelectorAll('#cliplist .clip').forEach((element, index) => {
    if (element.querySelector('.ai-details')) return;
    const clip = state.clips[index];
    if (!clip || clip.analysis_method !== 'ia') return;
    let decision;
    try { decision = clip.ai_decision && JSON.parse(clip.ai_decision); } catch (_) { decision = null; }
    const details = document.createElement('details');
    details.className = 'ai-details';
    if (!decision || !decision.criteria) {
      details.innerHTML = '<summary>Detalhes da análise</summary><p>Este corte é anterior ao registro de critérios e justificativas.</p>';
    } else {
      const label = decision.rubric_version === 2
        ? {gancho:'Gancho', emocao:'Emoção', compartilhamento:'Compartilhamento', autonomia:'Autonomia'}
        : {gancho:'Gancho', clareza:'Clareza', contexto:'Contexto', fechamento:'Fechamento'};
      const criteria = Object.entries(label).map(([key, text]) => `<span>${text} <b>${esc(decision.criteria[key])}/25</b></span>`).join('');
      const time = n => Number.isFinite(Number(n)) ? Number(n).toFixed(1) + 's' : '—';
      const changed = decision.suggested_start !== decision.start || decision.suggested_end !== decision.end;
      const basis = decision.rubric_version === 2 ? 'Potencial de engajamento estimado pela IA a partir da transcrição; não é probabilidade estatística.' : 'Avaliação anterior, baseada em gancho, clareza, contexto e fechamento.';
      details.innerHTML = `<summary>Ver avaliação da IA</summary><div class="criteria">${criteria}</div><p>${esc(decision.reason)}</p><p>Recomendação: <strong>${decision.publish ? 'publicar' : 'descartar'}</strong> · ${esc(clip.ai_provider)} / ${esc(clip.ai_model)}<br>Trecho aplicado: ${time(decision.start)}–${time(decision.end)} do candidato${changed ? `<br>Trecho sugerido: ${time(decision.suggested_start)}–${time(decision.suggested_end)}` : ''}</p><p>${basis}</p>`;
    }
    element.firstElementChild.append(details);
  });
}
new MutationObserver(addDecisionDetails).observe(document.getElementById('cliplist'), {childList:true, subtree:true});
addDecisionDetails();

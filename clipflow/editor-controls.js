// Controles mantidos separados para nao interferir na atualizacao da lista de cortes.
const editor = document.createElement('section');
editor.className = 'card section editor-settings';
editor.id = 'editor';
editor.innerHTML = `<div class="sectionhead"><div><h2>Estúdio de edição</h2><p>Configure a aparência dos próximos cortes.</p></div><span>✦</span></div>
<div class="mockup-section"><div class="mockup-copy"><span class="mockup-eyebrow">PRÉVIA AO VIVO</span><h3>Imagine seu próximo corte.</h3><p>Um exemplo visual de como o formato, o fundo, a legenda e a marca aparecem juntos.</p><p class="mockup-note">Ilustrativo: o conteúdo, a facecam e o enquadramento dependem da live. O zoom é uma simulação.</p><div class="mockup-tags"><span id="mockup-format-label">9:16 · Vertical</span><span id="mockup-background-label">Fundo desfocado</span></div></div><div class="mockup-stage"><div class="mockup-frame vertical blur" id="mockup-frame" aria-label="Prévia ilustrativa do vídeo"><div class="mockup-backdrop"></div><div class="mockup-game"><div class="mockup-sun"></div><div class="mockup-mountain mountain-back"></div><div class="mockup-mountain mountain-front"></div><div class="mockup-hud"><span>◉ AO VIVO</span><span>✦ CLIPFLOW</span></div><span class="mockup-play">▶</span></div><div class="mockup-watermark top_right" id="mockup-watermark" hidden></div><div class="mockup-caption highlight" id="mockup-caption">ESSE MOMENTO <span>FOI INSANO!</span></div></div></div></div>
<div class="editor-grid">
  <div class="editor-group"><div class="editor-row"><div><strong>Formato e fundo</strong><p>Escolha como o vídeo original será apresentado.</p></div></div>
  <label class="label" for="edit-orientation">Formato do vídeo</label><select class="editor-input" id="edit-orientation"><option value="vertical">Vertical · 9:16 (1080 × 1920)</option><option value="horizontal">Horizontal · 16:9 (1920 × 1080)</option></select>
  <label class="label" for="edit-background">Fundo nas áreas livres</label><select class="editor-input" id="edit-background"><option value="blur">Desfocado</option><option value="black">Preto</option></select><p class="hint">No formato horizontal, a imagem original ocupa o quadro e mantém a facecam original. O fundo aparece somente quando sobrar espaço.</p></div>
  <div class="editor-group"><div class="editor-row"><div><strong>Legendas</strong><p>Exibir palavras transcritas no vídeo.</p></div><input type="checkbox" id="edit-subtitles" aria-label="Ativar legendas"></div>
  <label class="label" for="edit-style">Modelo de legenda</label><select class="editor-input" id="edit-style"><option value="highlight">Destaque · palavra amarela</option><option value="pop">Pop · destaque com movimento</option><option value="clean">Clean · texto branco</option></select>
  <div class="style-preview" id="style-preview">UM <span>MOMENTO</span> INCRÍVEL</div><small class="editor-hint">Prévia ilustrativa. A transcrição usa o Whisper.</small></div>
  <div class="editor-group"><div class="editor-row"><div><strong>Zoom no momento</strong><p>Aplicar zoom próximo ao pico do chat.</p></div><input type="checkbox" id="edit-zoom" aria-label="Ativar zoom"></div>
  <label class="label" for="edit-watermark">Marca-d’água em texto</label><input class="editor-input" id="edit-watermark" maxlength="40" placeholder="Ex.: @seuperfil"><label class="label" for="edit-position">Posição da marca</label><select class="editor-input" id="edit-position"><option value="top_right">Superior direita</option><option value="top_left">Superior esquerda</option><option value="bottom_right">Inferior direita</option><option value="bottom_left">Inferior esquerda</option></select></div>
</div><div class="editor-group" style="margin-top:20px"><div class="editor-row"><div><strong>Duração dos cortes</strong><p>O contexto é capturado em volta do pico antes da escolha do trecho final.</p></div></div>
<label class="label" for="duration-mode">Modo de seleção</label><select class="editor-input" id="duration-mode"><option value="fixed">Fixo · usar todo o contexto</option><option value="pause">Automático · pausas da fala</option><option value="ai">Automático · IA</option></select>
<label class="label" for="ai-provider">Provedor de IA</label><select class="editor-input" id="ai-provider"><option value="openai">OpenAI · GPT</option><option value="anthropic">Anthropic · Claude</option></select><p class="hint" id="provider-status">Verificando configuração...</p>
<div class="editor-grid"><div><label class="label" for="context-before">Segundos antes do pico</label><input class="editor-input" id="context-before" type="number" min="5" max="120" step="1"><label class="label" for="duration-min">Duração mínima (s)</label><input class="editor-input" id="duration-min" type="number" min="5" max="180" step="1"></div><div><label class="label" for="context-after">Segundos após o pico</label><input class="editor-input" id="context-after" type="number" min="5" max="120" step="1"><label class="label" for="duration-max">Duração máxima (s)</label><input class="editor-input" id="duration-max" type="number" min="5" max="180" step="1"></div></div><p class="hint">Nos modos automáticos, os limites se aplicam ao corte final. Sem IA ou se ela falhar, o modo IA usa pausas. O modo fixo usa todo o contexto.</p></div>
<div class="editor-footer"><p id="edit-message" role="status">As alterações valem para os próximos cortes.</p><button class="primary" id="edit-save">Salvar configurações</button></div>`;
document.querySelector('.layout').before(editor);
document.querySelector('.nav').insertAdjacentHTML('beforeend', '<a href="#editor">✦ &nbsp; Edição</a>');
const sub = document.getElementById('edit-subtitles');
const style = document.getElementById('edit-style');
const zoom = document.getElementById('edit-zoom');
const watermark = document.getElementById('edit-watermark');
const position = document.getElementById('edit-position');
const orientation = document.getElementById('edit-orientation');
const background = document.getElementById('edit-background');
const durationMode = document.getElementById('duration-mode');
const provider = document.getElementById('ai-provider');
let aiStatus = {};
function showProviderStatus() {
  const info = aiStatus[provider.value];
  document.getElementById('provider-status').textContent = info
    ? `${info.model} · ${info.configured ? 'chave presente (não validada)' : 'chave não configurada; usará pausas'}`
    : 'Não foi possível verificar a chave.';
}
provider.addEventListener('change', showProviderStatus);
const contextBefore = document.getElementById('context-before');
const contextAfter = document.getElementById('context-after');
const durationMin = document.getElementById('duration-min');
const durationMax = document.getElementById('duration-max');
const message = document.getElementById('edit-message');
const save = document.getElementById('edit-save');
function preview() {
  style.disabled = !sub.checked;
  const example = document.getElementById('style-preview');
  example.className = 'style-preview ' + style.value + (sub.checked ? '' : ' disabled');
  const frame = document.getElementById('mockup-frame');
  frame.className = 'mockup-frame ' + orientation.value + ' ' + background.value + (zoom.checked ? ' zoom-on' : '');
  const caption = document.getElementById('mockup-caption');
  caption.className = 'mockup-caption ' + style.value;
  caption.hidden = !sub.checked;
  const mark = document.getElementById('mockup-watermark');
  mark.textContent = watermark.value.trim();
  mark.hidden = !mark.textContent;
  mark.className = 'mockup-watermark ' + position.value;
  document.getElementById('mockup-format-label').textContent = orientation.value === 'vertical' ? '9:16 · Vertical' : '16:9 · Horizontal';
  document.getElementById('mockup-background-label').textContent = background.value === 'black' ? 'Fundo preto' : 'Fundo desfocado';
}
sub.addEventListener('change', preview);
style.addEventListener('change', preview);
orientation.addEventListener('change', preview);
background.addEventListener('change', preview);
zoom.addEventListener('change', preview);
watermark.addEventListener('input', preview);
position.addEventListener('change', preview);
async function loadEditor() {
  try {
    const response = await fetch('/api/edit-settings');
    if (!response.ok) throw Error('Não foi possível carregar as configurações.');
    const data = await response.json();
    sub.checked = data.subtitles; style.value = data.subtitle_style; zoom.checked = data.zoom;
    watermark.value = data.watermark; position.value = data.watermark_position;
    orientation.value = data.orientation; background.value = data.background;
    durationMode.value = data.duration_mode; contextBefore.value = data.context_before;
    provider.value = data.ai_provider;
    contextAfter.value = data.context_after; durationMin.value = data.min_duration; durationMax.value = data.max_duration;
    const statusResponse = await fetch('/api/ai-status');
    if (statusResponse.ok) aiStatus = await statusResponse.json();
    showProviderStatus();
    save.disabled = false; preview();
  } catch (error) { message.textContent = 'Não foi possível carregar as configurações. Recarregue o painel.'; save.disabled = true; }
}
save.addEventListener('click', async () => {
  save.disabled = true; message.textContent = 'Salvando...';
  try {
    const response = await fetch('/api/edit-settings', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({subtitles: sub.checked, subtitle_style: style.value, zoom: zoom.checked,
        watermark: watermark.value.trim(), watermark_position: position.value, orientation: orientation.value, background: background.value, duration_mode: durationMode.value, ai_provider: provider.value,
        context_before: Number(contextBefore.value), context_after: Number(contextAfter.value),
        min_duration: Number(durationMin.value), max_duration: Number(durationMax.value)})});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Não foi possível salvar.');
    message.textContent = 'Salvo! Aplicado aos próximos cortes.';
  } catch (error) { message.textContent = error.message || 'Não foi possível salvar.'; }
  finally { save.disabled = false; }
});
save.disabled = true;
loadEditor();

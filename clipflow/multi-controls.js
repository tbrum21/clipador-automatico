// Os canais iniciam juntos e compartilham uma unica fila e um bot Telegram.
const firstChannel = document.getElementById('channel');
const firstLabel = document.querySelector('label[for="channel"]');
firstLabel.textContent = 'Canal 1';
const extras = document.createElement('div');
extras.innerHTML = `<label class="label" for="channel-2">Canal 2 (opcional)</label><div class="input"><input id="channel-2" placeholder="Nome ou link do canal" autocomplete="off"></div><label class="label" for="channel-3">Canal 3 (opcional)</label><div class="input"><input id="channel-3" placeholder="Nome ou link do canal" autocomplete="off"></div>`;
firstChannel.closest('.input').after(extras);
const secondChannel = document.getElementById('channel-2');
const thirdChannel = document.getElementById('channel-3');
for (const input of [secondChannel, thirdChannel]) input.addEventListener('input', () => editing = true);
const modeControls = document.createElement('fieldset');
modeControls.className = 'monitor-modes';
modeControls.innerHTML = `<legend>Como gerar cortes</legend>
  <label class="monitor-mode"><input type="checkbox" id="mode-peaks" checked><span><strong>Picos do chat</strong><small>Detecta momentos ao vivo e envia cortes ao Telegram.</small></span></label>
  <label class="monitor-mode"><input type="checkbox" id="mode-recordings" checked><span><strong>Gravações de 1 hora</strong><small>Grava blocos e analisa automaticamente para sugerir cortes.</small></span></label>
  <p class="monitor-mode-hint">Escolha uma ou ambas as opções para todos os canais. Para alterar, pare e inicie novamente.</p>`;
extras.after(modeControls);
const peakMode = document.getElementById('mode-peaks');
const recordingMode = document.getElementById('mode-recordings');
for (const input of [peakMode, recordingMode]) input.addEventListener('change', () => editing = true);
document.getElementById('monitor').querySelector('.hint').textContent = 'Até três canais iniciam e param juntos. Gravações e trabalhos já pendentes permanecem guardados.';
document.getElementById('start').onclick = () => {
  if (!peakMode.checked && !recordingMode.checked) { notice('Selecione pelo menos um tipo de corte.'); return; }
  action('start', {channels:[firstChannel.value, secondChannel.value, thirdChannel.value].map(x=>x.trim()).filter(Boolean), modes:{peaks:peakMode.checked, recordings:recordingMode.checked}});
};
function syncChannels() {
  if (!state) return;
  modeControls.disabled = state.active;
  if (editing) return;
  const names = state.channels || (state.channel ? [state.channel] : []);
  peakMode.checked = state.modes?.peaks ?? true;
  recordingMode.checked = state.modes?.recordings ?? true;
  secondChannel.value = names[1] || '';
  thirdChannel.value = names[2] || '';
  document.getElementById('current').textContent = names.length ? names.map(n=>'@'+n).join(' · ') : 'Nenhum canal';
  if (state.active) document.getElementById('currentstatus').textContent = 'Ativo · ' + [peakMode.checked && 'picos', recordingMode.checked && 'gravações'].filter(Boolean).join(' + ');
}
setInterval(syncChannels, 1000);
syncChannels();

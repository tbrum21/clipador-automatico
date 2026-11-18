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
document.getElementById('monitor').querySelector('.hint').textContent = 'Até três canais iniciam e param juntos. Os cortes usam uma única fila de edição.';
document.getElementById('start').onclick = () => action('start', {channels:[firstChannel.value, secondChannel.value, thirdChannel.value].map(x=>x.trim()).filter(Boolean)});
function syncChannels() {
  if (!state || editing) return;
  const names = state.channels || (state.channel ? [state.channel] : []);
  secondChannel.value = names[1] || '';
  thirdChannel.value = names[2] || '';
  document.getElementById('current').textContent = names.length ? names.map(n=>'@'+n).join(' · ') : 'Nenhum canal';
}
setInterval(syncChannels, 1000);
syncChannels();

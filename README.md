# ClipFlow (motor de cortes de live)

Monitora uma live da Twitch, detecta picos no chat, recorta o trecho do buffer, transcreve (whisper.cpp),
gera legenda palavra por palavra, monta o video 9:16 (fundo desfocado, gameplay, facecam opcional, zoom no
pico, audio normalizado) e envia a previa para o Telegram com botoes Aprovar / Rejeitar.

Pode rodar com Docker Compose no Windows (Docker Desktop com containers Linux) ou em um servidor Linux.
A imagem inclui Python, FFmpeg/FFprobe, fontes para legendas, Streamlink e whisper.cpp v1.8.2.
As versoes das dependencias Python estao fixadas em `requirements.lock` para os builds Docker.
O caminho Docker usa CPU para transcricao e renderizacao (`libx264`); nao utiliza a RX 570.

## 1. Rodar com Docker (recomendado)

Execute os comandos na pasta que contem este README, `Dockerfile` e `compose.yaml`.
No Windows, mantenha o Docker Desktop iniciado e usando containers Linux.

### Preparar

```powershell
# Apenas na primeira configuracao; preserve um .env que ja esteja preenchido.
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data,models,input
docker compose build
docker compose run --rm model
docker compose run --rm tools python -m clipflow.cli check
```

Ou simplesmente `docker compose run --rm tools`, pois o check e seu comando padrao.
O primeiro build baixa dependencias e compila o whisper.cpp; o comando `model` baixa o modelo
multilingue `base` para `models/`. Downloads completos sao reutilizados. Para trocar para `small`,
altere `WHISPER_MODEL_NAME=small` no `.env` e execute `docker compose run --rm model` novamente.

No Linux, prepare as pastas com `mkdir -p data models input` e copie o exemplo com
`cp -n .env.example .env`. Defina `LOCAL_UID` e `LOCAL_GID` no `.env` com os valores de
`id -u` e `id -g` do usuario dono dessas pastas. O padrao do container e `1000:1000`.

### Testar um video local sem Twitch, Telegram ou chave de IA

Copie um video curto com fala para `input/teste.mp4` e execute:

```powershell
docker compose run --rm tools python -m clipflow.cli make /input/teste.mp4 --peak 25 --no-llm
```

`--peak` indica o segundo do momento principal dentro do arquivo. A entrada usa o caminho do
container (`/input/...`), mesmo no Windows. Os resultados ficam em `data/out/`, e a transcricao,
legendas e previa ficam em `data/work/`. Nenhuma credencial externa e necessaria para essa etapa.

### Testar aprovacao no Telegram

Preencha `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` no `.env`. Crie o bot pelo BotFather e envie uma
mensagem a ele antes de testar. Em um terminal, mantenha o bot ouvindo:

```powershell
docker compose run --rm tools python -m clipflow.cli bot
```

Em outro terminal, envie o video:

```powershell
docker compose run --rm tools python -m clipflow.cli make /input/teste.mp4 --peak 25 --no-llm --send
```

Aprovacao copia o MP4 para `data/approved/`; rejeicao registra o status no SQLite.
O caminho mostrado pelo bot e interno ao container (`/app/data/...`), correspondente a `data/`
no computador. Use Ctrl+C para encerrar o bot de teste antes de iniciar o servico da live:
somente um processo deve consultar as atualizacoes do mesmo bot Telegram.

### Iniciar a live

No painel, em **Monitoramento**, informe de um a tres canais e clique em **Iniciar**.
Os canais iniciam e param juntos. Cada um possui seu proprio buffer de video e detector de
chat; a edicao usa uma unica fila compartilhada e um unico bot do Telegram. Uma live offline
nao impede as demais: sua captura tentara reconectar. Consulte os logs para verificar cada
conexao; o indicador de monitoramento significa que o processo esta ativo, nao que todas as
lives estejam online. Para mudar a lista, pare o monitoramento e inicie novamente.
Cada canal tambem abre uma segunda conexao de video para gravar blocos de uma hora. Tres canais
podem portanto usar ate seis fluxos de video, alem de disco e CPU. Se a maquina ficar
sobrecarregada, reduza o numero de canais ou a qualidade. As configuracoes sao compartilhadas.

Preencha tambem `TWITCH_CHANNEL` no `.env` e confirme que o canal esta ao vivo:

```powershell
docker compose run --rm tools python -m clipflow.cli check --live
docker compose up -d clipflow
docker compose logs -f --tail 100 clipflow
```

`check --live` verifica ferramentas, modelo e presenca das configuracoes; nao autentica no
Telegram nem verifica a conexao Twitch. O servico completo ja inclui o bot de aprovacao.
O detector precisa de aproximadamente um minuto de historico de chat antes de disparar.

Para parar: `docker compose down`. Para aplicar mudancas no codigo:
`docker compose up -d --build clipflow`. Mudancas no `.env` exigem recriar o container com
`docker compose up -d --force-recreate clipflow`.

A IA externa e opcional. Para OpenAI, preencha `OPENAI_API_KEY` e escolha `OPENAI_MODEL`
(padrao `gpt-5-mini`); para Claude, use `ANTHROPIC_API_KEY` e `LLM_MODEL`. No painel, selecione
o provedor e o modo de duracao IA. A presenca da chave nao confirma que ela seja valida ou que
o modelo esteja disponivel na conta. Falhas usam pausas e aparecem nos logs. Nunca compartilhe
o arquivo `.env`; modificar a chave exige recriar o container apos encerrar a live.

### Dados e migracao

| Caminho no computador | Conteudo | Caminho no container |
| --- | --- | --- |
| `data/` | Buffer, trabalhos, cortes, aprovados e SQLite | `/app/data` |
| `models/` | Modelos baixados, reutilizados entre containers | `/models` (leitura no servico) |
| `input/` | Videos para testes manuais | `/input` (somente leitura) |
| `templates.json` | Layouts/facecam | `/app/templates.json` (somente leitura) |

Para migrar, pare o servico antes de copiar `data/` para manter o banco e os arquivos consistentes.
Copie o projeto, `.env`, `templates.json`, `data/` e `models/` para o servidor, ajuste o dono das
pastas e execute `docker compose build` e `docker compose up -d clipflow`. `input/` e opcional.
Os caminhos internos permanecem iguais, inclusive os caminhos registrados no SQLite.
O modelo tambem pode ser baixado novamente no destino. Nao rode as duas instancias com o mesmo bot.

O painel publica a porta 8000 apenas no proprio computador (`127.0.0.1`). Twitch, Telegram e IA usam conexoes de saida.
Os arquivos `.env`, modelos, videos e banco nao entram no contexto da imagem.
`docker compose down` preserva as pastas locais. Trabalhos e cortes continuam acumulando em `data/`;
a limpeza automatica existente cobre apenas o buffer da live.

Para a transferencia detalhada a outro computador Windows, consulte `MIGRACAO-SERVIDOR.md`.

Referencias: [whisper.cpp v1.8.2](https://github.com/ggml-org/whisper.cpp/tree/v1.8.2),
[modelos oficiais](https://github.com/ggml-org/whisper.cpp/blob/v1.8.2/models/download-ggml-model.sh),
[variaveis de ambiente no Compose](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/).

## 2. Alternativa: instalacao nativa (Windows)

Perfil original: Windows 10/11, Ryzen 5 3600, RX 570 4 GB (AMD), 16 GB RAM.

1. **Python 3.11+** (python.org, marque "Add to PATH").
2. **FFmpeg**: `winget install Gyan.FFmpeg` (reabra o terminal depois).
3. Dependencias do projeto:
   ```
   cd clipflow
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. **whisper.cpp** (transcricao). Duas opcoes, comece pela A:
   - **A) CPU (mais facil, ja funciona):** baixe o `whisper-bin-x64.zip` em
     github.com/ggml-org/whisper.cpp/releases e extraia em `C:\whisper.cpp`.
   - **B) Vulkan (usa a RX 570):** instale o Vulkan SDK e o CMake, depois
     `cmake -B build -DGGML_VULKAN=1` e `cmake --build build -j --config Release`.
     Confira o README do whisper.cpp, pois os nomes de pastas e flags mudam entre versoes.
   - Modelo: dentro da pasta do whisper.cpp, `models\download-ggml-model.cmd base` (rapido) ou `small` (melhor).
5. **Telegram**: fale com @BotFather, crie um bot e copie o token. Mande uma mensagem ao bot e abra
   `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver seu `chat id`.
6. Copie `.env.example` para `.env` e preencha (canal, caminhos do whisper, token, chat id).
   Para execucao nativa, substitua `WHISPER_BIN` pelo caminho do `whisper-cli.exe` no Windows e
   `WHISPER_MODEL` pelo caminho do arquivo `ggml-base.bin` ou `ggml-small.bin` baixado.
   A chave da IA (`ANTHROPIC_API_KEY`) e opcional.

## 3. Testar na instalacao nativa

```
python -m clipflow.cli check
python -m clipflow.cli make meu_video.mp4 --peak 25 --no-llm --send
```
O segundo comando pega qualquer video (use um clipe seu) e roda o pipeline inteiro, sem precisar de live.
Anote o tempo que a transcricao leva e compare `base` x `small`, CPU x Vulkan.

## 4. Rodar ao vivo na instalacao nativa

```
python -m clipflow.main
```
Deixe o PC sem suspensao e com cabo de rede. Cada pico gera um corte com previa no Telegram; ao aprovar,
o arquivo final vai para `data\approved\`. Poste pelo YouTube Studio (ou outra rede) com credito ao streamer.

## 5. Ajustes

### Estudio de edicao no painel

Acesse `http://localhost:8000` e abra **Edicao**. E possivel ativar ou desativar as legendas,
escolher entre destaque amarelo, Pop animado e Clean branco, ativar o zoom e adicionar uma
marca-d'agua em texto nos quatro cantos. Clique em **Salvar configuracoes**; as escolhas ficam
em `data/edit-settings.json` e sao carregadas no inicio do processamento de cada novo corte.

Em **Formato e fundo**, escolha saida vertical 9:16 (1080x1920) ou horizontal 16:9
(1920x1080), e fundo preto ou desfocado para as areas livres. No formato vertical o quadro
da live e preservado dentro do video vertical; no horizontal a imagem original ocupa o quadro,
sem recorte separado da facecam. Se a imagem original ja for 16:9, o fundo horizontal nao sera
visivel, porque nao havera espaco livre. A previa do Telegram acompanha o formato escolhido.
Alterar as opcoes nao modifica cortes ja processados ou que ja comecaram a ser processados.
Desativar as legendas nao desativa a transcricao, usada na etapa opcional de IA. A marca atual
e texto, nao um arquivo de imagem. O painel mostra uma previa ilustrativa do estilo.

Depois de atualizar os arquivos, execute `docker compose up -d --build clipflow` para aplicar
a nova versao. O comando reinicia o monitor e pode interromper um corte em processamento.

### Fila de processamento

Novos picos aparecem em **Fila de cortes**, com as etapas de extracao, fila, transcricao,
analise, renderizacao, previa e envio. O trecho bruto e extraido logo apos o pico, antes de
aguardar a renderizacao de outros cortes; ele fica em `data/work/`. A fila e os estados sao
registrados no SQLite. Ao reiniciar, trabalhos com trecho bruto e sem corte registrado podem ser
retomados no mesmo canal. Se a extracao for interrompida ou o envio ficar incerto, a fila exibe
um erro; confira o Telegram antes de qualquer reenvio. Eventos anteriores a essa atualizacao
continuam na lista de cortes, mas nao aparecem retroativamente na fila.

### Duracao dos cortes

No **Estudio de edicao**, defina o contexto antes e depois do pico. O modo **Fixo** usa o
trecho inteiro. **Pausas** tenta encontrar bordas em intervalos da transcricao e respeita os
limites de duracao quando ha contexto suficiente. **IA** pede ao modelo selecionado para escolher
as bordas e usa pausas caso falte chave, falte transcricao ou a chamada falhe. Os parametros
ficam associados ao pico no momento em que ele e detectado, mesmo se forem alterados enquanto
o corte espera na fila. O padrao preserva 25 segundos antes e 10 depois, em modo fixo.

Para experimentar selecao variavel, use 60 segundos antes, 30 depois e limites de 15 a 90
segundos. Esperar mais apos o pico aumenta a latencia, e analisar um trecho maior exige mais
CPU e memoria. O modo IA requer chave e modelo validos para o provedor no `.env`. A analise
usa a transcricao, nao as imagens. Uma nota 50 na base corresponde a valor padrao quando nao
houve nota da IA; nao interprete como avaliacao real.

Nos cortes avaliados com a rubrica atual, a nota e a soma de quatro criterios de 0 a 25:
gancho, emocao, potencial de compartilhamento e autonomia fora da live. A IA justifica a
avaliacao e sugere publicar ou descartar. A analise e editorial e baseada somente na transcricao;
nao e uma probabilidade estatistica de viralizacao. Cortes avaliados antes dessa rubrica mantem
seus criterios originais e nao entram na media da rubrica nova.

### Analisar uma gravacao

Copie um video `.mp4`, `.mov`, `.mkv` ou `.webm` para a pasta `input/`, pare o
monitoramento e abra **Gravacoes** no painel. Escolha o arquivo e inicie a analise. O sistema
analisa no maximo os primeiros 60 minutos, em blocos com sobreposicao pelo menos igual a
duracao maxima configurada. Cada bloco e transcrito localmente e sua transcricao enviada ao
provedor de IA selecionado em **Edicao**; e necessaria uma chave valida e pode haver custo
de API. A analise usa texto, nao imagens, e nao depende do chat. A nota dos candidatos e
uma estimativa editorial e nao usa a mesma rubrica do monitoramento ao vivo.

O painel exibe ate cinco sugestoes sem sobreposicao. Use **Rever trecho** para conferir o
video de origem (a reproduçao depende do codec suportado pelo navegador) e **Renderizar corte**
para gerar apenas a sugestao escolhida. O resultado aparece em **Cortes**, onde pode ser
aprovado ou rejeitado; nao e enviado automaticamente ao Telegram. A renderizacao usa as
configuracoes de edicao salvas no inicio da analise, exceto zoom automatico de pico, que nao
se aplica a gravacoes. O arquivo adicionado manualmente permanece em `input/`; a analise
manual exige monitoramento parado. A renderizacao pode esperar na fila mesmo durante uma live.

### Gravacao automatica por hora

Em **Monitoramento**, selecione **Picos do chat**, **Gravacoes de 1 hora** ou ambas as opcoes
antes de iniciar. A escolha vale para todos os canais e fica salva para a retomada. Para mudar,
pare e inicie novamente. Apenas picos usam o buffer de live e o chat; apenas gravacoes dispensa
o Telegram. Trabalhos por pico pendentes aguardam a proxima ativacao de picos; gravacoes ja
concluidas continuam na fila automatica mesmo se a gravacao de novas horas estiver desativada.

Quando as gravacoes de uma hora estao ativadas, cada canal grava blocos em `data/hourly/`. Quando um
bloco e concluido e convertido em MP4, ele entra automaticamente na fila de analise; o provedor
de IA escolhido recebe sua transcricao e pode gerar custo. As tarefas pesadas sao serializadas
com a edicao dos cortes de pico. A fila compartilhada atende os trabalhos pesados por ordem
de chegada; a analise libera o recurso entre blocos de ate cinco minutos, voltando ao fim da
fila para o proximo bloco. A secao **Fila de cortes** mostra a ordem atual e o tempo decorrido,
sem prever quando cada tarefa terminara. Cortes de pico ainda podem esperar a conclusao do
bloco em andamento, e a fila pode crescer se a chegada de trabalho superar a capacidade do PC.
Na secao **Gravacoes**, examine as sugestoes, rejeite as que
nao quiser e renderize as demais; depois aprove ou rejeite os cortes gerados em **Cortes**.

O original automatico e excluido permanentemente somente depois que houver pelo menos uma
sugestao, todas forem rejeitadas ou seus cortes renderizados tiverem sido aprovados/rejeitados,
e cada copia aprovada tiver sido confirmada. Sem sugestoes, em caso de falha, ou se o arquivo
tiver sido alterado, ele e mantido. Uma analise com erro pode ser reenfileirada no painel.
Os videos adicionados manualmente nao sao apagados. Se a live cair ou o monitoramento for
parado antes de uma hora, o arquivo parcial permanece em `data/hourly/` e nao e enviado
automaticamente para analise. Pode haver pequeno intervalo entre blocos ao reconectar o fluxo.
Uma analise automatica interrompida pelo reinicio pode ser iniciada novamente e gerar custo.

- **Muitos/poucos alertas:** `PEAK_Z` (maior = mais exigente) e `PEAK_MIN_MSGS` no `.env`.
- **Facecam:** em `templates.json`, crie uma entrada com o nome do canal e as posicoes em fracao do frame
  (x, y, w, h de 0 a 1). Sem entrada, usa `default` (so gameplay).
- **Encoder:** o Docker fixa `libx264` (CPU). Na instalacao nativa, `ENCODER=h264_amf` habilita AMD quando disponivel.
- **Zoom:** `ZOOM=0` desliga.

## 6. O que foi testado e o que nao foi

Validado no Docker Desktop com containers Linux: build da imagem, download e reutilizacao do modelo
`base`, diagnostico de dependencias/configuracao e pipeline completo com whisper.cpp real em CPU.
O teste usou um video sintetico de 16 segundos e o audio em ingles
[`jfk.wav` do whisper.cpp](https://github.com/ggml-org/whisper.cpp/blob/v1.8.2/samples/jfk.wav).
Foram verificadas legendas ASS com destaque por palavra, render com zoom, audio, MP4 H.264 em
1080x1920 e previa em 540x960. Um frame do resultado foi inspecionado visualmente.

O README original tambem registra testes simulados do detector e do layout com facecam.
**Ainda nao validado nesta configuracao:** captura Twitch real, aprovacao real pelo Telegram,
Anthropic, qualidade da transcricao em portugues, Vulkan e h264_amf. Os comandos de teste local
acima permitem validar as etapas que dependem do seu video e das suas credenciais.

## 7. Proximos passos

Corte de silencio, mais de um template, deteccao por audio, postagem via API do YouTube, varios streamers
e migracao para VPS.

## Aviso

Republicar trechos de lives de terceiros pode gerar DMCA/strikes e a monetizacao no YouTube exige
contribuicao original. Mantenha a aprovacao humana, credite o streamer e acrescente comentario proprio.

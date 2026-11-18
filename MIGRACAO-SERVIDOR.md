# Levar o ClipFlow para outro computador Windows

O pacote leva o codigo e a configuracao de exemplo. Ele **nao** contem chaves, banco, videos,
modelo Whisper ou configuracoes pessoais; escolha abaixo o que transferir de modo privado.
Nao extraia por cima de uma instalacao que ja tenha dados sem fazer backup primeiro.

## 1. Preparar a transferencia no computador atual

O arquivo ZIP deve ser extraido em uma pasta propria no servidor. Transfira em separado, por
um meio privado:

- `.env`: mantem os tokens do Telegram e da OpenAI. Trate como senha; nao coloque o arquivo
  em repositorio, mensagens de grupo ou armazenamento compartilhado publicamente. Se preferir,
  configure um `.env` novo no destino a partir de `.env.example`.
- `data/` (opcional): necessario para levar historico, banco SQLite, configuracoes do painel,
  filas, trabalhos, videos e gravacoes pendentes. Pode ocupar muito espaco.
- `models/` (opcional): evita baixar novamente o modelo Whisper; caso contrario use o comando
  de download abaixo. `input/` e opcional e contem seus videos de entrada manuais.

Para copiar `data/`, primeiro pare o monitoramento no painel, aguarde o encerramento dos
processamentos e, na pasta do projeto no computador atual, execute:

```powershell
docker compose down
```

Confira se nao ha analise ou renderizacao em andamento antes de parar: tarefas interrompidas
podem precisar ser retomadas. Copie a pasta completa `data/` somente com o container parado,
para manter o SQLite e seus arquivos consistentes. Preserve tambem `templates.json` se o seu
foi personalizado (ele ja faz parte do pacote). Se usar os mesmos dados e bot, mantenha a
instalacao antiga parada durante a operacao no servidor.

## 2. Preparar o computador servidor

1. Abra o Docker Desktop, escolha containers Linux e espere o motor ficar pronto. O build
   precisa de acesso a Docker Hub, Debian, PyPI e GitHub; o modelo e baixado do Hugging Face.
2. Extraia o ZIP, por exemplo, em `C:\ClipFlow`. A pasta escolhida deve conter `compose.yaml`
   e `Dockerfile` diretamente. Copie nela o `.env` privado e, se quiser, `data/`, `models/`
   e `input/`. Nao sobrescreva dados existentes sem verificar.
3. Abra o PowerShell nessa pasta. Se voce nao copiou um `.env`, crie e edite um novo:

```powershell
cd C:\ClipFlow
Copy-Item .env.example .env
notepad .env
```

Preencha `TWITCH_CHANNEL`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` e, para analise com GPT,
`OPENAI_API_KEY`. O canal tambem pode ser configurado no painel. Use um modelo disponivel na
sua conta em `OPENAI_MODEL`. Para Claude, configure `ANTHROPIC_API_KEY` e `LLM_MODEL`.
Nao substitua um `.env` que voce tenha copiado. Salve e feche o editor.

4. No PowerShell, execute:

```powershell
cd C:\ClipFlow
New-Item -ItemType Directory -Force data,models,input | Out-Null
docker compose build
docker compose run --rm model
docker compose run --rm tools python -m clipflow.cli check --live
```

O primeiro build compila o whisper.cpp e pode demorar. O modelo `base` e baixado em `models/`;
se ele ja foi copiado, o download e reutilizado. `check --live` verifica apenas a presenca das
ferramentas e configuracoes, nao testa as credenciais ou se a live esta online.

5. Para iniciar o painel sem iniciar automaticamente uma captura nesta primeira verificacao:

```powershell
New-Item -ItemType File -Force data\monitor-paused | Out-Null
docker compose up -d clipflow
docker compose ps
```

Abra **http://localhost:8000** no navegador do servidor. Confirme canais e ajustes de Edicao e
so entao use **Monitoramento > Iniciar**. Ao iniciar o monitoramento, cada canal tambem grava
automaticamente blocos de uma hora; a transcricao dos blocos completos e enviada ao provedor de
IA selecionado e pode gerar custo. Confirme espaco em disco e conectividade antes de usar tres
canais. Um unico bot Telegram deve ser utilizado por uma unica instancia ativa.

O painel e acessivel apenas no proprio servidor (`127.0.0.1`), sem autenticacao. Para acesso
remoto use uma solucao de acesso remoto protegida; nao exponha a porta diretamente na internet.

## 3. Operacao

```powershell
# Acompanhar logs; Ctrl+C apenas deixa de acompanhar.
docker compose logs -f --tail 100 clipflow

# Parar o container apos encerrar o monitoramento pelo painel.
docker compose down

# Recriar apos mudar .env ou atualizar o codigo.
docker compose up -d --build clipflow
```

O Docker Desktop e o sistema operacional precisam estar ligados, com suspensao desativada para
operacao continua. A politica de reinicio do container nao substitui a inicializacao do Docker
Desktop nem o login quando o Windows os exigir. Configure o Docker Desktop para iniciar com o
Windows, conforme suas preferencias, e verifique o funcionamento apos reiniciar a maquina.

Faca backups periodicos de `data/` enquanto o servico estiver parado e guarde o `.env` em local
seguro. A exclusao automatica dos originais de blocos proprios ocorre apos a revisao completa;
gravacoes parciais, falhas e sem sugestoes sao mantidas. Verifique espaco em disco regularmente.
O processamento usa CPU (`libx264`); a imagem nao esta configurada para usar GPU.

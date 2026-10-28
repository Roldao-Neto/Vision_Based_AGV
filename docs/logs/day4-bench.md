# Dia 4 — Bancada: captura do dataset

## 1. Ferramenta de captura dentro do app

### O que foi feito e por quê

Foi construída uma ferramenta de captura **dentro do próprio app**: as imagens do dataset têm de sair exatamente do mesmo caminho de código que a inferência vai usar no Dia 5. Assim, o modelo treina com os mesmos quadros que vai ver no robô: a mesma câmera, as mesmas configurações automáticas de imagem, 1280 × 720 em MJPG e a mesma decodificação do OpenCV.

`Camera.open()` só abre a câmera e fixa o formato: não trava nenhum controle de imagem e não espera os 8 s de aquecimento que o travamento do foco exigia. Quando a ferramenta foi construída, `open()` ainda travava exposição, balanço de branco, foco e zoom; essa trava foi removida depois da verificação na placa (item 3).

A ferramenta tem quatro partes:

- **thread de captura** (`python/capture.py`): lê todos os quadros e guarda só o último par `(frame, t)`. É a mesma thread que o Dia 5 usa para a inferência, por isso já foi feita no formato definido no `CLAUDE.md` (a inferência fora do laço de captura, para que um quadro nunca seja mais velho que o seu carimbo de tempo);
- **carimbo de tempo** (`Camera.read()` devolve `(frame, t)`): t é o tempo do buffer V4L2, que o Dia 5 vai casar com a pose. A conferência desse relógio na placa continua no Dia 5;
- **pré-visualização** na página da missão: o último quadro reduzido para 640 × 360, em JPEG, no máximo 10 quadros/s, para gastar pouca CPU;
- **botão Capture**: baixa o último quadro inteiro (1280 × 720) em PNG, sem perdas, como `im_N.png` direto no PC. Nada é gravado na placa, então o armazenamento dela não enche. Fica só até o fim do dataset; depois sai da página.

### Comandos e código

```bash
uv run pytest
uvx basedpyright python bricks
./deploy.sh
```

Código (versões finais no apêndice):

- `bricks/opencv_camera_handler/camera.py`: `open()` e `read()`;
- `python/capture.py`: `Capture`;
- `python/webui.py`: `preview()` e as rotas `/snapshot.png` e `/snapshot/next`;
- `python/main.py`: as ligações;
- `tests/test_capture.py`, `tests/test_webui.py`;
- `pyproject.toml`: `bricks` no `pythonpath` do pytest, para os testes importarem `opencv_camera_handler`.

### Explicação passo a passo

**`Camera.open()`** abre o dispositivo com `cv2.VideoCapture(dispositivo, cv2.CAP_V4L2)`, pede MJPG, 1280 × 720 e um buffer de 1 quadro (`CAP_PROP_BUFFERSIZE = 1`), e então lê de volta a largura e a altura: se a câmera não aceitou 1280 × 720, libera o dispositivo e levanta `RuntimeError`. A resolução é a única coisa conferida, porque mudá-la invalida a homografia do chão e os k de `Z = k/h` do Dia 5.

**`Camera.read()`** lê um quadro e devolve também `cap.get(cv2.CAP_PROP_POS_MSEC) / 1000`, o tempo do buffer V4L2 em segundos. Para uma câmera UVC esse relógio é o `CLOCK_MONOTONIC` (o de `time.monotonic()`), tomado quando o quadro começa a chegar.

**`Capture.run()`** chama `open()` e registra o evento `camera_open`; depois, em laço, `self._latest = self._camera.read()`. Uma falha em `open()` ou em `read()` vira o evento `camera_error` (com `open:` ou `read:` na frente) e encerra a thread, liberando a câmera. `latest()` devolve o último par, ou `None` antes do primeiro quadro. Os leitores não precisam copiar nem travar nada: cada `read()` do OpenCV devolve um array novo (`cap_v4l.cpp` copia para a saída do chamador), então o array que um leitor segura nunca é sobrescrito.

**`preview()`** é o gerador do MJPEG em `/video_feed` (`Server.video` do brick `flask_video_webui`): a cada 0,1 s pega o último quadro, reduz com `cv2.INTER_AREA` para 640 × 360, codifica em JPEG qualidade 80 e emite uma parte `--frame`.

**`/snapshot.png?n=N`** codifica o último quadro em PNG na memória (`cv2.imencode(".png", ...)`) e o devolve como anexo `im_N.png`, com `Cache-Control: no-store`. Sem quadro ainda, responde 503 e não conta nada. A placa guarda na memória o próximo N e só o avança quando uma imagem sai; depois de reiniciar o app volta a 1, mas o N é editável na página, e `/snapshot/next` informa à página onde a placa está.

**O botão Capture** busca `/snapshot.png?n=N`, transforma a resposta num link de download com o nome `im_N.png`, clica nele e incrementa o N da página. Uma falha aparece abaixo do botão.

### Resultados

- `uv run pytest`: 49 testes passam, entre eles os novos: o par mais recente e o `camera_error` de leitura e de abertura (`tests/test_capture.py`); o PNG idêntico, pixel a pixel, ao quadro BGR de 1280 × 720, o 503 antes do primeiro quadro, a numeração e a nenhuma chamada à Bridge; a pré-visualização em JPEG de 640 × 360 (`tests/test_webui.py`).
- `uvx basedpyright python bricks`: 0 erros, 0 avisos.
- Na placa: ver o item 2.

### Conclusões

O dataset sai do mesmo `Camera` e da mesma thread de captura que a inferência vai usar, sem perdas e sem ocupar o armazenamento da placa.

## 2. Verificação na placa

### O que foi feito e por quê

Rolds fez o deploy da ferramenta (ainda com os controles travados) e a testou na placa, para confirmar a pré-visualização e o Capture antes de capturar o dataset.

*Detalhes a confirmar com Rolds: data e hora, o que foi conferido além da pré-visualização e do Capture (o `camera_open`, o 503, a resolução do `im_1.png`, a CPU) e como as imagens ruins se apresentavam.*

### Comandos

```bash
./deploy.sh
```

Depois, a página do app na porta 8888.

### Explicação

`deploy.sh` para o app, sincroniza `app.yaml`, `python/`, `sketch/`, `bricks/` e `models/` e inicia o app de novo. A thread de captura abre a câmera logo no início do app, e a página mostra a pré-visualização abaixo da arena.

### Resultados

- A pré-visualização apareceu na página e o Capture baixou as imagens: a ferramenta funciona na placa.
- As imagens com os controles travados ficaram ruins. *Como (escuras, borradas, com cor errada) a confirmar com Rolds.*

### Conclusões

A ferramenta está pronta, mas as configurações travadas não servem para o dataset: ver o item 3.

## 3. Remoção das travas dos controles da câmera

### O que foi feito e por quê

Decisão de Rolds, no Dia 4: `Camera.open()` não trava mais nenhum controle de imagem; fica só MJPG em 1280 × 720. Exposição, balanço de branco e foco ficam automáticos.

Os motivos:

- as configurações travadas davam imagens ruins (item 2);
- foram escritas para o plano antigo com ArUco, em que a pose vinha da câmera pela solvePnP com parâmetros intrínsecos fixos, e um foco ou zoom diferente os mudaria. Esse plano caiu: a localização é só odometria, e a câmera só detecta obstáculos e estima onde estão;
- o travamento não era confiável: o foco só "pegava" depois de cerca de 8 s de stream, e só pelo `cap.set` do OpenCV;
- a margem de erro do projeto cobre os erros de detecção e de tamanho que o ajuste automático possa causar.

A mudança foi feita **antes** de capturar o dataset, para que o dataset, a inferência e a calibração de distância do Dia 5 usem as mesmas configurações automáticas.

### Comandos e código

```bash
uv run pytest
uvx basedpyright python bricks
```

Em `bricks/opencv_camera_handler/camera.py` saíram:

- a tabela de ioctls V4L2 (`_G_CTRL`, `_S_CTRL`, `_CID`) e `_ctrl()`, que liam e escreviam os controles direto no dispositivo, porque o `v4l2-ctl` não existe dentro do contêiner do app;
- `CONTROLS` (16 controles: foco automático, exposição automática e balanço de branco automático desligados, exposição 156, ganho 64, temperatura de cor 4000 K, zoom 100, etc.), `FOCUS = 0` e `ZOOM = 100`;
- o aquecimento de 8 s (`warm_up_seconds`), a trava do foco no fim e o erro `focus lock failed`;
- os `print` de `verbose`.

Ficaram `open()` (abre com `CAP_V4L2`, MJPG, 1280 × 720, buffer de 1 quadro, confere a resolução), `read()` → `(frame, t)` e `release()`. A docstring da classe registra a decisão.

No `docs/ROADMAP.md`, saiu do Dia 5 o item que mandava `open()` falhar também quando zoom, exposição ou balanço de branco não pegassem. No `CLAUDE.md`, a descrição de `bricks/opencv_camera_handler` e a seção *Camera* agora dizem que os controles ficam automáticos.

### Explicação passo a passo

O `open()` novo é o começo do antigo, até a conferência da resolução; tudo o que vinha depois (o aquecimento, o laço sobre `CONTROLS` e a trava do foco) saiu. Sem nenhum `set` de controle, a câmera usa o que estiver ativo nela.

**Os controles UVC ficam guardados na câmera** enquanto ela está ligada, não no processo que os escreveu. Lidos na placa com o app ainda rodando a versão antiga (o `v4l2-ctl` existe no Debian da placa, só não no contêiner):

```bash
ssh unoq 'v4l2-ctl -d /dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920-video-index0 \
  -C focus_automatic_continuous,auto_exposure,white_balance_automatic,focus_absolute,zoom_absolute,exposure_time_absolute'
```

| Controle | Valor |
|---|---|
| `white_balance_automatic` | 0 |
| `focus_automatic_continuous` | 0 |
| `auto_exposure` | 1 (Manual Mode) |
| `focus_absolute` | 0 |
| `zoom_absolute` | 100 |
| `exposure_time_absolute` | 156 |

Como o `open()` novo não escreve nada, a câmera continua nesses valores travados depois do deploy até ser desligada. *Pendente:* desconectar e reconectar a câmera (ou reiniciar a placa) uma vez, e conferir com `v4l2-ctl --list-ctrls` que cada controle voltou ao seu `default`, antes de capturar o dataset.

### Resultados

- `uv run pytest`: 49 testes passam (os testes usam uma câmera falsa, então não mudaram).
- `uvx basedpyright python bricks`: 0 erros, 0 avisos.
- Na placa: *pendente* (deploy, volta dos controles ao automático, imagens do Capture).

### Conclusões

A câmera fica com o ajuste automático de fábrica e só o formato é fixado. O dataset ainda não foi capturado, então ele, a inferência e a calibração do Dia 5 vão usar as mesmas configurações.

## Apêndice — versões finais dos arquivos

*Preenchido ao fim do bloco.*

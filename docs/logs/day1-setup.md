# Dia 1 — Setup: toolchain, Bridge e tick de controle

> **Arquivo:** o código, os dados e os gráficos deste dia estão no branch `day1` (tag `day1-final`), com os dados em `results/day1/`. No `main`, parte do código citado aqui foi removida depois do Dia 1, e `data/day1/` não é versionado.

## Ordem cronológica real

| # | Etapa | Seção |
|---|---|---|
| 1 | Versões da placa + `system update` | 1 |
| 2 | Chave SSH, inspeção e backup dos apps da placa, instalação do `rsync` | 2 |
| 3 | `deploy.sh`, primeiros deploys, correção do OpenCV | 3, 5 |
| 4 | `sketch.yaml` a partir de um app de rascunho | 6 |
| 5 | Cópia corrigida da Bridge | 7 |
| 6 | `board-versions.txt` e fixação do `arduino_app_bricks` | 8 |
| 7 | App mínimo + `run_log.py` | 9, 4 |
| 8 | Tick de controle | 10 |
| 9 | Teste de estresse do pico e decisão | 11 |

## 1. Versões da placa primeiro

### O que foi feito

Foram lidas as versões das bibliotecas da placa para garantir um funcionamento dentro do esperado.

- arduino-app-cli ≥ 0.11,
- arduino-router ≥ 0.8.0
- Zephyr core 1.0.0)

Se algo estivesse mais antigo, o `system update` seria feito **agora**, porque depois disso as versões ficam congeladas até o fim do Dia 7.

### Comandos

No terminal da placa (aberto pelo App Lab):

```bash
hostname -I

# Update para Garantir
arduino-app-cli system update

arduino-app-cli version
arduino-router version
arduino-app-cli config get
arduino-app-cli app list
```

### Resultados

| Item | Mínimo exigido | Na placa |
|---|---|---|
| `arduino-app-cli` | ≥ 0.11 | **0.13.0** (daemon 0.13.0) ✓ |
| `arduino-router` | ≥ 0.8.0 | **0.10.0** ✓ |
| plataforma `arduino:zephyr` | 1.0.0 | **1.0.0** ✓ |

- `Data`: /var/lib/arduino-app-cli
- `Apps`: /home/arduino/ArduinoApps.

### Conclusões

- Todas as versões atendem ao mínimo. O update rodou uma única vez, no início, como manda o
  ROADMAP. **A partir daqui não há mais `system update`, `apt upgrade` nem update pelo App Lab até o
  fim do Dia 7.**
- O app de destino do deploy ainda não estava definido; isso foi resolvido na seção 2.

## 2. Antes do primeiro `deploy.sh` (acesso SSH e backup)

### 2.1 Acesso SSH por chave

#### O que foi feito

Configuração do SSH sem senha do PC para a placa.

#### Comandos

No PC:

```bash
ssh-keygen -t ed25519 -C "rolds-pc"
ssh-copy-id arduino@192.168.1.24
```

`~/.ssh/config`:

```
Host unoq
    HostName 192.168.1.24
    User arduino
```

#### Resultado

`ssh OK` / `uno2GB`, sem senha.

### 2.2 Backup: o `rsync` não existe na placa

#### O que aconteceu

A imagem da placa não traz `rsync`, e o `deploy.sh` depende dele dos dois lados. Por isso, ele teve que ser instalado a parte com o `apt`.

#### Comandos do backup (com `tar` pelo ssh)

```bash
dst=/home/rolds/Documents/Unifei/TCC_Artifacts/board_backup_20261010
mkdir -p "$dst"
ssh unoq 'cd /home/arduino/ArduinoApps && tar cf - --exclude=.cache --exclude=.venv --exclude=__pycache__ .' \
  | tar xf - -C "$dst"
```

#### Resultados

- Backup: 27 arquivos em `../TCC_Artifacts/board_backup_20261010/`.
- rsync instalado corretamente.

### 2.3 Pasta de destino do app

`/home/arduino/ArduinoApps/agv` → ID `user:agv`. 

Os apps antigos ficam intocados (e já estão no backup).

### Conclusões da seção 2

- Acesso SSH por chave funcionando com o apelido `unoq`.
- Tudo o que só existia na placa está salvo fora do repositório.
- `rsync` instalado sem atualizar nenhum pacote (o congelamento continua válido).

## 3. `deploy.sh`

Funcionou em 2 min 12 s (compilou o sketch, gravou o STM32 por SWD com o OpenOCD, criou o container
e iniciou o app). Linhas relevantes:

```
[INFO] Board platform: arduino:zephyr (1.0.0) in /home/arduino/.arduino15/packages/arduino/hardware/zephyr/1.0.0
[INFO] Used library Arduino_RouterBridge (0.4.3) in /home/arduino/.arduino15/internal/Arduino_RouterBridge_0.4.3_456a4ab6b378b066/Arduino_RouterBridge
[INFO] Used library Arduino_RPClite (0.3.1) in ...
[INFO] Used library MsgPack (0.4.2) in ...
[INFO] Used library DebugLog (0.8.4) in ...
[INFO] Used library ArxTypeTraits (0.3.2) in ...
[INFO] Used library ArxContainer (0.7.0) in ...
✓ App "AGV" started successfully
```

```bash
ssh unoq 'mkdir -p /home/arduino/ArduinoApps/agv/logs &&
  echo board_a > /home/arduino/ArduinoApps/agv/logs/test_pull_a.csv &&
  echo board_b > /home/arduino/ArduinoApps/agv/logs/test_pull_b.csv'
mkdir -p data/pulltest && echo pc_b > data/pulltest/test_pull_b.csv
./deploy.sh pull pulltest
```

## 4. Logs por execução (`run_log.py`)

O python/run_log.py garante quatro coisas:

1. Nome único e nada sobrescrito.
   - run_name (linha 36) monta o nome no formato AAAAMMDD-HHMMSS_<mode>_<params>, com hora UTC.
   - RunLog abre o arquivo com open(path, "x", ...) (linha 22). O modo "x" falha com FileExistsError se o arquivo já existe.
   - Nesse caso, open_run_log (linhas 53–58) tenta de novo com -1, -2… no fim do nome. Isso cobre dois logs com o mesmo nome criados no mesmo segundo.
2. Nenhuma linha perdida no app stop. buffering=1 faz cada linha ir para o disco assim que é escrita. Os handlers da Bridge rodam em outra thread, e os arquivos dessas threads nunca são fechados no app stop (a docstring explica isso). Sem o buffer por linha, as últimas linhas se perderiam.
3. Escrita segura entre threads. row() usa um threading.Lock (linhas 27–29), então duas threads não misturam linhas no mesmo arquivo.
4. Formato CSV com cabeçalho. O arquivo é escrito com csv.writer, e o cabeçalho é a primeira linha. A pasta /app/logs é criada se não existir (linha 50).

## 5. OpenCV 4.13 na placa

### Comandos

```bash
ssh unoq 'docker logs agv-main-1 2>&1 | head -60'
ssh unoq 'docker exec agv-main-1 cat /run.sh'
ssh unoq 'docker exec agv-main-1 sh -c "env | grep -iE \"^UV|PIP\"; cat /etc/uv-constraints.txt"'
ssh unoq 'docker exec agv-main-1 sh -c "pip list | grep -iE \"opencv|edge|six|flask|arduino|numpy|msgpack\""'
```

### Resultados

Log do container no primeiro deploy:

```
× No solution found when resolving dependencies:
╰─▶ Because there is no version of opencv-python-headless==4.13.0+1ddb20b
    and you require opencv-python-headless==4.13.0+1ddb20b, we can conclude
    that your requirements are unsatisfiable.
```

- A imagem (`ghcr.io/arduino/app-bricks/python-apps-base:0.12.0`) já traz
  `opencv-python-headless 4.13.0+1ddb20b`, uma build local (o `+1ddb20b` indica isso) que **não
  existe no PyPI**, e a trava com `UV_CONSTRAINT`.

- Simulação sem a linha do OpenCV: resolve 9 pacotes (`edge-impulse-linux 1.2.2`, `flask 3.1.3`,
  `six 1.17.0`, `blinker`, `click`, `itsdangerous`, `jinja2`, `markupsafe`, `werkzeug`).

### Explicação

A imagem define `UV_CONSTRAINT=/etc/uv-constraints.txt`, e esse arquivo contém `opencv-python-headless==4.13.0+1ddb20b`.

### Decisão

Tirar o OpenCV do `requirements.txt` e mantê-lo só no grupo `dev` do `pyproject.toml`:

Depois do deploy seguinte:

```
Resolved 9 packages in 4.62s
Installed 9 packages in 13ms
 + blinker==1.9.0  + click==8.5.0  + edge-impulse-linux==1.2.2  + flask==3.1.3
 + itsdangerous==2.2.0  + jinja2==3.1.6  + markupsafe==3.0.4  + six==1.17.0  + werkzeug==3.1.9
```

Versões no venv do app: `arduino_app_bricks 0.12.0`, `edge_impulse_linux 1.2.2`, `flask 3.1.3`,
`six 1.17.0`, `opencv-python-headless 4.13.0+1ddb20b`, `numpy 2.5.1`; Python 3.13.14. O
`installed_requirements.txt` foi gravado, então os próximos starts não reinstalam nada.

### Conclusões

- O OpenCV 4.13 está garantido **pela própria imagem**, não pelo `requirements.txt`.
- Lição: o `/run.sh` falha em silêncio. Depois de mudar o `requirements.txt`, é preciso olhar o log
  do container (`arduino-app-cli app logs ...`).

## 6. `sketch/sketch.yaml`

```yaml
profiles:
  default:
    fqbn: arduino:zephyr:unoq
    platforms:
      - platform: arduino:zephyr
    libraries:
default_profile: default
```

O `fqbn` só é lido pelo build do PC; a placa compila com o FQBN da plataforma (fonte: `compileUploadSketch`, que usa `platform.FQBN`).

## 7. Cópia corrigida do `Arduino_RouterBridge`

### O que foi feito e por quê

Na versão 0.4.3 (a mais recente publicada), a thread da Bridge no STM32 tem só **500 bytes** de pilha, e o caminho de leitura de uma mensagem já usa ~496 bytes antes das funções que ele chama. Um estouro de pilha corromperia a memória em silêncio. 

A solução combinada é uma cópia local da 0.4.3 com duas mudanças:

1. pilha de 2048 bytes (a mesma mudança da 0.4.4, ainda não publicada);
2. preencher a pilha com o padrão `0xAA` antes de criar a thread, para medir o pico de uso.

### Comandos

```bash
# Tags disponíveis e clone da 0.4.3
git ls-remote --tags https://github.com/arduino-libraries/Arduino_RouterBridge
git clone --depth 1 --branch 0.4.3 https://github.com/arduino-libraries/Arduino_RouterBridge bridge-0.4.3

# Cópia que a placa usa hoje, para comparar com a tag
mkdir board-bridge
ssh unoq 'cd /home/arduino/.arduino15/internal/Arduino_RouterBridge_0.4.3_456a4ab6b378b066/Arduino_RouterBridge && tar cf - .' \
  | tar xf - -C board-bridge
diff -r -x .git bridge-0.4.3 board-bridge

# O que a 0.4.4 muda no bridge.h
cd bridge-0.4.3 && git fetch --depth 50 origin ver_0_4_4_rc && git diff 0.4.3 FETCH_HEAD -- src/bridge.h

# A cópia no projeto
mkdir -p sketch/libraries/Arduino_RouterBridge
cp -r bridge-0.4.3/src bridge-0.4.3/library.properties sketch/libraries/Arduino_RouterBridge/
```

Configuração do Zephyr da placa:

```bash
ssh unoq 'A=.../variants/arduino_uno_q_stm32u585xx/llext-edk/include/zephyr/include/generated/zephyr/autoconf.h;
  grep -E "CONFIG_(DYNAMIC_THREAD[A-Z_]*|THREAD_STACK_INFO|THREAD_NAME|STACK_POINTER_RANDOM|HEAP_MEM_POOL_SIZE) " $A'
curl -sfL https://raw.githubusercontent.com/zephyrproject-rtos/zephyr/v4.4.0/kernel/dynamic.c -o dynamic.c
```

### Explicação

- A tag `0.4.3` é o commit `d681b872` (2026-06-23).
- O `diff -r` entre a tag e a cópia da placa só acusou `.github` e `.gitignore`: a placa usava
  exatamente a 0.4.3.
- O branch `ver_0_4_4_rc` (commit `8e4c8289`, "ver: 0.4.4", 2026-09-22) muda no `bridge.h` só isto:

```diff
-#define UPDATE_THREAD_STACK_SIZE    500
+#ifndef UPDATE_THREAD_STACK_SIZE
+#define UPDATE_THREAD_STACK_SIZE    2048
+#endif
```

### Os dois patches (marcados `// AGV patch`)

```diff
-#define UPDATE_THREAD_STACK_SIZE    500
+// AGV patch: 500 bytes overflows (issue #77); same change as 0.4.4.
+#ifndef UPDATE_THREAD_STACK_SIZE
+#define UPDATE_THREAD_STACK_SIZE    2048
+#endif
 #define UPDATE_THREAD_PRIORITY      5
@@
         upd_stack_area = k_thread_stack_alloc(UPDATE_THREAD_STACK_SIZE, 0);
+        // AGV patch: fill the stack with 0xAA so the sketch can measure its peak use.
+        if (upd_stack_area) {
+            for (size_t i = 0; i < UPDATE_THREAD_STACK_SIZE; i++) {
+                reinterpret_cast<uint8_t *>(upd_stack_area)[i] = 0xAA;
+            }
+        }
         upd_tid = k_thread_create(&upd_thread_data, upd_stack_area,
```

- Patch 1: igual ao da 0.4.4.
- Patch 2: escreve `0xAA` em todos os bytes da pilha **antes** de a thread existir. Como a pilha cresce para baixo, a parte nunca usada continua `0xAA` no fundo; o sketch conta esses bytes intocados a partir do fundo, e o pico de uso é `2048 − intocados`.

`sketch.yaml` ganhou:

```yaml
    libraries:
      - dir: libraries/Arduino_RouterBridge
```

Deploy:

```
[INFO] Used library Arduino_RouterBridge (0.4.3) in /home/arduino/ArduinoApps/agv/sketch/libraries/Arduino_RouterBridge
```

### Conclusões

- A placa compila com a cópia corrigida (confirmado pela linha "Used library").
- Naquele momento o binário tinha o mesmo tamanho de antes (73396 bytes), porque o sketch vazio não chamava `Bridge.begin()` e o código do patch não era compilado. **O patch foi confirmado no app mínimo**: a thread da Bridge tem `stack_size=2048` e a varredura mede um pico entre 0 e 2048.

## 8. Registro das versões (`docs/board-versions.txt`)

### O que foi feito

Registro das versões de software da placa e fixação do `arduino_app_bricks` no `pyproject.toml`
para o PC usar a mesma versão do container.

### Comandos

```bash
git ls-remote --tags https://github.com/arduino/app-bricks-py | grep -E "0\.12\.0|0\.13\.0"
ssh unoq 'arduino-app-cli version; arduino-router version;
  docker exec agv-main-1 sh -c ". /app/.cache/.venv/bin/activate && python -c \"...importlib.metadata.version(...)...\"";
  docker inspect agv-main-1 --format "{{.Config.Image}}";
  docker image inspect ghcr.io/arduino/app-bricks/python-apps-base:0.12.0 --format "{{index .RepoDigests 0}}";
  . /etc/os-release; echo "$PRETTY_NAME"; uname -r'
./deploy.sh --no-follow > deploy_out.txt 2>&1
```

E no PC:

```toml
# pyproject.toml
arduino-app-bricks = { git = "https://github.com/arduino/app-bricks-py", tag = "release/0.12.0" }
```

```bash
uv lock && uv sync
```

### Resultados

`docs/board-versions.txt`

### Conclusões

- A partir daqui, todo deploy confere plataforma e bibliotecas. Qualquer mudança para o app e mostra a diferença.
- Se o sketch passar a usar outra biblioteca de propósito, o `board-versions.txt` precisa ser atualizado de propósito.

## 9. App mínimo

As medições feitas com a versão instrumentada estão em [`day1-instrumentation.md`](day1-instrumentation.md).

O que o app faz:

- o Python repete um `ping` até o MCU responder e depois manda o heartbeat `hb` a 5 Hz;
- os handlers do MCU seguem a regra da fila de comandos e só recebem inteiros;
- o sketch mede o pico de pilha da thread da Bridge e entra em emergência com menos de 512 bytes livres;
- o MCU aceita um `set_path` de até 32 pontos em mm inteiros (≤ 217 B); o router recusa o mesmo caminho em floats (601 B).

### Sketch (`sketch/sketch.ino`)

**Fila de comandos.** Uma `k_msgq` do Zephyr com 8 comandos de três inteiros (`type`, `arg0`,
`arg1`), iniciada no `setup()`. Os handlers colocam com `K_NO_WAIT` (nunca bloqueiam) e o tick retira tudo no seu início (`drain_commands()`). Assim, o handler só valida, enfileira e retorna, e o comando é aplicado entre ticks, na ordem de chegada.

**Handlers**, registrados com `provide_safe`:

- `ping`: só retorna `true`.
- `hb`: só guarda o instante (`k_uptime_get_32()`) num atômico. O watchdog que freia depois de 1 s sem `hb` é do Dia 3.
- `set_path`: recusa (retorna `false`) se a emergência estiver ativa, se o número de valores não for par entre 2 e 64 ou se algum ponto sair da arena (0–2000 mm em x, 0–1500 mm em y) ou se a fila estiver cheia. A lista não cabe na fila, então é copiada sob mutex para um buffer estático, e o comando leva só `id` e `n`. O tick só aplica o caminho se `id` e `n` ainda conferem com o buffer: um `set_path` novo que chegue antes sobrescreve o buffer, e o comando antigo é descartado (o mais novo vence).

**Thread da Bridge.** O `setup()` guarda a thread principal. O primeiro handler que roda em outra thread grava a identidade dela (`atomic_ptr_cas(&bridge_tid, nullptr, current)`, que só grava uma vez): é a thread da Bridge, cuja pilha o tick varre.

**Pico de pilha e emergência.** A cada tick, `scan_bridge_stack()` conta os bytes `0xAA` a partir do fundo da pilha (`stack_info.start`); o pico é o tamanho menos esses bytes intocados. Ler a pilha de outra thread enquanto ela roda é seguro: os bytes só deixam de ser `0xAA`, e a varredura se repete a cada 20 ms. Com menos de 512 bytes intocados, a emergência trava (até reiniciar), dá short brake, passa a recusar `set_path` e manda `emergency(t_ms, pico, intocados)` uma vez.

**Motores: só IN1 = IN2 = L no boot e short brake na emergência.** Pela tabela do TB6612 (p. 4), IN1 = IN2 = H dá short brake, seja qual for o PWM; já IN1 = IN2 = L só é coast (alta impedância) com PWM = H. Aqui o PWM (D6, D9) não é tocado e fica baixo pelos pull-downs de 200 kΩ, e IN1 = IN2 = PWM = L não está na tabela: nenhuma direção é escolhida, então o motor não é acionado, mas não está especificado se ele fica em alta impedância ou em short brake (conferido no bloco Firmware, `day1-firmware.md`, seção 2; o código desta seção chamava esse estado de coast). Este código não consegue girar um motor, a LiPo estava desconectada também para o deploy.

**Telemetria**, sempre por `Bridge.notify` (o `Serial` do UNO Q é um RPC bloqueante):

- `status` a cada 25 ticks (500 ms): `t_ms`, os piores casos da janela (atraso do tick, corpo do tick, tempo fora do `loop()`), overruns desde o boot, pico e bytes intocados da pilha, idade do `hb` (−1 antes do primeiro), `path_id` aplicado e a flag de emergência;
- `hook(t_ms, duração)` a cada passagem fora do `loop()` acima de 3 ms (seção 11);
- `emergency`, uma vez.

### Python (`python/`)

- **`main.py`** só junta as peças: registra os handlers `status`, `hook` e `emergency` com `Bridge.provide` **antes** do `ping`, para nenhuma notificação do MCU se perder; grava o evento `start`; inicia a thread `mission`; chama `App.run`.
- **`telemetry.py`**: os CSVs `*_app_{status,events,hook}.csv` (abertos com `open_run_log`, seção 4), `event()`, que grava no CSV de eventos e no log do app, e os handlers de notificação, que só gravam uma linha.
- **`mcu_link.py`**:
  - `wait_for_mcu()` repete `Bridge.call("ping", timeout=1)` a cada 0,5 s até responder, capturando `TimeoutError`, `ValueError` (método ainda não registrado no router), `RuntimeError` e `ConnectionError`, e registra quantas tentativas e quanto tempo levou;
  - `heartbeat()` manda `Bridge.notify("hb")` a cada 0,2 s, numa thread própria;
  - `mission()` é a única thread que manda comandos ao MCU: faz o `ping` e inicia o heartbeat. Ainda não manda nenhum `set_path`.

### Conclusões

A base para o firmware dos próximos blocos está pronta: fila de comandos, pilha da Bridge vigiada, telemetria sem `Serial` e um único remetente de comandos no Python. E as medições estão registradas no outro log.

## 10. Tick de controle de 20 ms

### O que foi feito

Um tick no `loop()`, agendado com `micros()` (`next += 20000`), que aplica no seu início os comandos enfileirados, ressincroniza e registra o overrun quando atrasa mais de um período (sem ticks de recuperação com dt quase zero), manda a telemetria por `Bridge.notify` e mede o jitter (~1–2 ms esperados). Só se o jitter fosse inaceitável o tick iria para uma `k_thread` própria.

### Fatos verificados (core 1.0.0)

- `micros()` é `k_cyc_to_us_floor32(k_cycle_get_64())` com clock de 160 MHz
  (`cores/arduino/zephyrCommon.cpp`): resolução de 1 µs. O valor de 32 bits dá a volta a cada
  ~71,6 min, o que as diferenças em `int32` resolvem.
- `main.cpp` roda `for (;;) { loop(); __loopHook(); }`, e o `__loopHook` da Bridge dorme 1 ms
  (`k_msleep(1)`) quando não há RPC pendente. `CONFIG_SYS_CLOCK_TICKS_PER_SEC=10000`.

### Como funciona

O centro é `next_tick_us += kTickPeriodUs` em `run_tick_if_due()`:

- somar o período ao instante previsto (e não ao atual) mantém a grade de 20 ms: um tick atrasado não empurra os seguintes;
- o atraso em relação à grade (`late_us`) é a medida do jitter;
- com mais de um período de atraso, o tick conta um overrun e ressincroniza (`next_tick_us = now_us + kTickPeriodUs`). Sem isso, um atraso de 50 ms geraria ticks seguidos com dt ≈ 0, e uma velocidade calculada sobre esse dt explodiria;
- o tick aplica os comandos da fila, varre a pilha da Bridge e, a cada 25 ticks, manda o `status`.

A versão medida também calculava o dt real entre ticks e mandava estatísticas por janela e um
histograma do atraso; esse código saiu e está em `day1-instrumentation.md`.

### Resultados (`data/day1/20261010-171517_app_*.csv`, 146 s, 7500 ticks)

- 50,17 Hz e **nenhum overrun**.
- Atraso do início do tick entre 0 e 1,1 ms em **99,89 %** dos ticks, média de 0,60 ms, quase uniforme (de 656 a 719 ticks em cada faixa de 100 µs). Em regime, os piores casos por janela ficaram em 1,23–1,65 ms.
- dt em regime de 18,7 a 21,6 ms; corpo do tick ≤ 0,62 ms, incluindo os `notify`.
- Pilha da Bridge: pico de 928 B, 1120 B intocados.
- **Uma exceção:** um tick atrasou 13,2 ms na primeira janela (`t_ms` ≈ 4,45–4,95 s), quando o Python mandava os três `set_path` do teste de tamanho.

A distribuição uniforme de 0 a ~1,1 ms é o efeito do `k_msleep(1)`: o `loop()` olha o relógio
~1 vez por ms, e o tick vence em qualquer ponto desse intervalo (mais ~0,1 ms da resolução do kernel).

### Conclusões

- O tick funciona e, em regime, tem o jitter esperado (< 1,7 ms).
- O pico de 13 ms precisava de explicação antes de decidir manter o tick no `loop()` (seção 11).
- Além do timestamp do `hb` é compartilhado entre handlers e tick. Também são compartilhados os pontos do `set_path` (sob mutex) e a flag de emergência (o `set_path` a lê para recusar); tudo é atômico ou protegido por mutex.

## 11. Pico do tick: teste de estresse e decisão

### O que o decoder mostra

- As leituras da serial não bloqueiam (`SerialTransport::read` usa `setTimeout(0)`).
- `BridgeClass::update()` (thread `bridge`) e `update_safe()` (main, no `__loopHook`) esperam até 10 ms pelo `read_mutex`.
- A thread `bridge` repete `Bridge.update(); k_yield();` e só dorme 1 ms quando não há requisição completa.

### Experimento

- **Monitor de tempo fora do `loop()`** (ficou no código): `track_hook_time()` mede o tempo entre o fim de um `loop()` e o início do seguinte, que é o `__loopHook` mais qualquer preempção. Acima de 3 ms, manda `hook`; na versão do experimento, com quantas chamadas de cada handler, por thread, houve na pausa.
- **Variante `set_path_b`:** o mesmo handler, registrado com `provide`, que só a thread `bridge` executa. Se o pico sumisse com ela, a causa seria (a).
- **Fases de 30 s**, com uma chamada a cada 0,5 s: repouso, `ping`, `set_path` de 32 pontos, `set_path_b` de 32 pontos, repouso.

O código provisório está em `day1-instrumentation.md`, parte 6. Deploy com a LiPo ainda
desconectada.

### Resultados (`data/day1/20261010-172717_app_*.csv`)

| Fase (30 s, 2 Hz) | Maior tempo fora do `loop()` | Maior atraso do tick | dt (mín–máx) | RTT no Python |
|---|---|---|---|---|
| repouso, depois | 1,7 ms | 1,3 ms | 18,8–21,1 ms | – |
| `ping` | 1,8 ms (um caso de 7,2 ms) | 1,2 ms | 19,0–21,1 ms | mediana 4,5 ms |
| `set_path` (`provide_safe`) | 35,2 ms | 31,3 ms | 2,4–50,8 ms | mediana 46,5 ms |
| `set_path_b` (só thread `bridge`) | 38,0 ms | 36,4 ms | 1,3–55,7 ms | mediana 49,1 ms |

- A primeira fase de repouso não entra na tabela: a janela dela inclui o teste de tamanho do boot (12,8 ms de atraso).
- Cada `set_path` gerou em geral dois trechos seguidos fora do `loop()`, por exemplo 11,6 ms (sem handler) + 27,6 ms (com o `set_path` na thread `bridge`), somando ~35–40 ms. Muitos trechos medem ~10 ms, o timeout do `read_mutex`.
- 31 das 110 chamadas de `set_path` causaram overrun.

### Análise

1. `ping` e repouso não bloqueiam: o problema depende do **tamanho** da mensagem, não de haver um handler.
2. Com mensagens de poucos bytes (`ping`, `hb`), N² é desprezível.

### Impacto no projeto

- Só o `set_path` é grande; `stop`, `mode`, `reset_pose` e `hb` são pequenos.
- O desenho já envia o `set_path` com o robô parado: no Dia 3, no início da missão; no Dia 6, depois do `stop` com rampa.
- Com o robô em movimento, os PIs das rodas veriam um dt de até ~55 ms e um período se perderia; a odometria aguenta, porque integra pelos encoders.

### Decisão

**Aceitar e documentar:** `set_path` só com o robô parado; o tick continua no `loop()`.

- Código: saíram o `set_path_b` e as fases; ficou o monitor de tempo fora do `loop()` (`hook_max_us` na telemetria e a notificação `hook`, em `*_app_hook.csv`), para que um `set_path` com o robô em movimento apareça nos logs.
- A recusa do `set_path` no MCU fora de IDLE/ARRIVED fica para o Dia 3, quando essa máquina de estados existir.

## 12. Estado final e conclusões gerais

### Estado final do bloco Setup do Dia 1

| Item do ROADMAP | Estado |
|---|---|
| Versões da placa primeiro | ✓ (`system update` feito; congelado) |
| Antes do primeiro deploy | ✓ (backup) |
| `deploy.sh` (deploy e pull) | ✓ testado |
| Logs por execução | ✓ (`run_log.py` + 4 testes) |
| OpenCV 4.13 | ✓ (vem da imagem; fora do `requirements.txt`) |
| `sketch.yaml` | ✓ |
| Cópia corrigida da Bridge | ✓ (2048 B, padrão `0xAA`) |
| Registro das versões | ✓ (`board-versions.txt`, checado a cada deploy) |
| Checagem antes da Bridge | ✓ |
| App mínimo | ✓ (ping, hb 5 Hz, threads, pico 936 B, teste de tamanho) |
| Tick de controle | ✓ (jitter < 1,7 ms em regime; `set_path` só parado) |

### Dados do Dia 1 em `data/day1/`

| Arquivos | Conteúdo |
|---|---|
| `20261010-170912_bridge_{diag,events}.csv` | app mínimo instrumentado (seção 9; o modo dos logs só virou `app` na seção 10) |
| `20261010-171517_app_{diag,events,tick,tickhist}.csv` | tick, 146 s (seção 10) |
| `20261010-172717_app_{diag,events,hook,stress,tick,tickhist}.csv` | teste de estresse (seção 11) |
| `20261010-173441_app_{diag,events,hook,tick,tickhist}.csv` | versão limpa depois do teste de estresse (seção 11) |
| `20261010-231955_app_{events,hook,status}.csv` | app enxuto, ~207 s (seção 9) |
| `20261011-164934_app_{events,hook,status}.csv` | app enxuto depois da divisão do `main.py`, ~60 s (seção 9) |

### Conclusões gerais

1. **A cadeia funciona de ponta a ponta:** editar no PC → `deploy.sh` (com checagem de versões) → compilação e gravação na placa → Python no container → Bridge → logs CSV → `pull` → `data/day1/`.
2. **A pilha da Bridge está protegida e medida:** 2048 B, pico de ~930 B, mais de 1100 B de margem; qualquer aproximação do limite dispara a emergência.
3. **O limite de 256 B do router funciona:** a mensagem grande é recusada antes de chegar ao MCU, e o MCU continua respondendo.
4. **O tick no `loop()` é adequado:** atraso uniforme de 0–1,1 ms; a única exceção, mensagens grandes, está entendida e tratada por uma regra de operação.
5. **Um problema que teria custado tempo depois foi resolvido:** o OpenCV no `requirements.txt` impedia, em silêncio, a instalação de todas as dependências.
6. **As decisões que mudaram o desenho foram suas:** pasta `agv`, OpenCV fora do `requirements.txt`, `run_log.py` junto do app mínimo e opção 1 para o pico.

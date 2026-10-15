# Dia 1 — Firmware

## 1. Divisão do `sketch.ino` em módulos

### O que foi feito e por quê

O `sketch/sketch.ino` do app mínimo (275 linhas) foi dividido em módulos **sem mudar o comportamento**, antes de receber o driver do TB6612, os encoders e o PI. Com tudo num arquivo só, cada bloco novo teria acesso a todo o estado global do sketch; separado, cada módulo guarda o seu estado `static` no próprio `.cpp` e expõe só funções.

### Como ficou

```
sketch/
├── sketch.ino                       setup(), loop(), tick() e o envio do status
└── src/
    ├── config/config.h              pinos IN1/IN2, período do tick, status a cada 25 ticks, limites do caminho e da arena
    ├── motor_driver/motor_driver.*  coast() e short_brake()
    ├── commands/commands.*          k_msgq, caminho preparado sob o mutex, drain(), path_id()
    ├── handlers/handlers.*          ping, hb, set_path; identidade da thread da Bridge; instante do último hb
    ├── tick_timing/tick_timing.*    grade de 20 ms, overruns, piores casos da janela, tempo fora do loop() e o notify hook
    └── bridge_stack/bridge_stack.*  varredura da pilha, emergência e o notify emergency (uma vez)
```

Quem conhece quem:

| Módulo | Usa |
|---|---|
| `handlers` | `commands` (enfileira o `set_path`), `bridge_stack::emergency()` (recusa o `set_path`), `config` |
| `bridge_stack` | `motor_driver::short_brake()` na emergência. Recebe a thread a varrer como parâmetro, então não depende de `handlers` |
| `commands`, `tick_timing` | só `config` |
| `sketch.ino` | todos; é o único que junta os dados de vários módulos (o `status`) |

### Comandos

```bash
# Build do sketch dividido no PC, com todos os avisos ligados
arduino-cli compile --warnings all --build-path <tmp>/build sketch
# Banco de compilação do editor e checagem do clangd
arduino-cli compile --only-compilation-database --build-path build sketch
clangd --check=sketch/src/handlers/handlers.cpp --query-driver=".../arm-zephyr-eabi-g*"
clangd --check=sketch/sketch.ino --query-driver=".../arm-zephyr-eabi-g*"
```

### Resultados na placa (arduino-cli 1.4.2 do `arduino-app-cli` 0.13.0)

```bash
./deploy.sh --no-follow     # compila e grava o sketch dividido, sobe o app
# ~95 s rodando, LiPo como no Dia 1 (este código não gira motor: só coast no boot)
./deploy.sh pull day1
```

- **A placa compila o `src/`:** mesmo tamanho do PC (107 484 B / 43 532 B), e as linhas "Board platform" e "Used library" bateram com o `docs/board-versions.txt`, com a Bridge corrigida (`.../agv/sketch/libraries/Arduino_RouterBridge`).
- Dados: `results/day1/20261011-174706_app_{events,hook,status}.csv`.

## 2. Driver próprio do TB6612

### O que foi feito e por quê

Um driver próprio (o `TB6612FNG_XCR` foi descartado): duty com sinal por roda, coast e short brake explícitos, PWM a ~20 kHz. Antes de escrever o código, conferi nas fontes cada fato de que ele depende.

### Fatos verificados

**Devicetree** (`variants/arduino_uno_q_stm32u585xx/arduino_uno_q_stm32u585xx.overlay`):

| Pino | Timer/canal | Outros pinos do mesmo timer no overlay |
|---|---|---|
| D6 (PWM esquerdo) | `pwm3` canal 4 (`TIM3_CH4`, PB1) | D3 = `TIM3_CH3` (encoder direito A), D8 = `TIM3_CH1` (IN2 esquerdo) |
| D9 (PWM direito) | `pwm4` canal 3 (`TIM4_CH3`, PB8) | D10 = `TIM4_CH4` (IN1 direito) |

**TB6612FNG** (datasheet da Toshiba, 2007-06-30; a cópia da SparkFun, `cdn.sparkfun.com/assets/0/1/b/b/3/TB6612FNG.pdf`). O texto da tabela está em glifos de 2 bytes, decodificados com um script (código do caractere = glifo + 0x1F). Tabela "H-SW Control Function" (p. 4), com STBY = H:

| IN1 | IN2 | PWM | OUT1 | OUT2 | Modo |
|---|---|---|---|---|---|
| H | H | H/L | L | L | Short brake |
| L | H | H | L | H | CCW |
| L | H | L | L | L | Short brake |
| H | L | H | H | L | CW |
| H | L | L | L | L | Short brake |
| L | L | H | OFF | OFF | Stop (alta impedância) |
| H/L | H/L | H/L | (STBY = L) OFF | OFF | Standby |

Também na mesma fonte: `fPWM` máxima de 100 kHz (p. 3), e IN1, IN2, PWM e STBY com pull-down interno de 200 kΩ (tabela de pinos). A tabela da SparkFun Hookup Guide é a mesma.

Consequências para o driver:

1. **Duty d aciona o motor durante d do período e faz short brake no resto** (PWM = L com direção escolhida). É o único modo que o pino PWM do TB6612 oferece; K, τ e `pwm0` serão identificados nesse modo.
2. **Coast (alta impedância) é IN1 = IN2 = L com PWM = H.** "PWM 0" com a direção ainda escolhida é short brake, não coast.
3. **IN1 = IN2 = PWM = L não está na tabela.** É o estado no reset (pull-downs) e era o `coast()` do app mínimo. Nenhum lado alto conduz nos dois casos documentados vizinhos, então o motor não é acionado, mas se ele fica em alta impedância ou em short brake não está documentado.

- **Sentido por roda:** `config::kLeftMotorReversed` e `kRightMotorReversed` (hoje `false`) trocam IN1 e IN2, para que duty positivo seja "para frente" nas duas rodas; são ajustados no primeiro teste com as rodas no ar.
- **Thread:** o driver só é chamado da thread principal (`setup()` e tick). A emergência roda no tick, então também.
- **`status`** ganhou `pwm_hz` e `pwm_err` no fim (o `STATUS_HEADER` de `python/telemetry.py` também).

### Resultados na placa

```bash
./deploy.sh --no-follow
./deploy.sh pull day1
```

`results/day1/20261011-175914_app_{events,hook,status}.csv`, 63 s, 127 linhas de `status`

## 3. Encoders em quadratura x4

### O que foi feito e por quê

Interrupções em `CHANGE` nos dois canais (A e B) de cada encoder, com os pinos em `INPUT_PULLUP`: cada borda de A ou de B conta, ou seja 4 contagens por ciclo de cada canal (x4), a maior resolução que o encoder dá. "Para frente" tem que contar positivo nas duas rodas.

**Um handler por roda**, ligado aos dois pinos dela. O handler lê A e B (`digitalRead`) e consulta uma tabela de 16 posições indexada por `(estado anterior << 2) | estado novo`, com estado = `(A << 1) | B`:

  | de \ para | 00 | 01 | 10 | 11 |
  |---|---|---|---|---|
  | 00 | 0 | +1 | −1 | erro |
  | 01 | −1 | 0 | erro | +1 |
  | 10 | +1 | erro | 0 | −1 |
  | 11 | erro | −1 | +1 | 0 |

### Teste à mão: sinal da contagem

**Como foi feito:** com o app rodando (LiPo desconectada: os encoders são alimentados pelos 3,3 V da placa, e nada aciona os motores), girou-se as duas rodas ao mesmo tempo, várias voltas para a
frente e depois para trás, três vezes.

```bash
ssh unoq 'f=$(ls -t /home/arduino/ArduinoApps/agv/logs/*_status.csv | head -1); cat $f'
```

Dados: `results/day1/20261011-180736_app_{events,hook,status}.csv` (652 linhas, 326 s).

**Resultado (trecho, um valor por janela de 0,5 s em que a contagem mudou):**

| `t_ms` | `enc_l` | `enc_r` | |
|---|---|---|---|
| 279 456 | 68 | −64 | início, para a frente |
| 282 956 | 2 527 | −2 565 | |
| 283 456 | 2 531 | −2 575 | máximo |
| 286 956 | −177 | 130 | depois de voltar |
| 289 956 | 2 270 | −2 335 | 2º ciclo |
| 293 456 | −77 | 0 | |

- Para a frente, a esquerda subiu e a direita desceu, nos três ciclos: **o encoder direito conta ao contrário** → `kRightEncReversed = true`
- `enc_err_l` = `enc_err_r` = **0** com até ~1 700 contagens/s por roda (850 numa janela de 0,5 s).
- O tick não sentiu as interrupções: 0 overrun, atraso máximo 1 646 µs, pico da pilha da Bridge 896 B (1 152 B intocados). O corpo do tick chegou a 522 µs uma vez.

### Teste à mão: confirmação depois da correção

Deploy com `kRightEncReversed = true`; girou-se só para a frente, primeiro o motor A, depois o motor B. Dados: `results/day1/20261011-181645_app_{events,hook,status}.csv`.

| Trecho (`t_ms`) | `enc_l` | `enc_r` |
|---|---|---|
| 4 966 (repouso) | 0 | 0 |
| 42 466 → 50 966 (motor A) | 2 → 7 546 | 0 |
| 52 966 → 62 966 (motor B) | 7 546 | 47 → 13 025 |

- **As duas rodas contam positivo para a frente.**
- 0 erros com até ~3 000 contagens/s (1 523 numa janela de 0,5 s); 0 overrun; pico da pilha 896 B. O corpo do tick chegou a 554 e 536 µs, em duas janelas a 1 s uma da outra (`t_ms` 10 465 e 11 466).

### Conclusões

- Os encoders x4 funcionam nas duas rodas, sem bordas perdidas nas velocidades da mão, e o sinal está certo: `kLeftEncReversed = false`, `kRightEncReversed = true`.
- As interrupções não afetaram o tick nem a pilha da Bridge nessas taxas. A medida com os motores girando (taxas maiores) fica para os modos com motor.

## 4. Modo `count`: contagens por volta da roda

### O que foi feito

O modo `count` mede as **contagens por volta de cada roda**: marca-se a roda, gira-se 10 voltas à mão e lê-se quantas contagens o encoder deu. É o primeiro uso do comando `mode` da Bridge e o primeiro teste que precisa ser iniciado e parado com o app rodando, então as decisões abaixo valem para todos os testes do Dia 1 (`step`, rampa do `pwm0`, malha fechada).

**PC: `./deploy.sh run <comando>`**

- Cada comando vira um arquivo `cmd/<ns>.cmd`: escrito como `.<ns>.tmp` e renomeado (o `mv` na mesma pasta é atômico), então o Python nunca lê um arquivo pela metade; o nome em nanossegundos dá a ordem de envio.
- Só letras, números, espaço, `.`, `_` e `-` passam (o comando vai dentro de um `ssh`): testado com `run 'count; rm -rf x'`, que é recusado.
- Depois de 1 s, mostra as 3 últimas linhas do log de eventos, onde aparecem o ack e o resultado.
- O container grava como `arduino` (uid 1000: `logs/` é `arduino:arduino`), o mesmo usuário do ssh, então ele pode apagar os arquivos de `cmd/`. O `rsync --delete` do deploy só mexe nas pastas que sincroniza, então `cmd/` fica como `logs/`.

### Teste a seco do caminho dos comandos (sem girar as rodas)

```bash
./deploy.sh run count bogus
./deploy.sh run count start
./deploy.sh run count stop     # 2 s depois
```

Eventos (`20261011-182803_app_events.csv`):

```
cmd_rejected,count bogus
cmd,"count start -> mode(1, 0, 0, 0, 0) ack=True"
cmd,"count stop -> mode(0, 0, 0, 0, 0) ack=True"
count,duration=4.2s counts_l=0 counts_r=0 errors_l=0 errors_r=0
```

- O comando inválido foi recusado no Python, sem chegar ao MCU; os válidos tiveram ack do MCU.
- O `count` chegou logo depois do `stop` (~10 ms), com zero contagens (ninguém tocou nas rodas) e gravado em `20261011-182826_count.csv`; o `status` voltou a `mode` = 0.
- `cmd/` ficou vazia: o app apagou os três arquivos.

### Medição: 3 execuções de 10 voltas

Marcaram-se as duas rodas e, em cada execução, rodou `./deploy.sh run count start`, girou-se cada roda 10 voltas para a frente (marca alinhada com uma referência fixa no chassi) e rodou `./deploy.sh run count stop`. Dados: `results/day1/20261011-182826_count.csv` (a 1ª linha é o teste a seco) e `20261011-182803_app_{events,hook,status}.csv`.

| Execução | Duração | Contagens esq. | Contagens dir. | Erros esq./dir. |
|---|---|---|---|---|
| 1 | 70,6 s | 13 191 | 13 201 | 0 / 0 |
| 2 | 59,2 s | 13 196 | 13 193 | 0 / 0 |
| 3 | 50,4 s | 13 204 | 13 200 | 0 / 0 |

Cálculo (`statistics` do Python sobre o CSV; por volta = contagens ÷ 10):

| Roda | Média por volta | Desvio padrão por volta | Amplitude (10 voltas) |
|---|---|---|---|
| Esquerda | **1 319,7** | 0,66 (0,05 %) | 13 |
| Direita | **1 319,8** | 0,44 (0,03 %) | 8 |
| As duas | **1 319,75** | 0,50 | |

Explicação:

- As duas rodas dão o mesmo valor dentro do ruído: a diferença entre elas (0,1 contagem por volta) é menor que o desvio de cada uma.
- O desvio vem do alinhamento da marca à mão: 13 contagens em 10 voltas são ~3,5° de roda, ou ~2 mm no perímetro.
- Com Ø 67,5 mm nominal, cada contagem vale π × 67,5 / 1 319,75 = **0,1607 mm**.
- Durante as execuções: 0 erros de encoder com até ~1 750 contagens/s, 0 overrun, atraso máximo do tick 1 622 µs.
- Algumas chamadas de `mode` seguram o `loop()` por mais tempo que o `hb`: nas sessões deste bloco (`20261011-*`), toda janela com mais de 1,8 ms fora do `loop()`, fora a primeira depois do boot, teve uma chamada de `mode` (8 janelas para 54 chamadas, de 1 812 a 2 515 µs). No Setup, o `ping` e o `hb` ficaram abaixo de 1,8 ms, com um caso de 7 ms. Ainda abaixo do limite de 3 ms do `hook`, e nenhum overrun.

### Conclusões

- **Contagens por volta da roda: 1 319,7 (esquerda) e 1 319,8 (direita), ±0,5.**
- O caminho de comandos (`deploy.sh run` → arquivo → thread `mission` → `mode` → tick → `count` → CSV) funciona e serve para os próximos testes.

### Valor usado no firmware

**um valor para as duas rodas**, a média medida, porque a diferença entre elas está dentro do
ruído. Em `sketch/src/config/config.h`:

```cpp
constexpr float kCountsPerRev = 1319.75f;
constexpr float kWheelDiameterM = 0.0675f; // nominal
```

## 5. Velocidade das rodas pelas contagens e pelo dt medido

### O que foi feito e por quê

A cada tick, a velocidade de cada roda em **contagens/s** (a unidade do laço PI) é a diferença de contagens desde o tick anterior dividida pelo **dt medido** entre as duas amostras, não pelos 20 ms nominais. O tick atrasa de 0 a ~1,1 ms, então o
dt real varia de ~18,7 a ~21,6 ms; dividir pelo nominal daria até ~8 % de erro numa amostra, e um
overrun (dt de 40 ms ou mais) dobraria a velocidade.

Decisão:

**O instante da amostra é tomado junto com as contagens**, com um `micros()` próprio dentro do tick, e não o `now_us` do início do `loop()`: entre os dois pode haver um `notify` do `hook`, que leva tempo, e o dt ficaria errado.


### O código

- `sketch/src/wheel_speed/`: `update()` toma `micros()` e as duas contagens juntos; a partir da segunda chamada, `velocidade = (contagem − contagem_anterior) / dt`, com `dt` = `micros()` atual − anterior (diferença em `uint32_t`, que atravessa a volta do contador). `speed(roda)` devolve contagens/s em `float`; `dt_us()` devolve o último dt.
- `tick()`: `wheel_speed::update()` é a **primeira** coisa do tick, antes do `drain()`.
- `tick_timing`: a janela do `status` ganhou `dt_min_us` e `dt_max_us` (`note_dt()`), o jitter real entre amostras, que é o que o PI vai ver.
- `status` ganhou `spd_l`, `spd_r` (contagens/s arredondadas para inteiro, a velocidade do último tick da janela), `dt_min_us`, `dt_max_us` no fim.

### Resultados na placa: parado

`results/day1/20261011-191525_app_*` (primeiras linhas, rodas paradas):

- Velocidade exatamente 0 com as rodas paradas.
- dt entre 18,8 e 21,1 ms enquanto as rodas estavam paradas.
- **Quase todo dt fica na grade de 100 µs.**, e o dt usado é o medido, seja qual for.

## 6. Limites de movimento no firmware (e o núcleo do modo `step`)

- Todo modo que move o robô agora tem limite de tempo e de distância conferidos no próprio STM32, e um pedido fora dos limites fixos é recusado no handler. Uma queda do ssh, do Wi-Fi ou do Python durante um `step` não deixa o robô andando: ele para em no máximo ~1 s.
- O driver do TB6612 está completo: os dois motores giram para a frente com duty positivo (`kLeftMotorReversed = false`, `kRightMotorReversed = true`).

## 7. Modo `step`: amostragem das contagens a cada 2 ms

### O que foi feito e por quê

O ajuste do modelo de primeira ordem (K, τ) é feito sobre a **posição** (contagens acumuladas),
não sobre a velocidade: derivar contagens dá velocidades ruidosas, e um τ de algumas dezenas de ms teria só um par de amostras no tick de 20 ms. Por isso, durante cada `step`, o MCU guarda em RAM as contagens das duas rodas com o instante de cada amostra a cada 2 ms e, quando o `step` acaba, manda tudo ao Python em notificações de ~200 B. Cada notificação leva o id do `step`, o índice da primeira amostra e o total, para o Python perceber uma notificação perdida e o `step` ser repetido em vez de ajustado.

### Decisões

- **Amostragem por `k_timer` a cada 2 ms**, cuja função de expiração roda na interrupção do relógio do sistema: período regular, que não depende de o `loop()` estar livre. A interrupção só lê `micros()` e as duas contagens (atômicas) e escreve no buffer; o tick só lê o buffer depois de parar o timer.
- A amostra 0 é tomada no próprio início do `step`, antes de aplicar o duty.
- **Uma notificação a cada 2 ticks (40 ms)**.
- **Enquanto as amostras de um `step` ainda estão saindo, um novo `step` é recusado** no handler (ack `false`), para não sobrescrever o buffer; `idle` continua aceito.
- O id do `step` é um contador do MCU desde o boot, enviado também no `step_end`.

### Primeira execução, com as rodas no ar

**Execuções** (LiPo conectada, chave da bateria à mão). O 1º e o 2º comandos foram escritos direto
pelo ssh, com 1,3 s de intervalo, para o 2º chegar enquanto as amostras do 1º ainda saíam:

| # | Comando | Resultado |
|---|---|---|
| 1 | `step 200 200 1000 500` | fim por tempo, 1001 ms; **501 amostras**, todas recebidas; `20261011-194347_step_1_L200_R200.csv` gravado ~1,35 s depois do `step_end` |
| 2 | o mesmo, 1,3 s depois | **recusado** (`ack=False`): as amostras do 1º ainda estavam saindo |
| 3 | `step -200 -200 1000 500` | fim por tempo, 1000 ms; 501 amostras; `20261011-194357_step_2_L-200_R-200.csv` |

Dados: `results/day1/20261011-194346_step.csv`, os dois arquivos de amostras e
`20261011-194208_app_{events,hook,status}.csv`.

**Análise das amostras** (script Python sobre os CSVs):

| | `step` 1 (+20 %) | `step` 2 (−20 %) |
|---|---|---|
| Amostras | 501 | 501 |
| Intervalo entre amostras | 1 982–2 003 µs, média 2 000,0 | igual |
| Última amostra | t = 999 985 µs, 952 / 1092 | t = 999 985 µs, −842 / −1077 |
| Contagens no `step_end` | 952 / 1092 (iguais) | −842 / −1077 (iguais) |
| Contagens monotônicas | sim | sim |

- **O timer é regular:** todos os intervalos ficam a menos de 20 µs de 2 ms. O primeiro é o mais curto (1 982 µs) porque a amostra 0 é tomada no tick, um pouco depois do instante de referência.
- **Nada se perde:** as contagens da última amostra são exatamente as do `step_end`, ou seja o `step` acabou no tick logo depois da última amostra, sem movimento no meio.
- Para trás, as duas rodas contam para baixo, e de novo a direita conta mais que a esquerda com o mesmo duty.
- **O envio não atrapalha o tick:**

### Conclusões

- A amostragem a 2 ms, o envio em notificações de ~190 B com detecção de perda e o CSV por `step` funcionam, para a frente e para trás.

## 8. Rampa lenta de PWM para o `pwm0`

### O que foi feito e por quê

O `pwm0` é o duty a partir do qual a roda sai do repouso (atrito estático); ele entra no feedforward do PI, `pwm = pwm0·sign(v) + v/K`. Para medi-lo, um modo novo sobe o duty devagar e grava o duty aplicado junto com as contagens; a análise acha, para cada roda e sentido, o duty em que ela começou a andar.

### Teste dos limites fixos da rampa (nada se move)

| Comando | Limite violado | Ack |
|---|---|---|
| `ramp 2 50 300 100` | sentido ≠ ±1 | `False` |
| `ramp 0 50 300 100` | sentido = 0 | `False` |
| `ramp 1 9 50 100` | taxa < 10 ‰/s | `False` |
| `ramp 1 201 300 100` | taxa > 200 ‰/s | `False` |
| `ramp 1 50 301 100` | máximo > 300 ‰ | `False` |
| `ramp 1 40 300 100` | rampa de 7,5 s > 6 s (cada valor sozinho é válido) | `False` |
| `ramp 1 50 300 201` | distância > 200 mm | `False` |
| `ramp 1 50 300 0` | distância = 0 | `False` |

Os oito foram recusados (`20261011-195223_app_events.csv`).

### Primeira execução, com as rodas no ar

Montagem como na seção 7 (robô levantado, LiPo conectada, chave à mão). Dados:
`results/day1/20261011-195502_ramp.csv`, `20261011-195502_ramp_1_dir+1_rate50.csv`,
`20261011-195512_ramp_2_dir-1_rate50.csv`, `20261011-195518_step{,_3_L200_R200}.csv` e
`20261011-195223_app_*`.

| # | Comando | Fim | Duração | Último duty | Contagens esq. / dir. | Amostras |
|---|---|---|---|---|---|---|
| 1 | `ramp 1 50 300 200` | distância | 3 340 ms | +166 ‰ | 1 007 / 1 250 | 169, todas recebidas |
| 2 | `ramp -1 50 300 200` | distância | 3 420 ms | −170 ‰ | −949 / −1 263 | 173, todas recebidas |
| 3 | `step 200 200 300 500` | tempo | 300 ms | | 213 / 277 | 150 (amostra 0 + 1 a cada 2 ms) |

**Análise das amostras da rampa** (script Python sobre os CSVs):

- Intervalo médio de 20,0 ms (uma amostra por tick, de 19 a 21 ms), sem contar o de 63 µs até a amostra 1 (abaixo); o sinal do duty é o do sentido em todas as amostras; as contagens e o duty da última amostra são os do `ramp_end`.
- O limite de 200 mm são 1 245 contagens; a roda direita (a mais rápida) estava em 1 250 / −1 263
  quando o tick viu.
- **Para a Análise (rodas no ar, então não é o `pwm0` de verdade):** a primeira contagem isolada aparece bem antes do movimento contínuo. Para trás, a roda direita contou uma vez a −2,3 % e só andou de forma contínua a partir de −5,9 % (o primeiro duty com 5 amostras seguidas subindo); nas outras rodas e sentidos, 4,3 → 5,6 %, 3,4 → 5,4 % e 5,1 → 5,7 %. Provavelmente folga da caixa de redução ou balanço. O critério de partida tem de ser de **movimento sustentado**, não "primeira contagem".
- Na sessão: 0 overrun, atraso máximo 1 525 µs, corpo máximo 545 µs, nenhum `hook`.

### Conclusões

- A rampa funciona nos dois sentidos, para pelo limite de distância, e as amostras chegam completas com o duty aplicado em cada uma; o `step` continua funcionando com o buffer compartilhado.

## 9. Sessão de identificação no chão da arena

### O que foi feito

```bash
./deploy.sh --no-follow                   # o app estava parado desde o último pull
./deploy.sh run step 200 200 1000 400     # 1
./deploy.sh run step -200 -200 1000 400   # 2
./deploy.sh run step 250 250 1000 400     # 3
./deploy.sh run step -250 -250 1000 400   # 4
./deploy.sh run step 300 300 1000 400     # 5
./deploy.sh run step -300 -300 1000 400   # 6
./deploy.sh run ramp 1 50 300 100         # 7
./deploy.sh run ramp -1 50 300 100        # 8
./deploy.sh pull day1
```

### Resultados

Dados: `results/day1/20261011-195756_app_*`, `20261011-195816_step.csv` e `20261011-200129_ramp.csv`
(resumos), e um arquivo de amostras por execução (`20261011-195817_step_1_L200_R200.csv` …
`20261011-200158_ramp_8_dir-1_rate50.csv`).

| # | Comando | Fim | Duração | Contagens esq. / dir. | Amostras |
|---|---|---|---|---|---|
| 1 | `step 200 200` | tempo | 1000 ms | 756 / 849 | 500 |
| 2 | `step -200 -200` | tempo | 1001 ms | −656 / −817 | 501 |
| 3 | `step 250 250` | tempo | 1019 ms | 1 090 / 1 204 | 510 |
| 4 | `step -250 -250` | tempo | 1000 ms | −922 / −1 121 | 500 |
| 5 | `step 300 300` | tempo | 1000 ms | 1 395 / 1 514 | 501 |
| 6 | `step -300 -300` | tempo | 1001 ms | −1 220 / −1 524 | 501 |
| 7 | `ramp 1 50 300 100` | distância | 3 140 ms (último duty 156 ‰) | 513 / 625 | 159 |
| 8 | `ramp -1 50 300 100` | distância | 3 240 ms (último duty −161 ‰) | −463 / −632 | 164 |

- Todas as amostras chegaram (nenhum `samples_lost`), com intervalos de 1 982–2 006 µs nos `step`; 0 erros de encoder; `pwm_err` 0.
- Na sessão: 0 overrun, atraso máximo 1 622 µs, corpo máximo 549 µs, dt máximo 21,5 ms, nenhum `hook`; pico da pilha da Bridge 904 B, com no mínimo 1 144 B intocados. (A primeira linha do `status` tem pico e intocados 0 porque saiu antes de a thread da Bridge ser identificada.)
- O robô andou como esperado: no `step` 1, ~12 cm, desviando um pouco para a esquerda, porque a roda direita anda mais.

**Primeira olhada, não é a Análise** (velocidade média nos últimos 0,3 s de cada `step`, contra a
dos 0,3 s anteriores):

| `step` | esq. (contagens/s) | dir. (contagens/s) | em m/s (esq. / dir.) | 0,3 s antes (esq. / dir.) |
|---|---|---|---|---|
| +20 % | 910 | 980 | 0,146 / 0,157 | 862 / 950 |
| −20 % | −780 | −957 | | −750 / −930 |
| +25 % | 1 267 | 1 327 | 0,204 / 0,213 | 1 217 / 1 297 |
| −25 % | −1 090 | −1 353 | | −1 037 / −1 265 |
| +30 % | 1 631 | 1 674 | 0,262 / 0,269 | 1 583 / 1 670 |
| −30 % | −1 436 | −1 775 | | −1 366 / −1 664 |

- **A velocidade ainda subia 3–6 % no fim de 1 s** na maioria dos `step`: a resposta tem uma parte mais lenta que "algumas dezenas de ms". A Análise tem de verificar se 1 s basta para o ajuste de K e τ (o `step` aceita até 1000 ms).
- **As rodas são diferentes**, e mais para trás: a direita é mais rápida nos dois sentidos, e para trás a esquerda fica ~20 % abaixo da direita. K por roda e por sentido.
- A 30 % para a frente, ~0,26 m/s, um pouco acima da velocidade de cruzeiro (0,25 m/s).
- **Rampas**: para a frente 7,3 % (esq.) e 6,7 % (dir.), para trás 8,6 % e 7,1 %. A primeira contagem isolada apareceu bem antes (2,1–3,1 %), de novo. O critério final é da Análise.
- **`step_end` e a última amostra:** em 5 dos 6 `step`, as contagens do `step_end` vão 1 ou 2 além das da última amostra (no sentido do movimento), porque o `step` termina até ~2 ms depois dela (o tick que o encerra vem depois da última expiração do timer de 2 ms). O ajuste usa as amostras; o `step_end` só confere.

### Conclusões

- Os dados de identificação do Dia 1 estão coletados: seis `step` (20, 25, 30 %, nos dois sentidos) e duas rampas, completos, a 12,6 V.

## 10. Comandos deixados em `cmd/` com o app parado

### O que foi feito e por quê

1. `./deploy.sh pull day1` deixa o app parado;
2. `./deploy.sh run speed 250 500 4500 937` não confere se o app está rodando: escreve `cmd/<ns>.cmd` na placa e mostra as últimas linhas de um log de eventos antigo;
3. o `rsync --delete` do deploy não mexe em `cmd/` (só nas pastas que sincroniza);
4. no próximo start, a thread `mission` lê todos os `.cmd` logo depois do `wait_for_mcu()` e executa esse `speed`, talvez com o robô na mão ou fora da arena.

Os limites do firmware continuam valendo (o `speed` para em 4,5 s e 1 m), mas o movimento começa
sem aviso.

Decisão:

**A `mission` descarta, ao começar, os comandos que já estão em `cmd/`**, e grava cada um como evento `cmd_discarded`.

Por que na `mission`: todo comando que chega ao STM32 passa por ela, então a regra vale qualquer
que seja o jeito de iniciar o app.

```bash
./deploy.sh pull day1                # o app fica parado
./deploy.sh run count start          # o arquivo fica esperando em cmd/
ssh unoq 'ls -la /home/arduino/ArduinoApps/agv/cmd/'
./deploy.sh --no-follow
ssh unoq 'cd /home/arduino/ArduinoApps/agv; ls cmd/; cat "$(ls -t logs/*_events.csv | head -1)"'
```

### Resultados e Conclusões

- Um comando escrito com o app parado nunca mais roda no start seguinte, seja qual for o jeito de iniciar o app; ele fica registrado como `cmd_discarded`.
- O `run` continua sem conferir se o app está rodando: com o app parado, a mensagem que ele mostra é de um log antigo (ou um erro de `ls`/`tail`, se `logs/` estiver vazia), e o comando só aparece como descartado no próximo start.

# Dia 2 — Firmware

## 0. Ponto de partida: limpeza do `main` depois do Dia 1

O Dia 1 foi arquivado no branch `day1` (tag `day1-final`, com os dados em `results/day1/`), e o `main` ficou só com o que o Dia 2 usa.

## 1. Odometria a 20 ms

### O que foi feito e por quê

A odometria é a única localização do robô, e os modos de calibração do Dia 2 (`straight`, `spin`, `umbmark`) precisam dela para saber quanto andaram e giraram. Ela roda no tick, logo depois da leitura das contagens, com a integração pelo ponto médio do ROADMAP:

`d = (dL + dR)/2`

`dθ = (dR − dL)/b`

`x += d·cos(θ + dθ/2)`

`y += d·sin(θ + dθ/2)`

`θ += dθ`

Decisões:

- **Uma leitura das contagens por tick.** O `wheel_speed::update()` já lia as contagens no início do tick. Agora, é guardada essa leitura, a qual a odometria e as amostras gravadas usam.
- **Escala por roda.** `odometry::Config` tem um m/contagem para cada roda e a bitola b, porque a calibração (UMBmark) corrige as duas rodas separadamente. Até a bancada, as duas usavam o valor nominal, π·67,5 mm/1319,75 = 0,16068 mm por contagem, e b = 0,217 m.
- **θ não é normalizado.** Um `spin` de N voltas precisa do ângulo total (2πN); só os erros de rumo serão levados a (−π, π].
- **`double`, não `float`**. Somando o mesmo dθ a cada tick, um θ em `float` erra ~4·10⁻⁴ rad em duas voltas, porque o arredondamento se repete. Fisicamente é nada (0,02°), mas atrapalharia a comparação com o Python.

### Resultados na placa

Dados: `data/day2/20261015-191705_app_{events,status,hook}.csv` (628 s), `20261015-192703_speed.csv` e `20261015-192704_speed_1_v250_a500.csv`.

- Para ver a pose ao vivo pelo ssh:

  ```bash
  ssh unoq 'tail -f "$(ls -t /home/arduino/ArduinoApps/agv/logs/*_status.csv | head -1)" | stdbuf -oL cut -d, -f14,15,23-25'
  ```

**Rodas giradas à mão** (colunas `enc_l, enc_r, x_mm, y_mm, th_mrad`; não precisa de uma volta exata, o que se confere é a pose contra as contagens):

| Trecho | Contagens (esq., dir.) | Esperado pelas contagens | Odometria |
|---|---|---|---|
| as duas para a frente | +665, +695 | x +109,3 mm, θ +22,2 mrad | x +109, θ +22 |
| as duas para a frente | +672, +660 | x +107,0 mm, θ −8,9 mrad | x +107, θ −9 |
| esquerda para trás, direita para a frente | −4333, +3608 | θ +5,880 rad | θ −20 → 5860 mrad (+5,880 rad); x −7 mm, y −11 mm |

- O sinal de θ está certo: quando a roda direita anda mais, θ cresce (anti-horário).
- θ passou de π (3142 mrad) sem pular para negativo, como planejado para o `spin` de várias voltas.
- No giro, x e y quase não mudaram. As rodas não giraram por igual: sobra (3608 − 4333)/2 × 0,1607 = 58 mm para trás, espalhados por quase uma volta (337°), que se cancelam.

**No chão:** `speed 250 500 4500 937`, terminado por distância em 4500 ms, 6211 / 6215 contagens:

| | Antes | Depois | Diferença |
|---|---|---|---|
| x, y (mm) | 1500, −38 | 1813, 909 | 997,4 mm na direção 1,2516 rad |
| θ (mrad) | 7531 (= 1,2478 rad + 2π) | 7534 | +3 mrad |

- A distância pela odometria (997,4 mm) bate com a média das contagens × 0,1607 (998,3 mm); a diferença de ~1 mm é o arredondamento do `status` em mm.
- O robô andou na direção do θ que tinha antes (1,2516 contra 1,2478 rad): a pose de partida vinha das voltas à mão.
- θ mudou +3 mrad, exatamente (6215 − 6211) × 0,1607 / 217 = 3,0 mrad. Isso é o que os encoders viram; o desvio real do `speed` sem controle de rumo só a fita mostra (bancada).

### Conclusões

- A odometria segue a fórmula do ROADMAP com escala por roda, θ sem normalizar e precisão de `double`, e confere com as contagens em todas as checagens.
- A pose está no `status` (2 Hz) para acompanhar ao vivo. A comparação exata com a referência em Python vem com o `straight`, que grava as contagens do tick e manda as poses de início e fim (`day2-linux.md`).

## 2. Perfil de movimento e PI de rumo (módulos puros)

### Resultados

**Perfil.** O teste nativo mostrou um efeito da lei amostrada: a velocidade de frenagem sai da distância no início do tick, mas o robô anda durante o tick, então nos últimos ~6 cm ele freia até ~8 % mais forte que a (0,51–0,54 m/s²) e um ponto ideal para ~2,6 mm depois de 1,38 m. A alternativa seria a lei exata no tempo discreto, `v = −a·dt + sqrt((a·dt)² + 2·a·s)`, que mantém a frenagem em a. 

**2,6 mm é muito menos que o erro de seguimento das rodas** e que a faixa de parada de 1,5 cm. O teste aceita até 1,1·a·dt por passo.

**PI de rumo.** Planta: θ' = ω atrás das malhas das rodas (primeira ordem, Tcl = 0,1 s, projeto do Dia 1). Com `ω = Kp·e + Kp/Ti·∫e`, Kp ≈ 2,3 s⁻¹ e Ti ≈ 1 s dão cruzamento perto de 2,5 rad/s, quatro vezes abaixo das rodas, com ~55° de margem de fase.

A primeira simulação não mostrou nada (ω = 0 sempre): ela usava um erro de rumo inicial e uma roda 1 % maior que o seu mm/contagem, e **nenhum dos dois aparece nas contagens**. Essa é a observação principal: o PI segura o rumo **da odometria**, então só corrige o que os encoders veem (uma roda atrasada em relação à outra, um degrau do piso de um lado). O erro de diâmetro e o rumo inicial ficam para a calibração (UMBmark) e para a pose de partida.

A segunda versão usava malhas das rodas com atrasos diferentes (0,13 e 0,08 s) e mostrou −55 mrad na frenagem final: artefato do modelo, porque o `wheel_pi` tem o feedforward `τ·a_ref` e segue as rampas quase exatamente (no Dia 1 as duas rodas terminaram 1 m a 2–6 contagens uma da outra, ≤ 4 mrad).

Modelo final (`analysis/day2_heading.py`): o perfil passa pelo feedforward, com erro de ±1 % em cada roda durante as rampas; só a correção de rumo e as perturbações passam pela malha de 0,1 s. Perturbações: queda de 40 mm/s na roda esquerda por 0,3 s no começo (como a execução 1 do item 0) e erro constante de 2 mm/s na direita. Rumo medido por contagens inteiras, como no firmware.

`uv run python analysis/day2_heading.py` → `data/day2/plots/heading_gains.csv`, `day2_heading_sim.png`:

| Kp (1/s) | Ti (s) | lateral no fim (mm) | maior \|rumo\| depois de 1,5 s (mrad) | maior \|ω\| (rad/s) |
|---|---|---|---|---|
| sem malha de rumo | — | 103 | ~100 | 0 |
| 1,5 | 1,0 | 0,9 | 13,0 | 0,076 |
| 2,3 | 0,5 | 0,1 | 18,7 (oscila) | 0,118 |
| **2,3** | **1,0** | **0,5** | **10,9** | **0,101** |
| 2,3 | 2,0 | 1,7 | 5,3 | 0,093 |
| 3,5 | 1,0 | 0,2 | 8,9 | 0,135 |

- Sem a malha de rumo, a mesma perturbação deixa 103 mm de desvio lateral em 1,38 m; com o PI, ≤ 3 mm em todas as combinações.
- Ti = 0,5 s oscila; Ti = 2 s demora a tirar o erro constante; Kp = 3,5 reage mais rápido, mas o ω fica mais ruidoso (a quantização das contagens entra multiplicada por Kp).
- O ω usado fica em ~0,1 rad/s, longe do limite de 0,5 rad/s (±54 mm/s entre as rodas).
- `uv run pytest`: 21 testes passam.

**Decisão:** Kp = 2,3 s⁻¹, Ti = 1,0 s (o projeto analítico), `w_max` = 0,5 rad/s, a confirmar no chão com o `straight`.

## 3. Camada `drive` e modo `straight` (5)

### O que foi feito e por quê

- **`straight` nasce do `speed`, sem cópia**. A parte em malha fechada das rodas saiu do `modes.cpp` para o módulo `drive`, e o `speed` passou a usá-lo com ω = 0, sem mudar o comportamento. Assim, rodar o `speed` de novo confere a camada `drive` contra números já conhecidos (item 0), antes de testar o `straight`.
- **`drive`**: recebe a velocidade do eixo v, a aceleração a, a taxa de giro ω e a aceleração angular α, e manda para cada roda `v ∓ ω·b/2` (e `a ∓ α·b/2` para o feedforward), convertidos em contagens/s com o m/contagem **daquela roda** (o K, o τ e o `pwm0` continuam valendo quando a bancada mudar o m/contagem). Também guarda o `encoder_guard` das duas rodas e conta os ticks sem contagem (`stopped()`: 2 ticks sem contagem nas duas rodas).
- **`straight`**: rumo alvo = θ no início, mantido pelo PI de rumo; distância restante ao longo do rumo inicial, `s = (w − p)·u0` com `w = p0 + D·u0`; o perfil para no alvo; abaixo de 1,5 cm (e depois do alvo) o PI de rumo segura e v só desce a rampa; termina **por alvo** (motivo novo, 6) quando o v comandado é 0 e as rodas pararam. Limites: o tempo (até 10 s) e uma segurança de 10 cm além do alvo terminam com parada em rampa (0,5 m/s²); o comando novo também; a emergência e o `encoder_guard` terminam na hora, em roda livre. Parâmetros: v (mm/s, com sinal, 50–300), aceleração (100–500 mm/s²), tempo (1–10 000 ms) e distância alvo (1–1600 mm).
- **Gravação para a referência em Python.** Uma amostra por tick com 8 valores: t, fase, v e ω comandados, as contagens **absolutas** lidas no tick (as mesmas da odometria) e os duties; 5 amostras por notificação `run_samples` (~215 B). O fim manda `run_end` com as poses de início e de fim (µm, µrad) e as constantes usadas pela odometria (m/contagem por roda em pm, b em nm), para o Python refazer a execução sem depender de uma cópia do `config.h`. O buffer passou para 1600 amostras × 8 (32 s, 51 KB de RAM), que cabe o `umbmark` depois.

### Resultados na placa, rodas fora do chão

Dados: `data/day2/20261015-194151_app_{events,status,hook}.csv`, `20261015-194523_speed*.csv`, `20261015-194536_straight.csv` (resumos) e `20261015-1945*_straight_<id>_v<v>_d<d>.csv` (amostras). Robô levantado, LiPo ligada, chave à mão.

| # | Comando | Fim | Duração | Contagens esq. / dir. | Amostras | Pela odometria |
|---|---|---|---|---|---|---|
| 1 | `speed 250 500 1500 450` | tempo | 2000 ms | 2358 / 2363 | 101 | — (confere a camada `drive`) |
| 2 | `straight 250 500 8000 1380` | **alvo** | 6060 ms | 8580 / 8587 | 304 | 1379,2 mm ao longo do rumo inicial; θ +5,2 mrad no fim |
| 3 | `straight -250 500 8000 500` | **alvo** | 2499 ms | −3110 / −3103 | 126 | 499,2 mm para trás; θ +5,2 mrad |
| 4 | `straight 250 500 2000 1380` | tempo | 2500 ms (2 s + a parada) | 3137 / 3136 | 126 | θ −0,7 mrad |
| 5 | `straight 250 500 8000 1380` + `idle` em +3,0 s | comando | 3521 ms (parada de 0,54 s) | 4693 / 4696 | 177 | θ +2,2 mrad; depois, `idle` |

Na execução 2, o rumo pelas contagens ficou dentro de ±3 mrad (±4 contagens de diferença entre as rodas, a resolução é 0,74 mrad por contagem) durante a velocidade constante, com ω ≤ 6 mrad/s: **o sinal da malha de rumo está certo** (com o sinal errado as rodas se afastariam e o ω iria ao limite). No fim, dentro dos últimos 1,5 cm, onde o rumo fica parado, a roda direita andou 5 contagens a mais na frenagem e 2 depois do duty zerar: o `straight` termina ~5 mrad fora do rumo inicial. No `umbmark` isso some, porque cada lado gira até um rumo absoluto; no `straight` só muda o rumo final, não o desvio lateral.

A comparação com a referência em Python está em `docs/logs/day2-linux.md`: as quatro execuções do `straight` batem dentro de 0,8 µm e 0,5 µrad.

### Resultados no chão

Dados: `data/day2/20261015-194856_app_{events,status,hook}.csv`, `20261015-194954_straight.csv` e `20261015-195*_straight_<id>_v<±250>_d1380.csv`; comparação e gráfico: `data/day2/plots/odometry_check_20261015-194856.csv`, `day2_odometry_20261015-194856.png`. Sobre a linha A→B, ida e volta alternadas: `straight 250 500 8000 1380` e `straight -250 500 8000 1380`, cinco execuções.

| # | Sentido | Fim | Duração | Contagens esq. / dir. | θ no início (mrad) | θ no fim |
|---|---|---|---|---|---|---|
| 1 | ida | alvo | 6020 ms | 8582 / 8586 | 44,4 | 47,4 |
| 2 | volta | alvo | 6060 ms | −8586 / −8585 | 47,4 | 48,1 |
| 3 | ida | alvo | 6020 ms | 8578 / 8585 | 48,1 | 53,3 |
| 4 | volta | alvo | 6020 ms | −8585 / −8585 | 53,3 | 53,3 |
| 5 | ida | alvo | 6041 ms | 8579 / 8582 | 53,3 | 55,5 |

- Pelos encoders, o robô andou reto: o rumo ficou a ±5 mrad do inicial e o desvio lateral em relação à linha de partida a **±0,3 mm** durante toda a execução. As idas e voltas batem com a referência em Python dentro de 0,6 µm e 0,6 µrad (`day2-linux.md`).
- Na volta, o rumo oscila mais (±4 mrad, ~1 Hz): os modelos para trás das duas rodas são mais diferentes (`pwm0` 8,8 % contra 7,2 %), e o PI trabalha mais. No caminho, isso dá ±0,3 mm.
- **O robô não chegou à marca de B.** As marcas de A e B no chão estavam a ~1500 mm uma da outra (medidas erradas), então a execução de 1380 mm parou antes. A distância real andada por contagem fica para a bancada (5 medidas de fita com marcas cuidadosas). Repetiu-se com `straight 250 500 8000 1500` e `straight -250 500 8000 1500` (execuções 6–9 da sessão `20261015-200927`).
- **Depois de 4 execuções, o robô voltou alguns centímetros ao lado de A.** Cerca de 1 cm disso a odometria vê: cada `straight` segura o rumo do **seu** início, e nos últimos 1,5 cm (onde o rumo fica parado) termina 1–5 mrad fora dele, que a execução seguinte herda. O rumo de partida foi 44 → 47 → 48 → 53 mrad, e a própria odometria põe o robô de volta em A 11 mm ao lado (y de −0,5 para −11,8 mm). Para as medidas de bancada isso não importa, porque o robô é recolocado em A a cada execução; no Dia 3 o controle ponto a ponto mira waypoints absolutos e não herda o rumo. O resto (escorregamento, diferença real de diâmetro entre as rodas) os encoders não veem, e é o que o UMBmark mede.

### Conclusões

- O `straight` faz o que foi pedido: termina por alvo em 1380 mm pela odometria, segura o rumo dentro de poucos mrad, e as amostras refazem a odometria exata.
- O PI de rumo está confirmado no chão com Kp = 2,3 s⁻¹ e Ti = 1,0 s.
- O que sobra é calibração (mm/contagem por roda e b), que é o bloco de bancada.

### A e B medidos de novo, encosto na parede

Dados: `data/day2/20261015-200927_app_{events,status,hook}.csv`, `20261015-200953_straight.csv` e `20261015-20*_straight_<id>_*.csv` (11 execuções; todas batem com a referência em Python, `plots/odometry_check_20261015-200927.csv`).

**A e B.** As posições de A e B do `CLAUDE.md` vinham de uma medida errada. Mediu-se de novo usando um único ponto do robô, 7 mm atrás da traseira das rodas (40,75 mm atrás do eixo): A_ref = (137, 745) mm e B_ref = (1540, 745) mm, θ0 = 0 (de frente para B). A distância é 1403 mm. Pela geometria, o centro fica 110,75 mm à frente desse ponto: A = (248, 745) e B = (1651, 745) mm. Mediu-se o centro direto em ~(260, 745) e ~(1650, 745); o de B bate com a geometria e o de A não (12 mm), então vale a geometria. y saiu ~750 mm nesta medida e continua 745. 

O eixo na partida fica em x = 178 mm, **dentro** dos 24,6 cm de inflação da parede: isso ficou em aberto para decidir antes do Dia 4.

**Uma ida de 1400 mm** (execução 11, `straight 250 500 8000 1400`): terminou por alvo, 8700 / 8705 contagens; Mediu-se o robô a 28,1 mm do alvo. É um resultado preliminar com as constantes nominais; a linha de base da bancada (fase 1 no ROADMAP) separa o erro ao longo da linha do erro lateral, em 5 execuções.

## 4. Giro no lugar e modo `umbmark` (6)

### O que foi feito e por quê

O ROADMAP pede o giro no lugar sobre o perfil angular (usado pelo `umbmark` e, no Dia 3, pelo estado ROTATE) e o modo `umbmark`, o quadrado do UMBmark nos dois sentidos. A forma do percurso segue o próprio artigo (Borenstein e Feng, IEEE Trans. Robotics and Automation 12(6), 869–880, 1996, doi 10.1109/70.544770; lido na versão dos autores): "stop after each 4 m straight leg; make a total of four 90°-turns on the spot; run the vehicle slowly to avoid slippage" (Seção 3.3), e "the robot made a fourth 90° turn after returning to its starting area" (Seção 5). As duas voltas do artigo começam de frente para +x, e o CCW vira primeiro à esquerda e o CW à direita (Fig. 7), como as nossas.

### Decisões

- **Parâmetros do ROADMAP:** `umbmark <sentido> <lado_mm> <v_mm_s> <tempo_ms>`, sentido 1 = CCW e −1 = CW. A aceleração das pernas é fixa em 0,5 m/s², e o giro vai até 90°/s com α = 2a/b = 4,61 rad/s², de modo que cada roda também acelera e freia a 0,5 m/s². Uma parada em rampa durante o giro (tempo ou comando) freia ω em α.
- **Alvos absolutos, fixados pela pose de início**. O canto k é `p0 + L·(u0 + … + uk)`, e o rumo da perna k é `θ0 + sentido·k·π/2`. Cada perna mede o que falta até o seu canto ao longo do seu rumo, `s = (w − p)·u`, como o `straight`, e cada giro mira um rumo absoluto (θ não normalizado, então o alvo do quarto giro é `θ0 ± 2π`). Assim, os erros de parada de uma perna ou de um giro não se acumulam, e a odometria fecha o quadrado. O rumo da perna é fixo, sem re-mirar o canto: re-mirar é do controle ponto a ponto do Dia 3.
- **Quarto giro incluído**, como no artigo: o robô termina de frente para o rumo inicial.
- **`straight` e `umbmark` usam as mesmas peças.** O `straight` virou uma perna só (`tick_leg`), e o `umbmark` alterna `tick_leg` e `tick_turn`. A guarda de ultrapassagem passou a valer para qualquer perna (`kLegOvershootM`, 10 cm), e o motivo 2 (`distance`) passou a significar só essa guarda, já que o `speed` saiu (item 5).
- **Limites no handler:** sentido ±1, lado 100–1000 mm, v 50–300 mm/s, tempo 1–30 000 ms. O buffer de amostras tem 1600 amostras (32 s), e 30 s mais a parada cabem nele. Com lado de 1 m, uma volta leva 23,3 s a 250 mm/s (medido abaixo), e pela conta ~27 s a 200 mm/s; mais devagar que isso, o quadrado de 1 m não cabe nos 30 s.
- **Sem modo de giro separado:** o `spin` saiu do plano (item do ROADMAP), e o giro é testado dentro do `umbmark`.

### Resultados na placa, rodas fora do chão

Dados: `data/day2/20261015-214618_app_{events,status,hook}.csv`, `20261015-214733_umbmark.csv` (resumos) e `20261015-2148*`/`2149*_umbmark_<id>_<ccw/cw>_L1000.csv` (amostras). Robô levantado, LiPo ligada, chave à mão (regra do Dia 1 para código de motor novo).

- Deploy: o mesmo tamanho do PC (139 296 / 109 700 B), `Arduino_RouterBridge` da cópia corrigida.
- Comandos que precisam ser recusados, nenhum moveu as rodas:

| Comando | Resultado |
|---|---|
| `speed 250 500 1500 450` | `cmd_rejected` no Python (item 5) |
| `umbmark 2 1000 250 30000` | `ack=False` (sentido) |
| `umbmark 1 1000 250 30001` | `ack=False` (tempo) |
| `umbmark -1 1001 250 30000` | `ack=False` (lado) |
| `umbmark 1 1000 40 30000` | `ack=False` (velocidade) |
| `straight 250 500 8000 1601` | `ack=False` (distância) |

- Execuções:

| # | Comando | Fim | Duração | Amostras | Pela odometria |
|---|---|---|---|---|---|
| 1 | `umbmark 1 1000 250 30000` | **alvo** | 23 301 ms | 1166 | fechou a 1,6 mm (x) e 4,0 mm (y) do início; θ 10,0 mrad antes de θ0 + 2π |
| 2 | `umbmark -1 1000 250 30000` | **alvo** | 23 301 ms | 1166 | fechou a 1,2 mm e 1,3 mm; θ 10,7 mrad antes de θ0 − 2π |
| 3 | `umbmark 1 1000 250 30000` + `idle` em ~4,9 s | comando | 5140 ms | 258 | parou no meio do primeiro giro (30°), 0,34 s depois do `idle` |
| 4 | `umbmark -1 1000 250 5000` | tempo | 5341 ms | 268 | parou no meio do primeiro giro (49°), 0,34 s depois dos 5 s |

As quatro batem com a referência em Python (`docs/logs/day2-linux.md`, item 2). Por fase, pela tabela nova do `day2_odometry_check.py` (`uv run python analysis/day2_odometry_check.py data/day2/20261015-214618_app_events.csv`):

| | Execução 1 (CCW) | Execução 2 (CW) |
|---|---|---|
| Pernas: duração | 4,4–4,5 s | 4,5 s |
| Pernas: parada antes do canto | 1,4–1,7 mm | 1,4–1,6 mm |
| Pernas: maior desvio lateral da linha do canto | 2,5 mm | 1,8 mm |
| Pernas: maior erro de rumo | 10,5 mrad (no início, herdado do giro) | 13,1 mrad |
| Giros: duração | 1,3 s | 1,3–1,4 s |
| Giros: fim em relação ao alvo | 9,4–10,6 mrad **antes** | 9,7–13,1 mrad **antes** |

- O `umbmark` faz o quadrado: oito fases, cada uma termina parada, e a odometria volta ao início com o rumo inicial.
- **Os giros terminam ~0,6° antes do alvo, nunca depois**, ao contrário do que a simulação indicava. As amostras do fim do primeiro giro mostram por quê:

| t (ms) | ω comandado (mrad/s) | contagens no tick esq. / dir. | duty esq. / dir. (×10⁻⁴) |
|---|---|---|---|
| 5680 | 477 | −5 / 6 | −232 / 219 |
| 5700 | 386 | −4 / 3 | −97 / 92 |
| 5720 | 294 | −3 / 3 | 10 / 138 |
| 5740 | 202 | −2 / 0 | 120 / −19 |
| 5760 | 111 | 0 / 0 | 234 / 34 |
| 5780 | 19 | 1 / 0 | 0 / 0 |

  As rodas param de contar com o ω comandado ainda em 0,2–0,3 rad/s (21–31 mm/s na roda, bem acima dos 5 mm/s do `v_min`), e o duty já empurra no sentido contrário: elas param ~2 ticks antes da referência. A explicação mais provável (não medida à parte): o modelo das rodas (K, τ, `pwm0`) foi identificado no chão, com a massa do robô; no ar as rodas têm muito menos inércia, e o termo `τ·a_ref` do feedforward freia demais na descida. É a mesma tendência das pernas (paradas 1,4–1,9 mm antes, e o `straight` no ar 0,8 mm antes, item 3). No chão o número muda, e a tabela por fase vai mostrar isso já nas execuções da bancada.
- 0,6° está dentro dos 3°. A perna seguinte corrige o resto com o PI de rumo (erro de rumo ≤ 13 mrad no início da perna, ≤ 2,5 mm de desvio lateral pela odometria). Para a calibração isso não importa: o erro do UMBmark é real − odometria (bancada), e a odometria registra o giro que aconteceu.
- Status da sessão (419 linhas, 209 s): 0 overrun, 0 emergência, corpo do tick ≤ 0,55 ms, pico da pilha da Bridge 904 B (≥ 1144 B intactos), dt 18,7–21,1 ms, `pwm_hz` = 20000, 0 erro de encoder, nenhum `hook`. O atraso do início do tick chegou a 1,56 ms, com 96 de 419 janelas acima de 1,1 ms. Isso não é novo: desde a sessão da odometria (`20261015-191243`, item 1), 25–30 % das janelas com o robô parado ficam acima de 1,1 ms (máximo 1,66 ms), contra 2 de 172 na primeira sessão do dia. Não houve overrun em nenhuma sessão.

### Conclusões

- O giro no lugar segue a lei do `CLAUDE.md` (até 90°/s, α = 2a/b, descida em α abaixo de 3°, fim com ω = 0 e rodas paradas) e termina a ~0,6° do alvo no ar. É a mesma peça que o ROTATE do Dia 3 vai usar.
- O `umbmark` percorre o quadrado do artigo nos dois sentidos, para em cada canto, faz os quatro giros, termina por alvo em 23,3 s, e as paradas por comando e por tempo no meio de um giro são em rampa.
- O próximo passo é a bancada (`docs/logs/day2-bench.md`). As primeiras execuções no chão mostram, pela tabela por fase, onde os giros terminam com a inércia real.

## 5. Aposentadoria do `speed` (4)

### O que foi feito e por quê

O `speed` era o teste do PI das rodas em malha fechada (Dia 1). O ROADMAP o aposentava depois de o `straight` ser testado, como os códigos 1–3. O `straight` foi testado no ar e no chão (item 3), então ele saiu agora. O código 4 fica sem uso, para os registros do Dia 1 e do item 0 continuarem valendo.

| Onde | O que saiu |
|---|---|
| `modes` | `kSpeed`, os limites, `valid_speed`, `start_speed`, `tick_speed` (rampa ou degrau sem perfil de posição), o limite de distância pela roda mais distante (`distance_to_counts`, `distance_reached`), a amostra de 6 valores e o `speed_end` |
| Python | `SPEED` e o comando `speed` em `mode_commands.py`, `on_speed_end`, `on_speed_samples` e os cabeçalhos deles em `telemetry.py`, o registro em `main.py`; as amostras passaram a ter um formato só (`RUN_SAMPLE_HEADER`) |
| Testes | `test_parse_speed`; `test_parse` confere que `speed …` agora é recusado |

O que o `speed` testava continua no `straight` e no `umbmark`: as rodas são as mesmas (`drive` → `wheel_pi`), com o `encoder_guard`.

### Resultados

- `run speed 250 500 1500 450` → `cmd_rejected` no Python (tabela do item 4); se chegasse ao MCU, o `valid()` também o recusaria (código desconhecido).
- O tamanho do sketch está no item 4 (o `speed` saiu no mesmo deploy).

### Conclusões

O firmware tem agora só `idle`, `straight` e `umbmark`, todos com perfil de posição, parada em rampa e o relatório `run_end` para a referência em Python. O bloco Firmware do Dia 2 está completo; o que falta do Dia 2 é a bancada.

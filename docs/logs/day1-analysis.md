# Dia 1 — Análise: modelo das rodas e ganhos do PI

## 1. Ferramentas da análise (`analysis/`)

### O que foi feito e por quê

- **Separar a matemática do script.** `analysis/wheel_model.py` só tem funções puras (carregar os CSVs, ajustar o modelo, achar a partida na rampa), testadas com dados sintéticos em `tests/test_wheel_model.py`; `analysis/day1_identify.py` só aplica essas funções na sessão, imprime as tabelas deste log e desenha os gráficos.
- **A sessão é escolhida pelo log de eventos dela.** Os ids das execuções gravadas (`record_id`) recomeçam a cada boot, e a sessão com as rodas no ar também tem um `step_1_L200_R200`; os eventos `step_samples`/`ramp_samples` de cada sessão dizem exatamente quais arquivos são dela.
- **Só numpy no ajuste, sem scipy.** Para um τ fixo, o modelo é linear em `v_ss`, que então tem fórmula fechada (mínimos quadrados); só τ precisa ser procurado, numa grade de 1 ms seguida de seção áurea.

### Comandos

```bash
uv add --group analysis matplotlib numpy   # matplotlib 3.11.2, numpy 2.5.3
uv run pytest                               # 22 passed (6 novos em tests/test_wheel_model.py)
uv run python analysis/day1_identify.py     # tabelas abaixo + data/day1/plots/
```

### Saídas

- `data/day1/plots/identification_steps.csv`: um ajuste por `step` e roda;
- `data/day1/plots/identification_model.csv`: um resumo por roda e sentido;
- `data/day1/plots/day1_step_fits.png`, `day1_slip_check.png`, `day1_speed_vs_duty.png`.

## 2. Modelo de primeira ordem: K e τ pelos `step`

### O modelo

Por roda e sentido, em contagens/s, com u o duty em [0, 1] sem o sinal do sentido:

    τ·dv/dt + v = K·(u − pwm0)     enquanto a roda anda

Um degrau de duty u a partir do repouso dá a velocidade `v(t) = v_ss·(1 − e^(−t/τ))` com `v_ss = K·(u − pwm0)`, e as contagens acumuladas

    x(t) = v_ss·(t − τ·(1 − e^(−t/τ)))

O ajuste é feito em `x(t)`, as contagens gravadas a cada 2 ms, e não na velocidade: derivar contagens dá velocidades com degraus de 500 contagens/s a 2 ms (uma contagem a mais ou a menos), e a integral filtra esse ruído.

### Como cada `step` foi ajustado (`fit_first_order`)

1. O sinal do sentido é tirado (para trás as contagens são negativas).
2. O tempo zero é a amostra 0, tomada logo antes de o duty ser aplicado; o ajuste usa todas as ~500 amostras do `step` (1 s).
3. Para cada τ de 5 a 1000 ms, de 1 em 1 ms, `v_ss` sai de mínimos quadrados (`v_ss = Σg·x / Σg²`, com `g = t − τ(1 − e^(−t/τ))`); o τ com o menor erro é refinado por seção áurea entre os vizinhos da grade.
4. Conferência sem modelo: a velocidade numa janela centrada de 40 ms, normalizada pela média depois de 0,7 s, e os instantes em que ela passa de 50, 63,2 e 90 %. Num sistema de primeira ordem, t63 = τ.

Um tempo morto foi testado na exploração (τ, `v_ss` e atraso livres): o atraso ajustado foi 0 ms em todos os `step` (a primeira contagem aparece 4 ms depois do início), por isso ficou fora do modelo.

### Resultados (`identification_steps.csv`)

| roda | sentido | duty | v_ss (contagens/s) | τ (ms) | rms (contagens) | v 0,7–1 s | t50 | t63 | t90 (ms) |
|---|---|---|---|---|---|---|---|---|---|
| E | + | 0,20 | 900 | 164 | 2,2 | 910 | 118 | 170 | 370 |
| E | + | 0,25 | 1258 | 156 | 3,0 | 1266 | 104 | 164 | 410 |
| E | + | 0,30 | 1621 | 141 | 2,3 | 1627 | 100 | 156 | 346 |
| E | − | 0,20 | 779 | 161 | 1,7 | 782 | 104 | 168 | 420 |
| E | − | 0,25 | 1071 | 143 | 3,2 | 1089 | 104 | 148 | 434 |
| E | − | 0,30 | 1404 | 137 | 3,0 | 1432 | 98 | 146 | 352 |
| D | + | 0,20 | 972 | 128 | 1,3 | 980 | 88 | 126 | 308 |
| D | + | 0,25 | 1311 | 103 | 2,3 | 1327 | 72 | 106 | 246 |
| D | + | 0,30 | 1673 | 96 | 2,1 | 1674 | 66 | 100 | 238 |
| D | − | 0,20 | 955 | 147 | 2,6 | 960 | 100 | 152 | 380 |
| D | − | 0,25 | 1327 | 160 | 5,1 | 1353 | 110 | 168 | 438 |
| D | − | 0,30 | 1723 | 122 | 4,1 | 1774 | 88 | 132 | 300 |

- **O modelo de primeira ordem descreve bem os `step`:** o erro rms da posição fica entre 1,3 e 5,1 contagens (0,2–0,8 mm) em 650 a 1530 contagens percorridas, e o t63 sem modelo fica a 2–15 ms do τ ajustado (`day1_step_fits.png`).
- **A cauda lenta:** a velocidade média em 0,7–1 s fica 0–3 % acima do `v_ss` ajustado, e ajustando só os primeiros 0,5 s o τ cai 6–26 % (exploração). Existe uma parte mais lenta que a primeira ordem não captura, pequena (poucos %), que o integrador do PI absorve. 1 s de `step` (6–10 τ) basta para o ajuste.
- **O começo é um pouco mais rápido que a primeira ordem:** no `step` de +30 % da esquerda, aos 30 ms a roda tinha andado 9 contagens contra ~5 do modelo, efeito pequeno diante do resto do degrau.
- **As rodas diferem:** τ da direita para a frente (96–128 ms) é bem menor que o da esquerda (141–164 ms); para trás os dois ficam em 122–161 ms.

### K e pwm0 pela reta das velocidades de regime

Para cada roda e sentido, a reta `v_ss = K·(u − u0)` pelos três `step` (`steady_line`):

| roda | sentido | K (contagens/s por unidade de duty) | u0 (%) |
|---|---|---|---|
| E | + | 7210 | 7,53 |
| E | − | 6247 | 7,64 |
| D | + | 7007 | 6,18 |
| D | − | 7677 | 7,61 |

Em m/s (0,1607 mm por contagem no Ø nominal), K ≈ 1,0–1,23 m/s por unidade de duty. Os três pontos ficam quase sobre a reta (`day1_speed_vs_duty.png`): a relação entre duty e velocidade é linear com um deslocamento, como o feedforward `pwm = pwm0·sign(v) + v/K` supõe.

## 3. `pwm0` pelas rampas

### Critério de partida

Na rampa, uma contagem isolada aparece bem antes de a roda andar de verdade. O critério de partida é de **movimento sustentado**:

- a partida é o primeiro intervalo de 20 ms de uma sequência de **5 intervalos seguidos, cada um com pelo menos uma contagem** (≥ 50 contagens/s, ~8 mm/s, em cada um);
- o `pwm0` é o duty **aplicado nesse intervalo**: o duty gravado na amostra i é o aplicado desde a amostra i − 1, então é o duty da amostra que fecha o primeiro intervalo com contagem;
- a sensibilidade é conferida com 10 intervalos seguidos.

Como o duty sobe 1 ‰ por tick, o critério não tem atraso de detecção: o duty registrado é o do primeiro intervalo em movimento, não o do quinto.

### Segunda estimativa: a reta da parte em movimento

A rampa também dá uma reta velocidade × duty (`ramp_line`), com velocidade numa janela de 80 ms e pontos acima de 200 contagens/s. Numa rampa de taxa r, a velocidade de primeira ordem fica atrasada τ·r em duty em relação à de regime (5 %/s × ~0,15 s ≈ 0,7 %), e esse atraso é descontado antes do ajuste (testado em `test_ramp_line_removes_first_order_lag`).

### Resultados (`identification_model.csv`)

| roda | sentido | partida N = 5 (%) | N = 10 (%) | reta da rampa K / u0 (%) | reta dos `step` K / u0 (%) |
|---|---|---|---|---|---|
| E | + | 7,4 | 8,0 | 6231 / 5,64 | 7210 / 7,53 |
| E | − | 8,8 | 8,8 | 6042 / 6,52 | 6247 / 7,64 |
| D | + | 6,9 | 6,9 | 7726 / 6,15 | 7007 / 6,18 |
| D | − | 7,2 | 8,3 | 7997 / 6,43 | 7677 / 7,61 |

- **A partida (atrito estático) fica em 6,9–8,8 %**, perto da interseção da reta dos `step` (6,2–7,6 %): no gráfico `day1_speed_vs_duty.png`, a reta tirada só dos `step` (20–30 %) passa sobre a velocidade da rampa (7–16 %). Um modelo linear com deslocamento vale de 7 a 30 %.
- A reta só da rampa tem interseção 0,8–2,3 pontos de duty abaixo da partida: o atrito com a roda já girando é menor que o de partida, como esperado.
- Em dois casos (E+, D−) a roda hesitou logo depois de partir, e o critério com 10 intervalos dá 0,6–1,1 % a mais.

**Decisão:** o `pwm0` do feedforward é a partida com N = 5

## 4. Checagem de escorregamento

### Critério

K e τ ajustados a 20, 25 e 30 % devem concordar; um `step` com τ claramente menor que os outros escorregou (a roda acelerou mais rápido que o robô conseguia acompanhar), e então ele sai e ficam as amplitudes abaixo dele.

### Resultados (`day1_slip_check.png`)

| roda / sentido | τ a 20 / 25 / 30 % (ms) | t63 a 20 / 25 / 30 % (ms) |
|---|---|---|
| E + | 164 / 156 / 141 | 170 / 164 / 156 |
| E − | 161 / 143 / 137 | 168 / 148 / 146 |
| D + | 128 / 103 / 96 | 126 / 106 / 100 |
| D − | 147 / 160 / 122 | 152 / 168 / 132 |

- **K concorda:** os três pontos de regime ficam sobre uma reta em todas as rodas e sentidos (seção 2). Escorregamento só afeta a aceleração; em regime a roda não escorrega.
- **τ cai com a amplitude em quase todos os casos**, não só a 30 %: 14 % da esquerda para a frente, 15 % da esquerda para trás, 25 % da direita para a frente (já 20 % a 25 %); a direita para trás sobe a 25 % e cai 17 % a 30 %.
- A maior queda (D+) coincide com a maior aceleração inicial da roda, `v_ss/τ` ≈ 1,2 m/s² a 20 %, 2,0 a 25 % e 2,8 a 30 %; mas a esquerda também cai, com acelerações menores (0,8–1,8 m/s²).
- Só com os encoders não dá para separar escorregamento de uma dinâmica que muda com a amplitude: falta a posição real do robô durante o degrau.

### Decisão

**Nenhum `step` sai.** A queda de τ é gradual e aparece em todas as rodas e sentidos, então é tratada como dinâmica que depende da amplitude, não como escorregamento. τ por roda e sentido é a **média das três amplitudes** (E+ 154, E− 147, D+ 109, D− 143 ms), e o PI é conferido na simulação com o menor e o maior τ medidos de cada roda e sentido como planta (seção 5). As alternativas recusadas foram tirar os `step` D+ de 25 e 30 % (usando 128 ms para D+) e usar só os τ de 20 %.

Contexto que pesa a favor: a rampa de operação acelera a 0,5 m/s², bem abaixo das acelerações iniciais dos `step` (0,8–2,8 m/s²), então mesmo um escorregamento nos `step` maiores não acontece no uso.

## 5. Ganhos do PI

### Simulação preliminar

Simulação discreta da malha de uma roda (um script provisório fora do repositório; a versão final é `analysis/speed_loop.py`, abaixo): planta `τ·dv/dt + v = K(u − pwm0)` integrada a 0,5 ms, K = 7000, pwm0 = 7 %; tick de 20 ms; velocidade medida pela diferença de contagens inteiras no último tick (como `wheel_speed`); PI com cancelamento do polo (Ti = τ de projeto = 130 ms) e `Kp = τ/(K·Tcl)`; anti-windup por integração condicional; τ real de 100, 130 e 165 ms para cobrir o espalhamento medido.

| Variante | Tcl | Rampa 0,5 m/s² até 0,25 m/s: maior erro | Degrau 0 → 0,1 m/s: sobressinal / acomodação 2 % / duty máx. |
|---|---|---|---|
| `pwm0·sign(v) + v/K` + PI | 0,05 s | 17–24 mm/s | 25–27 % / 0,46–1,36 s / 0,39 |
| idem | 0,10 s | 23–32 mm/s | 19–22 % / 0,58–0,62 s / 0,28 |
| idem | 0,15 s | 25–36 mm/s | 18–22 % / 0,70–0,76 s / 0,24 |
| + termo de aceleração `τ·a_ref/K` no feedforward | 0,10 s | 15 mm/s | (degrau sem `a_ref`: igual à linha acima) |
| ponderação do setpoint no P (b = 0,5), sem termo de aceleração | 0,10 s | 29–39 mm/s | 2–8 % / 0,14–0,62 s / 0,23 |

- **O sobressinal de ~20 % no degrau vem da estrutura, não da sintonia:** com feedforward estático a planta já vai sozinha para o setpoint com τ, e o PI empurra junto. A malha fechada de r para v fica `(1 + (τ + Tcl)s) / ((1 + τs)(1 + Tcl·s))`, cujo zero é mais lento que os dois polos.
- **Na rampa, o feedforward estático deixa um erro de ~τ·a** (0,13 s × 0,5 m/s² ≈ 65 mm/s em malha aberta) que o integrador vai tirando; o termo de aceleração, calculado da aceleração comandada pelo perfil (não derivando o setpoint), corta o pico para ~15 mm/s, quase sem depender de Tcl e do τ real.
- O duty fica abaixo de 0,40 em todos os casos simulados.

### Decisões

- Qual `pwm0` no feedforward -> A **partida da rampa** (N = 5); K por mínimos quadrados pelos três `step` com esse deslocamento fixo (`gain_with_offset`).
- Termo de aceleração no feedforward? -> **Sim**: `τ·a_ref/K`, com `a_ref` a aceleração comandada pelo perfil (0 num degrau), nunca a derivada do setpoint. 
- Tcl e limite de duty -> **Tcl = 0,1 s** (5 ticks; o ruído de quantização da velocidade, 50 contagens/s por tick, vira ~1 % de duty) e **duty limitado a 50 %** em malha fechada.
- Anti-windup | **Integração condicional**: o integrador só anda enquanto o duty não está no limite, ou quando o erro o traz de volta

### O controlador (`analysis/speed_loop.py`)

A cada tick de 20 ms, por roda, em contagens/s, com os parâmetros da roda e do sentido de `v_ref`:

    u = pwm0·sign(v_ref) + (v_ref + τ·a_ref)/K + Kp·e + I,   

    e = (v_ref + v_ref_anterior)/2 − v_medida

    Kp = τ/(K·Tcl)

    Ki = Kp/τ = 1/(K·Tcl)

    I += Ki·e·0,02 s (condicional),   |u| ≤ 0,5

    |v_ref| abaixo de 5 mm/s: u = 0 (coast) e I = 0

- **PI por cancelamento do polo:** com Ti = τ, o zero do PI cancela o polo da roda e a malha fica `C·G = 1/(Tcl·s)`; sem o feedforward, a malha fechada seria uma primeira ordem com constante Tcl.
- **`e` usa o setpoint médio do último tick:** a velocidade medida é a média do último tick (`wheel_speed`), ou seja a velocidade de ~10 ms atrás. Comparada com o setpoint de agora, numa rampa de 0,5 m/s² ela parece 5 mm/s atrasada, e o PI empurra a roda 5 mm/s acima da referência: na simulação, o erro na rampa (depois de 0,1 s) caiu de 6,2 para 2,2 mm/s e a velocidade no fim da rampa de 0,256 para 0,252 m/s. Isso é guardar o setpoint do tick anterior e usar a média dos dois, que numa rampa é o setpoint de 10 ms atrás (a simulação provisória usou esse; a final e o firmware usam a média).

### Ganhos (`data/day1/plots/pi_gains.csv`)

| roda | sentido | K (contagens/s por unidade) | τ (ms) | `pwm0` (%) | Kp (duty por contagem/s) | Ki (duty por contagem) |
|---|---|---|---|---|---|---|
| E | + | 7160 | 154 | 7,4 | 2,145·10⁻⁴ | 1,397·10⁻³ |
| E | − | 6668 | 147 | 8,8 | 2,199·10⁻⁴ | 1,500·10⁻³ |
| D | + | 7271 | 109 | 6,9 | 1,500·10⁻⁴ | 1,375·10⁻³ |
| D | − | 7509 | 143 | 7,2 | 1,902·10⁻⁴ | 1,332·10⁻³ |

Leitura: um erro de 100 contagens/s (16 mm/s) dá ~2 % de duty pelo P; o mesmo erro mantido por 1 s acumula ~14 % pelo I.

### Comandos

```bash
uv run python analysis/day1_pi.py   # ganhos, simulação e data/day1/plots/day1_pi_sim.png
uv run pytest                       # 27 passed (5 novos em tests/test_speed_loop.py)
```

### Simulação dos dois testes de malha fechada do ROADMAP

Cada roda e sentido, com o modelo de projeto (τ médio) e com o menor e o maior τ medidos como planta (planta: `τ·dv/dt + v = K·max(|u| − pwm0, 0)`, integrada a 0,2 ms, contagens inteiras, velocidade medida pela diferença de contagens no tick):

| roda | sentido | τ da planta (ms) | rampa: erro máx. (mm/s) | depois de 0,1 s | vel. máx. (m/s) | duty máx. | degrau: sobressinal | acomodação 2 % (ms) | duty máx. |
|---|---|---|---|---|---|---|---|---|---|
| E | + | 154 | 10,0 | 2,2 | 0,252 | 0,36 | 19 % | 660 | 0,29 |
| E | + | 141 | 10,0 | 2,4 | 0,251 | 0,35 | 18 % | 600 | 0,29 |
| E | + | 164 | 10,0 | 4,1 | 0,254 | 0,36 | 19 % | 660 | 0,29 |
| E | − | 147 | 10,0 | 2,3 | 0,252 | 0,39 | 19 % | 620 | 0,32 |
| E | − | 137 | 10,0 | 2,4 | 0,251 | 0,38 | 18 % | 620 | 0,32 |
| E | − | 161 | 10,0 | 4,4 | 0,254 | 0,39 | 19 % | 640 | 0,32 |
| D | + | 109 | 10,0 | 2,5 | 0,252 | 0,33 | 20 % | 540 | 0,25 |
| D | + | 96 | 10,0 | 2,9 | 0,251 | 0,32 | 19 % | 520 | 0,25 |
| D | + | 128 | 10,0 | 5,7 | 0,256 | 0,34 | 21 % | 580 | 0,25 |
| D | − | 143 | 10,0 | 2,4 | 0,252 | 0,34 | 18 % | 620 | 0,27 |
| D | − | 122 | 10,0 | 3,6 | 0,251 | 0,33 | 18 % | 620 | 0,27 |
| D | − | 160 | 10,0 | 5,2 | 0,255 | 0,34 | 20 % | 640 | 0,27 |

- **O erro de 10,0 mm/s é o primeiro tick da rampa:** o setpoint já vale 0,5 m/s² × 20 ms enquanto a roda só começa a responder durante esse tick. Depois de 0,1 s o erro fica em 2–6 mm/s (`day1_pi_sim.png`).
- **O degrau 0 → 0,1 m/s não satura** (duty ≤ 0,32 com limite de 0,5), como o ROADMAP exige; o sobressinal de 18–21 % é o da estrutura feedforward + PI (seção acima), e a acomodação a 2 % leva 0,5–0,7 s.
- **O τ errado em ±15 % pouco muda:** o feedforward faz a maior parte do trabalho e o PI só corrige.
- A simulação não tem: a cauda lenta da seção 2, a queda da LiPo, o acoplamento entre as rodas pelo corpo do robô e a diferença entre atrito de partida e de movimento. Os testes no chão dizem o resto.

## 6. Firmware dos testes em malha fechada

### Decisões

| Pergunta | Decisão |
|---|---|
| Interface | **Um código, 4 = `speed`**: `mode(4, v, a, tempo, distância)`, p1 = velocidade alvo em mm/s (com sinal = sentido), p2 = aceleração em mm/s² (0 = degrau), p3 = limite de tempo em ms, p4 = limite de distância em mm. Comando de texto `speed <v> <a> <tempo_ms> <dist_mm>` |
| Limites e fim | Recusado no handler fora de \|v\| ≤ 300 mm/s, a = 0 ou 100..500 mm/s², tempo 1..3000 ms, distância 1..600 mm. **Tempo, distância ou um comando novo começam uma parada em rampa a 0,5 m/s² em malha fechada** (modo em malha fechada termina com parada em rampa), depois coast; emergência → freio travado. Duty limitado a 50 % dentro do PI |
| Gravação | **6 valores por tick**: t_us, v_ref (contagens/s), contagens esq. e dir., duty esq. e dir. em décimos de milésimo; 10 amostras por notificação; a gravação cobre a execução inteira, parada incluída |
| Plano de testes | **Os dois sentidos**: no chão, a 12,6 V, rampa `speed 250 500 1500 450` e degrau `speed 100 0 1500 250`, cada um para a frente e para trás, uma vez cada |

- **Os ganhos ficam em `config.h`** como `wheel_pi::Model` por roda e sentido (K, τ, `pwm0`), com Tcl, o limite de duty e a velocidade mínima; Kp e Ki saem de K, τ e Tcl dentro do `update()`, então os números do `config.h` são os medidos, não ganhos derivados.
- **Um `idle` ou `count` durante o `speed` espera a parada em rampa** e só então começa. Os modos gravados não chegam a esse caso: `valid()` os recusa enquanto as amostras do `speed` não saíram.
- **O perfil da rampa sai do tempo desde o início** (`v = a·t`, limitado ao alvo), não somando `a·dt` a cada tick, para o jitter do tick não se acumular; na parada, `v_ref` cai `0,5 m/s² × dt medido` por tick e o modo termina quando o próximo passo passaria de zero.
- **A primeira amostra é a do tick em que o modo começa** (repouso, tudo zero); diferente da rampa de PWM, não há uma amostra 0 repetida 63 µs antes.
- **`dt` do integrador é o medido** (`wheel_speed::dt_us()`), como as velocidades.

## 7. Testes em malha fechada no chão da arena

### O que foi feito

```bash
# os cinco fora dos limites: todos ack=False, nada se moveu
./deploy.sh run speed 301 0 1000 100
./deploy.sh run speed 100 50 1000 100
./deploy.sh run speed 100 0 3001 100
./deploy.sh run speed 100 0 1000 601
./deploy.sh run speed 0 0 1000 100
# no chão, alternando o sentido para o robô voltar perto do início
./deploy.sh run speed 250 500 1500 450    # 1 e 2 (ver abaixo)
./deploy.sh run speed -250 500 1500 450   # 3
./deploy.sh run speed 100 0 1500 250      # 4
./deploy.sh run speed -100 0 1500 250     # 5
./deploy.sh pull day1
uv run python analysis/day1_closed_loop.py
```

Dados: `data/day1/20261011-222209_app_{events,status,hook}.csv`, `20261011-222351_speed.csv`
(resumos) e um arquivo por execução, `20261011-222351_speed_1_v250_a500.csv` (sem motor) …
`20261011-222613_speed_5_v-100_a0.csv`.

| # | Comando | Fim | Duração (com a parada) | Contagens esq. / dir. | Amostras |
|---|---|---|---|---|---|
| 1 | `speed 250 500 1500 450` | tempo | 2019 ms | 0 / 0 (LiPo desconectada) | 102 |
| 2 | `speed 250 500 1500 450` | tempo | 2001 ms | 2343 / 2345 | 101 |
| 3 | `speed -250 500 1500 450` | tempo | 2019 ms | −2337 / −2332 | 102 |
| 4 | `speed 100 0 1500 250` | tempo | 1700 ms | 1000 / 1004 | 86 |
| 5 | `speed -100 0 1500 250` | tempo | 1681 ms | −998 / −992 | 85 |

- A rampa andou 377 mm (o planejado era ~375 mm: 62,5 mm subindo, 250 mm a 0,25 m/s, 62,5 mm
  parando) e o degrau 161 mm.
- **As duas rodas andaram a mesma distância** (diferença de 2 a 6 contagens, < 1 mm); nos `step` em
  malha aberta a direita andava 8–25 % mais.
- Na sessão (523 linhas de `status`): 0 overrun, atraso máximo do tick 1622 µs, corpo máximo 472 µs, maior passagem fora do `loop()` 2697 µs (abaixo dos 3 ms do `hook`, que ficou vazio), dt 18,7–21,5 ms, 0 erros de encoder, nenhuma emergência; **pico da pilha da Bridge 896 B, com no mínimo 1152 B intocados**, com os encoders e a malha fechada rodando.

### Definições da análise

- **Velocidade do intervalo:** diferença de contagens entre duas amostras sobre a diferença de tempo. A resolução é uma contagem por intervalo: 50 contagens/s = 8 mm/s, ou 8 % do degrau de 0,1 m/s.
- **Erro de seguimento de um intervalo:** o perfil no meio do intervalo (a média das referências calculadas nos dois ticks dele) menos a velocidade do intervalo, com o sinal do sentido tirado (positivo = mais devagar que a referência). É o erro sobre o qual o PI do firmware age.
- **Suavizado:** média móvel centrada de 5 intervalos (100 ms), que leva a quantização a ~1,6 mm/s.
- **Degrau:** sobressinal e acomodação sobre a velocidade suavizada, antes de a parada começar. Na velocidade constante a curva suavizada ainda oscila ±3–5 mm/s, do tamanho da faixa de ±5 % a 0,1 m/s, então a acomodação vai com ±5 % e com ±10 %.
- A simulação do modelo de projeto (`speed_loop.simulate`, seção 5) vai pontilhada nos gráficos.

### Resultados (`data/day1/plots/closed_loop.csv`, `day1_closed_loop_ramp.png`, `day1_closed_loop_step.png`)

**Rampa de 0,5 m/s² até 0,25 m/s** (mm/s; s = suavizado em 100 ms):

| sentido | roda | erro máx. | erro rms | máx. s, subida | médio, subida | máx. s, constante | médio, constante | máx. s, parada | duty máx. |
|---|---|---|---|---|---|---|---|---|---|
| + | E | 17,7 | 6,3 | 12,8 | 6,8 | 6,5 | −1,4 | 11,9 | 0,379 |
| + | D | 13,3 | 5,1 | 8,7 | 4,0 | 6,0 | −1,0 | 9,9 | 0,341 |
| − | E | 11,6 | 5,1 | 8,4 | 4,5 | 7,4 | −0,9 | 8,3 | 0,422 |
| − | D | 11,1 | 5,4 | 6,7 | −0,8 | 7,2 | −0,9 | 8,8 | 0,329 |

**Degrau de 0 → 0,1 m/s** (velocidade suavizada):

| sentido | roda | sobressinal | acomodação ±5 % (ms) | ±10 % (ms) | velocidade antes da parada (mm/s) | duty máx. |
|---|---|---|---|---|---|---|
| + | E | 10 % | 1100 | 280 | 100,9 | 0,271 |
| + | D | 17 % | 500 | 280 | 98,7 | 0,234 |
| − | E | 15 % | 460 | 420 | 98,7 | 0,306 |
| − | D | 15 % | 1200 | 400 | 97,1 | 0,253 |

- **As medidas seguem a simulação de perto** nos gráficos: a mesma forma, o mesmo pico e o mesmo tempo, nos quatro casos. O modelo de primeira ordem com `pwm0` e o projeto da seção 5 valem no chão.
- **Rampa:** erro rms de 5–6 mm/s por intervalo, que é quase todo quantização (8 mm/s por contagem); suavizado, até 6,7–12,8 mm/s na subida, 6,0–7,4 mm/s na velocidade constante e 8,3–11,9 mm/s na parada. Na subida a roda fica em média 4–7 mm/s atrás da referência (a direita para trás, não), mais que os ~2 mm/s da simulação: a partida real é mais lenta que o modelo (o atrito de partida e o começo da roda não são exatamente o modelo). Na velocidade constante o erro médio é −0,9 a −1,4 mm/s.
- **Degrau:** sobressinal de 10–17 % (a simulação dava 18–21 %), acomodação a ±10 % em 280–420 ms; a ±5 %, 460–500 ms em dois casos e 1100–1200 ms nos outros dois, em que a ondulação de ±5 mm/s encosta na faixa (no gráfico a roda esquerda para a frente já está estável em ~0,5 s).
- **O duty nunca saturou:** máximo 0,42 na rampa (esquerda para trás, no fim da subida; a simulação dava 0,39) e 0,31 no degrau, contra o limite de 0,5. O ROADMAP exigia que o degrau não saturasse.
- **A parada em rampa funciona:** a referência cai a 0,5 m/s² e as rodas acompanham, com erro suavizado de até 12 mm/s, e o modo termina em coast com as rodas praticamente paradas.

### Conclusões

- O último item da Análise do Dia 1 está feito: as duas rodas seguem a rampa de 0,5 m/s² até 0,25 m/s com o erro registrado, e o degrau de 0 → 0,1 m/s tem sobressinal e acomodação conhecidos, sem saturar.
- O pico da pilha da Bridge com os encoders e a malha fechada rodando é 896 B (1152 B intocados, acima dos 512 B do critério). Falta, para o registro do Dia 1, medir o pico também com tráfego de `set_path`
- A proteção contra encoder parado no `speed` foi aprovada e feita depois.

## 8. Proteção contra encoder parado (`encoder_guard`)

### O que foi feito e por quê

A execução 1 da seção 7 (LiPo desconectada) mostrou que, em malha fechada, um encoder que não conta parece uma roda parada: o PI sobe o duty até o limite de 50 %, o limite de distância (que conta ticks do encoder) nunca chega, e só o limite de tempo encerra o modo, até 3 s mais a parada. Com a LiPo ligada e um encoder morto (fio, sensor ou a alimentação de 3,3 V), o robô andaria a ~0,4 m/s até lá; com só uma roda sem encoder, giraria. Uma roda travada contra a parede tem a mesma assinatura.

**Regra:** a cada tick do `speed`, para cada roda, se o duty aplicado desde o tick anterior teve módulo ≥ 20 % e a contagem não mudou, soma um tick parado; uma contagem (ou um duty abaixo de 20 %) zera. **10 ticks seguidos (200 ms) encerram o modo na hora, em coast**, com o motivo novo `5 = encoder`. Coast e não parada em rampa, porque a parada em rampa precisa da realimentação que falhou; um `idle` ou `count` pendente é descartado.

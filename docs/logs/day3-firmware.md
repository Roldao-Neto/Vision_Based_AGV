# Dia 3 — Firmware

## 0. Ponto de partida: limpeza do `main` depois do Dia 2

O Dia 2 foi arquivado no branch `day2` (tag `day2-final`, com os dados em `results/day2/`), e o `main` ficou só com o que o Dia 3 usa. O que sai foi decidido por Rolds, item a item.

## 1. Seguidor de waypoints

### O que foi feito e por quê

- **Módulo puro novo, `follower`**: a máquina de estados IDLE → ROTATE → DRIVE → ARRIVED. É o `tick_turn` e o `tick_leg` do Dia 2 transformados, tirados do `modes.cpp` para um módulo puro.

- **ROTATE**: alvo absoluto = θ + `wrap(atan2(w − p) − θ)`, o giro mais curto, somado ao θ não normalizado da odometria.

- **DRIVE**: a cada tick, `u` e o rumo alvo são re-mirados no waypoint, até ele ficar a 10 cm (`freeze`); `s = (w − p)·u`; o PI de rumo do Dia 2 segura o rumo alvo; abaixo de 1,5 cm (e depois do waypoint) a direção segura e v só desce a rampa. Um erro de rumo acima de 30° antes do congelamento freia em rampa e volta para ROTATE no mesmo waypoint.

- **Parada em todo waypoint**: quando o v comandado é 0 e as rodas pararam, passa ao próximo waypoint (ROTATE) ou, no último, a ARRIVED. Um waypoint que já está a menos de 1,5 cm conta como alcançado (sem um giro de até 180° para andar 1 cm).

- Na troca de fase (ROTATE → DRIVE, waypoint → waypoint) o tick manda o comando zero: o robô já está parado, e assim uma fase nova nunca começa no mesmo tick em que outra terminou.

- **Heartbeat**: mais de 1 s sem `hb` durante um `path` termina a execução e deixa as rodas em freio curto, que fica até o próximo movimento. É o único lugar, além da emergência, com freio curto.
 
## 2. Uma execução é a missão inteira

### O que foi feito e por quê

Uma execução é a missão inteira, de A até o robô parar no objetivo ou falhar. As métricas só saem quando ela termina, nunca entre um `stop` e um replanejamento.

### Conclusões

- Um replanejamento nunca espera pelas amostras. Só uma execução **nova** espera (~3 s depois de uma de 7 s).

- Os 96 KB do buffer cabem na compilação; a placa confirma no primeiro deploy (o `status` mostra o pico da pilha da Bridge e qualquer falha de boot).

## 6. No chão: A→B 5 vezes e um caminho de vários waypoints 3 vezes

### O que foi feito e por quê

O *Done when* do Dia 3: A→B com o centro do robô chegando a B em 5 execuções seguidas, mais um caminho de vários waypoints escrito à mão, 3 vezes. O *Record* é o aprovado/reprovado de cada execução: o ponto de referência P parar dentro de um círculo de 5 cm marcado em volta de B_ref = (1,540; 0,745), com o robô alinhado à linha (decidido por Rolds no fim do Dia 2; o erro de chegada e o da odometria são medidos com a cruz de fita no Dia 7, S0).

Com o robô em A, antes de cada execução, mandaram-se os comandos e foi julgada cada chegada no círculo. As execuções usaram os comandos de texto (`./deploy.sh run`).

- **A→B:** o waypoint é o eixo com o centro em B: 1,651 − 0,07 = **(1581, 745)**.

- **Vários waypoints**: A → (600, 745) → (900, 1000) → (1250, 1000) → (1250, 745) → (1581, 745). 

### Comandos

```bash
./deploy.sh run reset_pose 178 745 0

# A→B, path_id 1 a 5
./deploy.sh run path 1 1581 745

# vários waypoints, path_id 6 a 8
./deploy.sh run path 6 600 745 900 1000 1250 1000 1250 745 1581 745
```

### Resultados

Dados em `data/day3/` (mesma sessão dos itens 4 e 5): `20261022-174445_app_*.csv`, `20261022-1752*`–`1801*_path_<record>_paths1.csv`, `record_id` 7 a 14.

**A→B, 5 seguidas: 5 aprovadas.**

| # | `record_id` | Duração | Fim pela odometria (mm) | Falta até o waypoint | θ no fim | Contagens esq./dir. | P no círculo |
|---|---|---|---|---|---|---|---|
| 1 | 7 | 6160 ms | (1580,37; 745,07) | 0,6 mm | 3,4 mrad | 8902 / 8891 | **sim** |
| 2 | 8 | 6160 ms | (1580,53; 745,13) | 0,5 mm | 4,9 mrad | 8902 / 8893 | **sim** |
| 3 | 9 | 6161 ms | (1580,92; 745,17) | 0,1 mm | 7,1 mrad | 8903 / 8897 | **sim** |
| 4 | 10 | 6200 ms | (1580,84; 745,05) | 0,2 mm | 4,9 mrad | 8904 / 8895 | **sim** |
| 5 | 11 | 6179 ms | (1580,69; 745,13) | 0,3 mm | 3,4 mrad | 8904 / 8893 | **sim** |

- O ROTATE de cada uma durou 2 ticks (o robô já apontava para B), v chegou a 250 mm/s e o \|duty\| máximo foi 0,33 (o limite é 0,5).
- No chão o robô também parou 0,1–0,6 mm **antes** do waypoint (fora do chão, ~0,5 mm antes), e não os ~4 mm depois da simulação.
- O rumo no fim, 3–7 mrad, é o mesmo efeito do Dia 2: nos últimos 1,5 cm a direção segura.

**Vários waypoints, 3 vezes: 3 aprovadas.**

| # | `record_id` | Duração | Erro de parada em cada waypoint (mm) | θ no fim | P no círculo |
|---|---|---|---|---|---|
| 1 | 12 | 14 199 ms | 0,3 / 0,5 / 0,5 / 0,7 / 0,5 | 7,7 mrad | **sim** |
| 2 | 13 | 14 119 ms | 0,4 / 0,6 / 0,5 / 0,6 / 0,8 | 11,3 mrad | **sim** |
| 3 | 14 | 14 157 ms | 0,7 / 0,8 / 0,5 / 0,5 / 1,3 | 8,4 mrad | **sim** |

- Os giros: +40° em 41–43 ticks (rumo no fim 707–709 mrad, para 705 do trecho), −40° em 41–43, −90° em 69–72 (−1563 a −1567 mrad), +90° em 68–70.
- Os erros acima são da odometria (onde o robô acha que parou). O que ela não vê, como o escorregamento nos giros, só o círculo mostra: as três chegaram dentro dele.

**Conferências da sessão inteira** (~1300 s, 14 execuções):

- `uv run python analysis/odometry_check.py data/day3/20261022-174445_app_events.csv`
 
- (`data/day3/plots/odometry_check_20261022-174445.csv` e `odometry_20261022-174445.png`).

### Conclusões

- **O *Done when* do Dia 3 está cumprido:** 5 de 5 A→B e 3 de 3 com vários waypoints, todas com P dentro do círculo de 5 cm.

- O seguidor para a ≤ 1,3 mm de cada waypoint pela odometria, e a odometria do firmware confere com a do Python em todas as execuções.

- As execuções foram mandadas com `./deploy.sh run`. O gerente de missão vai mandar as mesmas chamadas (`reset_pose`, `set_path`) e esperar o ARRIVED pela `pose`.

# Dia 5–6 — Linux: integração e replanejamento

## 1. Quadro casado com a pose e passagem para a arena

### O que foi feito

Cada quadro inferido carrega o tempo V4L2 em que foi capturado. A pose do STM32 chega com `t_linux`, o `t_ms` levado ao relógio do Linux pelo `clock_sync`. A posição de um obstáculo visto num quadro tem de usar a pose **daquele instante**, não a mais recente: a inferência leva ~0,2 s, e a 0,25 m/s o robô anda ~5 cm nesse tempo.

### Resultados

Na placa, robô parado em A (log `data/day5/20261030-023622_app_detections.csv`): `frame_t` − `pose_t` = 11,3 ms nas três primeiras linhas.

### Conclusões

O casamento usa a pose do instante do quadro, com ~10–20 ms de diferença, abaixo do intervalo entre poses.

## 2. Detecções ignoradas durante ROTATE

### O que foi feito

Girando a 90 °/s, um erro de 30–60 ms entre o quadro e a pose são 3–5° de rumo (3–7 cm a 0,7 m). As caixas de um quadro cuja pose casada está em ROTATE não são usadas.

A caixa é registrada no log com `outcome = rotate` e fica fora da lista `seen`. O quadro ainda passa por `Confirm.update()` sem ela, então a contagem de 3 quadros no mesmo lugar recomeça depois de um giro.

### Conclusões

Um obstáculo visto antes de um giro precisa de mais 3 quadros depois dele. Com ~5 quadros/s, isso leva ~0,6 s.

## 3. Associação, grade, bloqueio, parada e replanejamento

### O que foi feito

**Pose em A desde o início do app.** Antes de Start, a pose do STM32 é a do boot, (0, 0, 0): só Start mandava `reset_pose(178, 745, 0)`. Uma caixa vista de A antes de Start cairia no lugar errado da grade. Agora: 

- assim que o MCU responde, a thread da missão manda um **Reset**: `reset_pose(178, 745, 0)` e limpa os obstáculos;
- um botão **"Reset at A"** (e o comando `./deploy.sh run reset`) faz o mesmo, para quando o robô é recolocado em A à mão;
- o que a câmera vê de A antes de Start conta, e **Start planeja com `plan()`** em volta dos obstáculos conhecidos, sem limpá-los. Start ainda manda o `reset_pose`.

**O ciclo de uma detecção até o replanejamento:**

1. a caixa vira um ponto na arena; os filtros (`in_view`, `in_arena`) e a confirmação de 3 quadros no mesmo lugar (`Confirm`) decidem se ela conta;
2. cada detecção confirmada entra em `associate()`: até 20 cm de um obstáculo da mesma classe ela entra na média dele; mais longe, vira um obstáculo novo;
3. a grade é refeita e, com a missão em `running`, o resto do caminho passa por `blocked()`;
4. bloqueado: `stop` (parada em rampa) e status `stopping`;
5. quando chega uma `pose` do caminho atual em IDLE: `plan()` dessa pose até B, o último waypoint puxado 7 cm para trás, `set_path` com o próximo `path_id`, e o status volta a `running`;
6. sem caminho, ou com um `ack` recusado, a missão falha e manda `mode idle`, que encerra a corrida no STM32.

O progresso e o ARRIVED de poses com um `path_id` antigo são ignorados; a posição delas continua valendo para o casamento com os quadros.

### Resultados

Simulação, caixa no caminho A→B a 0,90 m:

| Momento | O que a missão fez |
|---|---|
| Reset | `reset_pose(178, 745, 0)` |
| Start (nenhum obstáculo conhecido) | `set_path(1, [1581, 745])`, a reta do Dia 3 |
| 3º quadro com a caixa | caixa confirmada em (0,890, 0,745); o caminho entra na inflação: `stop` com o eixo em x = 0,338 |
| `pose` em IDLE | `set_path(2, [875, 375, 1588, 715])`, contornando por baixo da caixa |

Ao fim, o obstáculo estava em (0,897, 0,745) com n = 4, a 3 mm da posição real: a diferença vem de a simulação desenhar a caixa a partir da pose atual e não da pose do quadro.

Simulação, caixa vista de A antes de Start:

- o quadro capturado antes do Reset (na pose de boot) foi descartado;
- a caixa foi confirmada de A em (0,900, 0,745), n = 3;
- Start planejou em volta dela já no primeiro caminho, `set_path(1, [975, 375, 1590, 711])`, sem parada.

Na placa, robô parado e caixa à frente: o app mandou o Reset ao iniciar (`mission_reset`), e a caixa foi confirmada no 3º quadro em (0,754, 0,843) da arena, Z = 0,37 m, 9,8 cm à esquerda do eixo do robô (`data/day5/20261030-023622_app_*`).

### Conclusões

- O ciclo inteiro funciona na simulação, e na placa a detecção chega à grade.
- No caminho replanejado, o robô termina alinhado com o último segmento, não com θ = 0: `pull_back_goal()` puxa o waypoint ao longo desse segmento, então o centro chega a B com o rumo do segmento.
- Falta a corrida real: S0 e S1 (seção 6).

## 4. Página da missão

### O que foi feito

`Mission.obstacles` e `Mission.grid` são preenchidos. Além disso:

- o botão **Reset at A** (`POST /reset`);
- a linha de informação lista os obstáculos (classe, posição, n), para comparar com a arena;
- o caminho desenhado começa no início do caminho atual (`path_start`), então um replanejamento aparece a partir de onde o robô parou.

## 5. Logs

### O que foi feito

Dois logs novos por execução do app, no mesmo padrão dos outros (`run_log.py`):

- `*_app_detections.csv`: uma linha por caixa de cada quadro inferido, com a pose casada, a geometria e o destino da caixa;
- `*_app_obstacles.csv`: a lista inteira de obstáculos depois de cada mudança (uma linha vazia quando é limpa).

O replanejamento fica nos eventos: `mission_blocked` (posição e obstáculos) e `mission_replan` (caminho novo).

## 6. Depuração em S0 e S1

### O que foi feito

Primeiras missões reais com a bateria dos motores ligada, pela página: Reset at A, Start, e S0 (sem caixa) ou S1 (caixa no caminho A→B). Os logs mostraram um erro: Starts que não faziam nada -> Corrigido com `simplify()`.

### Conclusões

- S0 e S1 chegam a B; o replanejamento funciona numa corrida real.
- O erro do Start com a caixa vista de A está corrigido sem mudar o final do robô: centro em B, alinhado com o último segmento.

## 7. Planejador: grade de 2,5 cm, margem de 1 cm e dois raios

### O que foi feito

A margem de 3 cm era grande demais, somada ao raio de giro do robô. Mudanças em `python/planner.py`:

- **Células de 2,5 cm** (80 × 60, eram 5 cm) e **margem de 1 cm**. As paredes ficam infladas em 22,6 cm.

- **Dois raios em volta de um obstáculo.** Passando reto, o robô ocupa metade da largura, 12 cm; girando no lugar, os cantos da frente varrem 21,6 cm. Com o canto da caixa (5,67 cm) e a margem: **18,7 cm para passar** e **28,3 cm para girar**.

- **Célula da partida.** A célula da partida conta como livre quando o próprio ponto tem espaço para girar; uma partida de fato dentro do raio de girar continua falhando.

Uma primeira versão dos dois raios, com a grade no raio de passar, foi abandonada: o A* contornava a caixa a ~19 cm, em V, e não sobrava ponto de giro com uma reta livre até o outro lado (nenhum caminho nos casos de S1).

### Conclusões

- O robô passa a caixa a ~19 cm do centro (~2,7 cm da face, quando de frente) e só gira longe dela; os caminhos ficaram 5–8 % mais curtos.
- O custo é a histerese menor: replanejamentos seguidos ficam mais prováveis.
- Os layouts do Dia 7 têm de ser conferidos com este planejador.

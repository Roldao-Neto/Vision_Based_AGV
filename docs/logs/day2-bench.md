# Dia 2 — Bancada: calibração da odometria

> **Arquivo:** o código, os dados e os gráficos deste dia estão no branch `day2` (tag `day2-final`), com os dados em `results/day2/`. No `main`, parte do código citado aqui foi removida depois do Dia 2, e `data/day2/` não é versionado.

## 0. Preparação: análise da bancada antes das medidas

### O que foi feito e por quê

A bancada do ROADMAP tem cinco passos: S1 (5 `straight` com as constantes nominais), Es, U1 (UMBmark com Es corrigido), Ed e Eb, e S2/U2 (tudo de novo, calibrado). Cada passo produz medidas de fita, e cada correção sai de uma conta sobre elas. Esta seção prepara essas contas antes da primeira medida, testadas no PC:

- a pose real a partir dos dois cantos traseiros medidos com a fita;
- o erro de cada execução;
- as fórmulas do UMBmark e a correção de Ed e Eb;
- um script que lê as medidas de cada passo, junta com o relatório de fim de cada execução (`run_end`) e imprime as constantes corrigidas.

As fórmulas vêm do artigo citado no ROADMAP: Borenstein e Feng, "Measurement and Correction of Systematic Odometry Errors in Mobile Robots", IEEE Trans. Robotics and Automation 12(6), 869–880, 1996, doi 10.1109/70.544770 (volume, número e páginas conferidos no Crossref). O texto lido foi a versão dos autores (cópia em `cs.au.dk/~ocaprani/legolab/.../paper58.pdf`), cujo cabeçalho diz "Vol 12, No 5, October 1996"; os números de equação abaixo são os dela.

### Decisões

- **O erro é real − odometria** (Eq. 3.1 do artigo: `εx = x_abs − x_calc`, e o mesmo para y e θ), e não "pose real − partida", como o ROADMAP dizia. A diferença é onde a própria odometria parou (alguns mm, pela faixa de parada): com real − odometria, o erro de parada do controle sai da conta e sobra só o erro da odometria. O ROADMAP foi atualizado.
- **Os cantos na partida são opcionais.** O CSV de cada passo tem colunas para os cantos na partida; se estiverem preenchidas, o script usa essa pose, e se estiverem vazias, usa a marca no chão com θ0 = 0. A recomendação é medir a partida nos `straight`: um erro de 0,5° ao esquadrar o robô em A desloca o fim de 1,4 m em ~12 mm para o lado. No UMBmark quase não importa, porque o robô volta perto da partida e um erro de rumo inicial só gira esse pequeno vetor.
- **Os dois deslocamentos ficam no referencial da partida** (x ao longo do rumo inicial, y à esquerda). A odometria não começa na pose da arena (o `reset_pose` é do Dia 3; ela começa no boot), então o deslocamento real e o da odometria são comparados cada um no seu referencial de partida.
- **O ponto medido é o eixo**, o ponto que a odometria acompanha e em torno do qual o robô gira (Fig. 2 do artigo, o ponto C).
- **Es** = média da distância real ÷ média da distância pela odometria (o ROADMAP, passo 2), as duas como distância em linha reta do eixo entre a partida e o fim, que não depende do rumo de partida.
- **Ed e Eb pela média das estimativas em x e em y**, como os autores fizeram (nota 2 da Seção 5); as duas aparecem na saída.
- **A regra prática do artigo** (Seção 5): se E_max,syst < 3·SEM, uma segunda correção dificilmente melhora. O script imprime o espalhamento rms de cada nuvem e 3·SEM.
- **As correções multiplicam as constantes em uso** (Eq. 4.33: `ΔU = c·c_m·N`): m/contagem esquerda × c_L, direita × c_R, b × Eb. Como c_L + c_R = 2, a média das duas m/contagem (o Es do passo 2) fica (Eq. 4.28); as constantes em uso vêm do `run_end` de cada execução, não de uma cópia do `config.h`, e o script recusa um passo cujas execuções usaram constantes diferentes.

### Formato das medidas

> Substituído no dia da bancada pela medida a partir das fitas no chão (item 1). O formato abaixo, com os cantos medidos das paredes, ficou só como registro do que foi preparado.

Um arquivo por passo, `data/day2/bench_<passo>.csv` (`s1`, `u1`, `s2`, `u2`), uma linha por execução, tudo em mm, x medido da parede do fundo e y da parede lateral (y = 0):

```csv
run,session,record_id,start_lx,start_ly,start_rx,start_ry,end_lx,end_ly,end_rx,end_ry,notes
1,20261016-101500,1,138,855,138,635,1531,862,1532,642,bateria 12.5 V
```

- `session`: o carimbo de hora da sessão do app (o nome do `*_app_events.csv`); `record_id`: o da execução, que aparece no `straight_end` ou `umbmark_end` (é a linha que `./deploy.sh run` mostra 1 s depois do comando, ou o `events` depois do `pull`).
- `start_*`: os cantos traseiros esquerdo (`l`) e direito (`r`) do robô na partida, opcionais. Vazios, a partida é a marca: no `straight`, A_ref = (137, 745) com θ0 = 0; no `umbmark`, o eixo em (500, 250) no CCW e em (500, 1250) no CW, θ0 = 0 (o ROADMAP, passo 3).
- `end_*`: os cantos onde o robô parou. Esquerdo e direito são os do robô.
- Na marca A, os cantos ficam em x ≈ 138 mm (0,75 mm à frente de A_ref) e, de frente para +x, o esquerdo tem o y maior.
- As marcas do UMBmark no chão são do ponto de referência (40,75 mm atrás do eixo, como A_ref e B_ref): (459, 250) e (459, 1250).

### Resultados

**Testes** (`uv run pytest`: 41 passam, 15 deles novos; `basedpyright` sem erros):

- O teste do UMBmark simula o modelo do artigo: um robô com Ed e Eb conhecidos (a média dos diâmetros nominal, ou seja, Es já corrigido) segue a sua odometria nominal à perfeição, então a odometria vê um quadrado perfeito, e o robô real faz pernas em arco e giros curtos ou longos. As fórmulas recuperam Ed e Eb:

| Ed real | Eb real | Ed calculado | Eb calculado | α em x / em y | β em x / em y |
|---|---|---|---|---|---|
| 1,004 | 1,000 | 1,003997 | 1,00011 | −0,00052 / 0,00085 rad | 0,018376 / 0,018388 rad |
| 1,000 | 1,030 | 1,000000 | 1,03061 | 0,04345 / 0,04987 rad | 0 / 0 |
| 1,004 | 1,030 | 1,004014 | 1,03066 | 0,04284 / 0,05061 rad | 0,015502 / 0,021419 rad |
| 0,997 | 0,980 | 0,997053 | 0,98042 | −0,03326 / −0,02946 rad | −0,015151 / −0,012054 rad |

  As fórmulas usam ângulos pequenos (Seção 4.1). Com os dois erros juntos, as estimativas em x e em y se afastam e a média fica a até 6·10⁻⁵ de Ed e 7·10⁻⁴ de Eb (0,15 mm de b); o teste aceita 10⁻⁴ e 10⁻³.
- Os sinais conferem com o artigo: girar pouco (Eb > 1) leva os dois fins para −x (Eqs. 4.4a, 4.8a: x4 ≈ −2Lα), α > 0; roda direita maior (Ed > 1) curva as pernas para a esquerda, β > 0.

**Ponta a ponta com dados inventados** (fora do repositório: um log de eventos e dois CSV gerados com Es = 1,01, Ed = 1,004, Eb = 1,03, ±2 mm de ruído na distância do `straight`, ±4 mm no fim do UMBmark e os cantos arredondados para o mm):

```
Es (mean real / mean odometry distance) = 1.01000
CW: c.g. (-115.2, -143.0) mm, r_c.g. 183.6 mm, rms spread about it 3.6 mm, 3·SEM 4.8 mm (5 runs)
CCW: c.g. (-55.1, 59.8) mm, r_c.g. 81.3 mm, rms spread about it 5.6 mm, 3·SEM 7.5 mm (5 runs)
E_max,syst = 183.6 mm
R = 55.8 m, Ed = 1.00389, Eb = 1.03060, c_L = 0.99806, c_R = 1.00194
→ m/count L 0.160388 mm, R 0.161012 mm, b 223.64 mm (used: 0.160700, 0.160700, 217.00)
```

O script recuperou o Es exato e o Ed e o Eb dentro do que o ruído permite. Os cantos medidos ao mm limitam o rumo pela fita: no exemplo, 3,0 mrad viraram 2,5 mrad. Com ±0,5 mm em cada canto, a ~22 cm um do outro, o rumo real tem resolução de ~2–3 mrad.

**Ensaio com logs reais, no dia da bancada** (antes da primeira execução no chão; fora do repositório): os logs de eventos das sessões `20261015-200927` e `20261015-194856` (`straight` no chão) foram copiados para uma pasta temporária, com um `bench_s1.csv` de duas linhas com cantos inventados (uma com a partida na marca, outra com a partida medida, de sessões diferentes). O script achou o `straight_end` de cada execução pelo `record_id` da sua sessão, leu as poses e as constantes do `run_end` real (`m_per_count_*_pm` = 160 680 063, `track_nm` = 217 000 000) e imprimiu a tabela e o Es. Os números desse ensaio não significam nada (os cantos são inventados); o que se confere é que o caminho do log real até as constantes corrigidas funciona. `uv run pytest`: 41 passam; `basedpyright` sem erros em `python`, `bricks`, `analysis` e `tests`.

### Conclusões

- A conta da bancada está pronta e testada: basta preencher um `bench_<passo>.csv` por passo e rodar `day2_bench.py`, que imprime as constantes para o `config.h`.
- O procedimento de cada passo fica:
  1. LiPo carregada; tensão anotada no início e no fim da fase (coluna `notes`).
  2. Robô na marca (ponto de referência sobre a marca, traseira no esquadro da linha). Nos `straight`, medir também os cantos na partida.
  3. `./deploy.sh run straight 250 500 8000 1403` (S1, S2), ou `run umbmark 1 1000 250 30000` (CCW, marca (459, 250)) e `run umbmark -1 1000 250 30000` (CW, marca (459, 1250)) em U1, U2. Anotar o `record_id` da linha `*_end`.
  4. Medir os cantos onde parou.
  5. No fim da fase, `./deploy.sh pull day2`, e depois `uv run python analysis/day2_bench.py data/day2`.
  6. Corrigir o `config.h` (`kOdometry`: m/contagem por roda e `kTrackM`), deploy, e o passo seguinte.

## 1. Medida da pose real: ponto de referência e ponto da frente

### O que foi feito e por quê

No dia da bancada, antes da primeira execução, trocou-se a forma de medir a pose real. O item 0 previa os dois cantos traseiros medidos das paredes (x da parede do fundo, y da parede lateral). Medir ~1,5 m da parede até o robô, com a trena reta e no esquadro, ao mm, é difícil; e já se posiciona o robô em A pelo ponto de referência (o ponto do meio embaixo da traseira, para o qual A_ref e B_ref foram medidos).

**Decisão:** medir dois pontos sobre a linha de centro do robô, a partir das fitas no chão:

- **as fitas:** a linha reta de A a B (y = 745 mm) e uma fita perpendicular a ela em A (x = 137 mm) e outra em B (x = 1540 mm), já coladas;
- **o ponto de referência P**, o mesmo usado para posicionar o robô: a distância da fita perpendicular até P, paralela à linha (`dx`), e a distância da linha até P, no esquadro com a linha (`dy`);
- **o ponto da frente F**, no meio da frente do robô, em cima (à frente da câmera): só a distância da linha até F (`dyf`);
- **uma vez:** a distância horizontal entre P e F (`rear_to_front_mm`).

O rumo sai dos dois pontos: `sen θ = (dyf − dy)/L`. Com L ≈ 24 cm, 1 mm de diferença entre os dois dá ~4 mrad, como os cantos (~22 cm entre eles). As medidas são curtas, a partir das fitas, e não das paredes.

Sinais: `dx` positivo se P passou da fita perpendicular (no sentido de +x, para B), negativo se ficou antes; `dy` e `dyf` positivos à esquerda do robô (de frente para B, ou seja, +y).

Cuidados combinados antes das execuções:

- medir sempre até a borda de cada fita que está exatamente na coordenada (a borda alinhada ao colar a fita);
- F precisa estar exatamente na linha de centro: 1 mm fora inclina todos os rumos medidos em ~4 mrad, o que dá ~6 mm de erro lateral falso no fim de 1,4 m;
- o esquadro em pé, vertical, para levar cada ponto ao chão (mais importante para F, que fica mais alto);
- medir a partida também, mesmo com o robô posicionado na marca;
- a distância entre as fitas perpendiculares de A e de B ao longo da linha (1403 mm) entra direto na distância real e, portanto, no Es.

O UMBmark usa o mesmo esquema, com uma cruz de fitas na marca de partida de cada sentido, (459, 250) no CCW e (459, 1250) no CW: o robô começa e termina ali, de frente para +x.

### Resultados

- `uv run pytest`: 43 passam (os 2 testes dos cantos saíram, 4 novos entraram); `basedpyright` sem erros.
- **Ensaio com logs reais** (o mesmo do item 0, com medidas inventadas no formato novo): execução 11 da sessão `20261015-200927`, partida em branco e fim `dx` = −30, `dy` = 8, `dyf` = 9 mm, L = 240 mm. Conferido à mão: P = (1510, 753) mm, θ = asen(1/240) = 4,17 mrad, eixo em (1550,75; 753,17) mm, a 1373,0 mm do eixo na partida (177,75; 745), que é o que o script imprimiu.

### Conclusões

- A análise lê as medidas do jeito que se vai medir; o S1 pode começar.

## 2. S1: `straight` antes da calibração, e Es

### O que foi feito e por quê

Passos 1 e 2 do ROADMAP: cinco `straight 250 500 8000 1403` de A a B com as constantes nominais (0,160680 mm por contagem nas duas rodas, b = 217 mm), medidos como no item 1, e o Es a partir delas. O Es corrige a escala média antes do UMBmark, que supõe a escala já corrigida (artigo, Seção 2.2).

Robô no chão da arena, LiPo carregada, `./deploy.sh --no-follow` (sessão `20261021-123458`). Posicionou-se o robô na cruz de A antes de cada execução (partida 0, 0, 0: P na cruz, traseira contra a perpendicular) e mediu `dx`, `dy` e `dyf` no fim, a partir da cruz de B. 

**Decisão:** sem medir L, a distância entre as fitas de A e B, a borda das fitas nem a tensão da bateria, que já tinham sido conferidas antes. L ficou 240 mm pela geometria, em `data/day2/bench_setup.csv`; ele não entra em nenhum resultado do S1, porque em todas as execuções `dyf` = `dy` (rumo real 0, qualquer que seja L).

### Comandos

```bash
./deploy.sh run straight 250 500 8000 1403   # 5 vezes, o robô levado à mão de volta para A
./deploy.sh pull day2
uv run python analysis/day2_bench.py data/day2
uv run python analysis/day2_odometry_check.py data/day2/20261021-123458_app_events.csv
```

- O `straight` anda 1403 mm (de A_ref a B_ref) ao longo do rumo de partida, a 250 mm/s com rampas de 0,5 m/s², e termina por alvo; 8 s é o limite de tempo (a execução leva ~6,1 s).
- O `day2_bench.py` junta cada linha de `data/day2/bench_s1.csv` ao `straight_end` do mesmo `record_id` e calcula o erro real − odometria no referencial da partida (item 0); o `day2_odometry_check.py` refaz a odometria de cada execução a partir das amostras gravadas.

### Resultados

Medidas (mm): `data/day2/bench_s1.csv`; erros por execução: `data/day2/plots/bench_s1.csv`; gráfico: `data/day2/plots/bench_straight.png`.

| Execução | Fim | `dx` / `dy` / `dyf` no fim (mm) | Distância real (mm) | Pela odometria (mm) | εx ao longo (mm) | εy lateral (mm) | εθ (mrad) |
|---|---|---|---|---|---|---|---|
| 1 | alvo, 6120 ms | −30 / 20 / 20 | 1373,1 | 1402,4 | −29,4 | 19,9 | −4,4 |
| 2 | alvo, 6120 ms | −28 / 16 / 16 | 1375,1 | 1401,4 | −26,4 | 16,2 | −5,2 |
| 3 | alvo, 6180 ms | −29 / 16 / 16 | 1374,1 | 1401,4 | −27,4 | 15,8 | −5,9 |
| 4 | alvo, 6180 ms | −25 / 17 / 17 | 1378,1 | 1401,4 | −23,4 | 16,9 | −3,0 |
| 5 | alvo, 6121 ms | −26 / 12 / 12 | 1377,1 | 1403,8 | −26,8 | 11,6 | −2,2 |
| **média ± dp** | | | | | **−26,7 ± 2,2** | **16,1 ± 3,0** | **−4,1 ± 1,5** |

```
Es (mean real / mean odometry distance) = 0.98103; constants used: m/count L 0.160680 mm, R 0.160680 mm, b 217.00 mm
→ m/count × Es: L 0.157632 mm, R 0.157632 mm
```

- **Distância:** o robô anda 1,9 % menos do que a odometria nominal calcula, nas cinco execuções (dp 2,2 mm), como na execução preliminar de 1400 mm do item 3 de `day2-firmware.md` (28,1 mm antes do alvo). O Ø efetivo das rodas é 67,5 × 0,98103 = 66,2 mm.
- **Lateral:** o robô termina 16 mm à esquerda da linha, com espalhamento de 3 mm, e os encoders veem só 0,1–0,2 mm: é um erro que os encoders não veem, o assunto do UMBmark. O rumo real no fim é 0 em todas (`dyf` = `dy`), enquanto a odometria registra 2–6 mrad à esquerda (os últimos 1,5 cm sem direção, `day2-firmware.md`, item 3), daí εθ negativo. Com uma curvatura constante (uma roda maior), 16 mm de desvio em 1,375 m viria com ~23 mrad de rumo no fim, ou ~5,6 mm entre `dyf` e `dy`, que a fita mostraria; um rumo de partida ~12 mrad à esquerda, mantido, daria ~2,8 mm. As medidas em mm inteiros não mostram nenhum dos dois, então o S1 não separa a origem do desvio lateral; o UMBmark mede o Ed e o Eb diretamente.
- **Odometria do firmware contra a referência em Python:** as cinco batem, |Δx|, |Δy| ≤ 0,58 µm e |Δθ| ≤ 0,69 µrad (`data/day2/plots/odometry_check_20261021-123458.csv`).
- **Sessão** (`data/day2/20261021-123458_app_status.csv`, 6011 linhas, 50 min): 0 overrun, 0 emergência, atraso do tick ≤ 1,66 ms, corpo do tick ≤ 0,61 ms, dt 18,7–21,6 ms, pico da pilha da Bridge 872–904 B (≥ 1144 B intactos), `pwm_hz` = 20000, `pwm_err` = 0, 0 erro de encoder, nenhum `hook`.

### Es no firmware

Passo 2 do ROADMAP: as duas m/contagem multiplicadas pelo Es. Em `sketch/src/config/config.h`:

```cpp
constexpr double kMetersPerCountNominal = 3.14159265358979 * (double)kWheelDiameterM / (double)kCountsPerRev;
constexpr double kScaleEs = 0.98103; // S1: mean real / mean odometry distance of 5 straight runs
constexpr double kMetersPerCount = kMetersPerCountNominal * kScaleEs;
constexpr double kTrackM = 0.217;
constexpr odometry::Config kOdometry = {
    {kMetersPerCount, kMetersPerCount},
    kTrackM
};
```

- O fator fica separado do valor nominal, para o `config.h` mostrar de onde vem cada constante; o Ed e o Eb (passo 4) entram do mesmo jeito.
- Tudo o que usa a m/contagem segue sozinho: a odometria, a conversão m/s → contagens/s de cada roda no `drive` (o K, o τ e o `pwm0` estão em contagens) e o `v_min` do `wheel_pi`. Com o Es, o robô passa a andar 0,25 m/s reais.
- `uv run pytest`: 43 passam; o sketch compila com 139 248 B de flash e 109 652 B de RAM, o mesmo tamanho de antes (só muda uma constante).

### Conclusões

- Es = 0,98103: a m/contagem das duas rodas passa a 0,157632 mm.
- O desvio lateral de 16 mm fica para o UMBmark (U1), já com o Es no firmware.

## 3. U1: UMBmark antes (com o Es), Ed e Eb

### O que foi feito e por quê

Passos 3 e 4 do ROADMAP: o quadrado de 1 m do UMBmark, 5 vezes no sentido anti-horário (CCW) e 5 no horário (CW), com o Es já no firmware (m/contagem 0,157632 mm nas duas rodas, b = 217 mm), e as fórmulas do artigo (item 0) para o Ed e o Eb.

**Fitas**: quatro linhas inteiras, c1 em y = 250 mm e c2 em y = 1250 mm (ao longo de x), c3 em x = 459 mm e c4 em x = 1459 mm (ao longo de y), medidas das paredes. Os cruzamentos receberam nomes que não se confundem com A, B, P e F: Q1 = c1 × c3, Q2 = c1 × c4, Q3 = c2 × c4, Q4 = c2 × c3. 

Conferências: todas dentro de ~2 mm: c3 a 322 mm da perpendicular de A sobre a linha A–B, c4 a 81 mm antes da perpendicular de B, e c1 a 1000 mm de c2 ao longo de c3.

```
  y=1500  +--------------------------------------------+  far wall
          |          |                     |           |
  y=1250  |----------+---------------------+-----------|  <- c2
          |        Q4|                     |Q3         |
  y=745   |   A======+=====================+=B         |  <- A-B line
          |        Q1|                     |Q2         |
  y=250   |----------+---------------------+-----------|  <- c1
          |          |                     |           |
  y=0     +--------------------------------------------+  side wall
          x=0        c3                    c4
```

- CCW: P em Q1, traseira ao longo de c3, de frente para c4; o eixo em (500, 250) mm, os cantos do quadrado em (1500, 250), (1500, 1250) e (500, 1250). No fim, `dx` medido de c3 e `dy`, `dyf` de c1.
- CW: o mesmo em Q4, com `dy`, `dyf` medidos de c2. Q2 e Q3 só servem de referência visual (onde P para no fim da primeira perna).
- Partida 0, 0, 0 em todas (P no cruzamento, traseira contra c3).
- **Sinais no CW:** mediu-se `dy` e `dyf` positivos na direção da linha A–B (a parede, negativa). No referencial da arena (+y para a parede de y = 1500) isso é o contrário, então os valores de y do CW foram gravados com o sinal trocado, com uma nota em cada linha de `bench_u1.csv`. No CCW, a convenção coincide com a da arena (negativo para a parede de y = 0).

### Comandos

```bash
./deploy.sh run umbmark 1 1000 250 30000    # CCW, de Q1
./deploy.sh run umbmark -1 1000 250 30000   # CW, de Q4
./deploy.sh pull day2
uv run python analysis/day2_bench.py data/day2
uv run python analysis/day2_odometry_check.py data/day2/20261021-133915_app_events.csv
```

### Resultados

Medidas: `data/day2/bench_u1.csv`; erros por execução: `data/day2/plots/bench_u1.csv`; gráfico: `data/day2/plots/bench_umbmark.png`. Todas terminaram por alvo, em 23,5–23,8 s.

| Execução | Record | `dx` / `dy` / `dyf` (mm, arena) | εx (mm) | εy (mm) | εθ (mrad) |
|---|---|---|---|---|---|
| CCW 1 | 4 | +35 / −33 / −20 | 34,6 | −30,5 | 61,2 |
| CCW 2 | 5 | +38 / −32 / −15 | 37,0 | −29,9 | 73,5 |
| CCW 3 | 6 | +37 / −46 / −30 | 35,7 | −43,4 | 65,7 |
| CCW 4 | 7 | +20 / −19 / −12 | 19,6 | −18,0 | 41,9 |
| CCW 5 | 8 | +25 / −25 / −15 | 24,1 | −23,2 | 47,9 |
| CW 1 | 9 | +5 / −6 / −4 | 5,0 | −5,1 | −10,3 |
| CW 2 | 10 | +2 / 0 / +2 | 1,7 | 0,7 | −11,7 |
| CW 3 | 12 | +1 / −2 / 0 | 0,4 | −1,3 | −11,7 |
| CW 4 | 13 | −2 / −10 / −7 | −2,3 | −9,6 | −3,2 |
| CW 5 | 14 | −10 / −8 / −4 | −9,5 | −7,7 | 1,7 |

```
CW: c.g. (-0.9, -4.6) mm, r_c.g. 4.7 mm, rms spread about it 6.2 mm, 3·SEM 8.3 mm (5 runs)
CCW: c.g. (30.2, -29.0) mm, r_c.g. 41.9 mm, rms spread about it 11.0 mm, 3·SEM 14.8 mm (5 runs)
E_max,syst = 41.9 mm
α: x -0.420°, y -0.349°, mean -0.385°
β: x 0.446°, y 0.481°, mean 0.464°
R = 123.6 m, Ed = 1.00176, Eb = 0.99575, c_L = 0.99912, c_R = 1.00088
→ m/count L 0.157494 mm, R 0.157770 mm, b 216.08 mm (used: 0.157632, 0.157632, 217.00)
```

- **As duas nuvens estão separadas:** o CW fecha a 4,7 mm do início e o CCW a 41,9 mm. No modelo do artigo, os dois erros sistemáticos (diâmetros diferentes e bitola errada) se somam num sentido e se cancelam no outro; essa diferença é o que separa o Ed do Eb.
- **As estimativas em x e em y concordam:** α −0,420° e −0,349°, β 0,446° e 0,481°. No teste com o robô simulado (item 0), elas só se afastam pelas aproximações de ângulo pequeno; aqui a diferença é do tamanho do espalhamento das medidas, então o modelo de dois erros explica bem os dados.
- **Ed = 1,00176:** a roda direita é 0,18 % maior que a esquerda (Ø efetivo 66,27 contra 66,15 mm, com o Es). Com contagens iguais, o robô curva para a esquerda: 0,00176/0,217 m = 8,1·10⁻³ rad/m, ou ~8 mm para a esquerda em 1,375 m. É o sentido do desvio do S1 (16 mm para a esquerda), que tem também uma parte que este modelo não explica (o rumo real no fim do S1 foi 0).
- **Eb = 0,99575:** a bitola efetiva é 216,08 mm, 0,9 mm menor que os 217 nominais. Com a bitola menor, o robô gira mais do que a odometria calcula (α < 0: giros longos).
- **Regra prática do artigo:** E_max,syst = 41,9 mm é bem maior que 3·SEM (14,8 mm no CCW, 8,3 mm no CW), então a correção vale a pena.
- **Giros no chão** (tabela por fase do `day2_odometry_check.py`, as 52 rotações das 13 execuções completas): terminam em média 7,9 mrad (0,45°) antes do alvo, de −20,0 a +5,7 mrad. No ar terminavam 9,4–13,1 mrad antes (`day2-firmware.md`, item 4); no chão ficam um pouco mais perto e às vezes passam do alvo. As pernas param 0–1,2 mm antes do canto. Isso é a odometria e não entra na calibração, que compara a pose real com a da odometria.
- **Odometria contra a referência em Python:** as 14 batem, |Δx|, |Δy| ≤ 0,83 µm e |Δθ| ≤ 0,86 µrad (`data/day2/plots/odometry_check_20261021-133915.csv`).
- **Sessão** (`data/day2/20261021-133915_app_status.csv`, 20 631 linhas): 0 overrun, 0 emergência, atraso do tick ≤ 1,72 ms, corpo do tick ≤ 0,69 ms, dt 18,7–21,6 ms, pico da pilha da Bridge 872–904 B (≥ 1144 B intactos), 0 erro de encoder, nenhum `hook`.

### Ed e Eb no firmware

Passo 4 do ROADMAP, em `sketch/src/config/config.h`, com os fatores separados como o Es (item 2):

```cpp
constexpr double kScaleEs = 0.98103; // S1: mean real / mean odometry distance of 5 straight runs
constexpr double kMetersPerCount = kMetersPerCountNominal * kScaleEs;
// U1 (UMBmark, 5 CW + 5 CCW): Ed = 1.00176 sets c_L, c_R (their mean stays 1), Eb = 0.99575
constexpr double kCorrLeft = 0.99912;
constexpr double kCorrRight = 1.00088;
constexpr double kTrackEb = 0.99575;
constexpr double kTrackM = 0.217 * kTrackEb;
constexpr odometry::Config kOdometry = {
    {kMetersPerCount * kCorrLeft, kMetersPerCount * kCorrRight},
    kTrackM
};
```

- m/contagem: esquerda 0,157493 mm, direita 0,157771 mm (a média continua a do Es, Eq. 4.28 do artigo); b = 216,078 mm.
- O `kTurnAccelRadS2 = 2a/b` usa o `kTrackM` e passa a 4,628 rad/s² (era 4,608) (Motion: α = 2a/b). O `drive` usa a bitola nova para dividir ω entre as rodas, e cada roda converte m/s em contagens/s com a sua m/contagem.
- Com o Ed no firmware, a odometria passa a ver a curva da roda maior, e o PI de rumo a corrige: o `straight` deve deixar de ir para a esquerda.
- `uv run pytest`: 43 passam; o sketch compila com 139 256 B de flash e 109 660 B de RAM.

### Conclusões

- Ed = 1,00176 e Eb = 0,99575, com E_max,syst = 41,9 mm antes da correção.
- Constantes calibradas: m/contagem 0,157493 mm (esquerda) e 0,157771 mm (direita), b = 216,08 mm.
- Falta o passo 5: S2 e U2 com essas constantes, para medir o depois.

## 4. Depois da calibração: U2 e S2

### O que foi feito e por quê

Passo 5 do ROADMAP: o mesmo UMBmark (5 CW + 5 CCW) e os mesmos cinco `straight` de A a B do U1 e do S1, agora com as constantes calibradas (item 3), para medir o antes e o depois. 

O U2 veio primeiro (as fitas c1–c4 estavam prontas), começando pelo CW. Antes, `./deploy.sh --no-follow` com o `config.h` do item 3; todas as execuções da sessão `20261021-163750` mandam no `run_end` as constantes novas (`m_per_count_l_pm` = 157 493 246, `m_per_count_r_pm` = 157 770 678, `track_nm` = 216 077 750). O que se esperava: os centros das nuvens perto da origem, com o mesmo espalhamento de antes, porque a correção tira só a parte sistemática.

Medidas: `data/day2/bench_u2.csv` e `data/day2/bench_s2.csv`; erros por execução: `data/day2/plots/bench_u2.csv`, `bench_s2.csv`; gráficos: `data/day2/plots/bench_umbmark.png` (U1 e U2) e `bench_straight.png` (S1 e S2).

Convenção de sinais, a mesma do U1: em Q1 (CCW) negativo para a parede e positivo para o centro, que é a da arena; em Q4 (CW) também negativo para a parede, que é o contrário da arena, então os y do CW foram gravados com o sinal trocado (nota em cada linha).

### Resultados: U2

| Execução | Record | `dx` / `dy` / `dyf` (mm, arena) | εx (mm) | εy (mm) | εθ (mrad) |
|---|---|---|---|---|---|
| CW 1 | 3 | 0 / −5 / −4 | 1,1 | −4,6 | −13,7 |
| CW 2 | 4 | +10 / +5 / +5 | 9,8 | 5,6 | −17,1 |
| CW 3 | 5 | 0 / −5 / −5 | −0,4 | −5,0 | −12,0 |
| CW 4 | 6 | −5 / −3 / −3 | −4,2 | −3,3 | −15,0 |
| CW 5 | 7 | 0 / −6 / −5 | 0,5 | −6,1 | −7,9 |
| CCW 1 | 8 | +21 / +5 / +5 | 20,8 | 5,0 | 22,0 |
| CCW 2 | 9 | +10 / −2 / −2 | 10,0 | −2,2 | 24,2 |
| CCW 3 | 10 | +10 / +5 / 0 | 9,0 | 4,0 | −1,0 |
| CCW 4 | 11 | 0 / 0 / 0 | −0,8 | 0,1 | 16,2 |
| CCW 5 | 12 | +1 / +5 / 0 | −0,2 | 4,3 | −3,9 |

```
CW: c.g. (1.4, -2.7) mm, r_c.g. 3.0 mm, rms spread about it 6.3 mm, 3·SEM 8.4 mm (5 runs)
CCW: c.g. (7.8, 2.2) mm, r_c.g. 8.1 mm, rms spread about it 8.4 mm, 3·SEM 11.3 mm (5 runs)
E_max,syst = 8.1 mm
α: x -0.131°, y 0.070°, mean -0.030°
β: x 0.092°, y 0.007°, mean 0.049°
R = 1166.1 m, Ed = 1.00019, Eb = 0.99967, c_L = 0.99991, c_R = 1.00009
```

| | U1 (antes) | U2 (depois) |
|---|---|---|
| Centro CW | (−0,9; −4,6) mm, r = 4,7 mm | (1,4; −2,7) mm, r = 3,0 mm |
| Centro CCW | (30,2; −29,0) mm, r = 41,9 mm | (7,8; 2,2) mm, r = 8,1 mm |
| **E_max,syst** | **41,9 mm** | **8,1 mm** |
| Espalhamento rms (CW / CCW) | 6,2 / 11,0 mm | 6,3 / 8,4 mm |
| εθ do CCW | +42 a +74 mrad | −4 a +24 mrad |

- **E_max,syst caiu 5,2 vezes**, de 41,9 para 8,1 mm. A nuvem CCW, que estava a 4 cm, veio para perto da origem; a CW já estava perto e continuou.
- **O espalhamento ficou o mesmo** (6–11 mm rms): é a parte não sistemática (escorregamento nos giros, piso, posicionamento, fita), que a calibração não corrige, como esperado.
- **Uma segunda correção não ajudaria:** E_max,syst = 8,1 mm está abaixo de 3·SEM (11,3 mm no CCW), a regra prática do artigo. O Ed e o Eb que o U2 daria (1,00019 e 0,99967) estão dentro do ruído: as estimativas de α em x e em y têm sinais opostos (−0,131° e +0,070°), o que mostra que não sobrou um erro sistemático que o modelo de dois erros explique. As constantes do item 3 ficam.
- **Giros no chão** (48 rotações das 12 execuções): terminam em média 8,3 mrad antes do alvo (−24,2 a +3,4 mrad), como no U1.

### Resultados: S2

| Execução | Record | `dx` / `dy` / `dyf` (mm) | Fim | εx ao longo (mm) | εy lateral (mm) | εθ (mrad) |
|---|---|---|---|---|---|---|
| 1 | 13 | 0 / 10 / 10 | alvo, 6160 ms | 1,2 | 9,7 | −7,0 |
| 2 | 14 | 0 / 0 / 0 | alvo, 6159 ms | 0,6 | −0,2 | −7,0 |
| 3 | 15 | 0 / 0 / 0 | alvo, 6120 ms | 0,6 | −0,3 | −7,0 |
| 4 | 16 | 0 / 9 / 9 | alvo, 6120 ms | 0,1 | 8,7 | −7,0 |
| 5 | 17 | 0 / 4 / 4 | alvo, 6121 ms | 0,2 | 3,6 | −8,5 |

| | S1 (nominal) | S2 (calibrado) |
|---|---|---|
| εx ao longo da linha | −26,7 ± 2,2 mm | **0,5 ± 0,4 mm** |
| εy lateral (esquerda +) | 16,1 ± 3,0 mm | **4,3 ± 4,7 mm** |
| εθ | −4,1 ± 1,5 mrad | −7,3 ± 0,7 mrad |

- **Distância:** o erro ao longo da linha sumiu (o Es que o S2 daria é 1,00038).
- **Lateral:** a média caiu de 16 para 4 mm, com o mesmo espalhamento de antes (3–5 mm); duas execuções terminaram sobre a linha.
- **Rumo:** o rumo real no fim é 0 em todas (`dyf` = `dy`), e a odometria registra ~7 mrad para a esquerda nos últimos 1,5 cm sem direção (`day2-firmware.md`, item 3), daí εθ ≈ −7 mrad. É o jeito como o `straight` termina, não erro de calibração; no Dia 3 o controle ponto a ponto mira waypoints absolutos.

### Conferências da sessão

- Odometria contra a referência em Python: as 17 execuções batem, |Δx|, |Δy| ≤ 0,83 µm e |Δθ| ≤ 0,83 µrad (`data/day2/plots/odometry_check_20261021-163750.csv`).
- `data/day2/20261021-163750_app_status.csv` (21 470 linhas): 0 overrun, 0 emergência, atraso do tick ≤ 1,66 ms, corpo do tick ≤ 0,78 ms, dt 18,7–21,6 ms, pico da pilha da Bridge 872–904 B (≥ 1144 B intactos), `pwm_err` = 0, 0 erro de encoder, nenhum `hook`.

### Conclusões

- A calibração está feita e conferida: m/contagem 0,157493 mm (esquerda) e 0,157771 mm (direita), b = 216,08 mm, no `config.h`.
- UMBmark: E_max,syst de 41,9 para 8,1 mm, abaixo de 3·SEM, então sem segunda correção.
- `straight` de 1403 mm: erro ao longo da linha de −26,7 para 0,5 mm, lateral de 16,1 para 4,3 mm.
- Os cinco passos da bancada estão registrados; o *Done when* do Dia 2 vale.

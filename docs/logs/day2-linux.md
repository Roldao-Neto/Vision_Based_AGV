# Dia 2 — Linux/PC: odometria de referência em Python

> **Arquivo:** o código, os dados e os gráficos deste dia estão no branch `day2` (tag `day2-final`), com os dados em `results/day2/`. No `main`, parte do código citado aqui foi removida depois do Dia 2, e `data/day2/` não é versionado.

## 1. Referência da odometria e comparação com o firmware

### O que foi feito e por quê

O ROADMAP pede uma implementação da odometria em Python, testada com pytest e alimentada com os registros por tick, para conferir a do firmware. Se as duas fazem a mesma conta sobre as mesmas contagens, chegam à mesma pose; uma diferença acima do arredondamento mostra um erro na odometria do firmware, na leitura das contagens ou no registro.

Para a comparação ser exata, o firmware foi preparado no item 3 de `docs/logs/day2-firmware.md`:

- a odometria e as amostras usam **a mesma leitura das contagens** por tick (`wheel_speed::count()`);
- cada amostra grava as contagens **absolutas**;
- o `run_end` manda a pose de início e de fim (µm, µrad) e as constantes que a odometria usou (m/contagem por roda em pm, bitola em nm), para a comparação não depender de uma cópia do `config.h`.

### Código

| Arquivo | O que tem |
|---|---|
| `analysis/odometry.py` | `Pose`, `step()` e `integrate()`: a mesma fórmula do firmware, em `float64` |
| `tests/test_odometry.py` | reta, duas voltas no lugar (θ sem normalizar), arco contra o círculo exato, escala por roda |
| `analysis/day2_odometry_check.py` | lê o log de eventos de uma sessão (o `*_end` de cada execução traz todos os campos do `run_end`) e o arquivo de amostras de cada execução, integra a partir da pose de início e compara com a pose de fim do firmware (tolerância 0,1 mm e 0,1 mrad); grava `plots/odometry_check_<sessão>.csv` e `plots/day2_odometry_<sessão>.png` (rumo e desvio lateral em relação à linha de partida) |

```bash
uv run pytest tests/test_odometry.py
uv run python analysis/day2_odometry_check.py data/day2/20261015-194151_app_events.csv
```

Passo a passo do `day2_odometry_check.py`: percorre o log de eventos; guarda cada `straight_end` (ou `umbmark_end`) pelo `record_id`; quando chega o `run_samples` do mesmo `record_id`, abre o arquivo de amostras, converte as constantes (pm → m, nm → m) e a pose de início (µm, µrad), integra as contagens amostra a amostra e subtrai a pose de fim do firmware.

### Resultados

`uv run pytest`: 26 testes passam (4 novos); `basedpyright` sem erros.

As execuções fora do chão (`data/day2/20261015-194151_app_events.csv`):

| Execução | Modo | Parâmetros | Fim | Δx (µm) | Δy (µm) | Δθ (µrad) | Bate |
|---|---|---|---|---|---|---|---|
| 2 | straight | 250 500 8000 1380 | alvo | −0,13 | 0,56 | 0,23 | sim |
| 3 | straight | −250 500 8000 500 | alvo | −0,78 | 0,27 | 0,23 | sim |
| 4 | straight | 250 500 2000 1380 | tempo | 0,15 | 0,42 | −0,46 | sim |
| 5 | straight | 250 500 8000 1380 | comando | 0,23 | −0,60 | 0,38 | sim |

No chão (`data/day2/20261015-194856_app_events.csv`, cinco `straight` de 1380 mm, ida e volta), as cinco batem: |Δx|, |Δy| ≤ 0,61 µm e |Δθ| ≤ 0,62 µrad (`data/day2/plots/odometry_check_20261015-194856.csv`).

As diferenças são menores que 1 µm e 1 µrad: é o arredondamento do relatório (0,5 µm, 0,5 µrad) e das constantes. A odometria do firmware faz exatamente a conta do ROADMAP sobre as contagens gravadas.

### Conclusões

- A odometria do firmware está conferida: dadas as contagens, ela calcula a pose certa. O que sobra é o erro físico (diâmetros, bitola, escorregamento), que é o assunto da bancada.
- O mesmo script confere o `umbmark`, sem mudança: ele manda o mesmo `run_end` (item 2).

## 2. `umbmark`: comparação e tabela por fase

### O que foi feito e por quê

O `umbmark` (`docs/logs/day2-firmware.md`, item 4) manda o mesmo `run_end` e as mesmas amostras de 8 valores que o `straight`, então a comparação com a referência em Python vale para ele sem mudança. Duas coisas foram acrescentadas ao `day2_odometry_check.py`, porque o gráfico de "desvio lateral da linha de partida" não diz nada num quadrado:

- um terceiro gráfico, o caminho pela odometria no referencial do início de cada execução;
- para cada `umbmark`, uma tabela por fase (a fase gravada em cada amostra, `perna·2 + girando`): duração; nas pernas, onde o robô parou em relação ao canto que o firmware mirava (positivo = depois do canto), o maior desvio lateral da linha do canto e o maior erro de rumo; nos giros, onde terminou em relação ao rumo-alvo (positivo = girou demais) e o ponto mais além do alvo. Os cantos e rumos são recalculados como no firmware: canto k = início + L·(u0 + … + uk), rumo k = θ0 + sentido·k·π/2.

### Código

| Arquivo | O que mudou |
|---|---|
| `analysis/day2_odometry_check.py` | `umbmark_phases()`, impressa depois da linha de cada `umbmark`; o terceiro gráfico (caminho) |
| `python/telemetry.py` | as amostras têm um formato só (`RUN_SAMPLE_HEADER`) e o fim de execução um tratador só (`on_run_end`), depois da saída do `speed` |

```bash
uv run python analysis/day2_odometry_check.py data/day2/20261015-214618_app_events.csv
```

### Resultados

As quatro execuções no ar (`data/day2/plots/odometry_check_20261015-214618.csv`, `day2_odometry_20261015-214618.png`):

| Execução | Modo | Parâmetros | Fim | Δx (µm) | Δy (µm) | Δθ (µrad) | Bate |
|---|---|---|---|---|---|---|---|
| 1 | umbmark | 1 1000 250 30000 | alvo | 0,36 | 0,09 | −0,39 | sim |
| 2 | umbmark | −1 1000 250 30000 | alvo | −0,27 | −0,63 | −0,15 | sim |
| 3 | umbmark | 1 1000 250 30000 | comando | −0,35 | 0,13 | −0,84 | sim |
| 4 | umbmark | −1 1000 250 5000 | tempo | −0,09 | 0,40 | 0,41 | sim |

As tabelas por fase estão em `docs/logs/day2-firmware.md`, item 4. A execução de 1166 amostras (23,3 s, com quatro giros de 90° e θ passando de 2π) bate tão bem quanto um `straight`. As outras sessões continuam batendo depois da mudança no script (`20261015-194856`: 5 de 5).

### Conclusões

- A odometria do firmware está conferida também nos giros no lugar e com θ acima de 2π.
- A tabela por fase vai mostrar, nas execuções da bancada no chão, onde as pernas e os giros terminam com a inércia real.

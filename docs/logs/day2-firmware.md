# Dia 2 — Firmware

## 0. Ponto de partida: limpeza do `main` depois do Dia 1

O Dia 1 foi arquivado no branch `day1` (tag `day1-final`, com os dados em `results/day1/`), e o `main` ficou só com o que o Dia 2 usa. A regra foi decidida por Rolds no início do Dia 2 e está em `CLAUDE.md` (Working rules).

**O que saiu do `main`:**

| Onde | O que saiu | Por quê |
|---|---|---|
| `modes` | `count` (1), `step` (2), `ramp` (3), seus limites e relatórios de fim | só serviam para identificar o modelo das rodas; os códigos 1–3 ficam sem uso, para os registros do Dia 1 continuarem valendo |
| `samples` | a amostragem de 2 ms por `k_timer` | só o `step` a usava; a gravação por tick continua, para os logs de odometria do Dia 2 |
| Python | `count`/`step`/`ramp` em `mode_commands.py`, os handlers e cabeçalhos deles em `telemetry.py` e o registro em `main.py` | os modos não existem mais no firmware |
| `analysis/` e testes | `wheel_model.py`, `speed_loop.py`, `day1_*.py`, `test_wheel_model.py`, `test_speed_loop.py` | análise do Dia 1, já feita |

O `speed` (4) ficou: é o teste em malha fechada que confere a limpeza na placa, sem código novo.

**Conferência no PC:** `uv run pytest` passa com 18 testes, `basedpyright` sem erros, e o sketch compila com 130 720 B de flash e 60 716 B de RAM, contra 135 028 B e 62 580 B no `e97d427`.

**Conferência na placa** (`data/day2/20261015-184258_app_{events,status,hook}.csv`, `20261015-184335_speed.csv` e um arquivo por execução; robô no chão da arena com a LiPo, por decisão de Rolds, sem levantar as rodas, porque o código de motor não mudou):

- `./deploy.sh`: a placa compilou o mesmo tamanho do PC (130 720 / 60 716 B), e as linhas de versão batem com `docs/board-versions.txt`.
- 95 s de `status`: 0 overrun, 0 emergência, atraso do tick ≤ 1,33 ms (5 de 191 janelas acima de 1,1 ms), dt 18,8–21,0 ms, pico da pilha da Bridge 872–904 B (≥ 1144 B intactos), `pwm_hz` = 20000, `pwm_err` = 0, 0 erro de encoder, nenhum `hook`.
- `run count start` e `run step 200 200 1000 300` → `cmd_rejected` no Python; `run idle` → ack.
- Execuções do `speed`, comparadas com o Dia 1 (`docs/logs/day1-analysis.md`, seção 7), analisadas com o `day1_closed_loop.py` da tag `day1-final`:

| # | Comando | Fim | Contagens esq. / dir. | Dia 1 | Erro suavizado máx. subindo (esq. / dir.) |
|---|---|---|---|---|---|
| 1 | `speed 250 500 1500 450` | tempo, 2000 ms | 2313 / 2321 | 2343 / 2345 | 37,8 / 22,7 mm/s |
| 2 | `speed -250 500 1500 450` | tempo, 2001 ms | −2343 / −2341 | −2337 / −2332 | 17,7 / 12,7 mm/s |
| 3 | `speed 100 0 1500 250` | tempo, 1700 ms | 1013 / 1022 | 1000 / 1004 | sobressinal 13 / 19 %, acomodação ±10 % 340 / 360 ms |
| 4 | `speed -100 0 1500 250` | tempo, 1700 ms | −1013 / −1011 | −998 / −992 | sobressinal 15 / 16 %, acomodação ±10 % 360 / 400 ms |
| 5 | `speed 250 500 4500 300` | distância, 1961 ms | 2253 / 2259 | — | 9,3 / 4,4 mm/s |

Todas as amostras chegaram (101, 101, 86, 86, 99).

A execução 1 seguiu a rampa pior que o Dia 1 (6,7–12,8 mm/s): a roda esquerda atrasou nos primeiros 0,3 s e precisou de mais duty a viagem toda (0,31 a 0,25 m/s, contra 0,29 na execução 5, com a mesma referência). A execução 5, para a frente e no fim da sessão, voltou ao nível do Dia 1. O caminho do `speed` não mudou na limpeza, então a diferença é da planta (primeira execução depois de o robô ficar parado, ponto do piso ou tensão da bateria), não do código.

**Repetição** (`data/day2/20261015-184952_app_*`, `20261015-184958_speed.csv` e `20261015-1849*`/`1851*_speed_<n>_v250_a500.csv`): o app foi reiniciado (o comando deixado em `cmd/` com o app parado virou `cmd_discarded`) e Rolds rodou `speed 250 500 1500 450` seis vezes. Todas terminaram por tempo, com todas as amostras e 0 erro de encoder:

| Execução | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Contagens esq. / dir. | 2319 / 2324 | 2313 / 2320 | 2345 / 2350 | 2349 / 2357 | 2323 / 2325 | 2346 / 2351 |
| Erro suavizado máx. subindo, esq. / dir. (mm/s) | 4,7 / 6,2 | 4,9 / 5,9 | 8,7 / 7,0 | 6,7 / 7,1 | 8,6 / 5,9 | 7,1 / 9,0 |
| Erro suavizado máx. a 0,25 m/s, esq. / dir. (mm/s) | 4,2 / 3,7 | 4,2 / 4,0 | 3,9 / 5,1 | 5,8 / 5,8 | 3,9 / 3,6 | 4,2 / 4,0 |
| Erro rms, esq. / dir. (mm/s) | 4,7 / 4,5 | 4,4 / 4,4 | 5,7 / 5,5 | 5,6 / 4,6 | 4,8 / 4,6 | 5,2 / 5,1 |

No Dia 1: 6,7–12,8 mm/s subindo, 6,0–7,4 mm/s a 0,25 m/s, rms 5–6 mm/s. Status da sessão (280 linhas): 0 overrun, 0 emergência, atraso ≤ 1,46 ms, pico da pilha 904 B, nenhum `hook`. A tensão da LiPo não foi medida.

**Conclusão:** a primeira execução depois do reinício seguiu a rampa tão bem quanto as outras, então a execução 1 da primeira sessão foi um caso isolado, e o `main` limpo se comporta como o Dia 1. A distância de uma mesma rampa variou 2313–2357 contagens (±3,5 mm em ~375 mm).

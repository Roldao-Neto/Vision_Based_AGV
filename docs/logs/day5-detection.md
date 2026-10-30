# Dia 5–6 — Linux: detecção

## Ordem cronológica real

| # | Etapa | Seção |
|---|---|---|
| 1 | Fonte do carimbo de tempo do quadro no OpenCV 4.13.0 | 1 |
| 2 | Medição temporária do carimbo no `capture.py` (a placa estava fora da rede) | 1 |
| 3 | Posição do obstáculo por geometria (`python/detections.py`) e quadro com o tempo no `Detector` | 2 |
| 4 | Pré-visualização com Z e lateral de cada caixa | 2 |
| 5 | Filtros (d_max, borda inferior, arena, 3 quadros seguidos por classe) e conferência no dataset | 3 |
| 6 | Confirmação passa a exigir o mesmo lugar (decidido por Rolds) | 3 |
| 7 | Placa de volta: deploy, medição do carimbo, remoção da medição temporária | 1 |

## 1. Carimbo de tempo V4L2 do quadro

### O que foi feito

Cada quadro é casado com a pose do robô no instante em que foi capturado. O quadro carrega `t = CAP_PROP_POS_MSEC / 1000`, que deveria ser o tempo do buffer V4L2, no relógio de `time.monotonic()`.

### Resultados

Log `data/day5/20261030-022636_app_events.csv`, 5 janelas de 150 quadros (750 quadros, 25 s):

| Janela | Atraso mín. (ms) | Mediana (ms) | Máx. (ms) | Carimbos 0 | Intervalo mediano / máx. (ms) |
|---|---|---|---|---|---|
| 1 | 12,6 | 16,7 | 69,3 | 0 | 32,0 / 68,0 |
| 2 | 12,7 | 17,2 | 27,2 | 0 | 32,0 / 36,1 |
| 3 | 16,7 | 17,4 | 24,4 | 0 | 32,0 / 36,1 |
| 4 | 17,1 | 18,2 | 23,1 | 0 | 32,0 / 36,1 |
| 5 | 17,6 | 18,3 | 23,7 | 0 | 32,0 / 36,1 |

- O atraso é sempre positivo e pequeno, ~17–18 ms na mediana, menos que um período de quadro. Um carimbo em outro relógio (o de tempo real, por exemplo) daria uma diferença enorme ou negativa: `t` está no relógio de `time.monotonic()` e é anterior ao fim do `read()`, que inclui a transferência e a decodificação do MJPEG.
- O único atraso grande (69,3 ms, e um intervalo de 68 ms) está na primeira janela, logo depois de a câmera abrir; depois o máximo fica em 23–27 ms.
- Os eventos saem a cada 5,0 s para 150 quadros, ou seja 30 quadros/s (33,3 ms em média); o intervalo entre carimbos alterna entre ~32 e ~36 ms (mediana 32,0, máximo 36,1), então o carimbo tem alguns ms de variação, bem abaixo dos 40 ms entre duas poses.

### Conclusões

O carimbo V4L2 fica antes do fim do `read()` e no mesmo relógio. **O `Camera.read()` continua carimbando com `CAP_PROP_POS_MSEC`**, sem mudança.

## 2. Posição do obstáculo por geometria

### O que foi feito

A posição sai só da geometria, sem calibração e sem constante ajustada. Modelo pinhole com a câmera horizontal em C = (0,17, 0) no referencial do eixo, pixels quadrados e o ponto principal no centro da imagem (640, 360):

- **f = 907 px** em 1280 × 720, da especificação da Logitech (78° na diagonal: f = 734,3 / tan 39°, ~70,4° × 43,3°);
- **profundidade** da face da frente ao longo do eixo óptico: `Z = f·H/h`, com h a altura da caixa em pixels do quadro e H a altura da classe (caixa: 75,2 mm). A lente (54,5 mm) fica abaixo do topo da caixa, então a caixa delimitadora vai da aresta de baixo à de cima da face da frente;
- **rumo** pelo ponto médio da borda inferior: `β = atan((640 − u_meio)/f)`, positivo à esquerda, e a face da frente fica em F = C + Z·(1, tan β);
- o obstáculo é o **centro da base**, F + (profundidade/2)·(cos β, sen β), que é o ponto que a inflação do planejador supõe (caixa: 80,2 mm de profundidade).

O `Detector` passou a guardar, junto com as caixas, o tempo `t` do quadro em que rodou (`Frame(t, boxes)`, lido com `latest()`), que o bloco 3 usa para achar a pose daquele instante.

### Resultados

No dataset do Dia 4 (164 caixas detectadas):

| | Z (m) |
|---|---|
| mínimo | 0,095 |
| p10 | 0,176 |
| mediana | 0,577 |
| p90 | 1,016 |
| máximo | 1,123 |

### Conclusões

- A geometria dá distâncias plausíveis com o modelo atual, sem nada ajustado.
- A resolução vem do modelo: uma linha da entrada de 160 px são 4,5 px do quadro, ~3 cm de Z a 0,7 m.

## 3. Filtros

### O que foi feito

Antes de chegar ao planejador, uma detecção passa por:

1. **d_max**: Z ≤ 0,7 m;
2. **borda inferior**: a caixa não pode tocar a parte de baixo da imagem, porque aí a face da frente pode estar cortada e h fica menor que a real;
3. **arena**: a posição na arena tem de cair dentro de 2 × 1,5 m;
4. **3 quadros seguidos no mesmo lugar**: uma detecção só conta depois que a mesma classe passou pelos filtros, no mesmo lugar, em 3 quadros de inferência consecutivos; um quadro sem ela ali recomeça a contagem.

### Conclusões

- **Mudou depois, na conferência da grade** (`day5-grid-check.md`, seção 2): uma caixa a ~5 cm da frente do robô era descartada por tocar a borda, e nunca entrava na grade. Agora uma caixa cortada pela borda de baixo não é descartada: a profundidade sai da aresta de cima. O raciocínio abaixo era o da primeira versão.

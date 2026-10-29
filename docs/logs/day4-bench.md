# Dia 4 — Bancada: captura do dataset

> **Arquivo:** o código e os dados deste dia estão no branch `day4` (tag `day4-final`), com os dados em `results/day4/`; a ferramenta de captura, removida no fim do dia, está no branch `day4_dataset_collection` (tag `day4-dataset-collection-final`). No `main`, `data/day4/` não é versionado.

## 1. Ferramenta de captura dentro do app

As imagens do dataset saem do mesmo caminho de código que a inferência usa: a mesma câmera, as mesmas configurações automáticas de imagem, 1280 × 720 em MJPG e a mesma decodificação do OpenCV. `Camera.open()` só abre a câmera e fixa o formato; exposição, balanço de branco e foco ficam automáticos.

- **Thread de captura** (`python/capture.py`): lê todos os quadros e guarda só o último par `(frame, t)`; a inferência roda em outra thread.
- **Carimbo de tempo:** `Camera.read()` devolve `(frame, t)`, com t o tempo do buffer V4L2. A conferência desse relógio na placa fica para o Dia 5.
- **Pré-visualização** na página da missão: o último quadro em 640 × 360, JPEG, no máximo 10 quadros/s.
- **Botão Capture:** baixa o último quadro (1280 × 720) em PNG, sem perdas, como `im_N.png` direto no PC; nada é gravado na placa.

## 2. Verificação na placa

Deploy da ferramenta e teste na placa: a pré-visualização aparece e o Capture baixa as imagens. Com os controles da câmera travados as imagens ficaram ruins, por isso eles passaram a ficar automáticos antes da captura do dataset.

## 3. Modo de redimensionamento do impulse

O impulse usa **Squash**: o quadro inteiro de 1280 × 720 é redimensionado para a entrada do modelo (160 × 160), e o modelo vê os ~70° horizontais da C920. "Fit shortest axis" cortaria para os 720 × 720 centrais (~43°) e deixaria fora da imagem obstáculos que bloqueiam o caminho. As coordenadas normalizadas de uma caixa voltam ao quadro multiplicando x por 1280 e y por 720.

## 4. Detector na placa

**Modelo:** a rede float32 do impulse (YOLO-Pro, 160 × 160 RGB), extraída do `.eim` exportado pelo Studio para `models/extracted-from-eim.tflite` (28 800 324 bytes), rodada com LiteRT (`ai-edge-litert` 2.3.0). 

**`python/detector.py`**, na thread `detector`: pega o último quadro da captura, converte BGR → RGB, faz o Squash para 160 × 160 e escala para 0..1; a rede devolve 525 caixas candidatas `(xmin, ymin, xmax, ymax, escore)`, e o detector guarda as de escore ≥ 0,5, aplica NMS por classe (IoU ≥ 0,2 descarta a de menor escore) e fica com no máximo 10. Os valores são os que o `.eim` usava. As caixas, em pixels de 1280 × 720, são desenhadas na pré-visualização.

**Resultados:**

- No dataset: caixa em 164 das 166 imagens com caixa, nenhuma nas de fundo, uma caixa por imagem. As duas perdidas (im_300 e im_393) têm a caixa a ~1,3 m, além de d_max = 0,7 m.
- Na placa: `detector_ready`, nenhum erro no log, e a pré-visualização desenha a caixa (`box 0.93`).

**FPS ao vivo na placa** (app parado, 100 quadros, mediana; caixa detectada em todos):

| Threads do LiteRT | Inferência | Quadros/s (inferência / com leitura da câmera) |
|---|---|---|
| **1 (padrão, em uso)** | 183,7 ms | **5,4 / 5,1** |
| 2 | 111,6 ms | 9,0 / 8,0 |
| 3 | 83,2 ms | 12,0 / 10,3 |
| 4 | 69,6 ms | 14,4 / 11,9 |

Manteve 1 thread: a ~5 quadros/s as 3 detecções seguidas levam ~0,6–0,8 s (~15–20 cm a 0,25 m/s), e o robô ainda para longe da inflação de um obstáculo visto a d_max. Se os Dias 5–6 mostrarem que é lento demais, `num_threads=3` no `Interpreter` dá 12 quadros/s.

## 5. Medição da caixa

A única classe por enquanto, `box`, um cubo vermelho, medido com paquímetro: base de 80,2 × 80,2 mm e altura de 75,2 mm.

| Grandeza | Valor |
|---|---|
| Raio circunscrito da base | 56,7 mm |
| Inflação de planejamento (24,6 cm + raio) | 30,3 cm |
| Inflação do teste de bloqueio (21,6 cm + raio) | 27,3 cm |
| Tamanho a d_max = 0,7 m, de frente | ~104 × 97 px no quadro, ~13 × 22 px na entrada do modelo |

A d_max a caixa é pequena na entrada do modelo; a qualidade da detecção a essa distância é medida no Dia 5.

## 6. Métricas do modelo

Métricas exportadas do Studio para o modelo em uso (projeto TCC-box, bloco 13), em `data/day4/ei-tcc-box-object-detection-model-evaluation-metrics-json-file-model.13.json`. **Não é o modelo final:** o dataset tem só a classe `box` e imagens de fundo.

Dataset: 449 imagens, 166 com a caixa e 283 só de fundo; 352 de treino (71 delas de validação) e 97 de teste.

| Métrica | Validação | Teste |
|---|---|---|
| mAP@[IoU=50] | 1,000 | 1,000 |
| mAP (IoU 0,50–0,95) | 0,769 | 0,804 |
| Recall | 0,783 | 0,829 |
| mAP das caixas pequenas (distantes) | 0,671 | 0,754 |

## 7. Remoção da ferramenta de captura

### O que foi feito e por quê

Com o dataset da caixa capturado, o botão Capture e as rotas `/snapshot.png` e `/snapshot/next` saíram da página no fim do Dia 4. A ferramenta fica no branch `day4_dataset_collection` (tag `day4-dataset-collection-final`).

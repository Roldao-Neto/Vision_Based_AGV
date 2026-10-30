# Dia 5–6 — Arena: conferência da grade

## 1. Grade contra a arena

### O que foi feito

Medido com a trena: a conferência foi verificar se o obstáculo desenhado na grade da página da missão fica onde a caixa está na arena.

### Comandos e código

Página `http://192.168.1.24:8888`; depois, com o robô parado:

```bash
./deploy.sh pull day5
```

### Resultados

**A grade bate quase exatamente com a arena.** Sessão `data/day5/20261030-023622_app_*` (1866 linhas de detecções):

| Posição (entre dois Resets) | Obstáculos na lista (x, y, n) |
|---|---|
| 1 | box (0,752, 0,844), n = 241 |
| 2 | box (0,752, 0,844), n = 100 |
| 3 | box (0,753, 0,842), n = 719 |
| 4 | box (0,727, 0,739), n = 39 e box (0,573, 0,869), n = 16 |
| 5 | box (0,574, 0,869), n = 25 |

| Destino das caixas | Linhas |
|---|---|
| `confirmed` | 1140 |
| `seen` (ainda sem 3 quadros no mesmo lugar) | 39 |
| `bottom` (tocando a borda de baixo, descartada) | 918 |
| `rotate` | 1 |

- Nas posições 1–3 a mesma caixa, parada, ficou dentro de 2 mm entre Resets.
- Na posição 4 a caixa foi mudada de lugar sem Reset: a posição antiga ficou na lista como um segundo obstáculo. É o esperado: um obstáculo nunca sai da lista durante uma sessão, só no Reset. Ao mudar a caixa de lugar, é preciso apertar "Reset at A".
- Os 918 `bottom` são a caixa encostada na câmera (seção 2).

### Conclusões

- A geometria só com f da especificação põe a caixa na grade no lugar certo.
- Mudar a caixa de lugar exige Reset.

## 2. Caixa muito perto da câmera

### O que foi feito

Com a caixa encostada à frente do robô, a página não mostrava obstáculo nenhum: toda caixa saía como `bottom`. A caixa delimitadora ia até a borda de baixo da imagem (y1 = 720), e o filtro da borda inferior a descartava. Sem obstáculo na grade, Start planejaria a reta e o robô andaria contra a caixa.

O quadro da pré-visualização mostrava a caixa ocupando a imagem de cima a baixo, com `Z=0.10`: com a parte de baixo da face cortada, h fica menor que a altura real e `f·H/h` dá uma distância maior que a real.

**A aresta de cima ainda dá a distância, pela mesma geometria.** A lente está a 54,5 mm do chão e o topo da caixa a 75,2 mm, então a aresta de cima fica 20,7 mm acima do eixo óptico, e aparece `f·0,0207/Z` pixels acima do centro da imagem:

```
Z = f·(H − 0,0545) / (360 − y_top)
```

A borda de baixo da face sai da imagem com Z < f·0,0545/360 = 0,137 m. Nesse alcance a aresta de cima está longe do centro e é precisa (com y_top ≈ 65 px, uma linha do modelo, 4,5 px, muda Z em ~1 mm). Longe ela fica perto do centro e é grosseira (a 0,7 m, 27 px acima do centro: uma linha do modelo seria ~17 % de Z), então só é usada quando a de baixo está cortada; no resto continua `f·H/h`. A única constante nova é a altura da lente, que já estava no `CLAUDE.md`.

### Resultados

Os 918 quadros `bottom` reprocessados:

| | Antes (`f·H/h`) | Depois (aresta de cima) |
|---|---|---|
| Z | 0,095–0,106 m | 0,052–0,066 m (mediana 0,064) |

No último quadro (y0 = 67,4, y1 = 719,2): Z = 0,064 m, face da frente a 0,234 m do eixo, ou seja a **5,4 cm da frente do robô** (a frente está a 0,18 m do eixo), e o centro da caixa em (0,452, 0,742) da arena.

Na placa, depois do deploy, com a caixa no mesmo lugar: `confirmed`, Z = 0,065 m, centro em (0,454, 0,743), na grade (n = 20 e subindo).

**Consequência para Start:** o centro da caixa fica a 0,274 m do eixo em A, dentro da inflação de planejamento dela (0,303 m), então a célula de partida está ocupada e `plan()` não acha caminho. Pela regra sem fuga, Start falha com "no path from the start" e o robô não se move.

### Conclusões

- A caixa encostada no robô agora é vista e posta na grade no lugar certo.
- Com ela a ~5 cm da frente, a missão falha de forma segura em vez de andar contra a caixa.

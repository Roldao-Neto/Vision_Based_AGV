# Dia 4 — PC: grade de ocupação, A*, simplificação, associação e teste de bloqueio

> **Arquivo:** o código deste dia está no branch `day4` (tag `day4-final`). O código do planejador continua no `main`.

## 1. Decisões antes do código

### O que foi feito e por quê

Célula de 5 cm não é grande demais?

- **Precisão de chegada: não muda.** A grade só escolhe os vértices do desvio. O STM32 segue waypoints em mm; o primeiro ponto é a pose real e o último é B puxado 7 cm para trás, nenhum dos dois arredondado para uma célula. A precisão vem do seguidor e da odometria.

- **Opções de caminho: pouco.** Uma caixa no centro da linha A→B (inflação de 30,3 cm em y = 0,745) deixa para o eixo os corredores y ∈ [0,246; 0,442] (19,6 cm) e [1,048; 1,254] (20,6 cm), 3–4 células de 5 cm: o caminho existe. Só somem as passagens de ~1 célula, que já são menores que a margem de 3 cm somada ao erro de detecção. O A* devolve um único caminho ótimo, e a simplificação tira o zigue-zague de 45°. No Dia 7 todo layout é conferido neste planejador antes dos ensaios.

- **O problema de verdade:** meia diagonal de uma célula de 5 cm é 3,5 cm, maior que a margem de 3 cm. Se uma célula contasse como livre pelo centro, um caminho por células livres poderia entrar 3,5 cm na inflação, e o mesmo arredondamento esconderia a faixa de histerese de 3 cm do teste de bloqueio. Células de 2,5 cm só reduzem isso a 1,8 cm.

### Decisões

1. **Células de 5 cm**, numa constante só (`CELL_M`): passar a 2,5 cm (80 × 60) é uma linha.
2. **Célula ocupada se qualquer parte dela está dentro da inflação** (ou fora do corredor das paredes). Um caminho por células livres é então sempre seguro; o custo é até uma célula de largura de corredor (19,6 cm → 15 cm).
3. **A grade só serve para a busca.** A simplificação por linha de visada e o teste de bloqueio usam geometria exata: a distância de cada segmento ao centro de cada obstáculo (raio de planejamento 24,6 cm + raio da base; de bloqueio, 21,6 cm + raio) e um retângulo para as paredes (x ≤ 1,754, y ∈ [0,246; 1,254]). O caminho simplificado encosta na borda real da inflação e recupera a largura perdida nas células, e a histerese de 3 cm fica exata. Isso muda o texto do ROADMAP ("simplificação no grid inflado").

## 2. Grade de ocupação e inflação

### O que foi feito e por quê

`python/planner.py`, módulo puro, em coordenadas do **eixo**. A grade tem 40 × 30 células de 5 cm. Uma célula fica ocupada se qualquer parte dela sai do corredor das paredes ou entra na inflação de um obstáculo.

- **Paredes:** o corredor livre do eixo é x ≤ 1,754, y ∈ [0,246; 1,254] (paredes infladas em 24,6 cm = 21,6 cm de raio de giro + 3 cm de margem), sem inflar a parede atrás de A (x = 0), como decidido por Rolds na revisão do Dia 3.

- **Obstáculos:** inflados em 24,6 cm + o raio circunscrito da base da classe. Para `box` (80,2 × 80,2 mm, Dia 4 Bancada), `math.hypot(0.0802, 0.0802) / 2` = 56,71 mm, então 30,27 cm.

### Conclusões

A grade perde no máximo 4 mm nas paredes (1,754 → 1,75; 0,246 → 0,25; 1,254 → 1,25) e até uma célula em volta de cada obstáculo. A partida e B ficam em células livres.

## 3. A* com 8 vizinhos, sem cortar cantos

### O que foi feito e por quê

A* sobre as células livres: 8 vizinhos, custo 1 em linha reta e √2 na diagonal, e uma diagonal só é permitida se as duas células laterais estão livres (sem cortar cantos). A heurística octil, `dx + dy + (√2 − 2)·min(dx, dy)`, é o custo exato numa grade vazia, então nunca superestima e o A* devolve o mesmo custo ótimo que o Dijkstra.

### Explicação

- `heap` guarda `(custo até aqui + heurística, célula)`; o `heapq` tira sempre a de menor valor. Quando a tirada é o objetivo, o caminho é refeito de trás para a frente por `prev`.
- Para cada vizinho: fora da grade ou ocupado, ignora; na diagonal, se uma das duas células laterais (`grid[iy][nx]`, `grid[ny][ix]`) está ocupada, ignora, para não passar raspando por um canto.
- Se o novo custo é menor que o conhecido, atualiza o custo e o antecessor e põe o vizinho na fila. Sem caminho, a fila esvazia e a função devolve `None`.

### Conclusões

A busca está correta e é barata. O caminho cru das células é seguro mas longo e cheio de degraus de 45°; a simplificação resolve.

## 4. Simplificação por linha de visada (geometria exata)

### O que foi feito e por quê

O caminho cru `[partida, centros das células intermediárias, objetivo]` é simplificado de forma gulosa: de cada ponto mantido, salta para o ponto mais adiante que está "à vista". "À vista" é geométrico: o segmento fica no corredor (um retângulo, então basta testar as pontas) e a distância do segmento ao centro de cada obstáculo é pelo menos o raio de planejamento. A partida e o objetivo entram como pontos reais, não como centros de célula.

### Conclusões

- A simplificação geométrica dá caminhos curtos (1,649 m contra 1,795 m do caminho cru) e com a margem de 3 cm exata.
- Fica a célula de 5 cm decidida. Um vão de 10–14 cm entre inflações é um corredor estreito para um robô que localiza só por odometria e posiciona obstáculos com erro de alguns cm, e todo layout do Dia 7 é conferido neste planejador antes dos ensaios. Se um layout precisar, passar a 2,5 cm é mudar `CELL_M`, `NX` e `NY` (3,1× mais tempo de busca, ainda ~2 ms no PC).

## 5. Associação de detecções

Duas detecções da mesma classe a até 20 cm são o mesmo obstáculo, e a posição dele é a média de todas as suas detecções. O raio é a constante `ASSOCIATION_RADIUS_M`, revista no Dia 5 com a curva de erro.

## 6. Teste "caminho bloqueado?" com histerese

### O que foi feito e por quê

O caminho é planejado com a inflação completa (24,6 cm + raio da base), mas o caminho restante só conta como bloqueado se entra na inflação **sem** a margem de 3 cm (21,6 cm + raio da base). Com a geometria exata (decisão 3), a faixa de histerese é de exatamente 3 cm, mais a folga que o caminho já tinha.

### Conclusões

Um deslocamento de 1–2 cm de um obstáculo conhecido não dispara replanejamento (item do ROADMAP); só um deslocamento acima de ~3 cm em direção ao caminho, ou um obstáculo novo sobre ele.

## 7. Grade na interface

### O que foi feito e por quê

O mapa da página da missão mostra a grade. A missão guarda a lista de obstáculos (`Mission.obstacles`, vazia até o Dia 6, quando a associação a preencher durante a execução) e a grade dela (`Mission.grid`). O `snapshot()` que a página lê a 5 Hz passa a levar a grade e os obstáculos; a página desenha as células ocupadas em cinza, as linhas das células e, para cada obstáculo, a inflação de planejamento (círculo tracejado) e a de bloqueio (contínuo). O Start continua mandando só A→B (decisão do Dia 3) até a integração do Dia 6.

### Conclusões

A interface já mostra a grade e está pronta para os obstáculos do Dia 6, sem mudar o comportamento da missão.

# Dia 3 — Linux: gerente de missão, centro ↔ eixo, relógio, Flask e logs

## 1. O que foi feito e por quê

O bloco Linux do Dia 3 põe no Python o que o firmware espera receber: uma missão que manda `reset_pose` e `set_path`, espera o ARRIVED pela `pose` e termina. 

### Conclusões

O código do bloco está no PC e testado com uma Bridge falsa. Falta a placa: o Flask na porta 8888, o Start e o Stop pela interface, a `pose` com o relógio, e A→B pela missão.

## 2. Placa: missão pela interface, Stop e o relógio

### O que foi feito e por quê

Na sessão: `20261022-182444`, colocou-se o robô em A, abriu-se `http://192.168.1.24:8888/` e usou-se a interface: um Start até o fim e dois Start interrompidos com Stop.

### Resultados

`20261022-182444_app_{events,status,hook,pose,paths}.csv`, `20261022-182508_path.csv` e `20261022-1825*`–`1826*_path_<record>_paths1.csv`.

### Conclusões

- A missão pela interface leva o robô de A a B (aprovado no círculo), e o Stop termina a execução em rampa em ~0,5 s, com `mission_aborted`.

- O relógio do STM32 deriva ~900 ppm em relação ao Linux; com a janela de 2 s o offset erra ~1,7 ms, e a coluna `delay_ms` agora mostra o atraso de verdade (mediana ~2 ms).

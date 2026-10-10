# Suporte de editor para o sketch

## O que foi feito

Configurar o clangd do Zed para entender o sketch com os headers do Arduino, do Zephyr e da cópia
corrigida da Bridge, iguais aos que a placa usa para compilar.

## Comandos

```bash
curl -sfLO https://github.com/arduino/arduino-cli/releases/download/v1.5.1/arduino-cli_1.5.1_Linux_64bit.tar.gz
curl -sfLO https://github.com/arduino/arduino-cli/releases/download/v1.5.1/1.5.1-checksums.txt
grep Linux_64bit.tar.gz 1.5.1-checksums.txt | sha256sum -c -
tar xzf arduino-cli_1.5.1_Linux_64bit.tar.gz arduino-cli
install -m 755 arduino-cli ~/.local/bin/arduino-cli

# Core na versão da placa
arduino-cli core update-index
arduino-cli core search zephyr
arduino-cli core install arduino:zephyr@1.0.0
arduino-cli board listall unoq

# Banco de compilação, a partir da raiz do repositório
arduino-cli compile --only-compilation-database --build-path build sketch
```

## Teste

Com o clangd do próprio Zed e um `.ino` provisório que usa APIs do Arduino, do Zephyr e da Bridge:

```bash
cat > sketch/_probe.ino <<'EOF'
#include <zephyr/drivers/pwm.h>
static k_tid_t main_tid;
static struct k_msgq q;
void probe() {
  main_tid = k_current_get();
  analogWrite(D6, 0);
  attachInterrupt(digitalPinToInterrupt(D2), probe, CHANGE);
  Bridge.notify("x", 1);
  uint32_t t = micros(); (void)t;
  size_t s = main_tid->stack_info.size; (void)s;
}
EOF
~/.local/share/zed/languages/clangd/clangd_23.1.0/bin/clangd --check=sketch/_probe.ino \
  --query-driver="/home/rolds/.arduino15/packages/zephyr/tools/arm-zephyr-eabi/*/bin/arm-zephyr-eabi-g*"
rm sketch/_probe.ino
```

## Resultados

- `core search zephyr`: `arduino:zephyr 1.0.0` (Arduino Q Boards), além de `zephyr_contrib` e
  `zephyr_main`.
- `board listall unoq`: `Arduino UNO Q  arduino:zephyr:unoq`.
- `compile_commands.json`: 30 entradas; `-I.../sketch/libraries/Arduino_RouterBridge/src`.
- `clangd --check` no probe: `System includes extractor: successfully executed ...arm-zephyr-eabi-g++`,
  `Compile command inferred from .../build/sketch/sketch.ino.cpp`, **`All checks completed, 0 errors`**.
- Teste negativo (o mesmo probe com `this_symbol_does_not_exist();`):
  `use of undeclared identifier 'this_symbol_does_not_exist'`, `1 errors`. Ou seja, "0 erros" não
  era um falso positivo.

## Conclusões

- Tudo resolve no editor: Arduino, Zephyr e a Bridge corrigida.
- Rodar o `compile --only-compilation-database` de novo sempre que o `sketch.yaml` ou as bibliotecas mudarem.

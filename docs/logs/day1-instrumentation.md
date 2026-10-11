# Dia 1 — Instrumentação do app mínimo (código retirado)

Este documento guarda esse código. Para cada parte: o código, as métricas que ele extraiu, para que
elas serviram, o resultado e o arquivo de dados.

Os trechos são **fragmentos** da versão completa do app mínimo: usam variáveis globais do sketch e
não compilam sozinhos. Para repetir uma medição, cada trecho volta para o lugar indicado.

## Resumo

| # | Código retirado | Métrica | Para que serviu | Resultado | Dados (`data/day1/`) |
|---|---|---|---|---|---|
| 1 | Contagem de handlers por thread + `threads` | Qual thread executa os handlers; identidade da thread `bridge` | Confirmar que um handler pode interromper o tick (base da regra da fila de comandos) e confirmar o patch 1 da Bridge | 256 chamadas na `bridge`, 95 na main; pilha de 2048 B no heap | `20261010-170912_bridge_*` |
| 2 | Estatísticas do tick por janela + histograma | Atraso médio, dt mínimo/máximo, distribuição do atraso | Decidir se o tick fica no `loop()` ou vai para uma `k_thread` | Atraso 0–1,1 ms em 99,89 %, média 0,60 ms; dt 18,7–21,6 ms | `20261010-171517_app_tick*` |
| 3 | Teste de tamanho do `set_path` + `path_rx` | Limite de 256 B por mensagem | Confirmar o contrato do `set_path` (32 pontos em mm inteiros) | 213 B aceitos e íntegros; 597 B recusados pelo router | `20261010-170912_bridge_events.csv` |
| 4 | Campos extras do `diag` | Frequência do `hb`, recusas, registros dos handlers | Confirmar que o heartbeat chega a 5 Hz e que os três handlers registraram | 4,99 Hz, idade máxima 171 ms; 0 recusas; `provided_mask` = 7 | `20261010-170912_bridge_diag.csv` |
| 5 | Contagem por handler no `hook` | Quais handlers rodaram durante cada pausa longa fora do `loop()` | Isolar a causa do pico de 13 ms (com o teste de estresse) | `set_path` de 32 pontos segura o `loop()` por ~35–40 ms | `20261010-172717_app_*` |
| 6 | Teste de estresse (`set_path_b` + fases de 30 s) | Tempo fora do `loop()`, atraso do tick e RTT por fase | Separar as hipóteses do pico de 13 ms | O bloqueio depende do tamanho da mensagem, não do handler | `20261010-172717_app_*` |

## 1. Qual thread executa os handlers

### Código

Sketch: cada handler chamava `note_handler_thread(H_<handler>)`, que contava a chamada por handler e
por thread. A parte que guarda a thread da Bridge (`atomic_ptr_cas`) **continua**, porque a varredura
da pilha precisa dela; saíram os contadores e o relatório `threads`.

```cpp
enum HandlerId { H_PING, H_HB, H_SET_PATH, kHandlerCount };
static atomic_t handler_calls[kHandlerCount][2]; // [handler][0 = main thread, 1 = other thread]

static void note_handler_thread(HandlerId id)
{
    const k_tid_t current = k_current_get();
    const bool on_main = current == main_tid;
    atomic_inc(&handler_calls[id][on_main ? 0 : 1]);
    if (!on_main) {
        // The first handler that runs off the main thread identifies the bridge thread.
        atomic_ptr_cas(&bridge_tid, nullptr, current);
    }
}

// send_reports(), once the bridge thread is known:
const k_tid_t tid = (k_tid_t)atomic_ptr_get(&bridge_tid);
if (!threads_reported && tid != nullptr) {
    threads_reported = true;
    Bridge.notify("threads", (uint32_t)(uintptr_t)main_tid, (uint32_t)(uintptr_t)k_current_get(),
                  (uint32_t)(uintptr_t)tid, MsgPack::str_t(tid->name),
                  (uint32_t)tid->stack_info.start, (uint32_t)tid->stack_info.size);
}

// send_reports(), totals for the diag message:
int32_t calls_on_main = 0;
int32_t calls_on_other = 0;
for (int id = 0; id < kHandlerCount; id++) {
    calls_on_main += (int32_t)atomic_get(&handler_calls[id][0]);
    calls_on_other += (int32_t)atomic_get(&handler_calls[id][1]);
}
```

Python:

```python
def on_threads(main_tid: int, loop_tid: int, bridge_tid: int, name: str, start: int, size: int) -> None:
    event(
        "threads",
        f"main={main_tid:#x} loop={loop_tid:#x} handler_thread={bridge_tid:#x} "
        f"name={name!r} stack_start={start:#x} stack_size={size}",
    )

Bridge.provide("threads", on_threads)
```

### Métricas e para que serviram

- **Chamadas por thread** (`handlers_on_main`, `handlers_on_other` no `diag`). Handlers `provide_safe` rodam nas duas threads. Se isso
  vale, um handler pode interromper o tick em qualquer ponto, e é por isso que os handlers só
  enfileiram comandos e tudo o que eles compartilham com o tick é atômico ou protegido por mutex.
- **`threads`**: confirma que `loop()` roda na main (`loop == main`), que a outra thread é a da Bridge
  (`name='bridge'`) e que o **patch 1** está ativo (`stack_size=2048`). O `stack_start` no heap
  confirma a análise do `kernel/dynamic.c` (a pilha de 2048 B vem do heap do sistema, não do pool de
  pilhas de 1024 B).

### Resultado (`20261010-170912_bridge_*`, 70 s)

```
threads: main=0x20001320 loop=0x20001320 handler_thread=0x2001bb68 name='bridge' stack_start=0x2000afe0 stack_size=2048
```

256 chamadas de handler na thread `bridge` e 95 na main.

## 2. Jitter do tick

### Código

Sketch: estatísticas por janela de 25 ticks (0,5 s) e um histograma do atraso desde o boot. **Ficam**
no `status` só os máximos (`late_max_us`, `exec_max_us`, `hook_max_us`) e os overruns; saíram a soma
para a média, o dt mínimo/máximo e o histograma.

```cpp
constexpr uint32_t kHistEveryTicks = 500;   // lateness histogram every 10 s
constexpr uint32_t kHistBinUs = 100;
constexpr int kHistBins = 31;               // 0..3 ms in 100 us bins, the last one is >= 3 ms

static uint32_t last_tick_us;
static uint32_t win_ticks;
static uint32_t win_late_sum_us;
static uint32_t win_dt_min_us;
static uint32_t win_dt_max_us;
static uint32_t late_hist[kHistBins];       // since boot, so a lost notification loses nothing

static void record_tick_timing(uint32_t late_us, uint32_t dt_us, bool has_dt)
{
    win_ticks++;
    win_late_sum_us += late_us;
    win_late_max_us = max(win_late_max_us, late_us);
    if (has_dt) {
        win_dt_min_us = min(win_dt_min_us, dt_us);
        win_dt_max_us = max(win_dt_max_us, dt_us);
    }
    late_hist[min(late_us / kHistBinUs, (uint32_t)kHistBins - 1)]++;
}

static void send_late_histogram(uint32_t now_ms)
{
    MsgPack::arr_t<uint32_t> counts(late_hist, late_hist + kHistBins);
    Bridge.notify("tick_hist", now_ms, kHistBinUs, counts);
}

// tick(), at its start:
const bool has_dt = tick_count > 0;
const uint32_t dt_us = now_us - last_tick_us; // measured dt, for the speed estimates
last_tick_us = now_us;
tick_count++;
record_tick_timing(late_us, dt_us, has_dt);
// ... and at its end:
if (tick_count % kHistEveryTicks == 0) {
    send_late_histogram(now_ms);
}

// send_reports(): tick timing over the window, then reset it
Bridge.notify("tick", now_ms, win_ticks, win_ticks ? win_late_sum_us / win_ticks : 0,
              win_late_max_us, win_dt_min_us, win_dt_max_us, win_exec_max_us, overrun_count,
              win_hook_max_us);
```

Python:

```python
TICK_HEADER = [
    "rx_monotonic", "t_ms", "ticks", "late_mean_us", "late_max_us", "dt_min_us", "dt_max_us",
    "exec_max_us", "overruns", "hook_max_us",
]
TICK_HIST_HEADER = ["rx_monotonic", "t_ms", "bin_us", "counts_since_boot"]
tick_log = open_run_log("app", TICK_HEADER, "tick")
tick_hist_log = open_run_log("app", TICK_HIST_HEADER, "tickhist")

def on_tick(*values: int) -> None:
    tick_log.row(time.monotonic(), *values)

def on_tick_hist(t_ms: int, bin_us: int, counts: list[int]) -> None:
    # Counts per lateness bin since boot; the last bin holds everything later than that.
    tick_hist_log.row(time.monotonic(), t_ms, bin_us, " ".join(map(str, counts)))

Bridge.provide("tick", on_tick)
Bridge.provide("tick_hist", on_tick_hist)
```

### Métricas e para que serviram

- **Atraso do início do tick** (`late`): quanto cada tick começa depois do seu lugar na grade de
  20 ms. É o jitter. O ROADMAP manda mover o tick para uma `k_thread` só se o jitter for
  inaceitável; essa medição decidiu que ele fica no `loop()`.
- **Histograma**: mostrou a **forma** do atraso, quase uniforme de 0 a 1,1 ms. Essa forma é a
  assinatura do `k_msleep(1)` do `__loopHook` (o `loop()` olha o relógio ~1 vez por ms), o que
  explicou o jitter em vez de só medi-lo. Cumulativo desde o boot, para uma notificação perdida não
  perder dados.
- **dt mínimo/máximo**: o intervalo real entre ticks, que o PI das rodas vai usar. Mostrou que o dt
  fica em 20 ± ~1,5 ms em regime.
- **Corpo do tick** (`exec_max_us`, continua no `status`): quanto tempo o tick leva. Hoje ≤ 0,62 ms;
  vai crescer com o PI e a odometria.

### Resultado (`20261010-171517_app_*`, 146 s, 7500 ticks)

| Métrica | Valor |
|---|---|
| Overruns | 0 |
| Atraso do início do tick | 0–1,1 ms em 99,89 %, média 0,60 ms |
| dt em regime | 18,7–21,6 ms |
| Corpo do tick | ≤ 0,62 ms |
| Exceção | um tick 13,2 ms atrasado no boot, durante o teste de tamanho (explicado na parte 5) |

## 3. Limite de 256 B: teste de tamanho do `set_path`

### Código

Sketch: depois de aplicar um caminho, o tick mandava `path_rx` com um checksum que depende da ordem
dos valores. O `set_path`, a cópia sob mutex e a fila **continuam**; saiu o `path_rx`.

```cpp
// Order-sensitive checksum, so Python can check the path arrived intact.
static uint32_t path_checksum(const int32_t *values, int32_t len)
{
    uint32_t sum = 0;
    for (int32_t i = 0; i < len; i++) {
        sum += (uint32_t)(i + 1) * (uint32_t)values[i];
    }
    return sum;
}

// apply_set_path(), after copying the staged path:
if (current) {
    Bridge.notify("path_rx", path_id, path_len, path_checksum(path_mm, path_len));
}
```

Python: o teste inteiro.

```python
import msgpack

PATH_RX_TIMEOUT_S = 2.0
path_rx: dict[int, tuple[int, int]] = {}  # path id -> (number of values, checksum)
path_rx_changed = threading.Condition()

def on_path_rx(path_id: int, length: int, checksum: int) -> None:
    with path_rx_changed:
        path_rx[path_id] = (length, checksum)
        path_rx_changed.notify_all()

def path_checksum(values: list[int]) -> int:
    """Same order-sensitive checksum as path_checksum() in the sketch."""
    return sum((i + 1) * v for i, v in enumerate(values)) & 0xFFFFFFFF

def worst_case_size(path_id: int, values: list) -> int:
    """Bytes of the call as Python packs it, with the largest 32-bit msgid."""
    packed = msgpack.packb([0, 2**32 - 1, "set_path", [path_id, values]])
    assert packed is not None
    return len(packed)

def send_int_path(path_id: int, xy_mm: list[int]) -> bool:
    """set_path with integer mm; True if acked and the tick reported the same values."""
    size = worst_case_size(path_id, xy_mm)
    try:
        ack = Bridge.call("set_path", path_id, xy_mm, timeout=2)
    except Exception as e:
        event("set_path_int", f"id={path_id} bytes={size} error={e!r}")
        return False
    expected = (len(xy_mm), path_checksum(xy_mm))
    with path_rx_changed:
        path_rx_changed.wait_for(lambda: path_id in path_rx, timeout=PATH_RX_TIMEOUT_S)
        received = path_rx.get(path_id)
    ok = ack is True and received == expected
    event("set_path_int", f"id={path_id} bytes={size} ack={ack!r} path_rx={received} expected={expected} ok={ok}")
    return ok

def send_float_path(path_id: int, xy_mm: list[int]) -> bool:
    """The same path as floats must be rejected by the router; True if it was."""
    values = [float(v) for v in xy_mm]
    size = worst_case_size(path_id, values)
    try:
        ack = Bridge.call("set_path", path_id, values, timeout=2)
    except ValueError as e:
        # The router answers BUFFER_LIMIT_EXCEEDED (6) for a message larger than the MCU buffer.
        event("set_path_float", f"id={path_id} bytes={size} rejected={e}")
        return True
    except Exception as e:
        event("set_path_float", f"id={path_id} bytes={size} unexpected_error={e!r}")
        return False
    event("set_path_float", f"id={path_id} bytes={size} NOT rejected, ack={ack!r}")
    return False

def size_test() -> None:
    # 32 waypoints, every coordinate in 256..2000 so each one packs as uint16 (3 bytes).
    xy_mm = []
    for i in range(32):
        xy_mm += [300 + i * 45, 500 if i % 2 else 1000]

    int_ok = send_int_path(1, xy_mm)
    # Last: a message that reached the MCU would block its RPC until the app restarts.
    float_ok = send_float_path(2, xy_mm)
    # The MCU must still answer afterwards.
    still_alive = send_int_path(3, [400, 745, 1600, 745])
    event("size_test", f"int_acked={int_ok} float_rejected={float_ok} mcu_alive_after={still_alive} "
          f"pass={int_ok and float_ok and still_alive}")

Bridge.provide("path_rx", on_path_rx)
# mission(): wait_for_mcu(), start the heartbeat thread, then size_test()
```

### Métricas e para que serviram

- **Ack do caminho de 32 pontos em inteiros**: confirma que o contrato do `set_path` (até 32
  waypoints em mm inteiros) cabe no limite de 256 B do MCU. O tamanho é calculado com o pior caso do
  `msgid` (32 bits).
- **Checksum do `path_rx`**: o ack só diz que o comando entrou na fila. O checksum confirma que o tick
  aplicou o caminho **inteiro e na ordem certa**, depois da cópia sob mutex.
- **Recusa do caminho em floats**: confirma que o router barra a mensagem grande **antes** de ela
  chegar ao MCU. Uma mensagem grande que chegasse travaria o decoder do MCU até reiniciar. O teste
  roda por último entre os grandes por esse motivo.
- **`set_path` pequeno depois**: confirma que o MCU continua respondendo.

### Resultado (`20261010-170912_bridge_events.csv`)

```
set_path_int: id=1 bytes=213 ack=True path_rx=(64, 2050960) expected=(64, 2050960) ok=True
set_path_float: id=2 bytes=597 rejected=Request 'set_path' failed: message size exceeds the limit (6)
set_path_int: id=3 bytes=31 ack=True path_rx=(4, 9670) expected=(4, 9670) ok=True
size_test: int_acked=True float_rejected=True mcu_alive_after=True pass=True
```

## 4. Campos extras do `diag`

### Código

O `diag` saía a cada 500 ms com 12 campos. **Ficam** no `status`: pico e bytes intocados da pilha,
emergência, idade do `hb` e `path_id`. Saíram o tamanho da pilha (sempre 2048), os totais por thread
(parte 1), o contador de `hb`, o contador de recusas e a máscara de registros.

```cpp
static atomic_t hb_count = ATOMIC_INIT(0);
static atomic_t rejected_count = ATOMIC_INIT(0);
static uint32_t stack_size;
static int32_t provided_mask; // bit i set when the i-th provide_safe in setup() succeeded

// on_hb(): atomic_inc(&hb_count);

static bool reject()
{
    atomic_inc(&rejected_count);
    return false;
}

// setup():
provided_mask |= Bridge.provide_safe("ping", on_ping) ? 1 : 0;
provided_mask |= Bridge.provide_safe("hb", on_hb) ? 2 : 0;
provided_mask |= Bridge.provide_safe("set_path", on_set_path) ? 4 : 0;

// send_reports():
Bridge.notify("diag", now_ms, stack_size, stack_peak, stack_untouched,
              (int32_t)atomic_get(&emergency), calls_on_main, calls_on_other, (int32_t)atomic_get(&hb_count),
              hb_ms == 0 ? -1 : (int32_t)(now_ms - hb_ms), (int32_t)atomic_get(&rejected_count),
              path_id, provided_mask);
```

Python:

```python
DIAG_HEADER = [
    "rx_monotonic", "t_ms", "stack_size", "stack_peak", "stack_untouched", "emergency",
    "handlers_on_main", "handlers_on_other", "hb_count", "hb_age_ms", "rejected", "path_id",
    "provided_mask",
]
diag_log = open_run_log("app", DIAG_HEADER, "diag")

def on_diag(*values: int) -> None:
    diag_log.row(time.monotonic(), *values)

Bridge.provide("diag", on_diag)
```

### Métricas e para que serviram

- **`hb_count`**: a frequência real do heartbeat (contagem dividida pelo tempo). O watchdog do Dia 3
  freia depois de 1 s sem `hb`, então era preciso saber se os 5 Hz chegam de fato.
- **`rejected`**: quantos `set_path` o MCU recusou na validação. Esperado 0 no teste.
- **`provided_mask`**: se os três `provide_safe` do `setup()` deram certo (7 = os três). Uma falha de
  registro não aparece de outro jeito.
- **`stack_size`**: confirmava o patch 1 a cada amostra (a parte 1 já confirma uma vez).

### Resultado (`20261010-170912_bridge_diag.csv`, 140 amostras, 69,5 s)

| Métrica | Valor |
|---|---|
| Heartbeat | 4,99 Hz; idade máxima 171 ms |
| Recusas | 0 |
| `provided_mask` | 7 |
| `stack_size` | 2048 em todas as amostras |

## 5. Contagem por handler no `hook`

### Código

O `hook` é mandado quando o `loop()` fica mais de 3 ms sem rodar. Ele **continua**, mas só com
`t_ms` e a duração; saiu a contagem das chamadas de cada handler, por thread, durante a pausa.

```cpp
static atomic_val_t prev_calls[kHandlerCount][2];

static void track_hook_time(uint32_t now_us)
{
    atomic_val_t calls[kHandlerCount][2];
    for (int id = 0; id < kHandlerCount; id++) {
        calls[id][0] = atomic_get(&handler_calls[id][0]);
        calls[id][1] = atomic_get(&handler_calls[id][1]);
    }
    const uint32_t hook_us = now_us - loop_end_us;
    win_hook_max_us = max(win_hook_max_us, hook_us);
    if (hook_us > kHookReportUs) {
        int32_t d[kHandlerCount][2];
        for (int id = 0; id < kHandlerCount; id++) {
            d[id][0] = (int32_t)(calls[id][0] - prev_calls[id][0]);
            d[id][1] = (int32_t)(calls[id][1] - prev_calls[id][1]);
        }
        Bridge.notify("hook", millis(), hook_us,
                      d[H_PING][0], d[H_PING][1], d[H_HB][0], d[H_HB][1],
                      d[H_SET_PATH][0], d[H_SET_PATH][1]);
    }
    for (int id = 0; id < kHandlerCount; id++) {
        prev_calls[id][0] = calls[id][0];
        prev_calls[id][1] = calls[id][1];
    }
}
```

Python:

```python
HOOK_HEADER = [
    "rx_monotonic", "t_ms", "hook_us", "ping_main", "ping_other", "hb_main", "hb_other",
    "set_path_main", "set_path_other",
]
```

O código do teste de estresse que usou essa contagem (a variante `set_path_b` e as fases de 30 s)
está na parte 6.

### Métricas e para que serviram

- **Handlers por pausa**: mostrou se cada pausa longa fora do `loop()` tinha um handler rodando, e em
  qual thread. Com o teste de estresse, isso separou as hipóteses do pico de 13 ms (seção 11 de
  `day1-setup.md`): o pico depende do **tamanho** da mensagem, não de um handler rodando na main.

### Resultado (`20261010-172717_app_*`)

Cada `set_path` de 32 pontos gerou dois trechos seguidos fora do `loop()`, por exemplo 11,6 ms (sem
handler) + 27,6 ms (`set_path_other: 1`), somando ~35–40 ms. Isso levou à regra de enviar o
`set_path` só com o robô parado.

## 6. Teste de estresse do pico do tick

Código provisório da seção 11 de [`day1-setup.md`](day1-setup.md): separou as hipóteses do pico
de 13 ms do tick e foi retirado logo depois do experimento. Usa a contagem por handler da parte 5.

### Código: sketch (variante `set_path_b`, que só a thread `bridge` executa)

```cpp
enum HandlerId { H_PING, H_HB, H_SET_PATH, H_SET_PATH_B, kHandlerCount };

// The validation and queuing of on_set_path() moved into a shared function:
static bool queue_set_path(int32_t id, const MsgPack::arr_t<int32_t> &xy_mm) { /* same body */ }

static bool on_set_path(int32_t id, MsgPack::arr_t<int32_t> xy_mm)
{
    note_handler_thread(H_SET_PATH);
    return queue_set_path(id, xy_mm);
}

// Experiment (tick spike): the same handler registered with provide(), so only the
// bridge thread runs it. Removed once the experiment is done.
static bool on_set_path_b(int32_t id, MsgPack::arr_t<int32_t> xy_mm)
{
    note_handler_thread(H_SET_PATH_B);
    return queue_set_path(id, xy_mm);
}

// setup():
provided_mask |= Bridge.provide("set_path_b", on_set_path_b) ? 8 : 0;

// track_hook_time(): the hook notification also carried the set_path_b counts
Bridge.notify("hook", millis(), hook_us,
              d[H_PING][0], d[H_PING][1], d[H_HB][0], d[H_HB][1],
              d[H_SET_PATH][0], d[H_SET_PATH][1], d[H_SET_PATH_B][0], d[H_SET_PATH_B][1]);
```

### Código: Python (fases de 30 s)

```python
HOOK_HEADER = [
    "rx_monotonic", "t_ms", "hook_us", "ping_main", "ping_other", "hb_main", "hb_other",
    "set_path_main", "set_path_other", "set_path_b_main", "set_path_b_other",
]
STRESS_HEADER = ["monotonic", "phase", "call", "path_id", "ok", "rtt_ms"]
stress_log = open_run_log("app", STRESS_HEADER, "stress")

STRESS_PHASE_S = 30.0
STRESS_PERIOD_S = 0.5


def stress_phase(phase: str, method: str | None, first_id: int) -> int:
    """Call `method` every STRESS_PERIOD_S for STRESS_PHASE_S (None: stay idle)."""
    event("stress_phase_start", phase)
    xy_mm = []
    for i in range(32):
        xy_mm += [300 + i * 45, 500 if i % 2 else 1000]
    path_id = first_id
    end = time.monotonic() + STRESS_PHASE_S
    while time.monotonic() < end:
        if method is not None:
            start = time.monotonic()
            try:
                if method == "ping":
                    ok = Bridge.call("ping", timeout=2) is True
                else:
                    ok = Bridge.call(method, path_id, xy_mm, timeout=2) is True
            except Exception as e:
                ok = False
                event("stress_error", f"{phase} {method} {e!r}")
            stress_log.row(start, phase, method, path_id, ok, round((time.monotonic() - start) * 1000, 2))
            path_id += 1
        time.sleep(STRESS_PERIOD_S)
    event("stress_phase_end", phase)
    return path_id


def stress_test() -> None:
    path_id = 100
    for phase, method in [
        ("idle", None),
        ("ping", "ping"),
        ("set_path_safe", "set_path"),
        ("set_path_bridge_only", "set_path_b"),
        ("idle_after", None),
    ]:
        path_id = stress_phase(phase, method, path_id)
    event("stress_test", "done")

# mission(): size_test() followed by stress_test()
```

### Código: análise

```python
import csv
D = "data/day1/20261010-172717_app_"
rd = lambda n: list(csv.DictReader(open(D + n + ".csv")))
tick, hook, ev, stress = rd("tick"), rd("hook"), rd("events"), rd("stress")
# MCU clock (t_ms) -> Python monotonic: the least-delayed message gives the offset
off = min(float(r["rx_monotonic"]) - int(r["t_ms"]) / 1000 for r in tick)
# phases from the stress_phase_start/end events; per phase: max late_max_us, hook_max_us,
# dt range, hook events with the handler counts, and the RTT of each call
```

### Métricas e para que serviram

- **Tempo fora do `loop()` e atraso do tick por fase**: comparar repouso, `ping` (mensagem pequena) e
  `set_path` de 32 pontos mostrou que o bloqueio depende do **tamanho** da mensagem.
- **`set_path` contra `set_path_b`**: o mesmo bloqueio com um handler que nunca roda na main descartou
  a hipótese de o handler demorar dentro do `__loopHook`.
- **RTT no Python**: quanto cada chamada leva de ponta a ponta em cada fase.

### Resultado (`20261010-172717_app_*`)

Cada `set_path` de 32 pontos manteve o `loop()` parado por ~35–40 ms, com `provide_safe` ou com
`provide`, e 31 das 110 chamadas causaram overrun; `ping` e repouso ficaram abaixo de 1,8 ms. A causa
é o parse quadrático do `Arduino_RPClite` na thread `bridge`, e a decisão foi enviar o `set_path` só
com o robô parado (seção 11 de `day1-setup.md`, com a tabela por fase).

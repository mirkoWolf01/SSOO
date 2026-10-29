#!/usr/bin/env python3
"""
SSOO - Ejercicio 2 (el anillo) - tests

Uso (desde la raíz del taller, adentro de la VM):
    python3 tests/tests_ej2.py ./bin/anillo [--check=NOMBRE]

NOMBRE puede ser: parametros | resultado | recorrido | fds | procesos |
sin-kill | huerfanos. Si no se pasa --check, corren todas.

Normalmente no hace falta invocarlo a mano: el Makefile lo corre adentro
de la VM con "make test-ej2" (y "make test-ej2-recorrido", etc. para una
sola sección).

Variables de entorno:
    TIMEOUT_FACTOR  multiplica todos los timeouts en máquinas lentas

Como no hay ningún número aleatorio, la salida del anillo es
COMPLETAMENTE determinista: el hijo distinguido recibe c + k*n en su
k-ésima vuelta. Por eso acá no nos conformamos con mirar el número final,
sino que comparamos el recorrido completo del número por el anillo.
"""

import math
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402
from lib import expect, fail, end_section, ok, run_section, section, skip  # noqa: E402

BIN = lib.tests_init(sys.argv, 1, "uso: tests_ej2.py ./bin/anillo [--check=SECCION]")

RE_CHILD = re.compile(r"^HIJO (\d+) PID (\d+) NUM (-?\d+)$")
RE_PARENT = re.compile(r"^PADRE RESULTADO (-?\d+)$")


# ---------------------------------------------------------------------
# El modelo: qué TIENE que pasar en una corrida válida
# ---------------------------------------------------------------------


def laps(n, c, p):
    """Cuántas vueltas completas da el número antes de cortar."""
    return math.ceil((p - c) / n)


def expected_result(n, c, p):
    return c + laps(n, c, p) * n


def expected_route(n, s, c, p):
    """La secuencia exacta de (hijo, valor) que se tiene que imprimir."""
    steps = []
    index = s - 1
    value = c
    for _ in range(laps(n, c, p) * n + 1):
        steps.append((index + 1, value))
        value += 1
        index = (index + 1) % n
    return steps


def parse_output(text):
    """Saca del stdout del anillo los pasos, el resultado final, las
    líneas que sobran y los PIDs de cada hijo."""
    steps, result, leftovers, pids = [], None, [], {}
    for line in text.splitlines():
        if not line.strip():
            continue
        m = RE_CHILD.match(line)
        if m:
            index, pid, value = int(m.group(1)), int(m.group(2)), int(m.group(3))
            steps.append((index, value))
            pids.setdefault(index, set()).add(pid)
            continue
        m = RE_PARENT.match(line)
        if m:
            result = int(m.group(1))
            continue
        leftovers.append(line)
    return steps, result, leftovers, pids


def run_ring(n, s, c, p, seconds=15):
    return lib.run(seconds, BIN, n, s, c, p)


# El anillo hace unos 14 mil saltos por segundo adentro de la VM, así que
# una cota de 20000 da alrededor de un segundo y medio de corrida: tiempo
# de sobra para mirar /proc mientras gira.
LONG_BOUND = 20000


def spinning_ring(n, bound=LONG_BOUND):
    """Arranca un anillo que va a estar dando vueltas un rato, con la
    salida a /dev/null. Lo devuelve sin esperarlo."""
    return subprocess.Popen(
        [BIN, str(n), "1", "0", str(bound)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def is_steady(n, child_fds, parent_fds):
    """¿Ya se acomodaron todos? En régimen, cada hijo se queda con dos
    pipes (lee del antecesor, escribe al sucesor), el distinguido con
    tres (más el que va al padre), y el padre con uno solo (por el que
    espera el resultado)."""
    if len(child_fds) != n:
        return False
    pipes = [c.get("pipe", 0) for c in child_fds.values()]
    return (
        parent_fds.get("pipe", 0) == 1
        and all(p in (2, 3) for p in pipes)
        and pipes.count(3) == 1
    )


def sample_when_steady(n, attempts=3):
    """Mira /proc mientras el anillo gira, hasta encontrar el estado
    estable.

    Hay que esperar a que se acomode: justo después de cada fork el padre
    todavía tiene todos los pipes abiertos y los hijos todavía no
    cerraron los suyos, así que muestrear ahí daría un falso negativo.

    Devuelve si encontró el estado estable, y la última muestra que
    llegó a sacar."""
    bound = LONG_BOUND
    last = None
    for _ in range(attempts):
        process = spinning_ring(n, bound)
        deadline = time.monotonic() + 10 * lib.TIMEOUT_FACTOR
        try:
            while time.monotonic() < deadline and process.poll() is None:
                children = lib.children_of(process.pid)
                if len(children) == n:
                    child_fds = {h: lib.count_fds(h) for h in children}
                    parent_fds = lib.count_fds(process.pid)
                    if all(child_fds.values()):
                        last = (child_fds, parent_fds)
                        if is_steady(n, child_fds, parent_fds):
                            return True, last
                time.sleep(0.01)
        finally:
            lib.kill_group(process.pid)
            process.wait()
        bound *= 4
    return False, last


# ---------------------------------------------------------------------
if run_section("parametros"):
    section("Validación de parámetros inválidos (no debe colgarse ni segfaultear)")
    CASES = [
        ([], "sin argumentos"),
        ([2, 1, 0, 10], "n < 3"),
        ([4, 0, 0, 10], "s < 1"),
        ([4, 5, 0, 10], "s > n"),
        ([4, 1, 10, 5], "p < c"),
        ([4, 1, 10, 10], "p == c"),
        (["abc", 1, 0, 10], "n no numérico"),
        ([4, 1, 0], "faltan argumentos"),
    ]
    for args, reason in CASES:
        label = " ".join(str(a) for a in args) or "(vacío)"
        res = lib.run(5, BIN, *args)
        if res.timed_out:
            fail(f"con parámetros [{label}] ({reason}) el programa se cuelga")
        elif res.killed_by_signal:
            fail(f"con parámetros [{label}] ({reason}) muere por señal "
                 f"(posible segfault), señal {res.signal_number}")
        else:
            expect(
                res.rc != 0,
                f"parámetros [{label}] rechazados prolijamente (rc={res.rc})",
                f"con parámetros [{label}] ({reason}) el programa devuelve 0, "
                f"debería rechazarlos",
                res.output,
            )
    end_section()

# ---------------------------------------------------------------------
if run_section("resultado"):
    section("Resultado final (determinista: c + n*ceil((p-c)/n))")
    COMBOS = [
        (3, 1, 0, 10),
        (3, 2, 0, 10),
        (3, 3, 0, 10),    # el resultado no depende de s
        (4, 1, 0, 10),
        (5, 1, 0, 10),    # p-c es múltiplo exacto de n
        (5, 3, 7, 8),     # alcanza con una vuelta
        (3, 1, 0, 1),     # el caso mínimo
        (10, 7, 100, 137),
        (8, 8, 0, 100),   # s == n
    ]
    for n, s, c, p in COMBOS:
        expected = expected_result(n, c, p)
        res = run_ring(n, s, c, p)
        if res.timed_out:
            fail(f"({n} {s} {c} {p}) se colgó (timeout)")
            continue
        if res.killed_by_signal:
            fail(f"({n} {s} {c} {p}) murió por señal {res.signal_number} (posible segfault)",
                 res.output)
            continue
        _, got, leftovers, _ = parse_output(res.out)
        if got is None:
            fail(f"({n} {s} {c} {p}) no imprimió ninguna línea 'PADRE RESULTADO <v>'",
                 res.output)
        elif leftovers:
            fail(f"({n} {s} {c} {p}) imprimió líneas que no siguen el formato pedido",
                 "\n".join(leftovers[:5]))
        else:
            expect(
                got == expected,
                f"({n} {s} {c} {p}) -> {got}",
                f"({n} {s} {c} {p}) dio {got}, esperaba {expected}",
                res.output,
            )

    # Sin el rand() de antes, la misma entrada tiene que dar SIEMPRE lo mismo.
    results = set()
    for _ in range(5):
        res = run_ring(4, 2, 0, 20)
        _, value, _, _ = parse_output(res.out)
        results.add(value)
    expect(
        results == {expected_result(4, 0, 20)},
        "5 corridas de (4 2 0 20) dan siempre el mismo resultado",
        f"(4 2 0 20) no es determinista: en 5 corridas dio {sorted(results)}",
    )
    end_section()

# ---------------------------------------------------------------------
if run_section("recorrido"):
    section("Recorrido del número por el anillo")

    # Los dos casos chiquitos se comparan paso por paso contra el modelo.
    for n, s, c, p in [(3, 1, 0, 4), (4, 3, 0, 9)]:
        expected = expected_route(n, s, c, p)
        res = run_ring(n, s, c, p)
        steps, result, _, _ = parse_output(res.out)
        if steps == expected and result == expected_result(n, c, p):
            ok(f"({n} {s} {c} {p}): el número recorre el anillo exactamente como "
               f"debe ({len(expected)} pasos)")
        else:
            detail = [
                "esperado:",
                "  " + " ".join(f"({i},{v})" for i, v in expected),
                "obtenido:",
                "  " + " ".join(f"({i},{v})" for i, v in steps),
            ]
            fail(f"({n} {s} {c} {p}): el recorrido del número no es el esperado",
                 "\n".join(detail))

    # Y sobre varios combos se chequean las invariantes estructurales.
    for n, s, c, p in [(3, 1, 0, 10), (5, 2, 0, 23), (7, 7, -5, 9), (10, 4, 0, 41)]:
        res = run_ring(n, s, c, p)
        if res.timed_out:
            fail(f"({n} {s} {c} {p}) se colgó (timeout)")
            continue
        steps, result, leftovers, pids = parse_output(res.out)
        expected_lines = laps(n, c, p) * n + 1

        problem = None
        if leftovers:
            problem = ("hay líneas que no respetan ninguno de los dos formatos:\n  "
                       + "\n  ".join(leftovers[:5]))
        elif len(steps) != expected_lines:
            problem = f"imprimió {len(steps)} líneas HIJO, esperaba {expected_lines}"
        elif result is None:
            problem = "falta la línea 'PADRE RESULTADO <v>'"
        elif sorted(pids) != list(range(1, n + 1)):
            problem = f"los hijos reportados son {sorted(pids)}, esperaba 1..{n}"
        elif any(len(v) != 1 for v in pids.values()):
            changing = [i for i, v in pids.items() if len(v) != 1]
            problem = f"los hijos {changing} reportan más de un PID"
        elif len({next(iter(v)) for v in pids.values()}) != n:
            problem = f"los {n} hijos deberían tener {n} PIDs distintos"
        elif res.out.strip().splitlines()[-1] != f"PADRE RESULTADO {result}":
            problem = "la línea 'PADRE RESULTADO' no es la última de la salida"

        if problem:
            fail(f"({n} {s} {c} {p}): {problem}", res.out)
        else:
            ok(f"({n} {s} {c} {p}): {expected_lines} líneas HIJO, {n} PIDs distintos, "
               f"PADRE al final")

    # El PID del padre no puede aparecer como el de un hijo.
    proc = subprocess.Popen([BIN, "5", "1", "0", "40"], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    output = proc.communicate(timeout=30 * lib.TIMEOUT_FACTOR)[0].decode()
    _, _, _, pids = parse_output(output)
    todos = {next(iter(v)) for v in pids.values()}
    expect(
        proc.pid not in todos,
        "el PID del padre no aparece como el de ningún hijo",
        f"el PID del padre ({proc.pid}) aparece también como el de un hijo",
    )
    end_section()

# ---------------------------------------------------------------------
if run_section("fds"):
    section("File descriptors: cerrar los que no se usan")

    if not lib.has_strace():
        skip("no hay strace instalado en la VM (algo salió mal en 'make install')")
    else:
        N, S, C, P = 5, 2, 0, 12
        res, trace = lib.run_traced(30, BIN, N, S, C, P,
                                    syscalls="pipe,pipe2,close,clone,clone3,fork,vfork,wait4,waitid")
        if trace is None or trace.root_pid is None:
            skip("no pude correr strace acá")
        else:
            _, _, _, pids_by_child = parse_output(res.out)
            pid_of = {i: next(iter(v)) for i, v in pids_by_child.items()}

            # 1) La topología: exactamente n+1 pipes, ni uno más.
            created = trace.count(trace.root_pid, "pipe", "pipe2")
            hint = None
            if created > N + 1:
                hint = ("Pista: pará en el momento justo en que el padre arranca "
                        "la ronda. ¿Qué file descriptors tiene abiertos ahí, antes "
                        "de cerrar nada? ¿Y alguno de los pipes que te sobran hace "
                        "algo que no se pueda hacer con esos?")
            expect(
                created == N + 1,
                f"crea exactamente {N + 1} pipes: los {N} del anillo más el del resultado",
                f"creó {created} pipes, esperaba {N + 1} "
                f"({N} del anillo + 1 para avisarle el resultado al padre)",
                hint,
            )

            # 2) Los cierres. Cada hijo hereda los 2*(n+1) extremos de todos
            #    los pipes y se queda solo con los suyos: 2 si es un hijo
            #    común (lee del antecesor, escribe al sucesor) y 3 si es el
            #    distinguido (más el pipe hacia el padre).
            inherited = 2 * (N + 1)
            if len(pid_of) != N:
                fail(f"esperaba ver {N} hijos en la salida, vi {len(pid_of)}", res.out)
            else:
                missing = []
                for index, pid in sorted(pid_of.items()):
                    keeps = 3 if index == S else 2
                    minimum = inherited - keeps
                    closed = trace.count(pid, "close")
                    if closed < minimum:
                        missing.append(
                            f"hijo {index} (pid {pid}): cerró {closed} fds, "
                            f"tendría que cerrar al menos {minimum} "
                            f"(hereda {inherited} y usa {keeps})"
                        )
                expect(
                    not missing,
                    "cada hijo cierra todos los extremos de pipe que no usa",
                    "hay hijos que se quedaron con file descriptors abiertos de más:",
                    "\n".join(missing),
                )

                # 3) El padre: cierra los 2n del anillo (si no, el EOF no
                #    llega nunca) más el extremo de escritura del resultado.
                parent_minimum = 2 * N + 1
                closed = trace.count(trace.root_pid, "close")
                expect(
                    closed >= parent_minimum,
                    f"el padre cierra los {2 * N} extremos del anillo y el de escritura "
                    f"del resultado",
                    f"el padre cerró {closed} fds, tendría que cerrar al menos "
                    f"{parent_minimum}: los {2 * N} del anillo (si no, el EOF no llega "
                    f"nunca) más result_pipe[WRITE]",
                )

    # 4) Y ahora en vivo, mirando /proc mientras el anillo gira.
    N = 5
    found, last = sample_when_steady(N)
    if last is None:
        skip("no llegué a mirar /proc mientras el anillo giraba")
    elif found:
        ok(f"en vivo: los {N} hijos tienen abiertos solo sus pipes (2 cada uno, "
           f"3 el distinguido) y al padre le queda solo el del resultado")
    else:
        child_fds, parent_fds = last
        detail = [
            f"hijo pid {h}: {c.get('pipe', 0)} pipes abiertos (esperaba 2, "
            f"o 3 si es el distinguido)"
            for h, c in sorted(child_fds.items())
        ]
        detail.append(
            f"padre: {parent_fds.get('pipe', 0)} pipes abiertos (esperaba 1)"
        )
        fail(
            "quedaron file descriptors abiertos de más mientras el anillo gira. "
            "Cada hijo tiene que cerrar todos los extremos menos el que lee de su "
            "antecesor y el que escribe a su sucesor, y el padre todo el anillo",
            "\n".join(detail),
        )
    end_section()

# ---------------------------------------------------------------------
if run_section("procesos"):
    section("Terminación en cascada: los hijos terminan antes que el padre")

    # 1) Que la cascada efectivamente termine. Si algún hijo se queda con
    #    un extremo de escritura abierto, el read() del sucesor nunca ve el
    #    EOF y esto se cuelga.
    for n, s, c, p in [(3, 1, 0, 10), (8, 5, 0, 30), (12, 12, 0, 50)]:
        res = run_ring(n, s, c, p, seconds=20)
        if res.timed_out:
            fail(f"({n} {s} {c} {p}) se colgó: los hijos no terminan en cascada. "
                 f"Suele ser que alguno se quedó con un extremo de escritura abierto "
                 f"y el EOF nunca llega")
        else:
            expect(
                res.rc == 0,
                f"({n} {s} {c} {p}) termina en cascada, rc=0",
                f"({n} {s} {c} {p}) terminó con rc={res.rc}, esperaba 0",
                res.output,
            )

    # 2) Que no quede nadie vivo ni zombie después.
    #
    #    Se usa una cota grande a propósito: con una corrida instantánea
    #    el muestreo no llegaría a ver ningún hijo y el chequeo pasaría
    #    sin haber mirado nada. Por eso además se exige haber visto los 6.
    N = 6
    process = spinning_ring(N)
    watcher = lib.Watcher(process.pid)
    watcher.watch_until(process)
    process.wait()
    time.sleep(0.3)
    survivors = watcher.survivors()
    if len(watcher.seen) != N:
        fail(f"esperaba ver {N} hijos mientras el anillo giraba, vi "
             f"{len(watcher.seen)}: o no se crean los n procesos, o terminan antes "
             f"de tiempo")
    else:
        expect(
            not survivors and not watcher.zombies,
            f"después de terminar no queda ninguno de los {N} hijos vivo ni zombie",
            "quedaron procesos dando vueltas después de que terminó el padre:",
            f"vivos: {survivors}\nzombies vistos: {watcher.zombies}",
        )

    # 3) El orden de terminación, directo de la traza.
    if not lib.has_strace():
        skip("no hay strace instalado, no puedo verificar el orden de terminación")
    else:
        _, trace = lib.run_traced(30, BIN, 5, 1, 0, 25,
                                  syscalls="clone,clone3,fork,vfork,wait4,waitid,exit_group")
        if trace is None:
            skip("no pude correr strace acá")
        else:
            passed, detail = lib.parent_exits_last(trace)
            expect(passed, "el padre es el último en terminar",
                   "el padre terminó antes que alguno de sus hijos", detail)

            waits = trace.count(trace.root_pid, "wait4", "waitid", only_successful=False)
            expect(
                waits >= 5,
                f"el padre espera a sus 5 hijos ({waits} llamadas a wait)",
                f"el padre solo hizo {waits} llamadas a wait, esperaba al menos 5 "
                f"(una por hijo): si no los espera, quedan zombies",
            )
    end_section()

# ---------------------------------------------------------------------
if run_section("sin-kill"):
    section("La terminación no puede resolverse a señales")

    if not lib.has_strace():
        skip("no hay strace instalado en la VM")
    else:
        # Ojo: killpg NO es una syscall (es un envoltorio de libc sobre
        # kill), así que ponerla acá haría fallar a strace entero.
        _, trace = lib.run_traced(30, BIN, 6, 3, 0, 25, syscalls="kill,tgkill,tkill")
        if trace is None:
            skip("no pude correr strace acá")
        else:
            signals = trace.calls_to("kill", "tgkill", "tkill")
            expect(
                not signals,
                "no se manda ninguna señal: la cascada la arma el EOF de los pipes",
                f"el programa manda {len(signals)} señales, y el enunciado no lo "
                f"permite: los hijos tienen que terminar solos por EOF",
                "\n".join(l.line for l in signals[:10]),
            )

    if shutil.which("nm") is None:
        skip("no hay nm instalado en la VM")
    else:
        forbidden = ("kill", "killpg", "tgkill")
        output = ""
        for cmd in (["nm", "-D", "--undefined-only", BIN], ["nm", BIN]):
            r = lib.run(10, cmd[0], *cmd[1:])
            output += r.out
        found_symbols = [
            l for l in output.splitlines()
            if re.match(r"^[0-9a-fA-F ]* *[UtTwW] (" + "|".join(forbidden) + r")$", l)
        ]
        expect(
            not found_symbols,
            "el binario no referencia kill/killpg/tgkill",
            "el binario usa símbolos de envío de señales, que el enunciado prohíbe:",
            "\n".join(found_symbols),
        )
    end_section()

# ---------------------------------------------------------------------
if run_section("huerfanos"):
    lib.orphans_section(BIN)

lib.summary()

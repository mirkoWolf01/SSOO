#!/usr/bin/env python3
"""
SSOO - Ejercicio 1 (la mini shell) - tests

Uso (desde la raíz del taller, adentro de la VM):
    python3 tests/tests_ej1.py ./bin/minishell [--check=NOMBRE]

NOMBRE puede ser: basico | pipes | robustez | fds | procesos |
interactivo | huerfanos. Si no se pasa --check, corren todas.

Normalmente no hace falta invocarlo a mano: el Makefile lo corre adentro
de la VM con "make test-ej1" (y "make test-ej1-fds", etc. para una sola
sección).

Variables de entorno:
    TIMEOUT_FACTOR  multiplica todos los timeouts en máquinas lentas

Casi todos los tests le pasan los comandos a la mini shell por un pipe y
comparan su stdout carácter por carácter. Eso funciona porque el prompt
se muestra solo cuando stdin es una terminal: con un pipe, la salida
queda limpia. La sección 'interactivo' es la que levanta una terminal de
verdad para probar el prompt, Ctrl-C y Ctrl-D.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402
from lib import expect, fail, end_section, run_section, section, skip  # noqa: E402

BIN = lib.tests_init(sys.argv, 1, "uso: tests_ej1.py ./bin/minishell [--check=SECCION]")


def session(commands, seconds=15):
    """Le pasa una lista de comandos a la mini shell por stdin."""
    stdin_text = "".join(c + "\n" for c in commands)
    return lib.run(seconds, BIN, stdin_text=stdin_text)


def normalize(text):
    """Saca los espacios de los bordes de cada línea. Hace falta porque
    algunas herramientas (wc, por ejemplo) alinean su salida con espacios
    y eso no tiene nada que ver con lo que estamos probando."""
    return "\n".join(l.strip() for l in text.splitlines())


def check_output(commands, expected, label, exact=True, seconds=15):
    """Corre una sesión y compara su stdout contra lo esperado."""
    res = session(commands, seconds)
    if res.timed_out:
        fail(f"{label}: la mini shell se cuelga (timeout)")
        return
    if res.killed_by_signal:
        fail(f"{label}: la mini shell muere por señal {res.signal_number} "
             f"(posible segfault)", res.output)
        return

    got = res.out if exact else normalize(res.out)
    want = expected if exact else normalize(expected)
    expect(
        got == want,
        label,
        f"{label}: la salida no es la esperada",
        f"comandos:\n  " + "\n  ".join(commands)
        + f"\nesperaba: {want!r}\nobtuve:   {got!r}"
        + (f"\nstderr:   {res.err!r}" if res.err else ""),
    )


# ---------------------------------------------------------------------
if run_section("basico"):
    section("Un solo comando")

    check_output(["echo hola"], "hola\n", "echo hola")
    check_output(["seq 1 5"], "1\n2\n3\n4\n5\n", "seq 1 5")
    check_output(["printf %s-%s a b"], "a-b", "un comando con varios argumentos")
    check_output(["   echo    hola   mundo  "], "hola mundo\n",
           "espacios de más entre los tokens")
    check_output(["", "   ", "echo sigo-vivo"], "sigo-vivo\n",
           "las líneas vacías se ignoran y la shell sigue viva")
    check_output(["echo uno", "echo dos", "echo tres"], "uno\ndos\ntres\n",
           "tres comandos en la misma sesión")

    # Si no espera a que termine el pipeline antes de leer la línea
    # siguiente, el "FIN" se cuela en el medio de los números.
    check_output(["seq 1 3 | cat", "echo FIN"], "1\n2\n3\nFIN\n",
           "espera a que termine el pipeline antes del comando siguiente")
    end_section()

# ---------------------------------------------------------------------
if run_section("pipes"):
    section("Pipelines")

    check_output(["seq 1 10 | wc -l"], "10\n", "2 comandos: seq | wc", exact=False)
    check_output(["seq 3 -1 1 | sort"], "1\n2\n3\n", "2 comandos: seq | sort")
    check_output(["seq 1 10 | tail -n 3 | wc -l"], "3\n", "3 comandos", exact=False)
    check_output(["seq 1 20 | head -n 10 | tail -n 3 | tr \\n ,"], "8,9,10,",
           "4 comandos")
    check_output(["seq 1 100 | head -n 50 | tail -n 20 | head -n 5 | wc -l"], "5\n",
           "5 comandos", exact=False)

    # El que consume corta antes de tiempo: el productor recibe SIGPIPE y
    # muere. Si la mini shell no cerró bien los extremos, esto se cuelga.
    check_output(["seq 1 1000000 | head -n 1"], "1\n",
           "el consumidor corta antes (SIGPIPE al productor)")
    check_output(["yes | head -n 3"], "y\ny\ny\n",
           "productor infinito: yes | head -n 3")

    check_output(["seq 1 3 | wc -l", "seq 1 7 | wc -l"], "3\n7\n",
           "dos pipelines seguidos en la misma sesión", exact=False)
    end_section()

# ---------------------------------------------------------------------
if run_section("robustez"):
    section("Robustez: la mini shell no se muere por un comando roto")

    res = session(["no-existe-este-comando", "echo sobrevivi"])
    expect(
        res.out == "sobrevivi\n" and res.err.strip() != "",
        "un comando inexistente avisa por stderr y no mata a la shell",
        "con un comando inexistente la mini shell tendría que avisar por stderr "
        "y seguir andando",
        f"stdout: {res.out!r}\nstderr: {res.err!r}",
    )

    res = session(["echo hola | no-existe-este-comando | cat", "echo sobrevivi"])
    expect(
        "sobrevivi" in res.out,
        "un comando inexistente en el medio de un pipe tampoco la mata",
        "la mini shell no sobrevivió a un comando inexistente en el medio de un pipe",
        f"stdout: {res.out!r}\nstderr: {res.err!r}",
    )

    res = session(["echo x"])
    expect(res.rc == 0, "termina con exit code 0 al llegar al fin de archivo",
           f"terminó con rc={res.rc}, esperaba 0")

    # Una línea larga no tiene que desbordar ningún buffer.
    long_line = "a" * 2000
    check_output([f"echo {long_line}"], long_line + "\n", "una línea de 2000 caracteres")

    # Un pipe con un lado vacío es un error de sintaxis, no un motivo
    # para morirse.
    res = session(["ls |", "| wc -l", "echo sobrevivi"])
    expect(
        "sobrevivi" in res.out,
        "un pipe con algún lado vacío se rechaza sin matar a la shell",
        "la mini shell no sobrevivió a una línea mal formada",
        f"stdout: {res.out!r}\nstderr: {res.err!r}",
    )
    end_section()

# ---------------------------------------------------------------------
if run_section("fds"):
    section("File descriptors: cerrar los que no se usan")

    # Un pipeline de tres sleeps se queda quieto el tiempo suficiente
    # como para mirar /proc con calma.
    process = subprocess.Popen(
        [BIN], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True,
    )
    try:
        process.stdin.write(b"sleep 5 | sleep 5 | sleep 5\n")
        process.stdin.flush()

        ready = lib.wait_until(
            lambda: len(lib.children_of(process.pid)) == 3, seconds=8
        )
        children = lib.children_of(process.pid)
        if not ready:
            fail(f"esperaba ver 3 procesos hijo corriendo el pipeline, vi "
                 f"{len(children)}")
        else:
            # Después del dup2, las puntas del pipe viven en los fds 0 y 1.
            # Cualquier otra cosa abierta es una copia que quedó sin cerrar.
            leftovers = []
            for h in children:
                extra = lib.extra_fds(h)
                if extra:
                    leftovers.append(
                        f"pid {h}: le sobran {len(extra)} fds: "
                        + ", ".join(f"{n} -> {d}" for n, d in sorted(extra.items()))
                    )
            expect(
                not leftovers,
                "cada comando del pipeline se queda solo con stdin, stdout y stderr",
                "hay comandos del pipeline con extremos de pipe sin cerrar. Después "
                "del dup2 hay que cerrar TODAS las copias, incluidas las de los "
                "pipes de los otros comandos",
                "\n".join(leftovers),
            )

            # Y la propia mini shell, mientras espera, tampoco puede
            # quedarse con nada: si retiene un extremo de escritura, el
            # lector de ese pipe no ve nunca el EOF.
            shell_extra = lib.extra_fds(process.pid)
            expect(
                not shell_extra,
                "la mini shell no se queda con ningún extremo de pipe mientras espera",
                "la mini shell tiene extremos de pipe abiertos mientras espera al "
                "pipeline. Tiene que cerrar los suyos apenas termina de forkear",
                "\n".join(f"fd {n} -> {d}" for n, d in sorted(shell_extra.items())),
            )
    finally:
        lib.kill_group(process.pid)
        process.wait()

    # Lo mismo, pero contado desde la traza: es determinista y no depende
    # de agarrar el momento justo.
    if not lib.has_strace():
        skip("no hay strace instalado en la VM")
    else:
        res, trace = lib.run_traced(
            30, BIN, syscalls="pipe,pipe2,close,dup2,dup3,clone,clone3,fork,vfork,execve",
            stdin_text="seq 1 5 | cat | cat | wc -l\n",
        )
        if trace is None or trace.root_pid is None:
            skip("no pude correr strace acá")
        else:
            created = trace.count(trace.root_pid, "pipe", "pipe2")
            expect(
                created == 3,
                "para 4 comandos crea exactamente 3 pipes",
                f"creó {created} pipes para un pipeline de 4 comandos, esperaba 3 "
                f"(uno entre cada par de comandos consecutivos)",
            )
            # Cada comando hereda las 6 puntas de los 3 pipes y tiene que
            # cerrarlas todas: las que usa ya quedaron duplicadas en 0 y 1.
            sloppy = []
            for pid in trace.children:
                closed = trace.count(pid, "close")
                if closed < 6:
                    sloppy.append(f"pid {pid}: cerró {closed} fds, esperaba al "
                                  f"menos 6")
            expect(
                not sloppy and len(trace.children) >= 4,
                "cada comando cierra las 6 puntas de pipe que heredó",
                "hay comandos que no cierran todos los extremos de pipe heredados:",
                "\n".join(sloppy) or f"solo vi {len(trace.children)} comandos, esperaba 4",
            )
            shell_closed = trace.count(trace.root_pid, "close")
            expect(
                shell_closed >= 6,
                "la mini shell cierra sus 6 copias después de forkear",
                f"la mini shell solo cerró {shell_closed} fds, esperaba al menos 6",
            )
    end_section()

# ---------------------------------------------------------------------
if run_section("procesos"):
    section("Procesos: esperar a todos los comandos, no dejar zombies")

    process = subprocess.Popen(
        [BIN], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )
    watcher = lib.Watcher(process.pid)
    try:
        # El 'sleep 1' del primer comando mantiene el pipeline vivo el
        # tiempo suficiente como para verlo. Con un pipeline instantáneo
        # el muestreo no llegaría a ver nada y el chequeo pasaría sin
        # haber mirado nada.
        process.stdin.write(b"sleep 1 | cat | cat\n")
        process.stdin.flush()
        lib.wait_until(lambda: len(watcher.sample()) >= 3, seconds=10)
        process.stdin.close()
        process.wait(timeout=20 * lib.TIMEOUT_FACTOR)
    except subprocess.TimeoutExpired:
        pass
    finally:
        lib.kill_group(process.pid)
    time.sleep(0.3)

    if len(watcher.seen) < 3:
        fail(f"esperaba ver al menos 3 comandos del pipeline, vi {len(watcher.seen)}")
    else:
        survivors = watcher.survivors()
        expect(
            not survivors and not watcher.zombies,
            f"no queda ninguno de los {len(watcher.seen)} comandos vivo ni zombie",
            "quedaron procesos del pipeline dando vueltas:",
            f"vivos: {survivors}\nzombies vistos: {watcher.zombies}",
        )

    if not lib.has_strace():
        skip("no hay strace instalado en la VM")
    else:
        _, trace = lib.run_traced(
            30, BIN, syscalls="clone,clone3,fork,vfork,wait4,waitid,exit_group",
            stdin_text="seq 1 3 | cat | cat\n",
        )
        if trace is None:
            skip("no pude correr strace acá")
        else:
            waits = trace.count(trace.root_pid, "wait4", "waitid",
                                only_successful=False)
            expect(
                waits >= 3,
                f"espera a los 3 comandos del pipeline ({waits} llamadas a wait)",
                f"la mini shell hizo {waits} llamadas a wait para un pipeline de "
                f"3 comandos, esperaba al menos 3: si no los espera a todos, quedan "
                f"zombies y la salida se mezcla con el comando siguiente",
            )
            passed, detail = lib.parent_exits_last(trace)
            expect(passed, "la mini shell es la última en terminar",
                   "la mini shell terminó antes que alguno de los comandos del "
                   "pipeline", detail)
    end_section()

# ---------------------------------------------------------------------
if run_section("interactivo"):
    section("Con una terminal de verdad: prompt, Ctrl-C y Ctrl-D")

    # 1) Con terminal, tiene que aparecer el prompt.
    prompt = ""
    pty = lib.PtySession(BIN)
    try:
        output = pty.read(2.0)
        expect(
            output.strip() != "",
            f"con una terminal muestra un prompt ({output.strip()!r})",
            "con una terminal la mini shell no muestra ningún prompt",
        )
        pty.write("seq 1 3 | wc -l\n")
        response = pty.read(2.0)
        expect(
            "3" in response,
            "ejecuta comandos desde la terminal",
            "no ejecutó 'seq 1 3 | wc -l' desde la terminal",
            f"leí: {response!r}",
        )
        prompt = output.strip()

        # 2) Ctrl-D después de texto sin newline NO cierra: la terminal
        #    solo hace que el read() devuelva lo que había en la línea, y
        #    getline sigue esperando el fin de línea.
        pty.write("echo hola")
        pty.ctrl_d()
        time.sleep(0.5 * lib.TIMEOUT_FACTOR)
        expect(
            pty.process.poll() is None,
            "un Ctrl-D después de texto sin fin de línea no cierra la shell",
            "la mini shell se cerró con un Ctrl-D en el medio de una línea; "
            "el fin de archivo recién llega con la línea vacía",
        )
        pty.write("\n")
        expect("hola" in pty.read(2.0),
               "y el comando a medio escribir se ejecuta al completar la línea",
               "no ejecutó el comando después de completar la línea")

        # 3) Ctrl-D en línea vacía sí cierra, y prolijamente.
        pty.ctrl_d()
        rc = pty.wait(5)
        expect(rc == 0, "Ctrl-D en una línea vacía cierra la shell con rc=0",
               f"Ctrl-D cerró la shell con rc={rc}, esperaba 0")
    finally:
        pty.close()

    # 4) Sin terminal no puede haber prompt: stdout tiene que quedar
    #    limpio para que se pueda encadenar la mini shell con otras cosas.
    res = session(["echo hola"])
    expect(
        res.out == "hola\n",
        "con stdin redirigido no imprime el prompt (stdout queda limpio)",
        "con stdin redirigido la mini shell ensucia stdout con el prompt u otra "
        "cosa. Mostralo solo cuando isatty(STDIN_FILENO) sea verdadero",
        f"esperaba 'hola\\n', obtuve {res.out!r}",
    )
    if prompt:
        expect(
            prompt not in res.out,
            "el prompt no aparece en la salida cuando no hay terminal",
            f"el prompt ({prompt!r}) aparece en stdout aunque stdin no es una "
            f"terminal",
        )

    # 5) Ctrl-C mata a la mini shell y a lo que esté corriendo.
    pty = lib.PtySession(BIN)
    try:
        pty.read(1.0)
        pty.write("sleep 100\n")
        lib.wait_until(lambda: len(lib.descendants_of(pty.pid)) >= 1, seconds=5)
        children = lib.descendants_of(pty.pid)
        pty.ctrl_c()
        rc = pty.wait(5)
        expect(
            rc is not None,
            f"Ctrl-C mata la mini shell (rc={rc})",
            "Ctrl-C no cerró la mini shell",
        )
        all_gone = lib.wait_until(lambda: not lib.alive_among(children), seconds=5)
        expect(
            all_gone,
            "y se lleva puesto también al comando que estaba corriendo",
            f"después del Ctrl-C quedaron vivos los procesos {lib.alive_among(children)}",
        )
    finally:
        pty.close()
    end_section()

# ---------------------------------------------------------------------
if run_section("huerfanos"):
    lib.orphans_section(BIN)

lib.summary()

"""
Funciones comunes a los tests de los tres ejercicios.

Los tests corren SIEMPRE adentro de la VM (ver el Makefile), o sea sobre
Linux, parados en la raíz del taller. Por eso todas las rutas son
relativas y se pueden dar por sentadas cosas de Linux: /proc, strace, nm.

El formato de salida es exactamente el mismo que el del taller de
syscalls (que está escrito en bash): secciones, [OK] / [FAIL] / [SKIP] y
un resumen final. Lo que ve el alumno es idéntico; cambia la
implementación nomás.

En máquinas lentas (por ejemplo una Mac con Apple Silicon, donde la VM
corre emulada por software) los timeouts se pueden estirar:

    TIMEOUT_FACTOR=3 make test-ej2
"""

import fcntl
import os
import re
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import time

TIMEOUT_FACTOR = float(os.environ.get("TIMEOUT_FACTOR", "1"))

# ---------------------------------------------------------------------
# Estado de la corrida
# ---------------------------------------------------------------------

TOTAL = 0
OK = 0
FAIL = 0

BINS = []
CHECK = "todos"
TMPDIR = None

RULE = "================================================"


def _usage(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def tests_init(argv, n_bins=1, usage=None):
    """Parsea los argumentos comunes: las rutas a los binarios y un
    --check=SECCION opcional (para poder correr una sola sección, útil
    para corregir con puntaje por partes)."""
    global BINS, CHECK, TMPDIR

    usage = usage or f"uso: {argv[0]} " + " ".join(
        f"/ruta/al/binario{i + 1}" for i in range(n_bins)
    ) + " [--check=SECCION]"

    for arg in argv[1:]:
        if arg.startswith("--check="):
            CHECK = arg[len("--check="):]
        else:
            BINS.append(arg)

    if len(BINS) != n_bins:
        _usage(usage)
    for b in BINS:
        if not os.path.isfile(b) or not os.access(b, os.X_OK):
            _usage(f"no encontré el binario ejecutable '{b}'\n{usage}")

    TMPDIR = tempfile.mkdtemp(prefix="taller-ipc-")
    import atexit

    atexit.register(lambda: shutil.rmtree(TMPDIR, ignore_errors=True))
    return BINS if n_bins > 1 else BINS[0]


def run_section(name):
    """¿Toca correr esta sección?"""
    return CHECK in ("todos", name)


def section(title):
    print(f"=== {title} ===")


def end_section():
    print("")


# ---------------------------------------------------------------------
# Contadores
# ---------------------------------------------------------------------


def ok(message):
    global TOTAL, OK
    TOTAL += 1
    OK += 1
    print(f"  [OK] {message}")


def fail(message, detail=None):
    global TOTAL, FAIL
    TOTAL += 1
    FAIL += 1
    print(f"  [FAIL] {message}", file=sys.stderr)
    if detail:
        for line in str(detail).rstrip("\n").split("\n"):
            print(f"         {line}", file=sys.stderr)
    sys.stderr.flush()


def skip(message):
    print(f"  [SKIP] {message}")


def expect(condition, ok_message, fail_message, detail=None):
    """El caballito de batalla: un check que pasa o falla."""
    if condition:
        ok(ok_message)
        return True
    fail(fail_message, detail)
    return False


def summary():
    """Resumen y exit code de los tests."""
    line = f" Resultado: {OK}/{TOTAL} checks OK, {FAIL} fallidos"
    if FAIL > 0:
        print(RULE, file=sys.stderr)
        print(line, file=sys.stderr)
        print(RULE, file=sys.stderr)
        sys.exit(1)
    print(RULE)
    print(line)
    print(RULE)
    sys.exit(0)


# ---------------------------------------------------------------------
# Correr programas
# ---------------------------------------------------------------------


class Result:
    """Lo que dejó una corrida. `rc` sigue la convención de bash:
    124 = se colgó (timeout), >= 128 = lo mató una señal."""

    def __init__(self, rc, out, err, pid):
        self.rc = rc
        self.out = out
        self.err = err
        self.pid = pid

    @property
    def output(self):
        return self.out + self.err

    @property
    def timed_out(self):
        return self.rc == 124

    @property
    def killed_by_signal(self):
        return self.rc >= 128

    @property
    def signal_number(self):
        return self.rc - 128 if self.rc >= 128 else None

    def __repr__(self):
        return f"<Result rc={self.rc} out={len(self.out)}B err={len(self.err)}B>"


def _normalize_rc(rc):
    # subprocess devuelve negativo si lo mató una señal; lo pasamos a la
    # convención de bash (128 + señal) para que los mensajes se lean igual.
    return 128 + (-rc) if rc is not None and rc < 0 else rc


def kill_group(pid):
    """Barre el grupo de procesos entero.

    IMPORTANTE: si la entrega se cuelga, matar solo al proceso que
    arrancamos dejaría vivos a los hijos que ya forkeó. Por eso todo se
    corre con start_new_session=True (grupo propio) y después se barre el
    grupo completo. Se barre SIEMPRE, no solo si hubo timeout: una
    entrega rota puede terminar el padre sin esperar a los hijos y
    dejarlos huérfanos aunque el timeout nunca haya disparado."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def spawn(prog, *args, stdin_pipe=True, cwd=None, env=None):
    """Arranca un proceso en su propio grupo y lo devuelve sin esperarlo."""
    return subprocess.Popen(
        [prog, *[str(a) for a in args]],
        stdin=subprocess.PIPE if stdin_pipe else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        cwd=cwd,
        env=env,
    )


def run(seconds, prog, *args, stdin_text=None, cwd=None, env=None, output=None):
    """Corre un programa con timeout, en su propio grupo de procesos.

    `stdin_text` es lo que se le manda por stdin (str o bytes; None =
    stdin vacío y cerrado). `output` es opcional: la ruta de un archivo
    donde dejar stdout+stderr, para poder mostrarlo cuando algo falla."""
    if isinstance(stdin_text, str):
        stdin_text = stdin_text.encode()

    p = subprocess.Popen(
        [prog, *[str(a) for a in args]],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        cwd=cwd,
        env=env,
    )
    try:
        out, err = p.communicate(stdin_text, timeout=seconds * TIMEOUT_FACTOR)
        rc = _normalize_rc(p.returncode)
    except subprocess.TimeoutExpired:
        kill_group(p.pid)
        try:
            out, err = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            out, err = b"", b""
        rc = 124
    finally:
        kill_group(p.pid)

    out = out.decode(errors="replace")
    err = err.decode(errors="replace")
    if output:
        with open(output, "w") as f:
            f.write(out + err)
    return Result(rc, out, err, p.pid)


def tmp(name):
    return os.path.join(TMPDIR, name)


# ---------------------------------------------------------------------
# Inspección de /proc: file descriptors y procesos
# ---------------------------------------------------------------------


def open_fds(pid):
    """{numero_de_fd: a_donde_apunta} leyendo /proc/<pid>/fd."""
    base = f"/proc/{pid}/fd"
    res = {}
    try:
        names = os.listdir(base)
    except OSError:
        return res
    for n in names:
        try:
            res[int(n)] = os.readlink(os.path.join(base, n))
        except (OSError, ValueError):
            pass
    return res


def fd_type(target):
    """Clasifica el destino de un fd: 'pipe', 'socket', 'tty', 'archivo'."""
    if target.startswith("pipe:"):
        return "pipe"
    if target.startswith("socket:"):
        return "socket"
    if target.startswith("/dev/pts/") or target in ("/dev/tty", "/dev/console"):
        return "tty"
    if target.startswith("anon_inode:"):
        return "anon"
    return "archivo"


def extra_fds(pid):
    """Los fds abiertos que NO son stdin/stdout/stderr.

    Es lo que interesa casi siempre: qué se dejó abierto el proceso por
    su cuenta. Los fds 0, 1 y 2 se heredan y pueden ser cualquier cosa
    (una terminal, un archivo, o un pipe si al taller lo corriste por
    ssh), así que contarlos ensucia la medición."""
    return {n: d for n, d in open_fds(pid).items() if n > 2}


def count_fds(pid, include_standard=False):
    """{'pipe': 2, 'socket': 1, ...} para un proceso."""
    fds = open_fds(pid) if include_standard else extra_fds(pid)
    res = {}
    for target in fds.values():
        t = fd_type(target)
        res[t] = res.get(t, 0) + 1
    return res


def describe_fds(pid):
    """Texto legible con los fds de un proceso, para los mensajes de error."""
    fds = open_fds(pid)
    if not fds:
        return f"(pid {pid}: sin fds o ya terminó)"
    return "\n".join(f"pid {pid}: fd {n} -> {d}" for n, d in sorted(fds.items()))


def _stat(pid):
    """(comm, estado, ppid, sid) de /proc/<pid>/stat, o None si no existe."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            data = f.read()
    except OSError:
        return None
    # El comm va entre paréntesis y puede tener espacios adentro, así que
    # se busca el ÚLTIMO paréntesis, no el primero.
    try:
        close_paren = data.rindex(")")
    except ValueError:
        return None
    comm = data[data.index("(") + 1: close_paren]
    fields = data[close_paren + 2:].split()
    return comm, fields[0], int(fields[1]), int(fields[3])


def all_pids():
    return [int(n) for n in os.listdir("/proc") if n.isdigit()]


# Fotos que sacamos al arrancar, para distinguir lo que levantaron los
# tests de lo que ya estaba corriendo en la máquina: es muy común dejar
# un "make run-servidor" abierto en otra terminal y correr los tests al
# mismo tiempo. Ver orphans_section().
_PIDS_AT_START = set(all_pids())
_OUR_SID = os.getsid(0)


def children_of(pid):
    """PIDs cuyo padre es `pid` (solo un nivel).

    Se usa /proc/<pid>/task/<pid>/children, que resuelve todo con una
    sola lectura. Importa: estos tests muestrean en un loop apretado, y
    escanear /proc entero cada vez es carísimo adentro de la VM."""
    try:
        with open(f"/proc/{pid}/task/{pid}/children") as f:
            return [int(x) for x in f.read().split()]
    except OSError:
        pass
    # Por si el kernel no trae CONFIG_PROC_CHILDREN.
    res = []
    for other in all_pids():
        st = _stat(other)
        if st and st[2] == pid:
            res.append(other)
    return res


def descendants_of(pid):
    """Todos los descendientes de `pid`, a cualquier profundidad."""
    res, frontier = set(), [pid]
    while frontier:
        for child in children_of(frontier.pop()):
            if child not in res:
                res.add(child)
                frontier.append(child)
    return res


def pid_exists(pid):
    return os.path.exists(f"/proc/{pid}")


def zombies_of(pid):
    """Hijos de `pid` que quedaron en estado Z (terminaron y nadie los
    esperó con wait)."""
    res = []
    for child in children_of(pid):
        st = _stat(child)
        if st and st[1] == "Z":
            res.append((child, st[0]))
    return res


def alive_among(pids):
    """De un conjunto de PIDs, cuáles siguen existiendo."""
    return sorted(p for p in pids if pid_exists(p))


def running_among(pids):
    """De un conjunto de PIDs, cuáles siguen corriendo de verdad.

    Un zombie no cuenta: ese proceso ya terminó, lo que falta es que
    alguien lo coseche (de eso se ocupa zombies_of). Ojo que
    alive_among() sí lo cuenta, porque /proc/<pid> existe hasta que lo
    esperan con wait."""
    res = []
    for pid in pids:
        st = _stat(pid)
        if st and st[1] != "Z":
            res.append(pid)
    return sorted(res)


class Watcher:
    """Va anotando qué descendientes tuvo un proceso mientras corre, para
    poder chequear, después de que el padre murió, que ninguno quedó vivo.

    Hace falta porque un huérfano se re-parenta a init: una vez que el
    padre terminó ya no hay forma de saber de quién era hijo."""

    def __init__(self, pid):
        self.pid = pid
        self.seen = set()
        self.zombies = []

    def sample(self):
        self.seen |= descendants_of(self.pid)
        for z in zombies_of(self.pid):
            if z not in self.zombies:
                self.zombies.append(z)
        return self.seen

    def watch_until(self, process, interval=0.02):
        """Muestrea mientras `process` (un Popen) siga vivo."""
        while process.poll() is None:
            self.sample()
            time.sleep(interval)
        self.sample()

    def survivors(self):
        """Descendientes que siguen vivos ahora."""
        return alive_among(self.seen)


def wait_until(condition, seconds=5, interval=0.02):
    """Espera activa hasta que `condicion()` sea verdadera. Devuelve si
    se cumplió."""
    deadline = time.monotonic() + seconds * TIMEOUT_FACTOR
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


# ---------------------------------------------------------------------
# Trazas de strace
# ---------------------------------------------------------------------

_RE_LINE = re.compile(r"^(\d+)\s+(.*)$")
_RE_CALL = re.compile(r"^([a-zA-Z_][a-zA-Z_0-9]*)\((.*)\)\s*=\s*(.*)$")
_RE_UNFINISHED = re.compile(r"^([a-zA-Z_][a-zA-Z_0-9]*)\((.*)<unfinished \.\.\.>$")
_RE_RESUMED = re.compile(r"^<\.\.\. ([a-zA-Z_][a-zA-Z_0-9]*) resumed>(.*)\)\s*=\s*(.*)$")
_RE_EXITED = re.compile(r"^\+\+\+ exited with (-?\d+) \+\+\+$")


class Call:
    def __init__(self, order, pid, name, args, ret, line):
        self.order = order
        self.pid = pid
        self.name = name
        self.args = args
        self.ret = ret
        self.line = line

    @property
    def ret_int(self):
        m = re.match(r"^(-?\d+)", self.ret.strip())
        return int(m.group(1)) if m else None

    def __repr__(self):
        return f"<{self.pid} {self.name}({self.args}) = {self.ret}>"


class Trace:
    """Una traza de `strace -f` ya parseada."""

    def __init__(self, calls, deaths, root_pid):
        self.calls = calls
        self.deaths = deaths          # [(orden, pid, exit_code)]
        self.root_pid = root_pid

    def calls_of(self, pid):
        return [l for l in self.calls if l.pid == pid]

    def calls_to(self, *names):
        return [l for l in self.calls if l.name in names]

    def count(self, pid, *names, only_successful=True):
        n = 0
        for l in self.calls:
            if l.pid == pid and l.name in names:
                if only_successful and (l.ret_int is None or l.ret_int < 0):
                    continue
                n += 1
        return n

    @property
    def pids(self):
        seen = []
        for l in self.calls:
            if l.pid not in seen:
                seen.append(l.pid)
        return seen

    @property
    def children(self):
        return [p for p in self.pids if p != self.root_pid]

    def death_order(self):
        """PIDs en el orden en que strace los vio terminar."""
        return [pid for _, pid, _ in sorted(self.deaths)]


def parse_trace(path):
    calls = []
    deaths = []
    root_pid = None
    pending = {}   # pid -> (nombre, args_parciales)
    order = 0

    with open(path, errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m = _RE_LINE.match(line)
            if not m:
                continue
            pid, rest = int(m.group(1)), m.group(2).strip()
            if root_pid is None:
                root_pid = pid
            order += 1

            m2 = _RE_EXITED.match(rest)
            if m2:
                deaths.append((order, pid, int(m2.group(1))))
                continue

            if rest.startswith("---") or rest.startswith("+++"):
                continue

            m2 = _RE_UNFINISHED.match(rest)
            if m2:
                pending[pid] = (m2.group(1), m2.group(2))
                continue

            m2 = _RE_RESUMED.match(rest)
            if m2:
                name = m2.group(1)
                previous_args = pending.pop(pid, (name, ""))[1]
                calls.append(
                    Call(order, pid, name, previous_args + m2.group(2),
                         m2.group(3), line)
                )
                continue

            m2 = _RE_CALL.match(rest)
            if m2:
                calls.append(
                    Call(order, pid, m2.group(1), m2.group(2), m2.group(3), line)
                )

    return Trace(calls, deaths, root_pid)


def has_strace():
    return shutil.which("strace") is not None


def run_traced(seconds, prog, *args, syscalls=None, stdin_text=None, cwd=None):
    """Corre un programa bajo `strace -f` y devuelve (Resultado, Traza).
    Si strace no está o falla, devuelve (Resultado, None)."""
    path = tmp(f"traza_{os.path.basename(prog)}_{int(time.time() * 1e6)}.txt")
    cmd = ["strace", "-f", "-o", path]
    if syscalls:
        cmd += ["-e", "trace=" + syscalls]
    res = run(seconds, cmd[0], *cmd[1:], prog, *args, stdin_text=stdin_text, cwd=cwd)
    if not os.path.exists(path):
        return res, None
    return res, parse_trace(path)


def parent_exits_last(trace):
    """¿El proceso raíz terminó DESPUÉS que todos sus hijos?

    Devuelve si se cumplió, y el detalle cuando no."""
    order = trace.death_order()
    if not order:
        return False, "la traza no registró la terminación de ningún proceso"
    if trace.root_pid not in order:
        return False, f"la traza no registró la terminación del padre (pid {trace.root_pid})"
    position = order.index(trace.root_pid)
    if position != len(order) - 1:
        after = order[position + 1:]
        return False, (
            f"el padre (pid {trace.root_pid}) terminó antes que "
            f"{len(after)} de sus hijos: {after}\n"
            f"orden de terminación observado: {order}"
        )
    return True, ""


# ---------------------------------------------------------------------
# Sockets UNIX
# ---------------------------------------------------------------------

_socket_counter = [0]


def socket_path(prefix="s"):
    """Una ruta libre para un socket UNIX.

    Va en /tmp y no en el directorio del taller: esa carpeta se comparte
    con la VM por 9p, que no soporta crear sockets (el bind falla con
    EOPNOTSUPP). Además la ruta tiene que ser corta, porque entra en
    sun_path, que son 108 bytes."""
    _socket_counter[0] += 1
    return f"/tmp/taller-{os.getpid()}-{prefix}{_socket_counter[0]}.sock"


def connect_to_socket(path, timeout=10):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(path)
    return s


def wait_for_socket(path, seconds=10):
    """Espera a que alguien esté escuchando en el socket."""

    def is_listening():
        try:
            connect_to_socket(path, timeout=0.3).close()
            return True
        except OSError:
            return False

    return wait_until(is_listening, seconds, interval=0.05)


# ---------------------------------------------------------------------
# Pseudo-terminales (para probar los programas interactivos de verdad)
# ---------------------------------------------------------------------


def _login_tty(fd):
    os.setsid()
    try:
        fcntl.ioctl(fd, termios.TIOCSCTTY, 0)
    except OSError:
        pass
    for target in (0, 1, 2):
        os.dup2(fd, target)
    if fd > 2:
        os.close(fd)


class PtySession:
    """Un programa corriendo atado a una pseudo-terminal, para poder
    probar el prompt, Ctrl-C y Ctrl-D como los ve un alumno de verdad."""

    def __init__(self, prog, *args, cwd=None, echo=False):
        import pty

        self.master, slave = pty.openpty()
        if not echo:
            attrs = termios.tcgetattr(slave)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(slave, termios.TCSANOW, attrs)
        # 24x80, por si el programa pregunta.
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))

        self.process = subprocess.Popen(
            [prog, *[str(a) for a in args]],
            stdin=slave, stdout=slave, stderr=slave,
            preexec_fn=lambda: _login_tty(slave),
            cwd=cwd,
            close_fds=True,
        )
        os.close(slave)
        self.buffer = ""

    @property
    def pid(self):
        return self.process.pid

    def write(self, text):
        os.write(self.master, text.encode())

    def read(self, seconds=2.0):
        """Lee lo que haya salido hasta que pase `segundos` sin novedades."""
        deadline = time.monotonic() + seconds * TIMEOUT_FACTOR
        output = ""
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.master], [], [], 0.1)
            if not ready:
                continue
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                break
            if not chunk:
                break
            output += chunk.decode(errors="replace")
            deadline = time.monotonic() + 0.3 * TIMEOUT_FACTOR
        self.buffer += output
        return output.replace("\r\n", "\n")

    def read_until(self, text, seconds=5.0):
        """Lee hasta encontrar `texto` en la salida acumulada."""
        deadline = time.monotonic() + seconds * TIMEOUT_FACTOR
        accumulated = ""
        while time.monotonic() < deadline:
            accumulated += self.read(0.3)
            if text in accumulated.replace("\r\n", "\n"):
                return True, accumulated
        return False, accumulated

    def ctrl_c(self):
        """Manda el carácter VINTR. La disciplina de línea de la terminal
        lo traduce a un SIGINT al grupo de procesos en primer plano."""
        self.write("\x03")

    def ctrl_d(self):
        """Manda el carácter VEOF. No es una señal: hace que el read()
        pendiente retorne ya mismo con lo que haya en la línea (0 bytes
        si estaba vacía, que es justo lo que se ve como fin de archivo)."""
        self.write("\x04")

    def wait(self, seconds=5.0):
        try:
            return _normalize_rc(
                self.process.wait(timeout=seconds * TIMEOUT_FACTOR)
            )
        except subprocess.TimeoutExpired:
            return None

    def close(self):
        kill_group(self.process.pid)
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
        try:
            os.close(self.master)
        except OSError:
            pass


# ---------------------------------------------------------------------
# Sección compartida por los tests de los tres ejercicios
# ---------------------------------------------------------------------


def orphans_section(*names, seconds=8):
    """Chequeo final: que no hayan quedado procesos vivos de los
    binarios después de todas las corridas.

    Se espera a que desaparezcan en vez de mirar una sola vez: al
    terminar, los tests barren a señales los grupos de procesos que
    levantó, y una señal tarda un instante en hacer efecto. Un proceso
    realmente colgado no se va a ir por más que lo esperemos; uno que
    está terminando, sí.

    Solo miramos los procesos que levantaron los tests: si tenés un
    servidor corriendo a mano en otra terminal mientras corrés esto, no
    cuenta como huérfano."""
    section("Sin procesos huérfanos/zombies después de correr")
    basenames = {os.path.basename(n) for n in names}

    def is_ours(pid, sid):
        """¿Este proceso lo levantamos nosotros?

        Todo lo que levantan los tests arranca con start_new_session, así
        que su sesión es nueva: el sid es un pid que no existía cuando
        empezamos. Lo del alumno, en cambio, cuelga de una sesión que ya
        estaba (la de su terminal), y sus hijos heredan ese mismo sid
        aunque nazcan mientras corren los tests.

        La excepción es nuestra propia sesión: si algo se nos escapó sin
        start_new_session, queda con nuestro sid y sí hay que contarlo."""
        if pid in _PIDS_AT_START:
            return False
        return sid not in _PIDS_AT_START or sid == _OUR_SID

    def remaining():
        alive = []
        for pid in all_pids():
            st = _stat(pid)
            if st and st[0] in basenames and is_ours(pid, st[3]):
                alive.append(f"pid {pid}  {st[0]}  estado {st[1]}")
        return alive

    wait_until(lambda: not remaining(), seconds)
    left_over = remaining()
    expect(
        not left_over,
        "no quedaron procesos huérfanos",
        f"quedaron procesos vivos del binario {seconds}s después de terminar "
        f"las corridas:",
        "\n".join(left_over),
    )
    end_section()

#!/usr/bin/env python3
"""
SSOO - Ejercicio 3 (servidor y cliente HTTP) - tests

Uso (desde la raíz del taller, adentro de la VM):
    python3 tests/tests_ej3.py ./bin/servidor ./bin/cliente [--check=NOMBRE]

NOMBRE puede ser: servidor-basico | servidor-errores | servidor-keepalive |
servidor-concurrencia | servidor-fds | servidor-procesos |
servidor-seguridad | cliente | interop | huerfanos.
Si no se pasa --check, corren todas.

Normalmente no hace falta invocarlo a mano: el Makefile lo corre adentro
de la VM con "make test-ej3" (y "make test-ej3-servidor-concurrencia",
etc. para una sola sección).

El servidor se prueba con un cliente escrito acá en python, que permite
mandarle cosas mal formadas y controlar los tiempos. El cliente se prueba
contra un servidor de referencia, también de acá: así un servidor roto no
tapa un cliente roto, ni al revés. Y al final hay una sección de interop
que los pone a los dos a hablar entre sí.
"""

import os
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402
from lib import expect, fail, end_section, ok, run_section, section  # noqa: E402

BIN_SERVIDOR, BIN_CLIENTE = lib.tests_init(
    sys.argv, 2,
    "uso: tests_ej3.py ./bin/servidor ./bin/cliente [--check=SECCION]",
)

PUBLIC = "public"
TIMEOUT = 10 * lib.TIMEOUT_FACTOR


def read_fixture(name):
    with open(os.path.join(PUBLIC, name), "rb") as f:
        return f.read()


# ---------------------------------------------------------------------
# Un cliente del protocolo, para probar el servidor
# ---------------------------------------------------------------------


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def content_length(self):
        return self.headers.get("Content-Length")

    def __repr__(self):
        return f"<{self.status!r} len={len(self.body)}>"


class Connection:
    """Habla el protocolo del ejercicio contra el servidor del alumno."""

    def __init__(self, path, timeout=TIMEOUT):
        self.sock = lib.connect_to_socket(path, timeout)
        self.buffer = b""

    def send(self, text):
        self.sock.sendall(text.encode())

    def _read_exactly(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("el servidor cerró la conexión")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def read_line(self):
        while b"\n" not in self.buffer:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("el servidor cerró la conexión")
            self.buffer += chunk
        line, _, self.buffer = self.buffer.partition(b"\n")
        return line.rstrip(b"\r").decode(errors="replace")

    def response(self):
        status = self.read_line()
        # La despedida no trae ni headers ni cuerpo.
        if status == "Connection: close":
            return Response(status, {}, b"")
        headers = {}
        while True:
            line = self.read_line()
            if line == "":
                break
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()
        long_line = int(headers.get("Content-Length", 0))
        return Response(status, headers, self._read_exactly(long_line))

    def request(self, line):
        self.send(line + "\n")
        return self.response()

    def saw_eof(self, seconds=1.0):
        """¿El servidor ya cerró del otro lado?"""
        self.sock.settimeout(seconds)
        try:
            return self.sock.recv(1) == b""
        except socket.timeout:
            return False
        except OSError:
            return True
        finally:
            try:
                self.sock.settimeout(TIMEOUT)
            except OSError:
                pass

    def close_abruptly(self):
        """Se va sin avisar, como un cliente que se murió.

        En sockets UNIX no existe el RST de TCP, pero no hace falta: al
        cerrar de este lado el servidor ve el EOF enseguida, y si estaba
        escribiendo se come un EPIPE. Que es exactamente la situación
        que queremos probar."""
        try:
            self.sock.close()
        except OSError:
            pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ---------------------------------------------------------------------
# El servidor del alumno, levantado sobre su propio socket
# ---------------------------------------------------------------------


class Server:
    def __init__(self, path=None):
        self.path = path or lib.socket_path("srv")
        self.process = subprocess.Popen(
            [BIN_SERVIDOR, self.path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        self.started = lib.wait_for_socket(self.path, 15)

    @property
    def pid(self):
        return self.process.pid

    def children(self):
        return lib.children_of(self.pid)

    def is_alive(self):
        return self.process.poll() is None

    def connect(self, **kw):
        return Connection(self.path, **kw)

    def close(self):
        lib.kill_group(self.pid)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def start_server(section_name, path=None):
    """Levanta el servidor o devuelve None avisando el problema."""
    s = Server(path)
    if not s.started:
        s.close()
        fail(f"el servidor no llegó a escuchar en {s.path}; "
             f"no puedo correr la sección '{section_name}'")
        return None
    return s


# ---------------------------------------------------------------------
# Un servidor de referencia, para probar el cliente por separado
# ---------------------------------------------------------------------


class ReferenceServer:
    """Habla el protocolo del enunciado correctamente. Se le puede pedir
    que mande el cuerpo de a pedacitos o que corte de golpe, para ver
    cómo reacciona el cliente."""

    def __init__(self, files, chunk=None, delay=0.0, hang_up=False):
        self.files = files
        self.chunk = chunk
        self.delay = delay
        self.hang_up = hang_up
        self.path = lib.socket_path("ref")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        self.sock.listen(16)
        self.stop_flag = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _send(self, conn, data):
        if self.chunk:
            for i in range(0, len(data), self.chunk):
                conn.sendall(data[i:i + self.chunk])
                if self.delay:
                    time.sleep(self.delay)
        else:
            conn.sendall(data)

    def _handle(self, conn):
        pending_data = b""
        with conn:
            while not self.stop_flag.is_set():
                while b"\n" not in pending_data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    pending_data += chunk
                line, _, pending_data = pending_data.partition(b"\n")
                request_line = line.rstrip(b"\r").decode(errors="replace")

                if request_line == "Connection: close":
                    conn.sendall(b"Connection: close\n")
                    return
                if self.hang_up:
                    return      # cierra sin contestar nada
                if not request_line.startswith("GET /"):
                    status = (b"HTTP/1.1 405 Method Not Allowed"
                              if " /" in request_line
                              else b"HTTP/1.1 400 Bad Request")
                    self._send(conn, status + b"\nContent-Length: 0\n\n")
                    continue
                path = request_line[4:]
                body = self.files.get(path)
                if body is None:
                    self._send(conn, b"HTTP/1.1 404 Not Found\n"
                                       b"Content-Length: 0\n\n")
                    continue
                header = (f"HTTP/1.1 200 OK\nContent-Length: {len(body)}\n\n"
                            ).encode()
                self._send(conn, header + body)

    def _serve(self):
        while not self.stop_flag.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,),
                             daemon=True).start()

    def close(self):
        self.stop_flag.set()
        try:
            self.sock.close()
        except OSError:
            pass
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def run_client(path, commands, seconds=20):
    stdin_text = "".join(c + "\n" for c in commands)
    return lib.run(seconds, BIN_CLIENTE, path, stdin_text=stdin_text)


# ---------------------------------------------------------------------
if run_section("servidor-basico"):
    section("Servidor: servir archivos de public/")
    srv = start_server("servidor-basico")
    if srv:
        with srv, srv.connect() as c:
            for name in ("hola.txt", "poema.txt", "vacio.txt", "grande.txt"):
                expected = read_fixture(name)
                try:
                    r = c.request(f"GET /{name}")
                except (EOFError, OSError) as e:
                    fail(f"GET /{name}: se cortó la conexión ({e})")
                    continue
                if r.status != "HTTP/1.1 200 OK":
                    fail(f"GET /{name}: contestó {r.status!r}, esperaba "
                         f"'HTTP/1.1 200 OK'")
                elif r.content_length != str(len(expected)):
                    fail(f"GET /{name}: Content-Length dice {r.content_length}, "
                         f"el archivo mide {len(expected)} bytes")
                else:
                    expect(
                        r.body == expected,
                        f"GET /{name}: {len(expected)} bytes correctos",
                        f"GET /{name}: el cuerpo no coincide con el archivo. "
                        f"Con archivos grandes suele ser que se cortó la lectura "
                        f"del archivo antes de tiempo",
                        f"esperaba {len(expected)} bytes, llegaron {len(r.body)}",
                    )
            try:
                r = c.request("GET /sub/anidado.txt")
                expect(
                    r.status == "HTTP/1.1 200 OK"
                    and r.body == read_fixture("sub/anidado.txt"),
                    "GET /sub/anidado.txt: resuelve rutas en subcarpetas",
                    f"GET /sub/anidado.txt contestó {r.status!r}",
                )
            except (EOFError, OSError) as e:
                fail(f"GET /sub/anidado.txt: se cortó la conexión ({e})")

    # Un socket UNIX es un archivo, y el bind() lo crea. Si el servidor
    # murió mal y quedó el archivo dado vuelta, el arranque siguiente
    # falla con EADDRINUSE salvo que se haga unlink() antes del bind.
    path = lib.socket_path("stale")
    first = Server(path)
    if not first.started:
        fail(f"el servidor no llegó a escuchar en {path}")
    else:
        # Lo matamos a lo bruto, para que el archivo quede colgado.
        first.process.kill()
        first.process.wait()
        existed = os.path.exists(path)
        second = Server(path)
        try:
            if not second.started:
                fail(
                    f"con un socket viejo tirado en {path} el servidor no "
                    f"arranca. Hacé unlink() de la ruta antes del bind(): si el "
                    f"archivo ya existe, bind() falla con EADDRINUSE",
                    (second.process.stderr.read().decode(errors="replace")
                     if second.process.stderr else ""),
                )
            else:
                with second.connect() as c:
                    r = c.request("GET /hola.txt")
                expect(
                    r.body == read_fixture("hola.txt"),
                    f"arranca aunque haya quedado un socket viejo tirado "
                    f"(unlink antes del bind; el archivo {'quedó' if existed else 'no quedó'})",
                    "arrancó sobre un socket viejo pero no sirve bien",
                )
        finally:
            second.close()
    end_section()

# ---------------------------------------------------------------------
if run_section("servidor-errores"):
    section("Servidor: pedidos que no se pueden servir")
    srv = start_server("servidor-errores")
    if srv:
        CASES = [
            ("GET /no-existe.txt", "HTTP/1.1 404 Not Found", "archivo inexistente"),
            ("GET /sub", "HTTP/1.1 404 Not Found", "una carpeta no es un archivo"),
            ("hola", "HTTP/1.1 400 Bad Request", "línea de una sola palabra"),
            ("POST /hola.txt", "HTTP/1.1 405 Method Not Allowed", "método no soportado"),
            ("GET", "HTTP/1.1 400 Bad Request", "GET sin ruta"),
            ("GET hola.txt", "HTTP/1.1 400 Bad Request", "ruta sin / inicial"),
            ("GET  /hola.txt", "HTTP/1.1 400 Bad Request", "un espacio de más entre el verbo y la ruta"),
            ("POST hola.txt", "HTTP/1.1 400 Bad Request", "la forma se valida antes que el método"),
        ]
        with srv:
            for request_line, expected, reason in CASES:
                try:
                    with srv.connect() as c:
                        r = c.request(request_line)
                    expect(
                        r.status == expected,
                        f"{request_line!r} -> {expected} ({reason})",
                        f"{request_line!r} contestó {r.status!r}, esperaba {expected!r} "
                        f"({reason})",
                    )
                except (EOFError, OSError) as e:
                    fail(f"{request_line!r}: el servidor cortó la conexión en vez de "
                         f"contestar {expected} ({e})")

            # Un error no puede dejar la conexión inservible.
            try:
                with srv.connect() as c:
                    r1 = c.request("GET /no-existe.txt")
                    r2 = c.request("GET /hola.txt")
                expect(
                    r1.status.endswith("404 Not Found")
                    and r2.status.endswith("200 OK")
                    and r2.body == read_fixture("hola.txt"),
                    "después de un 404 la misma conexión sigue sirviendo",
                    f"después de un 404 el pedido siguiente dio {r2.status!r}",
                )
            except (EOFError, OSError) as e:
                fail(f"el servidor cerró la conexión después de un 404 ({e})")
    end_section()

# ---------------------------------------------------------------------
if run_section("servidor-keepalive"):
    section("Servidor: la conexión queda viva (keep-alive)")
    srv = start_server("servidor-keepalive")
    if srv:
        with srv:
            hello = read_fixture("hola.txt")
            try:
                with srv.connect() as c:
                    three = [c.request("GET /hola.txt") for _ in range(3)]
                expect(
                    all(r.status.endswith("200 OK") and r.body == hello
                        for r in three),
                    "tres GET seguidos sobre la misma conexión",
                    "los tres GET sobre una misma conexión no dieron todos 200",
                    "\n".join(repr(r) for r in three),
                )
            except (EOFError, OSError) as e:
                fail(f"la conexión se cortó durante tres GET seguidos ({e})")

            try:
                with srv.connect() as c:
                    twenty = [c.request("GET /poema.txt") for _ in range(20)]
                poem = read_fixture("poema.txt")
                expect(
                    all(r.body == poem for r in twenty),
                    "20 GET sobre una única conexión, sin desalinearse",
                    "en 20 GET seguidos alguna respuesta salió mal: probablemente "
                    "el parseo se desalinea al leer más bytes de los que dice "
                    "Content-Length",
                )
            except (EOFError, OSError) as e:
                fail(f"la conexión se cortó durante 20 GET seguidos ({e})")

            # Sin "Connection: close" el servidor NO puede cerrar.
            try:
                with srv.connect() as c:
                    c.request("GET /hola.txt")
                    expect(
                        not c.saw_eof(1.5),
                        "sin 'Connection: close' el servidor deja la conexión abierta",
                        "el servidor cerró la conexión después de un GET; el "
                        "keep-alive es lo que obliga a forkear por cliente",
                    )
            except (EOFError, OSError) as e:
                fail(f"el servidor cerró la conexión después de un solo GET ({e})")

            # Y con "Connection: close" tiene que despedirse y cerrar.
            try:
                with srv.connect() as c:
                    r = c.request("Connection: close")
                    said_bye = r.status == "Connection: close"
                    closed_it = c.saw_eof(3)
                expect(
                    said_bye and closed_it,
                    "'Connection: close' se contesta y se cierra el socket",
                    f"con 'Connection: close' el servidor contestó {r.status!r} "
                    f"y {'cerró' if closed_it else 'NO cerró'} el socket",
                )
            except (EOFError, OSError) as e:
                fail(f"'Connection: close' cortó la conexión sin contestar ({e})")
    end_section()

# ---------------------------------------------------------------------
if run_section("servidor-concurrencia"):
    section("Servidor: muchos clientes a la vez")
    srv = start_server("servidor-concurrencia")
    if srv:
        with srv:
            hello = read_fixture("hola.txt")
            poem = read_fixture("poema.txt")

            # 10 clientes en paralelo, 5 GET cada uno.
            errors = []
            def repeat_client(i):
                try:
                    with srv.connect() as c:
                        for j in range(5):
                            r = c.request("GET /poema.txt")
                            if r.body != poem:
                                errors.append(f"cliente {i}, pedido {j}: "
                                              f"cuerpo incorrecto")
                except Exception as e:      # noqa: BLE001
                    errors.append(f"cliente {i}: {e}")

            threads = [threading.Thread(target=repeat_client, args=(i,))
                       for i in range(10)]
            for h in threads:
                h.start()
            for h in threads:
                h.join(timeout=TIMEOUT * 3)
            expect(
                not errors,
                "10 clientes en paralelo con 5 pedidos cada uno: los 50 correctos",
                "hubo problemas con 10 clientes en paralelo:",
                "\n".join(errors[:10]),
            )

            # 50 conectados al mismo tiempo.
            connections, errors = [], []
            try:
                for _ in range(50):
                    connections.append(srv.connect())
                def one_get(c, i):
                    try:
                        if c.request("GET /hola.txt").body != hello:
                            errors.append(f"conexión {i}: cuerpo incorrecto")
                    except Exception as e:      # noqa: BLE001
                        errors.append(f"conexión {i}: {e}")
                threads = [threading.Thread(target=one_get, args=(c, i))
                           for i, c in enumerate(connections)]
                for h in threads:
                    h.start()
                for h in threads:
                    h.join(timeout=TIMEOUT * 3)
                expect(
                    not errors,
                    "50 clientes conectados a la vez, todos atendidos",
                    "con 50 clientes conectados a la vez hubo problemas:",
                    "\n".join(errors[:10]),
                )
            finally:
                for c in connections:
                    c.close()

            # El test que separa "forkea" de "atiende de a uno": un cliente
            # que se conecta y no dice nada no puede frenar a los demás.
            slow = srv.connect()
            try:
                start_time = time.monotonic()
                with srv.connect() as fast:
                    r = fast.request("GET /hola.txt")
                elapsed = time.monotonic() - start_time
                expect(
                    r.body == hello and elapsed < 3 * lib.TIMEOUT_FACTOR,
                    f"un cliente colgado no frena a los demás (el otro tardó "
                    f"{elapsed:.2f}s)",
                    "mientras un cliente está conectado sin mandar nada, los demás "
                    "no reciben respuesta: el servidor está atendiendo de a uno. "
                    "Hay que forkear después de cada accept()",
                )
            except (EOFError, OSError, socket.timeout) as e:
                fail("mientras un cliente está conectado sin mandar nada, los "
                     f"demás no pueden ser atendidos ({e}). Hay que forkear "
                     f"después de cada accept()")
            finally:
                slow.close()

            # Un proceso hijo por cliente conectado. Antes hay que esperar
            # a que terminen los hijos de los clientes anteriores, si no
            # los contamos de más.
            lib.wait_until(lambda: not srv.children(), seconds=10)
            connections = [srv.connect() for _ in range(5)]
            children = []
            try:
                lib.wait_until(lambda: len(srv.children()) == 5, seconds=8)
                # Nos anotamos los pids mientras los hijos están vivos: así
                # la espera de más abajo es sobre ESTOS procesos y no se
                # puede cumplir sola porque todavía no exista ninguno.
                children = srv.children()
                expect(
                    len(children) == 5,
                    "con 5 clientes conectados hay 5 procesos hijo atendiéndolos",
                    f"con 5 clientes conectados el servidor tiene "
                    f"{len(children)} hijos, esperaba 5",
                )
            finally:
                for c in connections:
                    c.close()
            expect(
                lib.wait_until(lambda: not lib.running_among(children), seconds=10),
                "al irse los 5 clientes, los 5 hijos terminan",
                f"después de cerrar los 5 clientes quedaron "
                f"{lib.running_among(children)} hijos vivos",
            )
    end_section()

# ---------------------------------------------------------------------
if run_section("servidor-fds"):
    section("Servidor: file descriptors")
    srv = start_server("servidor-fds")
    if srv:
        with srv:
            # Con nadie conectado, al padre solo le corresponde el socket
            # de escucha.
            #
            # Antes hay que dejar que se asiente: para saber que el
            # servidor ya está escuchando nos conectamos una vez, y esa
            # conexión de sondeo tarda un instante en terminar de
            # cerrarse de los dos lados.
            def only_listening_socket():
                return not srv.children() and len(lib.extra_fds(srv.pid)) == 1

            lib.wait_until(only_listening_socket, seconds=10)
            base = lib.extra_fds(srv.pid)
            expect(
                len(base) == 1 and lib.fd_type(next(iter(base.values()))) == "socket",
                "sin clientes, el servidor tiene abierto solo el socket de escucha",
                f"sin clientes conectados el servidor tiene {len(base)} fds "
                f"abiertos además de stdin/stdout/stderr, esperaba 1 (el socket "
                f"de escucha)",
                "\n".join(f"fd {n} -> {d}" for n, d in sorted(base.items())),
            )

            with srv.connect() as c:
                c.request("GET /hola.txt")
                lib.wait_until(lambda: len(srv.children()) == 1, seconds=8)
                children = srv.children()
                if len(children) != 1:
                    fail(f"esperaba 1 proceso hijo atendiendo al cliente, hay "
                         f"{len(children)}")
                else:
                    child_extra = lib.extra_fds(children[0])
                    expect(
                        len(child_extra) == 1,
                        "el hijo cierra el socket de escucha que heredó",
                        f"el hijo que atiende al cliente tiene {len(child_extra)} "
                        f"fds abiertos, esperaba 1 (el socket de ese cliente). "
                        f"O no cerró el socket de escucha que heredó (no lo "
                        f"necesita, él no acepta conexiones nuevas), o heredó "
                        f"sockets de otros clientes que el padre no cerró",
                        "\n".join(f"fd {n} -> {d}"
                                  for n, d in sorted(child_extra.items())),
                    )
                lib.wait_until(lambda: len(lib.extra_fds(srv.pid)) == 1,
                               seconds=5)
                parent_extra = lib.extra_fds(srv.pid)
                expect(
                    len(parent_extra) == 1,
                    "el padre cierra su copia del socket del cliente",
                    "con un cliente conectado el padre tiene más de un fd abierto: "
                    "no cerró su copia del socket del cliente después de forkear",
                    "\n".join(f"fd {n} -> {d}"
                              for n, d in sorted(parent_extra.items())),
                )

            # Y que no se le vayan acumulando con el uso: acá es donde se
            # nota el clásico olvido de cerrar el socket del cliente en el
            # padre, que en 50 conexiones deja 50 fds tirados.
            for _ in range(50):
                with srv.connect() as c:
                    c.request("GET /hola.txt")
            lib.wait_until(only_listening_socket, seconds=15)
            after = lib.extra_fds(srv.pid)
            expect(
                len(after) == 1,
                "después de 50 conexiones el servidor sigue con un solo fd abierto",
                f"después de 50 conexiones el servidor tiene {len(after)} fds "
                f"abiertos, esperaba 1: se le están fugando",
                "\n".join(f"fd {n} -> {d}" for n, d in sorted(after.items())),
            )
    end_section()

# ---------------------------------------------------------------------
if run_section("servidor-procesos"):
    section("Servidor: procesos y desconexiones bruscas")
    srv = start_server("servidor-procesos")
    if srv:
        with srv:
            hello = read_fixture("hola.txt")

            # Sin zombies: los hijos que terminaron hay que esperarlos.
            for _ in range(30):
                with srv.connect() as c:
                    c.request("GET /hola.txt")
            # Ojo con muestrear una sola vez: entre que un hijo termina y el
            # padre lo cosecha hay un instante en el que está en Z sin que
            # nadie haya hecho nada mal, y al cerrar el último cliente su
            # hijo ni siquiera terminó todavía. Así que esperamos a que no
            # quede NINGÚN hijo (un hijo sigue siéndolo mientras nadie lo
            # cosecha) y nos quedamos con la última muestra, sin volver a
            # mirar después.
            zombies = lib.zombies_of(srv.pid)
            deadline = time.monotonic() + 10 * lib.TIMEOUT_FACTOR
            while time.monotonic() < deadline:
                if not zombies and not lib.children_of(srv.pid):
                    break
                time.sleep(0.1)
                zombies = lib.zombies_of(srv.pid)
            expect(
                not zombies,
                "después de 30 conexiones no quedan hijos zombies",
                f"quedaron {len(zombies)} hijos en estado Z: hay que esperarlos "
                f"con waitpid (por ejemplo desde un handler de SIGCHLD)",
                str(zombies[:10]),
            )

            # Un cliente que se va de golpe (RST) no puede tumbar al servidor.
            c = srv.connect()
            c.request("GET /hola.txt")
            # Si contestó, el hijo que lo atiende ya existe: lo anotamos
            # antes de cortar para después esperar a que termine ESE, y no
            # a que no quede ningún hijo (un rezagado de otra conexión
            # haría fallar un chequeo que no habla de él).
            children = srv.children()
            c.close_abruptly()
            time.sleep(0.5)
            try:
                with srv.connect() as other:
                    r = other.request("GET /hola.txt")
                expect(
                    r.body == hello,
                    "una desconexión abrupta del cliente no afecta al servidor",
                    "después de que un cliente se desconectó de golpe, el servidor "
                    "dejó de atender bien",
                )
            except (EOFError, OSError) as e:
                fail(f"el servidor dejó de andar después de una desconexión "
                     f"abrupta ({e})")
            expect(
                lib.wait_until(lambda: not lib.running_among(children), seconds=10),
                "y el hijo que lo atendía termina",
                f"quedó vivo el hijo {lib.running_among(children)} después de que "
                f"su cliente se desconectó de golpe",
            )

            # SIGPIPE: pedir un archivo grande y cortar sin leerlo.
            c = srv.connect()
            c.send("GET /grande.txt\n")
            time.sleep(0.2)
            c.close_abruptly()
            time.sleep(0.5)
            expect(
                srv.is_alive(),
                "el servidor no muere por SIGPIPE al escribir a un cliente que se fue",
                "el servidor se murió cuando un cliente cortó en medio de una "
                "transferencia. Es el SIGPIPE de send(): hay que ignorarlo con "
                "signal(SIGPIPE, SIG_IGN)",
            )
            if srv.is_alive():
                try:
                    with srv.connect() as other:
                        expect(
                            other.request("GET /hola.txt").body == hello,
                            "y sigue atendiendo clientes nuevos",
                            "el servidor sigue vivo pero ya no atiende bien",
                        )
                except (EOFError, OSError) as e:
                    fail(f"el servidor sigue vivo pero no atiende más ({e})")

            # Y al bajarlo, no queda nadie dando vueltas.
            watcher = lib.Watcher(srv.pid)
            watcher.sample()
            srv.process.terminate()
            try:
                srv.process.wait(timeout=5 * lib.TIMEOUT_FACTOR)
            except subprocess.TimeoutExpired:
                pass
            time.sleep(0.5)
            expect(
                not watcher.survivors(),
                "al bajar el servidor no queda ningún hijo huérfano",
                f"después de bajar el servidor quedaron vivos "
                f"{watcher.survivors()}",
            )
    end_section()

# ---------------------------------------------------------------------
if run_section("servidor-seguridad"):
    section("Servidor: no se puede salir de public/")
    srv = start_server("servidor-seguridad")
    if srv:
        with srv:
            secret = b"# SSOO - Taller de IPC"
            CASES = [
                ("GET /../Makefile", ("403", "404")),
                ("GET /sub/../../Makefile", ("403", "404")),
                ("GET /../../etc/passwd", ("403", "404")),
                ("GET /..%2fMakefile", ("403", "404")),
                ("GET //etc/passwd", ("403", "404")),
            ]
            for request_line, acceptable in CASES:
                try:
                    with srv.connect() as c:
                        r = c.request(request_line)
                except (EOFError, OSError) as e:
                    fail(f"{request_line!r}: el servidor cortó la conexión ({e})")
                    continue
                code_ok = any(code in r.status for code in acceptable)
                if not code_ok:
                    fail(f"{request_line!r} contestó {r.status!r}, esperaba un "
                         f"{' o '.join(acceptable)}")
                elif secret in r.body or b"root:" in r.body:
                    fail(f"{request_line!r} contestó {r.status!r} pero igual devolvió "
                         f"contenido de afuera de public/",
                         r.body[:200].decode(errors="replace"))
                else:
                    ok(f"{request_line!r} -> {r.status}, sin filtrar nada")
    end_section()

# ---------------------------------------------------------------------
if run_section("cliente"):
    section("Cliente: contra un servidor de referencia")

    hello = b"hola mundo\n"
    # Un cuerpo que ADENTRO tiene algo que parece una línea de estado: si
    # el cliente no cuenta los bytes del Content-Length y se guía por el
    # texto, se confunde acá.
    tricky = b"HTTP/1.1 200 OK\nContent-Length: 999\n\nesto es parte del cuerpo\n"
    big_file = read_fixture("grande.txt")

    FILES = {"/hola.txt": hello, "/tramposo.txt": tricky, "/grande.txt": big_file}

    with ReferenceServer(FILES) as ref:
        res = run_client(ref.path, ["GET /hola.txt", "Connection: close"])
        expect(
            "HTTP/1.1 200 OK" in res.out and "hola mundo" in res.out,
            "un GET: muestra la línea de estado y el cuerpo",
            "el cliente no mostró bien la respuesta de un GET",
            f"stdout: {res.out!r}\nstderr: {res.err!r}",
        )

        res = run_client(ref.path,
                             ["GET /no-existe.txt", "GET /hola.txt",
                              "Connection: close"])
        expect(
            "404" in res.out and "hola mundo" in res.out,
            "después de un 404 sigue aceptando comandos",
            "el cliente no se recupera de un 404",
            f"stdout: {res.out!r}",
        )

        res = run_client(ref.path,
                             ["GET /tramposo.txt", "GET /hola.txt",
                              "Connection: close"])
        expect(
            tricky.decode() in res.out and "hola mundo" in res.out,
            "lee exactamente los bytes de Content-Length, sin dejarse engañar "
            "por el contenido",
            "el cliente se desalineó con un cuerpo que adentro parece una "
            "respuesta. Hay que leer exactamente Content-Length bytes, no "
            "buscar texto",
            f"stdout: {res.out!r}",
        )

        res = run_client(ref.path, ["GET /grande.txt", "Connection: close"],
                         seconds=40)
        body = res.out.encode(errors="replace")
        expect(
            big_file in body,
            f"recibe entero un cuerpo de {len(big_file)} bytes",
            "el cliente no recibió entero el archivo grande",
            f"esperaba {len(big_file)} bytes de cuerpo, stdout trajo {len(body)}",
        )

        res = run_client(ref.path, ["Connection: close"])
        expect(
            res.rc == 0 and "Connection: close" in res.out,
            "'Connection: close' cierra el cliente prolijamente (rc=0)",
            f"con 'Connection: close' el cliente terminó con rc={res.rc}",
            f"stdout: {res.out!r}",
        )

    # El cuerpo llega de a pedacitos: un solo recv() no alcanza.
    with ReferenceServer(FILES, chunk=1024, delay=0.002) as ref:
        res = run_client(ref.path, ["GET /grande.txt", "Connection: close"],
                         seconds=60)
        expect(
            big_file in res.out.encode(errors="replace"),
            "reensambla un cuerpo que llega en trozos de 1 KB con pausas",
            "el cliente no reensambla un cuerpo que llega de a pedazos: recv() "
            "puede devolver menos de lo pedido, hay que insistir en un loop",
        )

    # El servidor corta de golpe: el cliente tiene que terminar, no colgarse.
    with ReferenceServer(FILES, hang_up=True) as ref:
        res = run_client(ref.path, ["GET /hola.txt"], seconds=15)
        expect(
            not res.timed_out,
            "si el servidor corta de golpe, el cliente termina en vez de colgarse",
            "el cliente se queda colgado cuando el servidor corta la conexión",
        )

    # Un socket que no existe: error claro y exit code distinto de cero.
    res = run_client(lib.socket_path("nadie"), ["GET /hola.txt"], seconds=15)
    expect(
        res.rc != 0 and res.err.strip() != "",
        f"si el socket no existe avisa por stderr y sale con rc={res.rc}",
        "conectarse a un socket que no existe tiene que avisar por stderr y "
        "terminar con exit code distinto de 0",
        f"rc={res.rc}\nstdout: {res.out!r}\nstderr: {res.err!r}",
    )

    # El prompt, igual que en la mini shell: solo si hay terminal.
    with ReferenceServer(FILES) as ref:
        res = run_client(ref.path, ["GET /hola.txt", "Connection: close"])
        clean = res.out
        pty = lib.PtySession(BIN_CLIENTE, ref.path)
        try:
            output = pty.read(2.0)
            expect(
                output.strip() != "" and output.strip() not in clean,
                f"con terminal muestra un prompt ({output.strip()!r})",
                "el cliente no muestra prompt cuando lo corrés desde una terminal",
                f"con terminal leí {output!r}; con pipe la salida fue {clean!r}",
            )
        finally:
            pty.close()
    end_section()

# ---------------------------------------------------------------------
if run_section("interop"):
    section("El cliente y el servidor del alumno hablando entre sí")
    srv = start_server("interop")
    if srv:
        with srv:
            commands = ["GET /hola.txt", "GET /poema.txt", "GET /no-existe.txt",
                        "GET /sub/anidado.txt", "GET /grande.txt",
                        "Connection: close"]
            watcher = lib.Watcher(srv.pid)
            res = run_client(srv.path, commands, seconds=60)
            watcher.sample()

            problems = []
            if res.timed_out:
                problems.append("la sesión se colgó")
            for name in ("hola.txt", "poema.txt", "sub/anidado.txt", "grande.txt"):
                if read_fixture(name).decode(errors="replace") not in res.out:
                    problems.append(f"falta el contenido de {name}")
            if "404" not in res.out:
                problems.append("no apareció el 404 del archivo inexistente")
            if res.rc != 0:
                problems.append(f"el cliente terminó con rc={res.rc}")

            expect(
                not problems,
                "sesión completa de 5 pedidos más la despedida, punta a punta",
                "la sesión punta a punta entre tu cliente y tu servidor falló:",
                "\n".join(problems) + f"\nstderr: {res.err[:400]!r}",
            )

            # Nos quedamos con la última muestra del loop en vez de sacar
            # una nueva para el expect: entre una y otra el hijo puede
            # pasar a Z por un instante sin que nadie haya hecho nada mal.
            # children_of() ya incluye a los zombies, así que con esto
            # alcanza para las dos cosas.
            children = srv.children()
            deadline = time.monotonic() + 10 * lib.TIMEOUT_FACTOR
            while children and time.monotonic() < deadline:
                time.sleep(0.1)
                children = srv.children()
            expect(
                not children,
                "y no quedan hijos vivos ni zombies después de la sesión",
                f"quedaron hijos sin cosechar: {children}",
            )
    end_section()

# ---------------------------------------------------------------------
if run_section("huerfanos"):
    lib.orphans_section(BIN_SERVIDOR, BIN_CLIENTE)

lib.summary()

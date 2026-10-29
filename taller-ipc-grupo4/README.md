# Taller de IPC: pipes y sockets

> El taller se compila y se ejecuta adentro de una VM Linux que levanta el
> propio `make`. Si todavía no la preparaste, arrancá por **[VM.md](https://github.com/SSOO-Exactas-2026-2C/taller-tools/blob/main/VM.md)**:
> ahí está el setup (`make install`, `make start-vm`, `make shell`) y los
> comandos generales del entorno.

## Ejercicio 1: Mini shell

### Enunciado

Implementar en `src/ej1/minishell.c` un shell mínimo que abra un prompt, lea
comandos de a una línea y los ejecute. Cada línea puede ser:

- El nombre de un programa con sus argumentos. Por ejemplo: `ls -al`
- Varios programas comunicados por pipes `|`. Por ejemplo: `ls -al | wc -l`

Se usa así:

```console
$ make run-minishell
minishell> seq 1 10 | tail -n 3 | wc -l
3
minishell> echo chau
chau
minishell>
```

Tu mini shell tiene que:

- Mostrar el prompt `minishell> ` **solo si la entrada estándar es una
  terminal** (`isatty`). Si le pasás los comandos por un pipe o un archivo, la
  salida tiene que quedar limpia, igual que hace `bash`.
- Soportar pipelines de uno o más comandos. Ojo con el caso de **un solo
  comando**.
- **Esperar a que terminen todos los procesos** del pipeline antes de volver a
  mostrar el prompt.
- **No morirse** si el comando no existe: avisá por salida de error y seguí
  aceptando comandos.
- Terminar con Ctrl-D (fin de archivo) y morir con Ctrl-C.

El parser ya está resuelto en `src/ej1/parser.c`: te devuelve el pipeline
partido en comandos, cada uno con sus argumentos en un arreglo terminado en
`NULL`, listo para `execvp`. Leelo antes de arrancar.

El template ya trae el `main()` con el prompt y el parseo de la línea: lo que
falta es armar el pipeline y ejecutar cada comando.

### Aclaraciones

- No se puede usar la función `system` para resolver el ejercicio.

### Validación de tu solución

```bash
make test-ej1
```

Los tests prueban pipelines de uno a cinco comandos, chequean con `/proc` que no
te hayan quedado file descriptors abiertos, verifican que esperes a todos los
comandos y que no queden zombies, y levantan una terminal de verdad para probar
el prompt, Ctrl-C y Ctrl-D.

---

## Ejercicio 2: One ring to rule them all

### Enunciado

Implementar en `src/ej2/anillo.c` un programa que arme un esquema de
comunicación en forma de anillo entre sus procesos hijo (al menos tres) y
ejecute el siguiente protocolo:

- Cada proceso hijo se comunica con exactamente dos procesos: su antecesor y su
  sucesor (visto desde el orden de creación). Recibe un mensaje del antecesor y
  le manda un mensaje al sucesor. Esa comunicación se hace con `pipes`.
- Para arrancar, el padre le manda el valor inicial `C` al hijo indicado por
  `S`. Ese es el **proceso distinguido**, y es el único que usa la cota `P`.
- Cada vez que un hijo recibe un mensaje, incrementa el valor en uno y se lo
  manda a su sucesor. El proceso distinguido también incrementa el mensaje
  inicial antes de mandarlo por primera vez. Cuando el valor completa una
  vuelta, el distinguido arranca otra ronda si el número que recibió todavía es
  menor que `P`.
- Cuando el proceso distinguido recibe de su antecesor un valor **mayor o igual
  que `P`**, no arranca una ronda nueva: le manda ese último valor al padre,
  que lo muestra por salida estándar. Después el distinguido termina, y eso
  inicia la terminación en cascada del resto de los procesos del anillo.
- El padre recién termina cuando terminaron todos los procesos del anillo.

El programa recibe cuatro parámetros. Se corre así:

```bash
make run-anillo N=5 S=1 C=0 P=20
```

donde:

- **`N`** es la cantidad de procesos del anillo, como mínimo 3.
- **`S`** es el número del hijo que arranca la comunicación, con $1 \leq S \leq N$.
- **`C`** es el valor del mensaje inicial.
- **`P`** es la cota que usa únicamente el proceso distinguido, con $P > C$.

En el código los vas a recibir por `argv`, en ese mismo orden.

### Formato de salida

Las pruebas verifican estas dos líneas, así que respetá el formato al pie de la
letra:

```
HIJO <i> PID <pid> NUM <valor>
PADRE RESULTADO <valor>
```

Cada hijo imprime su línea **al recibir el número, antes de reenviarlo**, y el
padre imprime el resultado al final. Los hijos se numeran de 1 a `N`.

Acordate de hacer `fflush(stdout)` después de cada línea: cuando la salida va a
un pipe en vez de a la terminal, se guarda en un buffer y sale toda junta
recién al terminar el proceso, así que sin el `fflush` la traza sale
desordenada.

Por ejemplo, `make run-anillo N=3 S=1 C=0 P=4` debe imprimir así (los PID
obviamente van a ser distintos):

```
HIJO 1 PID 4021 NUM 0
HIJO 2 PID 4022 NUM 1
HIJO 3 PID 4023 NUM 2
HIJO 1 PID 4021 NUM 3
HIJO 2 PID 4022 NUM 4
HIJO 3 PID 4023 NUM 5
HIJO 1 PID 4021 NUM 6
PADRE RESULTADO 6
```

### Aclaraciones

- No está permitido que el padre termine a los hijos con `kill()` ni con
  ninguna otra señal o mensaje "especial" enviado por el anillo.

### Validación de tu solución

```bash
make test-ej2
```

La salida del anillo es completamente determinístico a partir de los argumentos.
Los tests comparan el recorrido entero del número por el anillo, no solo el
resultado final. Además cuentan los pipes que creás, chequean con `/proc` que
hayas cerrado los que no usás, verifican que el padre termine último y que no 
mandes ninguna otra señal.

---

## Ejercicio 3: Servidor y cliente HTTP

### Enunciado

Implementar un servidor y un cliente que hablen un protocolo inspirado en
HTTP/1.1, bastante más chico, sobre un **socket UNIX**. Los dos programas se
entregan:

- `src/ej3/servidor.c`, que se corre con `make run-servidor`
- `src/ej3/cliente.c`, que se corre con `make run-cliente`

Los dos reciben por `argv` la ruta del socket. `make` les pasa
`/tmp/taller-ipc.sock`; si querés otra, `make run-servidor SOCK=/tmp/otra.sock`.

Un socket UNIX se identifica por una ruta del sistema de archivos, en vez de por
una dirección IP y un puerto. Es el mecanismo que se usa cuando los dos procesos
están en la misma máquina: no hay que resolver nombres ni pasar por la pila de
red.

> **Ojo con dónde vive el socket.** Tiene que estar en `/tmp`, **no** en la
> carpeta del taller: esa carpeta se comparte con la VM por 9p, que no soporta
> crear sockets, y el `bind` falla con *Operation not supported*. Además la ruta
> entra en `sun_path`, que son 108 bytes, así que no puede ser muy larga.

### El protocolo

El cliente manda **una única línea de texto terminada en `\n`**. No hay headers
del lado del cliente. El servidor contesta con una línea de estado, un
`Content-Length`, una línea en blanco y el cuerpo:

```
-> GET /hola.txt
<- HTTP/1.1 200 OK
<- Content-Length: 11
<-
<- hola mundo
```

Si el archivo no existe:

```
-> GET /no-existe.txt
<- HTTP/1.1 404 Not Found
<- Content-Length: 0
<-
```

Si la ruta intenta salirse de `public/`:

```
-> GET /../Makefile
<- HTTP/1.1 403 Forbidden
<- Content-Length: 0
<-
```

Si la línea no se entiende (no son exactamente dos partes separadas por un
espacio, o la ruta no empieza con `/`):

```
-> hola que tal
<- HTTP/1.1 400 Bad Request
<- Content-Length: 0
<-
```

Y si la línea se entiende pero el método no es `GET`, que es el único que este
servidor sabe contestar:

```
-> POST /hola.txt
<- HTTP/1.1 405 Method Not Allowed
<- Content-Length: 0
<-
```

Fijate el orden: primero se valida la **forma** de la línea y recién después el
**método**, igual que en HTTP. Por eso `POST hola.txt` es un 400 y no un 405.

Para cortar la conexión, el cliente manda `Connection: close`. Ojo que acá eso
**no es un header**, es un mensaje en sí mismo: el servidor contesta lo mismo y
cierra el socket.

```
-> Connection: close
<- Connection: close        (y cierra el socket)
```

### El servidor

- Sirve archivos de texto plano de la carpeta `public/`, subcarpetas incluidas.
- **La conexión queda viva por defecto** (keep-alive): el mismo cliente puede
  mandar varios pedidos uno atrás del otro, y la conexión se cierra recién con
  `Connection: close` o cuando el cliente se va.
- Eso es justamente lo que obliga a que el servidor pueda **comunicarse con
  varios clientes al mismo tiempo**: mientras un cliente tiene la conexión
  abierta sin mandar nada, los demás tienen que poder ser atendidos igual.
- **No está permitido resolverlo con `select()`, `poll()` ni `epoll()`.**
- Cuidado con los **file descriptors**: cada conexión abre uno nuevo, y todo el
  que deje de hacer falta hay que cerrarlo. Si se te escapan, el servidor se
  queda sin ninguno y deja de aceptar conexiones.
- Si tu solución crea procesos, **hay que esperar a los que terminan** (con
  `waitpid`, por ejemplo desde un handler de `SIGCHLD`) para no llenar la tabla
  de procesos de zombies.
- Si el cliente se desconecta de golpe, el servidor tiene que soltar esa
  conexión y seguir aceptando las demás. Cuidado con `SIGPIPE`: si escribís a
  un socket que el otro lado ya cerró, por defecto la señal **te mata el
  proceso**.
- Validá que la ruta pedida no contenga `..`.
- Para pensar: ¿Por qué `Content-Length`?

> **Nota:** el motivo de prohibir `select()` y `poll()` es que este taller es de
> procesos. Que quede claro igual que son herramientas totalmente válidas: con
> ellas un solo proceso puede vigilar muchos sockets a la vez y atenderlos a
> todos, que es como están hechos los servidores de verdad cuando tienen que
> manejar miles de clientes.

### El cliente

- Lee líneas de la entrada estándar y se las manda tal cual al servidor.
- Muestra el prompt solo si la entrada es una terminal, igual que la mini shell
  del ejercicio 1.
- Al recibir la respuesta, tiene que leer **exactamente** los bytes que dice
  `Content-Length`, ni uno más. Acordate de que `recv()` puede devolver **menos
  bytes de los que le pediste**: los datos van llegando por la red de a chunks,
  así que hay que insistir en un loop hasta juntar todo.
- Termina con Ctrl-D, con `Connection: close`, o si el servidor cierra.
- Si el socket no existe o no hay nadie escuchando, avisá por salida de error y
  terminá con un exit code distinto de cero.

### Probarlo a mano

El servidor y el cliente corren los dos adentro de la VM, así que necesitás dos
terminales. En una:

```bash
make run-servidor
```

Y en la otra:

```bash
make run-cliente
```

**Probá varios clientes al mismo tiempo**: abrí tres o cuatro terminales con
`make run-cliente` y verificá que todas se conectan y reciben respuesta. Si
tu servidor atiende de a uno, el primero que se conecte va a dejar colgados
a los demás.

También podés hablarle al servidor a mano con `nc`, que es lo más cómodo para
mandarle cosas mal formadas y ver qué contesta:

```bash
make shell
nc -U /tmp/taller-ipc.sock
GET /hola.txt
```

El `-U` es lo que le dice a `nc` que del otro lado hay un socket UNIX y no una
dirección de red.

### Validación de tu solución

```bash
make test-ej3
```

Los tests prueban el servidor contra un cliente propio (para poder mandarle
pedidos mal formados y controlar los tiempos), el cliente contra un servidor de
referencia (así un servidor roto no tapa un cliente roto), y al final los ponen
a los dos a hablar entre sí. Chequean 50 clientes simultáneos, que un cliente
colgado no frene a los demás, que no se filtren file descriptors ni queden
procesos zombies, el `SIGPIPE` y que no se pueda salir de `public/`.

---

## Comandos del taller

| Comando | Qué hace |
|---|---|
| `make build-ej1` | Compila tu `src/ej1/` |
| `make run-minishell` | Abre tu mini shell interactiva |
| `make strace-ej1` | Traza las syscalls de tu mini shell |
| `make test-ej1` | Tests del ejercicio 1 |
| `make build-ej2` | Compila tu `src/ej2/anillo.c` |
| `make run-anillo N=5 S=1 C=0 P=20` | Corre tu anillo |
| `make strace-ej2 N=5 S=1 C=0 P=20` | Traza tu anillo |
| `make test-ej2` | Tests del ejercicio 2 |
| `make build-ej3` | Compila tu `src/ej3/` |
| `make run-servidor` | Levanta tu servidor |
| `make run-cliente` | Corre tu cliente |
| `make strace-ej3` | Traza tu servidor |
| `make test-ej3` | Tests del ejercicio 3 |

---

## Entrega

### Ejercicio 1

- `src/ej1/minishell.c` — La mini shell.

### Ejercicio 2

- `src/ej2/anillo.c` — El anillo de procesos.

### Ejercicio 3

- `src/ej3/servidor.c` — El servidor.
- `src/ej3/cliente.c` — El cliente.

### Ejecución esperada

```bash
make run-minishell
make run-anillo N=5 S=2 C=0 P=20
make run-servidor               # y en otra terminal: make run-cliente
```

---

## Materiales provistos

- **`src/ej1/parser.c`** y **`src/ej1/parser.h`** — El parser de la línea de
  comandos de la mini shell, ya resuelto.
- **`public/`** — Los archivos que sirve el servidor del ejercicio 3.

---

## Recomendaciones

### Para todos los ejercicios

- **Cuidado con el buffer de `stdout`.** Cuando la salida va a una terminal se
  vacía en cada `\n`, pero cuando va a un pipe se acumula hasta el final. Si
  imprimís desde varios procesos, poné `fflush(stdout)`.
- Usá `make strace-ejN` cuando algo no cierre. Ver las syscalls en orden suele
  ser más rápido que llenar el código de `printf`.

### Para el ejercicio 1

- Probá el caso de un solo comando (sin ningún pipe) desde el principio: es el
  que más se olvida.

### Para el ejercicio 2

- Dibujá el anillo en papel antes de escribir nada. ¿De qué pipe lee el hijo
  `i`? ¿A cuál escribe?
- ¿Necesitás un pipe aparte para que el distinguido le hable al padre, o podés
  reusar uno del anillo? Pensá quién más podría leer ese dato.
- El padre tiene todos los pipes abiertos cuando arranca. ¿Hace falta un pipe
  extra para mandarle el valor inicial al distinguido?
- Arrancá con `n = 3` y una cota chica, que la traza entra en una pantalla.

### Para el ejercicio 3

- Empezá por un servidor que atienda **un solo** cliente y un solo pedido. Recién
  cuando eso ande, agregale el keep-alive, y al final la concurrencia.
- Leé la línea del pedido **byte a byte hasta el `\n`**. Si leés de a bloques
  grandes te vas a llevar parte del pedido siguiente, y ahí empieza el
  desastre.
- `recv()` puede devolver **menos bytes de los que le pediste**, así que va en
  un loop hasta juntar todo lo que anunció el `Content-Length`.
- Probá con `nc -U` antes de tener el cliente listo: así aislás los problemas
  del servidor de los del cliente.

---

## Debugging y herramientas útiles

Todo el taller se maneja con `make`: es lo que se encarga de compilar y de
correr las cosas adentro de la VM. La única excepción es cuando entrás vos
mismo a la VM con `make shell` (ver [VM.md](https://github.com/SSOO-Exactas-2026-2C/taller-tools/blob/main/VM.md)): ahí quedás en una terminal
parada en la carpeta del taller, con todo Linux disponible, y ahí sí invocás
los binarios de `bin/` a mano.

```bash
# Ver procesos vivos
ps -ef | grep anillo

# Ver procesos zombies
ps -ef | grep defunct

# Matar procesos colgados
pkill -f anillo

# Qué file descriptors tiene abiertos un proceso
lsof -p <pid>
ls -l /proc/<pid>/fd

# Quiénes son los hijos de un proceso
pgrep -P <pid>

# Trazas a medida
strace -f -e trace=%desc,%process ./bin/anillo 5 1 0 20
strace -f -e trace=%network ./bin/servidor /tmp/taller-ipc.sock

# Hablarle al servidor a mano
nc -U /tmp/taller-ipc.sock
```

---

## Preguntas frecuentes

**P: Mi pipeline se cuelga y no entiendo por qué.**
R: Preguntate quién está bloqueado y esperando qué. Si es alguien leyendo,
acordate de que un programa que lee "hasta el final del archivo" necesita que
alguien le avise que ese final llegó: ¿cuándo decide el kernel que un pipe se
terminó? Mirá `ls -l /proc/<pid>/fd` de cada proceso involucrado y contá.

**P: ¿Por qué mi anillo imprime todo desordenado?**
R: Por el buffer de `stdout`. Cuando la salida no va a una terminal sino a un
pipe o a un archivo —que es lo que hacen los tests para capturarla—
se acumula y sale toda junta recién al terminar el proceso. Poné
`fflush(stdout)` después de cada `printf`.

**P: ¿Cuántos pipes necesito para el anillo?**
R: Dibujalo en papel: un círculo con los hijos y, aparte, el padre. Ahora uní
con una flecha cada par de procesos que necesitan hablarse entre sí. Contá las
flechas: ahí está tu respuesta.

**P: ¿Qué señal manda Ctrl-D?**
R: Ninguna, y es una confusión muy común. Ctrl-D es el carácter de fin de
archivo de la terminal: hace que el `read()` que está esperando devuelva ya
mismo lo que haya en la línea. Si la línea está vacía devuelve 0 bytes, y eso
es exactamente lo que un programa ve como fin de archivo. Por eso, si escribís
algo y apretás Ctrl-D sin Enter, no se cierra nada: tenés que apretarlo con la
línea vacía. Los que sí mandan señales son Ctrl-C (`SIGINT`) y Ctrl-\
(`SIGQUIT`). Mirá `stty -a` y `man 3 termios`.

**P: Mi servidor se muere solo cuando cierro un cliente.**
R: Es `SIGPIPE`. Escribir a un socket que el otro lado ya cerró genera esa
señal, que por defecto termina el proceso. Ignorala con
`signal(SIGPIPE, SIG_IGN)` y manejá el `-1` con `EPIPE` que te devuelve
`send()`.

**P: Me quedan un montón de procesos `<defunct>`.**
R: Son zombies: hijos que ya terminaron pero que nadie esperó. Cada uno sigue
ocupando una entrada en la tabla de procesos. ¿Quién es el único que puede
esperarlos, y qué le quedó pendiente entregarle el hijo al terminar?

**P: Se me colgó todo, ¿cómo lo mato?**
R: `Ctrl+C` en la terminal. Si quedaron procesos dando vueltas adentro de la
VM: `make shell` y después `pkill -f anillo` (o el nombre que sea). En el peor
caso, `make stop-vm` se lleva todo puesto.

**P: ¿Puedo usar `sigaction()` en lugar de `signal()`?**
R: Sí, es incluso mejor: es más portable y más predecible.

Los problemas del entorno (la VM no arranca, falta qemu, etc.) están en
[VM.md](https://github.com/SSOO-Exactas-2026-2C/taller-tools/blob/main/VM.md).

---

## Referencias útiles

- **man 2 pipe**, **man 7 pipe** — Los pipes y sus propiedades (incluida la
  atomicidad de las escrituras chicas)
- **man 2 dup2**, **man 2 close**, **man 2 execvp**, **man 2 fork**,
  **man 2 wait**
- **man 2 socket**, **man 2 bind**, **man 2 listen**, **man 2 accept**,
  **man 2 connect**
- **man 7 unix** — Los sockets UNIX: `sockaddr_un`, el archivo que crea el
  `bind`, y por qué conviene borrarlo antes
- **man 2 send**, **man 2 recv** — Prestale atención a lo que devuelven
- **man 7 socket**, **man 3 termios**

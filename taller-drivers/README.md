# Taller de drivers

> El taller se compila y se ejecuta adentro de una VM Linux que levanta el
> propio `make`. Si todavía no la preparaste, arrancá por **[VM.md](https://github.com/SSOO-Exactas-2026-2C/taller-tools/blob/main/VM.md)**:
> ahí está el setup (`make install`, `make start-vm`, `make shell`) y los
> comandos generales del entorno.

## Ejercicio 1: Nulo (`/dev/nulo`)

### Enunciado

Implementar un módulo de kernel para el dispositivo `/dev/nulo` que
replique **exactamente** el comportamiento de `/dev/null`:

- Debe descartar toda la información que se escriba en él (`write` devuelve
  siempre la cantidad de bytes recibidos, como si los hubiera escrito).
- No debe devolver ningún carácter cuando se intente leer (`read` devuelve
  siempre 0 bytes, fin de archivo inmediato).

Completá los `TODO` de `src/nulo/nulo.c`: falta registrar `nulo_read` y
`nulo_write` en `nulo_operaciones`, y crear/destruir el character device
(`cdev`, la región de números major/minor y el nodo en `/dev`) en
`hello_init`/`hello_exit`.

### Compilar, cargar y probar

```bash
make build-nulo     # compila src/nulo/nulo.c -> src/nulo/nulo.ko
make load-nulo       # insmod: aparece /dev/nulo
make dmesg-nulo       # ver los printk de tu módulo
make unload-nulo      # rmmod
```

Mientras iterás sobre el código, `make reload-nulo` recompila, descarga la
versión vieja (si estaba cargada) y carga la nueva en un solo paso.

#### Validación de tu solución

```bash
make test-nulo
```

También podés usar `make test-ej1`, como en los talleres anteriores.

Esto carga el módulo, corre `tests/tests_nulo.py` (comparando `/dev/nulo`
contra el `/dev/null` real de la VM) y lo descarga al terminar, sea cual
sea el resultado. Nunca queda el módulo cargado después de correr los
tests.

Para explorar el dispositivo a mano:

```bash
make shell
echo "hola" > /dev/nulo
cat /dev/nulo    # no imprime nada, corta al instante
```

---

## Ejercicio 2: LED (`/dev/led`)

### Enunciado

Vamos a escribir el driver de un LED RGB "inteligente" conectado al puerto
paralelo de la máquina. El hardware real es mínimo: el puerto solo guarda
un byte, y usamos su bit 0 como el interruptor del LED (`1` prendido, `0`
apagado). El color y el brillo no existen en el hardware: los recuerda el
driver en memoria y los dibuja un visualizador en la terminal
(`src/led/led_terminal.py`).

Hay que implementar un módulo de kernel para el dispositivo `/dev/led`, de
**lectura y escritura**, con un único estado global compartido por todos
los procesos que lo abran (no un estado por cada apertura).

#### Protocolo

A diferencia de `/dev/nulo`, `/dev/led` **no se comunica vía texto plano**:
tanto `write` como `read` usan una misma estructura de **8 bytes**,
con estos campos, en este orden y sin padding:

| Campo | Representación | Tamaño |
|---|---|---|
| `status` | `0` apagado, `1` prendido | 1 byte |
| `color.r` | Rojo, de `0` a `255` | 1 byte |
| `color.g` | Verde, de `0` a `255` | 1 byte |
| `color.b` | Azul, de `0` a `255` | 1 byte |
| `brillo` | Float IEEE 754 de 32 bits entre `0.0` y `1.0` | 4 bytes |

En Python es `struct.Struct("<BBBBf")` (`<`: little-endian sin padding;
`B`: byte sin signo; `f`: float de 32 bits). En `src/led/led.c` ya está
declarada como `struct led_estado`.

#### Qué tiene que hacer el driver

**`write`** — cambiar el estado del LED:

- Una escritura de `0` bytes devuelve `0` y no cambia nada.
- Cualquier otro tamaño distinto de 8 falla con `-EINVAL`. Siempre se
  manda la estructura completa, incluso para apagar el LED (apagarlo no
  borra el color ni el brillo).
- Si `status` no es `0` ni `1`, o el brillo es negativo, mayor a `1.0`,
  infinito o NaN, falla con `-EINVAL`. **Un dato inválido no debe
  modificar el LED.**
- Si todo es válido: guarda color y brillo en memoria, escribe el estado
  en el puerto correspondiente y devuelve el tamaño escrito.
- Registra cada escritura válida con `printk`, con un
  formato parecido a:

  ```text
  led: LED ON, RGB(255, 80, 0), brillo=0.500
  ```

**`read`** — consultar el estado del LED:

- Devuelve la misma estructura de 8 bytes. El `status` se obtiene
  leyendo el bit 0 del puerto (el hardware es la fuente de
  verdad); el color y el brillo son los guardados en memoria, tal cual se
  recibieron (sin multiplicar el RGB por el brillo: eso lo hace el
  visualizador).
- Respeta `size` y `*offset`: se puede leer de a partes (por ejemplo, de
  a 1 byte), y una vez leídos los 8 bytes devuelve `0` (fin de archivo).
  Cada nueva apertura del dispositivo vuelve a empezar desde el byte 0.

**Carga y descarga del módulo:**

- Al cargar, crear `/dev/led` y dejar el LED **apagado**, con color verde
  `(0, 255, 0)` y brillo `1.0`.
- Al descargar, apagar el LED y destruir el dispositivo.

**En todo momento:**

- Si falla una copia entre espacio de usuario y kernel, devolver
  `-EFAULT`.
- Varios procesos pueden leer y escribir el LED a la vez: hay que
  sincronizar el acceso al estado compartido para que una lectura nunca
  devuelva campos mezclados de dos escrituras distintas.

#### El brillo es un `float`, pero en el kernel no hay `float`

El código del kernel no puede usar aritmética de punto flotante (ni `%f`
en `printk`). El driver nunca opera con el brillo como número: guarda sus
4 bytes tal cual (por eso el campo es `__le32` y no `float`) y lo valida
comparando sus bits como un entero. Pista: para floats positivos, el orden
de sus representaciones binarias como enteros coincide con el orden de los
números (y `1.0f` es `0x3f800000`). Cuidado con `-0.0` (`0x80000000`),
que es un cero válido.
Si quieren leer referencias al respecto pueden ir a: https://docs.kernel.org/core-api/floating-point.html

Para el `printk` ya te damos `brillo_milesimas`, que convierte los bits de
un brillo válido en milésimas redondeadas usando solo enteros.

Funciones útiles:

- `outb(valor, puerto)` / `inb(puerto)` (`<asm/io.h>`).
- `copy_from_user` / `copy_to_user` (`<linux/uaccess.h>`).
- `struct mutex`, `mutex_lock` y `mutex_unlock` (`<linux/mutex.h>`).
- `le32_to_cpu` / `cpu_to_le32` para interpretar y guardar el brillo.
- `printk` (`<linux/kernel.h>`).

Completá los `TODO` de `src/led/led.c`: falta implementar `led_read` y
`led_write`, registrarlas en `led_operaciones`, crear/destruir el
character device en `led_init`/`led_exit` (igual que en los otros
ejercicios) y agregar la sincronización que hace falta para el estado
compartido. Ya vienen dados el formato (`struct led_estado`), el estado
inicial y `brillo_milesimas`.

### Compilar, cargar y probar

Desde la raíz del taller, en tu máquina:

```bash
make build-led     # compila src/led/led.c dentro de la VM
make load-led      # compila y carga el módulo: aparece /dev/led
make dmesg-led     # muestra los mensajes del driver
make unload-led    # descarga el módulo
```

Mientras iterás, `make reload-led` recompila, descarga la versión vieja
(si estaba cargada) y carga la nueva en un solo paso.

Con el módulo cargado, ejecutá el visualizador:

```bash
make led-simulador
```

Corre dentro de la VM, pero muestra el LED en tu terminal local. En otra
terminal de tu máquina, desde la raíz del taller, podés cambiar el estado:

```bash
make led-encendido-blanco-brillante  # status=1, RGB(255,255,255), brillo=1
make led-apagado-blanco-brillante    # status=0, RGB(255,255,255), brillo=1
make led-encendido-rojo-intermedio   # status=1, RGB(255,0,0), brillo=0.5
make led-apagado-rojo-intermedio     # status=0, RGB(255,0,0), brillo=0.5
```

Para elegir otros valores, entrá a la VM con `make shell` y ejecutá desde
la carpeta compartida del taller:

```bash
sudo python3 src/led/led_terminal.py --device /dev/led --status 1 --color 255 80 0 --brillo 0.5
sudo python3 src/led/led_terminal.py --device /dev/led --status 0
```

El script conserva el color y el brillo actuales si no los indicás.
`echo 1 > /dev/led` no sirve: la interfaz recibe una estructura,
no texto. Por la misma razón, `cat /dev/led` devuelve bytes; para
inspeccionarlos dentro de la VM podés usar `sudo od -An -tx1 /dev/led`.

#### Validación de tu solución

```bash
make test-led
```

También podés usar `make test-ej2`, que ejecuta el mismo test.

Esto compila y carga el módulo, corre `tests/tests_led.py` y lo descarga
al terminar, incluso si fallan los tests. Las pruebas escriben estados y
leen `/dev/led` para verificar colores RGB, brillo, encendido/apagado,
lecturas parciales, fin de archivo y rechazo de datos inválidos sin
modificar el estado anterior. No escribas al LED desde otra terminal
mientras corren. También se incluyen al ejecutar `make test`.

---

## Ejercicio 3: Clave/Valor (`/dev/clave_valor`)

### Enunciado

Implementar un módulo de kernel para el dispositivo `/dev/clave_valor`, una
base de datos clave-valor simplificada: una tabla global de tamaño igual a
`CANTIDAD_CLAVES`, compartida por todos los procesos que
abran el dispositivo (no una nueva tabla por cada apertura). Sus operaciones son:

- `write` recibe, como texto, la clave (un entero entre `0` y
  `CANTIDAD_CLAVES - 1`) cuyo contenido hay que incrementar en 1. Si la clave no es un
  entero válido o está fuera de rango, se debe fallar con `-EINVAL`.
- `read` no usa ningún parámetro: siempre devuelve el valor del
  casillero que le corresponde al proceso que lo invoca, calculado a
  partir de su PID.
- Un proceso puede incrementar **cualquier** clave por `write`, pero solo
  puede leer de vuelta **el contenido del suyo**.
- Al ser una tabla global compartida, hay que tener cuidado con las races conditions.

Funciones útiles:

- `copy_from_user` / `copy_to_user` (`<linux/uaccess.h>`)
- `kstrtoint` (`<linux/kernel.h>`)
- `struct mutex` (`<linux/mutex.h>`)
- `current`: macro del kernel que da un puntero a la `struct task_struct`
  del thread que está ejecutando el código. Dentro de `read`, es el thread
  que hizo esa llamada.
- `task_tgid_nr(current)` (`<linux/sched.h>`): devuelve el PID del *grupo
  de threads* (thread group) del proceso que está ejecutando la syscall
  en este momento — es el mismo valor que ve ese proceso al llamar a
  `getpid()` desde espacio de usuario. No confundir con `current->pid`,
  que identifica al *thread* que está corriendo (dentro de un mismo
  proceso, dos threads tienen distinto `current->pid` pero el mismo
  `task_tgid_nr`); para este ejercicio hay que usar `task_tgid_nr`, así
  todos los threads de un mismo proceso comparten el mismo casillero.

Completá los `TODO` de `src/clave_valor/clave_valor.c`: falta implementar
`clave_valor_read` y `clave_valor_write`, registrarlas en
`clave_valor_operaciones`, crear/destruir el character device en
`clave_valor_init`/`clave_valor_exit` (igual que en los otros ejercicios),
y agregar la sincronización que hace falta para la tabla compartida.

### Compilar, cargar y probar

```bash
make build-clave_valor   # compila src/clave_valor/clave_valor.c
make load-clave_valor    # insmod: aparece /dev/clave_valor
make dmesg-clave_valor   # ver los printk de tu módulo
make unload-clave_valor  # rmmod
```

Mientras iterás, `make reload-clave_valor` recompila, descarga la versión
vieja (si estaba cargada) y carga la nueva en un solo paso.

Para explorar el dispositivo a mano:

```bash
make shell
echo -n "3" > /dev/clave_valor   # incrementa la clave 3
cat /dev/clave_valor              # imprime el valor de TU casillero (según tu PID)
```

#### Validación de tu solución

```bash
make test-clave_valor
```

También podés usar `make test-ej3`, que ejecuta el mismo test.

Esto carga el módulo, corre `tests/tests_clave_valor.py` y lo descarga al
terminar, sea cual sea el resultado. Su test de concurrencia hace que
varios procesos con distinto PID escriban a la vez sobre la misma clave
explícita y verifica que el total leído coincida con lo esperado — si
falla ahí (y no en los tests anteriores), es señal de que falta (o está
mal puesta) la sincronización sobre la tabla.

---

## Comandos del taller

Los targets numerados siguen el orden Nulo (1), LED (2) y Clave/Valor (3).
Cada `make test-ejN` equivale al test con el nombre del dispositivo.

| Comando | Qué hace |
|---|---|
| `make build-nulo` | Compila tu `src/nulo/nulo.c` contra el kernel de la VM |
| `make load-nulo` | Carga el módulo (`insmod`) |
| `make unload-nulo` | Descarga el módulo (`rmmod`) |
| `make reload-nulo` | Recompila y recarga, útil mientras editás |
| `make dmesg-nulo` | Últimas líneas del log de kernel relacionadas con `nulo` |
| `make test-nulo` o `make test-ej1` | Tests del ejercicio Nulo |
| `make build-led` | Compila `src/led/led.c` dentro de la VM |
| `make load-led` | Compila y carga el módulo LED |
| `make unload-led` | Descarga el módulo LED |
| `make reload-led` | Recompila y recarga el módulo LED |
| `make dmesg-led` | Muestra estado, RGB y brillo en el log del driver |
| `make test-led` o `make test-ej2` | Carga, ejecuta los tests del LED y descarga |
| `make led-simulador` | Abre el visualizador del LED; requiere el módulo cargado |
| `make led-encendido-blanco-brillante` | Prende en blanco con brillo `1` |
| `make led-apagado-blanco-brillante` | Apaga con color blanco y brillo `1` |
| `make led-encendido-rojo-intermedio` | Prende en rojo con brillo `0.5` |
| `make led-apagado-rojo-intermedio` | Apaga con color rojo y brillo `0.5` |
| `make build-clave_valor` | Compila tu `src/clave_valor/clave_valor.c` |
| `make load-clave_valor` | Carga el módulo (`insmod`) |
| `make unload-clave_valor` | Descarga el módulo (`rmmod`) |
| `make reload-clave_valor` | Recompila y recarga, útil mientras editás |
| `make dmesg-clave_valor` | Últimas líneas del log de kernel relacionadas con `clave_valor` |
| `make test-clave_valor` o `make test-ej3` | Tests del ejercicio `clave_valor` |

---

## Entrega

### Ejercicio Nulo

- `src/nulo/nulo.c` — Módulo que replica el comportamiento de `/dev/null`.

### Ejercicio `clave_valor`

- `src/clave_valor/clave_valor.c` — Módulo de la base de datos clave-valor
  `/dev/clave_valor`.

### Ejercicio `led`

- `src/led/led.c` — Módulo del LED `/dev/led`, con estado, color RGB y brillo.

---

## Debugging y herramientas útiles

Con `make shell` (ver [VM.md](https://github.com/SSOO-Exactas-2026-2C/taller-tools/blob/main/VM.md)) entrás a una terminal adentro de la VM,
parada en la carpeta del taller.

```bash
# Ver si el módulo está cargado
lsmod | grep nulo

# Ver el log completo del kernel
dmesg | tail -50

# Info del dispositivo
ls -l /dev/nulo
cat /proc/devices | grep nulo
```

**P: `insmod` me dice "File exists".**
R: El módulo ya estaba cargado de una corrida anterior. Usá
`make reload-nulo`, o `make unload-nulo` y después `make load-nulo`.

**P: `make test-nulo` falla con "no existe /dev/nulo".**
R: Es que tu `hello_init` todavía no crea el nodo del dispositivo
(`class_create` + `device_create`), o `hello_init` devuelve un error antes
de llegar a esa parte. Mirá `make dmesg-nulo`.

Los problemas del entorno (la VM no arranca, falta qemu, etc.) están en
[VM.md](https://github.com/SSOO-Exactas-2026-2C/taller-tools/blob/main/VM.md).

---

## Referencias útiles

- **man 2 open**, **man 2 read**, **man 2 write**
- Documentación del kernel: `Documentation/filesystems/vfs.rst`,
  `struct file_operations` en `include/linux/fs.h`

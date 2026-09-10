# SSOO - Taller de IPC
#
# Todo se compila y se ejecuta adentro de una VM Linux, no en tu máquina.
# Así el entorno es idéntico para todos (Linux, macOS y Windows con WSL2)
# y herramientas como strace funcionan siempre.
#
# La carpeta del taller se comparte con la VM, así que podés editar los
# archivos con tu editor de siempre y compilar/correr con make.
#
# Arranca con:   make install
# Y después:     make help

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------
# Herramientas compartidas por todos los talleres de la materia (la VM,
# principalmente). Viven en su propio repo y las baja make solo, la primera
# vez.  https://github.com/SSOO-Exactas-2026-2C/taller-tools
TOOLS_REPO ?= https://github.com/SSOO-Exactas-2026-2C/taller-tools.git
TOOLS_REF  ?= main

# Se clona en una carpeta temporal y recién ahí se mueve a tools/, para que un
# Ctrl-C a mitad de la descarga no deje un tools/ incompleto (que después haría
# fallar todos los clones siguientes con "destination path already exists").
#
# Ojo: el resultado se chequea con el exit status del $(shell) y NO con un
# segundo $(wildcard). Make cachea el listado de cada directorio y no lo
# invalida después de un $(shell), así que el wildcard seguiría dando vacío y
# abortaría un clone que en realidad anduvo bien.
ifeq ($(wildcard tools/vm.mk),)
$(info ==> Bajando las herramientas compartidas del taller...)
TOOLS_OK := $(shell rm -rf tools tools.tmp && \
	git clone --quiet --depth 1 --branch $(TOOLS_REF) $(TOOLS_REPO) tools.tmp 1>&2 && \
	mv tools.tmp tools && echo ok)
ifneq ($(TOOLS_OK),ok)
$(error No pude bajar las herramientas del taller desde $(TOOLS_REPO) -- necesitás git y conexión a internet)
endif
endif

include tools/vm.mk

# ---------------------------------------------------------------------
# Carpeta con los fuentes a compilar. Por defecto la del alumno; la cátedra
# puede apuntar a la solución sin copiar archivos a src/:
#   make test SRC_DIR=src-solucion
SRC_DIR ?= src

# Ejercicio 1: la mini shell
SRC_EJ1  := $(SRC_DIR)/ej1/minishell.c $(SRC_DIR)/ej1/parser.c
BIN_EJ1  := bin/minishell
TEST_EJ1 := tests/tests_ej1.py

# Ejercicio 2: el anillo de pipes
SRC_EJ2  := $(SRC_DIR)/ej2/anillo.c
BIN_EJ2  := bin/anillo
TEST_EJ2 := tests/tests_ej2.py

# Ejercicio 3: servidor y cliente HTTP
SRC_EJ3_SERVIDOR := $(SRC_DIR)/ej3/servidor.c
SRC_EJ3_CLIENTE  := $(SRC_DIR)/ej3/cliente.c
BIN_EJ3_SERVIDOR := bin/servidor
BIN_EJ3_CLIENTE  := bin/cliente
TEST_EJ3         := tests/tests_ej3.py

# Argumentos de los programas. Se pueden pisar desde la línea de comandos:
#   make run-anillo N=5 S=2 C=0 P=20
#   make run-servidor SOCK=/tmp/otro.sock
N ?=
S ?=
C ?=
P ?=
ARGS_EJ2  := $(or $(N),5) $(or $(S),1) $(or $(C),0) $(or $(P),20)

# El servidor y el cliente del ejercicio 3 se hablan por un socket UNIX,
# que es un archivo. NO puede estar en la carpeta del taller: esa se
# comparte con la VM por 9p, que no soporta crear sockets. Por eso vive
# en /tmp, adentro de la VM.
SOCK ?= /tmp/taller-ipc.sock

# Traza de syscalls: la completa queda en TRACE_LOG (lo define tools/vm.mk),
# por pantalla se muestra solo lo filtrado por FILTRO.
#
# Ojo: con "strace -f" cada línea arranca con el PID, así que el filtro no
# puede anclarse al principio de la línea.
FILTRO := pipe|dup2|dup3|close|clone|fork|execve|wait4|waitid|exit_group|socket|bind|listen|accept|connect
STRACE := strace -f -e trace=%process,%desc,%network

.PHONY: help \
        build build-ej1 build-ej2 build-ej3 \
        run-ej1 run-ej2 run-minishell run-anillo run-servidor run-cliente \
        strace-ej1 strace-ej2 strace-ej3 \
        test test-ej1 test-ej2 test-ej3 \
        clean

help:
	@echo "Taller de IPC"
	@echo ""
	$(VM_HELP)
	@echo ""
	@echo "  Ejercicio 1 - la mini shell"
	@echo "    make build-ej1            compila tu $(SRC_DIR)/ej1/"
	@echo "    make run-minishell        abre tu mini shell interactiva"
	@echo "    make strace-ej1           traza tu implementación (para debuggear)"
	@echo "    make test-ej1             corre los tests del ejercicio 1"
	@echo "      secciones: basico pipes robustez fds procesos interactivo huerfanos"
	@echo "      por ejemplo:  make test-ej1-fds"
	@echo ""
	@echo "  Ejercicio 2 - el anillo"
	@echo "    make build-ej2            compila tu $(SRC_EJ2)"
	@echo "    make run-anillo N=5 S=1 C=0 P=20"
	@echo "    make strace-ej2 N=5 S=1 C=0 P=20"
	@echo "    make test-ej2             corre los tests del ejercicio 2"
	@echo "      secciones: parametros resultado recorrido fds procesos sin-kill huerfanos"
	@echo ""
	@echo "  Ejercicio 3 - servidor y cliente HTTP"
	@echo "    make build-ej3            compila tu $(SRC_DIR)/ej3/"
	@echo "    make run-servidor         levanta tu servidor en $(SOCK)"
	@echo "    make run-cliente          conecta tu cliente a ese socket"
	@echo "    make strace-ej3           traza tu servidor"
	@echo "    make test-ej3             corre los tests del ejercicio 3"
	@echo "      secciones: servidor-basico servidor-errores servidor-keepalive"
	@echo "                 servidor-concurrencia servidor-fds servidor-procesos"
	@echo "                 servidor-seguridad cliente interop huerfanos"
	@echo ""
	@echo "  Todo junto"
	@echo "    make build / make test"
	@echo ""
	$(VM_HELP_LIMPIEZA)

# ---------------------------------------------------------------------
# Ejercicio 1: la mini shell
# ---------------------------------------------------------------------

# Los binarios se compilan adentro de la VM. Como la carpeta es compartida,
# los .c se leen y los binarios aparecen del lado del host también.
build-ej1:
	@for f in $(SRC_EJ1); do \
		test -f $$f || { echo "Falta $$f: es tu entrega del ejercicio 1."; exit 1; }; \
	done
	@$(VM) exec "gcc $(CFLAGS) -o $(BIN_EJ1) $(SRC_EJ1)"
	@echo "compilado: $(BIN_EJ1)"

run-minishell: build-ej1
	@$(VM) run "./$(BIN_EJ1)" $(INTERACTIVO)

run-ej1: run-minishell

strace-ej1: build-ej1
	@$(VM) run "rm -f $(TRACE_LOG); $(STRACE) -o $(TRACE_LOG) ./$(BIN_EJ1)" $(INTERACTIVO)
	$(VM_SHOW_TRACE)

test-ej1: build-ej1
	@$(VM) run "python3 $(TEST_EJ1) ./$(BIN_EJ1)"

# Una sección sola, para corregir con puntaje por partes:
#   make test-ej1-fds
test-ej1-%: build-ej1
	@$(VM) run "python3 $(TEST_EJ1) ./$(BIN_EJ1) --check=$*"

# ---------------------------------------------------------------------
# Ejercicio 2: el anillo
# ---------------------------------------------------------------------

build-ej2:
	@test -f $(SRC_EJ2) || { \
		echo "Falta $(SRC_EJ2): es tu entrega del ejercicio 2."; exit 1; }
	@$(VM) exec "gcc $(CFLAGS) -o $(BIN_EJ2) $(SRC_EJ2)"
	@echo "compilado: $(BIN_EJ2)"

run-anillo: build-ej2
	@$(VM) run "./$(BIN_EJ2) $(ARGS_EJ2)" $(INTERACTIVO)

run-ej2: run-anillo

strace-ej2: build-ej2
	@$(VM) run "rm -f $(TRACE_LOG); $(STRACE) -o $(TRACE_LOG) ./$(BIN_EJ2) $(ARGS_EJ2)" $(INTERACTIVO)
	$(VM_SHOW_TRACE)

test-ej2: build-ej2
	@$(VM) run "python3 $(TEST_EJ2) ./$(BIN_EJ2)"

test-ej2-%: build-ej2
	@$(VM) run "python3 $(TEST_EJ2) ./$(BIN_EJ2) --check=$*"

# ---------------------------------------------------------------------
# Ejercicio 3: servidor y cliente HTTP
# ---------------------------------------------------------------------

build-ej3:
	@test -f $(SRC_EJ3_SERVIDOR) || { \
		echo "Falta $(SRC_EJ3_SERVIDOR): es tu entrega del ejercicio 3."; exit 1; }
	@test -f $(SRC_EJ3_CLIENTE) || { \
		echo "Falta $(SRC_EJ3_CLIENTE): es tu entrega del ejercicio 3."; exit 1; }
	@$(VM) exec "gcc $(CFLAGS) -o $(BIN_EJ3_SERVIDOR) $(SRC_EJ3_SERVIDOR)"
	@$(VM) exec "gcc $(CFLAGS) -o $(BIN_EJ3_CLIENTE) $(SRC_EJ3_CLIENTE)"
	@echo "compilado: $(BIN_EJ3_SERVIDOR) $(BIN_EJ3_CLIENTE)"

run-servidor: build-ej3
	@$(VM) run "./$(BIN_EJ3_SERVIDOR) $(SOCK)" $(INTERACTIVO)

run-cliente: build-ej3
	@$(VM) run "./$(BIN_EJ3_CLIENTE) $(SOCK)" $(INTERACTIVO)

strace-ej3: build-ej3
	@$(VM) run "rm -f $(TRACE_LOG); $(STRACE) -o $(TRACE_LOG) ./$(BIN_EJ3_SERVIDOR) $(SOCK)" $(INTERACTIVO)
	$(VM_SHOW_TRACE)

test-ej3: build-ej3
	@$(VM) run "python3 $(TEST_EJ3) ./$(BIN_EJ3_SERVIDOR) ./$(BIN_EJ3_CLIENTE)"

test-ej3-%: build-ej3
	@$(VM) run "python3 $(TEST_EJ3) ./$(BIN_EJ3_SERVIDOR) ./$(BIN_EJ3_CLIENTE) --check=$*"

# ---------------------------------------------------------------------

build: build-ej1 build-ej2 build-ej3

test: test-ej1 test-ej2 test-ej3

clean:
	rm -f $(BIN_EJ1) $(BIN_EJ2) $(BIN_EJ3_SERVIDOR) $(BIN_EJ3_CLIENTE) $(TRACE_LOG)

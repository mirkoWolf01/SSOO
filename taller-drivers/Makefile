# SSOO - Taller de drivers
#
# Todo se compila y se ejecuta adentro de una VM Linux, no en tu máquina.
# Así el entorno es idéntico para todos (Linux, macOS y Windows con WSL2)
# y podés hacer insmod/rmmod sin arriesgar tu propio kernel.
#
# La carpeta del taller se comparte con la VM, así que podés editar los
# archivos con tu editor de siempre y compilar/cargar con make.
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
#   make test-nulo SRC_DIR=src-solucion
SOL_DIR := src-solucion
SRC_DIR ?= src

# Ejercicio 1, Nulo: /dev/nulo
SRC_NULO    := $(SRC_DIR)/nulo/nulo.c
KBUILD_NULO := $(SRC_DIR)/nulo/Makefile   # manifest de kbuild (obj-m := nulo.o)
DEVICE_NULO := /dev/nulo
TEST_NULO   := tests/tests_nulo.py

# El .c y el manifest de kbuild se copian a esta carpeta ANTES de compilar,
# y ahí es donde kbuild deja todo lo intermedio (.o, .mod, .cmd,
# Module.symvers, etc.) además del .ko final. Está fuera de /taller (la
# carpeta compartida por 9p con el host) a propósito: así ningún archivo
# de compilación aparece del lado del host ni hay que gitignorearlo. Vive
# solo adentro de la VM, se recrea de cero en cada build-nulo.
BUILD_NULO := /tmp/taller-drivers/nulo
MOD_NULO   := $(BUILD_NULO)/nulo.ko

# Ejercicio 3: /dev/clave_valor
SRC_CLAVE_VALOR    := $(SRC_DIR)/clave_valor/clave_valor.c
KBUILD_CLAVE_VALOR := $(SRC_DIR)/clave_valor/Makefile
DEVICE_CLAVE_VALOR := /dev/clave_valor
TEST_CLAVE_VALOR   := tests/tests_clave_valor.py

BUILD_CLAVE_VALOR := /tmp/taller-drivers/clave_valor
MOD_CLAVE_VALOR   := $(BUILD_CLAVE_VALOR)/clave_valor.ko

# Ejercicio 2: /dev/led
SRC_LED    := $(SRC_DIR)/led/led.c
KBUILD_LED := $(SRC_DIR)/led/Makefile
DEVICE_LED := /dev/led
TEST_LED   := tests/tests_led.py
# El visualizador es una herramienta, no parte de la entrega: siempre se usa
# el de src/, aunque se compile otra carpeta con SRC_DIR.
TERMINAL_LED := src/led/led_terminal.py

BUILD_LED := /tmp/taller-drivers/led
MOD_LED   := $(BUILD_LED)/led.ko

# El módulo de kernel se compila contra los headers del kernel que corre la
# VM (no los del host), o sea los de linux-headers-$(uname -r). No están en
# el packages: de taller-tools (es compartido por los 5 talleres, y solo
# drivers los necesita), así que se instalan acá, una sola vez por VM.
#
# Ojo: Debian solo publica los headers del último kernel. Si la imagen base
# es más vieja, los del kernel que corre ya no se pueden bajar. En ese caso
# se instala el paquete "meta" linux-headers-amd64, que trae el kernel más
# nuevo junto con sus headers, y hay que reiniciar la VM para arrancarlo.
#
# El \$$ es para que $(uname -r) se evalúe adentro de la VM y no en el host.
INSTALAR_HEADERS = test -d /lib/modules/\$$(uname -r)/build || \
	{ sudo apt-get update -qq && \
	  sudo apt-get install -y -qq linux-headers-\$$(uname -r) 2>/dev/null; } || \
	{ sudo apt-get install -y -qq linux-headers-amd64 && echo && \
	  echo 'Debian ya no publica los headers del kernel de la VM ('\$$(uname -r)').' && \
	  echo 'Se instaló un kernel más nuevo con sus headers: reiniciá la VM con' && \
	  echo '  make stop-vm start-vm' && \
	  echo 'y volvé a correr este comando.' && exit 1; }

DMESG_LINES ?= 50

# Si el rmmod normal falla (el módulo quedó con el device abierto por algún
# proceso colgado), lo forzamos: matamos con -9 a quien lo tenga abierto
# (fuser -k manda SIGKILL por default) y reintentamos con rmmod -f.
define RMMOD_FORZADO
sudo rmmod $(1) 2>/dev/null || { sudo fuser -k $(2); sleep 1; sudo rmmod -f $(1); }
endef

.PHONY: help \
        build build-nulo load-nulo unload-nulo reload-nulo dmesg-nulo \
        build-clave_valor load-clave_valor unload-clave_valor \
        reload-clave_valor dmesg-clave_valor \
        build-led load-led unload-led reload-led dmesg-led led-simulador \
        led-encendido-blanco-brillante \
        led-apagado-blanco-brillante \
        led-encendido-rojo-intermedio \
        led-apagado-rojo-intermedio \
        test test-nulo test-clave_valor test-led \
        test-ej1 test-ej2 test-ej3 \
        clean

help:
	@echo "Taller de drivers"
	@echo ""
	$(VM_HELP)
	@echo ""
	@echo "  Ejercicio 1 - Nulo (/dev/nulo)"
	@echo "    make build-nulo           compila tu $(SRC_NULO)"
	@echo "    make load-nulo            carga el módulo (insmod)"
	@echo "    make unload-nulo          descarga el módulo (rmmod)"
	@echo "    make reload-nulo          descarga y vuelve a cargar (tras editar el .c)"
	@echo "    make dmesg-nulo           últimas líneas del log de kernel de tu módulo"
	@echo "    make test-nulo            carga, corre los tests y descarga"
	@echo "    make test-ej1             alias compatible de test-nulo"
	@echo ""
	@echo "  Ejercicio 2 - Smart LED (/dev/led)"
	@echo "    make build-led            compila tu $(SRC_LED)"
	@echo "    make load-led             carga el módulo (insmod)"
	@echo "    make unload-led           descarga el módulo (rmmod)"
	@echo "    make reload-led           descarga y vuelve a cargar (tras editar el .c)"
	@echo "    make dmesg-led            últimas líneas del log de kernel de tu módulo"
	@echo "    make test-led             carga, corre los tests y descarga"
	@echo "    make test-ej2             alias compatible de test-led"
	@echo "    make led-simulador         abre el visualizador en la VM (requiere load-led)"
	@echo "    Presets (requieren load-led):"
	@echo "    make led-encendido-blanco-brillante   prende en blanco, brillo 1"
	@echo "    make led-apagado-blanco-brillante     apaga con blanco y brillo 1"
	@echo "    make led-encendido-rojo-intermedio    prende en rojo, brillo 0.5"
	@echo "    make led-apagado-rojo-intermedio      apaga con rojo y brillo 0.5"
	@echo ""
	@echo "  Ejercicio 3 - Clave/Valor (/dev/clave_valor)"
	@echo "    make build-clave_valor         compila tu $(SRC_CLAVE_VALOR)"
	@echo "    make load-clave_valor          carga el módulo (insmod)"
	@echo "    make unload-clave_valor        descarga el módulo (rmmod)"
	@echo "    make reload-clave_valor        descarga y vuelve a cargar (tras editar el .c)"
	@echo "    make dmesg-clave_valor         últimas líneas del log de kernel de tu módulo"
	@echo "    make test-clave_valor          carga, corre los tests y descarga"
	@echo "    make test-ej3                  alias compatible de test-clave_valor"
	@echo ""
	@echo "  Todo junto"
	@echo "    make build / make test"
	@echo ""
	$(VM_HELP_LIMPIEZA)

# ---------------------------------------------------------------------
# Ejercicio Nulo: /dev/nulo
# ---------------------------------------------------------------------

# El módulo se compila adentro de la VM, contra sus propios headers, en
# $(BUILD_NULO) (fuera de la carpeta compartida: ver el comentario junto a
# esa variable). Se copian ahí el .c y el manifest de kbuild antes de
# compilar, así que "tu" código siempre se lee fresco desde $(SRC_DIR).
build-nulo:
	@test -f $(SRC_NULO) || { \
		echo "Falta $(SRC_NULO): es tu entrega de este ejercicio."; exit 1; }
	@$(VM) exec "$(INSTALAR_HEADERS)"
	@$(VM) exec "rm -rf $(BUILD_NULO) && mkdir -p $(BUILD_NULO) && \
		cp $(SRC_NULO) $(KBUILD_NULO) $(BUILD_NULO)/ && make -C $(BUILD_NULO)"
	@echo "compilado (adentro de la VM, no aparece del lado host): $(MOD_NULO)"

load-nulo: build-nulo
	@$(VM) exec "sudo insmod $(MOD_NULO)"
	@echo "cargado: $(MOD_NULO) -> $(DEVICE_NULO)"

unload-nulo:
	@$(VM) exec "$(call RMMOD_FORZADO,nulo,$(DEVICE_NULO))"
	@echo "descargado: nulo"

# Para iterar rápido después de editar el .c: recompila, descarga la versión
# vieja si estaba cargada y carga la nueva.
reload-nulo: build-nulo
	-@$(VM) exec "sudo rmmod nulo 2>/dev/null"
	@$(VM) exec "sudo insmod $(MOD_NULO)"
	@echo "recargado: $(MOD_NULO) -> $(DEVICE_NULO)"

dmesg-nulo:
	@$(VM) exec "sudo dmesg | tail -n $(DMESG_LINES) | grep -i nulo || echo '(sin entradas de nulo en dmesg)'"

# El módulo puede haber quedado cargado de una corrida anterior (por
# ejemplo si un test previo se cortó a mano); se lo descarga antes de
# empezar para arrancar de un estado limpio y conocido.
#
# El rmmod final se hace pase lo que pase con los tests (éxito, falla o
# corte), igual que "huerfanos" en el taller de syscalls: nunca queremos
# dejar el módulo cargado después de "make test-nulo". El código de salida
# que importa es el de los tests, no el del rmmod de limpieza.
test-nulo: build-nulo
	-@$(VM) exec "sudo rmmod nulo 2>/dev/null"
	@$(VM) exec "sudo insmod $(MOD_NULO)"
	@rc=0; $(VM) exec "sudo python3 $(TEST_NULO) -v" || rc=$$?; \
	 $(VM) exec "$(call RMMOD_FORZADO,nulo,$(DEVICE_NULO))" >/dev/null 2>&1 || true; \
	 exit $$rc

# Alias numerados para mantener la interfaz de los otros talleres. Los
# nombres propios siguen disponibles para identificar cada dispositivo.
test-ej1: test-nulo

# ---------------------------------------------------------------------
# Ejercicio 3, Clave/Valor: /dev/clave_valor
# ---------------------------------------------------------------------

build-clave_valor:
	@test -f $(SRC_CLAVE_VALOR) || { \
		echo "Falta $(SRC_CLAVE_VALOR): es tu entrega de este ejercicio."; exit 1; }
	@$(VM) exec "$(INSTALAR_HEADERS)"
	@$(VM) exec "rm -rf $(BUILD_CLAVE_VALOR) && mkdir -p $(BUILD_CLAVE_VALOR) && \
		cp $(SRC_CLAVE_VALOR) $(KBUILD_CLAVE_VALOR) $(BUILD_CLAVE_VALOR)/ && make -C $(BUILD_CLAVE_VALOR)"
	@echo "compilado (adentro de la VM, no aparece del lado host): $(MOD_CLAVE_VALOR)"

load-clave_valor: build-clave_valor
	@$(VM) exec "sudo insmod $(MOD_CLAVE_VALOR)"
	@echo "cargado: $(MOD_CLAVE_VALOR) -> $(DEVICE_CLAVE_VALOR)"

unload-clave_valor:
	@$(VM) exec "$(call RMMOD_FORZADO,clave_valor,$(DEVICE_CLAVE_VALOR))"
	@echo "descargado: clave_valor"

reload-clave_valor: build-clave_valor
	-@$(VM) exec "sudo rmmod clave_valor 2>/dev/null"
	@$(VM) exec "sudo insmod $(MOD_CLAVE_VALOR)"
	@echo "recargado: $(MOD_CLAVE_VALOR) -> $(DEVICE_CLAVE_VALOR)"

dmesg-clave_valor:
	@$(VM) exec "sudo dmesg | tail -n $(DMESG_LINES) | grep -i clave_valor || echo '(sin entradas de clave_valor en dmesg)'"

test-clave_valor: build-clave_valor
	-@$(VM) exec "sudo rmmod clave_valor 2>/dev/null"
	@$(VM) exec "sudo insmod $(MOD_CLAVE_VALOR)"
	@rc=0; $(VM) exec "sudo python3 $(TEST_CLAVE_VALOR) -v" || rc=$$?; \
	 $(VM) exec "$(call RMMOD_FORZADO,clave_valor,$(DEVICE_CLAVE_VALOR))" >/dev/null 2>&1 || true; \
	 exit $$rc

test-ej3: test-clave_valor

# ---------------------------------------------------------------------
# Ejercicio 2, Smart LED: /dev/led
# ---------------------------------------------------------------------

build-led:
	@test -f $(SRC_LED) || { \
		echo "Falta $(SRC_LED): es tu entrega de este ejercicio."; exit 1; }
	@$(VM) exec "$(INSTALAR_HEADERS)"
	@$(VM) exec "rm -rf $(BUILD_LED) && mkdir -p $(BUILD_LED) && \
		cp $(SRC_LED) $(KBUILD_LED) $(BUILD_LED)/ && make -C $(BUILD_LED)"
	@echo "compilado (adentro de la VM, no aparece del lado host): $(MOD_LED)"

load-led: build-led
	@$(VM) exec "sudo insmod $(MOD_LED)"
	@echo "cargado: $(MOD_LED) -> $(DEVICE_LED)"

unload-led:
	@$(VM) exec "$(call RMMOD_FORZADO,led,$(DEVICE_LED))"
	@echo "descargado: led"

reload-led: build-led
	-@$(VM) exec "sudo rmmod led 2>/dev/null"
	@$(VM) exec "sudo insmod $(MOD_LED)"
	@echo "recargado: $(MOD_LED) -> $(DEVICE_LED)"

dmesg-led:
	@$(VM) exec "sudo dmesg | tail -n $(DMESG_LINES) | grep -i led || echo '(sin entradas de led en dmesg)'"

test-led: build-led
	-@$(VM) exec "sudo rmmod led 2>/dev/null"
	@$(VM) exec "sudo insmod $(MOD_LED)"
	@rc=0; $(VM) exec "sudo python3 $(TEST_LED) -v" || rc=$$?; \
	 $(VM) exec "$(call RMMOD_FORZADO,led,$(DEVICE_LED))" >/dev/null 2>&1 || true; \
	 exit $$rc

test-ej2: test-led

led-simulador:
	@$(VM) run "sudo python3 $(TERMINAL_LED)" $(INTERACTIVO)

# Estos comandos requieren el modulo cargado con load-led o reload-led.

led-encendido-blanco-brillante:
	@$(VM) exec "sudo python3 $(TERMINAL_LED) --device $(DEVICE_LED) --status 1 --color 255 255 255 --brillo 1"

led-apagado-blanco-brillante:
	@$(VM) exec "sudo python3 $(TERMINAL_LED) --device $(DEVICE_LED) --status 0 --color 255 255 255 --brillo 1"

led-encendido-rojo-intermedio:
	@$(VM) exec "sudo python3 $(TERMINAL_LED) --device $(DEVICE_LED) --status 1 --color 255 0 0 --brillo 0.5"

led-apagado-rojo-intermedio:
	@$(VM) exec "sudo python3 $(TERMINAL_LED) --device $(DEVICE_LED) --status 0 --color 255 0 0 --brillo 0.5"

# ---------------------------------------------------------------------

build: build-nulo build-led build-clave_valor

test: test-nulo test-led test-clave_valor

clean:
	-@$(VM) exec "sudo rmmod nulo 2>/dev/null"
	-@$(VM) exec "sudo rmmod clave_valor 2>/dev/null"
	-@$(VM) exec "sudo rmmod led 2>/dev/null"
	-@$(VM) exec "rm -rf $(BUILD_NULO) $(BUILD_CLAVE_VALOR) $(BUILD_LED)"

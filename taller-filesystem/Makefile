# SSOO - Taller de filesystem (ext2)
# Se edita en el host; se compila y ejecuta dentro de la VM compartida.
# Arrancá con make install y make help.

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

CXXFLAGS ?= -g -Wall -pedantic -std=gnu++17
INCLUDES := -I'$(SRC_DIR)'
SRCS := '$(SRC_DIR)/hdd.cpp' '$(SRC_DIR)/mbr.cpp' '$(SRC_DIR)/pentry.cpp' '$(SRC_DIR)/ext2fs.cpp' tests/probe_hdd.cpp
BUILD_DIR := /tmp/taller-fs
BIN := $(BUILD_DIR)/probe_hdd
IMAGE := tests/hdd.raw
# Donde empieza la partición dentro de la imagen: sector 2048 (ver
# PARTITION_START_LBA en tests/gen_hdd.py) × 512 bytes.
IMAGE_OFFSET := 1048576

# Siempre se compila con ASan + UBSan y se corre con detección de leaks:
# avisa si la implementación lee fuera de un buffer, usa memoria liberada o
# pierde memoria (por ejemplo, un buffer de bloque sin su delete[]). Corre
# más lento, pero en un taller vale la pena.
SANFLAGS := -fsanitize=address,undefined -fno-omit-frame-pointer -O1
SANOPTS  := ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=print_stacktrace=1

.PHONY: help build test test-ej1 test-ej2 test-ej3 test-imagen \
	test-e2e debugfs hdd clean

help:
	@echo "Taller de filesystem (ext2)"
	@echo ""
	$(VM_HELP)
	@echo ""
	@echo "  Compilar y probar (adentro de la VM)"
	@echo "    make build                compila los fuentes de $(SRC_DIR)"
	@echo "    make test                 corre todos los tests"
	@echo "    make test-imagen          verifica disco, superbloque y grupos"
	@echo "    make test-ej1             carga de inodos"
	@echo "    make test-ej2             direccionamiento de bloques"
	@echo "    make test-ej3             búsqueda en directorios (requiere ej. 1 y 2)"
	@echo "    make test-e2e             lee todos los archivos (requiere los 3)"
	@echo ""
	@echo "  Herramientas"
	@echo "    make debugfs CMD=\"ls -l /\"   explora la imagen con debugfs"
	@echo "    make hdd                  regenera tests/hdd.raw (para la cátedra)"
	@echo ""
	$(VM_HELP_LIMPIEZA)

# Los artefactos quedan fuera de /taller, como en el taller de drivers.
# Siempre se recompila para tomar las últimas modificaciones de los fuentes.
build:
	@test -f "$(SRC_DIR)/ext2fs.cpp" || { echo "Falta $(SRC_DIR)/ext2fs.cpp"; exit 1; }
	@$(VM) exec "mkdir -p $(BUILD_DIR) && g++ $(CXXFLAGS) $(SANFLAGS) -UNDEBUG \
		$(INCLUDES) $(SRCS) -o $(BIN)"
	@echo "Compilado dentro de la VM: $(BIN)"

# tests/test_hdd.py compara lo que devuelve la implementación (a través de
# probe_hdd) contra debugfs. El filesystem es de solo lectura: HDD abre la
# imagen en modo "rb", así que los tests corren directamente sobre ella.
define RUN_TEST
	@$(VM) exec "$(SANOPTS) python3 tests/test_hdd.py $(BIN) $(IMAGE) $(1)"
endef

test: build
	$(call RUN_TEST,all)

test-imagen: build
	$(call RUN_TEST,imagen)

test-ej1: build
	$(call RUN_TEST,ej1)

test-ej2: build
	$(call RUN_TEST,ej2)

test-ej3: build
	$(call RUN_TEST,ej3)

test-e2e: build
	$(call RUN_TEST,e2e)

# Corre un comando de debugfs sobre la imagen, para explorarla. Sin paginador:
# en la terminal de la VM no funciona bien.
CMD ?= ls -l /
debugfs:
	@$(VM) exec "DEBUGFS_PAGER=__none__ /sbin/debugfs -R '$(CMD)' '$(IMAGE)?offset=$(IMAGE_OFFSET)'"

# Regenera la imagen de disco con los casos que arma tests/gen_hdd.py.
hdd:
	@$(VM) exec "python3 tests/gen_hdd.py $(IMAGE)"

clean:
	@$(VM) exec "rm -rf $(BUILD_DIR)"

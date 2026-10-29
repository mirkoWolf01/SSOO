#!/usr/bin/env python3
"""Genera la imagen de disco del taller (tests/hdd.raw).

La imagen es un MBR con una sola partición ext2. El contenido del
filesystem está armado a propósito para ejercitar los casos que nos
interesan (ver generate() más abajo y tests/README.md).

Corre adentro de la VM, porque usa mke2fs y debugfs (e2fsprogs):

    make hdd

o directamente:

    python3 tests/gen_hdd.py tests/hdd.raw
"""

import os
import subprocess
import sys
import tempfile

MKE2FS = "/sbin/mke2fs"
DEBUGFS = "/sbin/debugfs"

SECTOR_SIZE = 512
BLOCK_SIZE = 1024
INODE_SIZE = 128
BLOCKS_PER_GROUP = 1024          # chico, para tener varios block groups
FS_BLOCKS = 3 * BLOCKS_PER_GROUP
INODES = 384

# La partición arranca en el sector 2048 (1 MiB), como hacen fdisk y sfdisk.
PARTITION_START_LBA = 2048
PARTITION_SECTORS = FS_BLOCKS * BLOCK_SIZE // SECTOR_SIZE
PARTITION_TYPE_LINUX = 0x83

# Con bloques de 1 KiB y direcciones de 4 bytes, en un bloque de punteros
# entran 256 direcciones.
DIRECT_BLOCKS = 12
ADDRS_PER_BLOCK = BLOCK_SIZE // 4
SINGLE_INDIRECT_END = DIRECT_BLOCKS + ADDRS_PER_BLOCK                 # 268
DOUBLE_TABLE_CROSSING = SINGLE_INDIRECT_END + ADDRS_PER_BLOCK + 1     # 525

# Directorio de varios bloques: todos los nombres tienen el mismo largo, así
# cada entrada ocupa exactamente 8 + NAME_LENGTH bytes y se puede calcular en
# qué bloque cae cada una.
NAME_LENGTH = 40
ENTRY_SIZE = 8 + NAME_LENGTH                                          # 48 bytes
ENTRIES_IN_BLOCK_0 = (BLOCK_SIZE - 12 - 12) // ENTRY_SIZE             # después de . y ..
ENTRIES_PER_BLOCK = BLOCK_SIZE // ENTRY_SIZE


def content(path, size):
    """Contenido de un archivo: cada bloque dice a qué archivo y bloque
    pertenece, así un bloque leído de la dirección equivocada se nota."""
    out = bytearray()
    n = 0
    while len(out) < size:
        line = ("%s bloque %d\n" % (path, n)).encode()
        out += (line * (BLOCK_SIZE // len(line) + 1))[:BLOCK_SIZE]
        n += 1
    return bytes(out[:size])


def fixed_name(base):
    assert len(base) <= NAME_LENGTH
    return base + "_" * (NAME_LENGTH - len(base))


class Generator:
    def __init__(self, workdir, fs_image):
        self.workdir = workdir
        self.fs_image = fs_image
        self.commands = []
        self.files = 0

    # --- comandos de debugfs, se ejecutan todos juntos en flush() ---

    def mkdir(self, path):
        self.commands.append("mkdir %s" % path)

    def file(self, path, size):
        self.files += 1
        local = os.path.join(self.workdir, "file%d" % self.files)
        with open(local, "wb") as f:
            f.write(content(path, size))
        self.commands.append("write %s %s" % (local, path))

    def rm(self, path):
        self.commands.append("rm %s" % path)

    def flush(self):
        script = os.path.join(self.workdir, "commands.txt")
        with open(script, "w") as f:
            f.write("\n".join(self.commands) + "\n")
        self.commands = []
        r = subprocess.run([DEBUGFS, "-w", "-f", script, self.fs_image],
                           capture_output=True, text=True)
        if r.returncode != 0 or "rror" in r.stderr.replace("debugfs 1.", ""):
            sys.exit("debugfs falló:\n" + r.stderr)

    # --- consultas, para verificar que la imagen quedó como esperamos ---

    def query(self, command):
        r = subprocess.run([DEBUGFS, "-R", command, self.fs_image],
                           capture_output=True, text=True)
        return r.stdout

    def blocks(self, path):
        """Bloques del archivo (incluye los de punteros, alcanza para verificar
        contigüidad y block groups)."""
        return [int(b) for b in self.query("blocks %s" % path).split()]

    def entry_logical_block(self, directory, name):
        output = self.query("dirsearch %s %s" % (directory, name))
        # "Entry found at logical block 1, phys 515, offset 0"
        words = output.replace(",", "").split()
        return int(words[words.index("logical") + 2])


def generate(g):
    # Raíz: un archivo suelto y un directorio vacío.
    g.file("/raiz.txt", 100)
    g.mkdir("/vacio")

    # Directos no contiguos: se llena con archivos de un bloque, se borra uno
    # por medio y recién ahí se escribe el archivo, que ocupa los huecos.
    g.mkdir("/fragmentado")
    for i in range(2 * DIRECT_BLOCKS):
        g.file("/fragmentado/relleno_%02d" % i, BLOCK_SIZE)
    g.flush()
    for i in range(1, 2 * DIRECT_BLOCKS, 2):
        g.rm("/fragmentado/relleno_%02d" % i)
    g.flush()
    g.file("/fragmentado/no_contiguo.txt", DIRECT_BLOCKS * BLOCK_SIZE)

    # Archivos de distintos tamaños, para cada caso de direccionamiento.
    g.mkdir("/archivos")
    g.file("/archivos/vacio.txt", 0)
    g.file("/archivos/un_byte.txt", 1)
    g.file("/archivos/un_bloque.txt", BLOCK_SIZE)
    g.file("/archivos/directos.txt", DIRECT_BLOCKS * BLOCK_SIZE)
    g.file("/archivos/indirecto_simple.txt", DIRECT_BLOCKS * BLOCK_SIZE + 1)
    g.file("/archivos/fin_indirecto_simple.txt", SINGLE_INDIRECT_END * BLOCK_SIZE)
    g.file("/archivos/indirecto_doble.txt", SINGLE_INDIRECT_END * BLOCK_SIZE + 1)
    g.file("/archivos/cruce_tabla_doble.txt", DOUBLE_TABLE_CROSSING * BLOCK_SIZE)

    # Nombres que son prefijo de otros, en los dos órdenes posibles.
    g.mkdir("/prefijos")
    for name in ["g10", "g11", "g1"]:             # g1 está DESPUÉS que g10
        g.mkdir("/prefijos/%s" % name)
        g.file("/prefijos/%s/nota.txt" % name, 20)
    g.file("/prefijos/archivo_largo.txt", 30)     # el largo antes que el corto
    g.file("/prefijos/archivo", 30)
    g.file("/prefijos/dato", 30)                  # el corto antes que el largo
    g.file("/prefijos/dato.bak", 30)

    # Path anidado.
    g.mkdir("/anidado")
    g.mkdir("/anidado/a")
    g.mkdir("/anidado/a/b")
    g.mkdir("/anidado/a/b/c")
    g.file("/anidado/a/b/c/hoja.txt", 50)

    # Directorio de varios bloques, con entradas borradas.
    total = ENTRIES_IN_BLOCK_0 + 2 * ENTRIES_PER_BLOCK + 1   # la última, sola en el bloque 3
    names = [fixed_name("entrada_%02d" % i) for i in range(total)]
    middle = ENTRIES_IN_BLOCK_0 // 2
    first_of_block_1 = ENTRIES_IN_BLOCK_0
    names[middle] = fixed_name("borrada_en_el_medio")
    names[first_of_block_1] = fixed_name("borrada_primera_del_bloque")
    names[-1] = fixed_name("solo_en_el_ultimo_bloque")
    g.mkdir("/multibloque")
    for name in names:
        g.file("/multibloque/%s" % name, 10)
    g.flush()

    # Se verifica antes de borrar que las entradas quedaron en el bloque que
    # calculamos.
    expected = {middle: 0, first_of_block_1: 1, total - 1: 3}
    for i, block in expected.items():
        actual = g.entry_logical_block("/multibloque", names[i])
        assert actual == block, (names[i], actual, block)

    # Borrar una entrada del medio de un bloque la "absorbe" la anterior
    # (que agranda su record_length) pero sus bytes quedan en el bloque.
    # Borrar la primera entrada de un bloque deja una entrada con inode == 0.
    g.rm("/multibloque/%s" % names[middle])
    g.rm("/multibloque/%s" % names[first_of_block_1])
    g.flush()

    # Verificaciones de lo que no se puede calcular de antemano.
    non_contiguous = g.blocks("/fragmentado/no_contiguo.txt")
    assert any(b - a != 1 for a, b in zip(non_contiguous, non_contiguous[1:])), \
        "no_contiguo.txt quedó con bloques contiguos: %s" % non_contiguous

    crossing = g.blocks("/archivos/cruce_tabla_doble.txt")
    groups = {(b - 1) // BLOCKS_PER_GROUP for b in crossing}
    assert len(groups) > 1, "cruce_tabla_doble.txt quedó en un solo block group"

    assert len(g.blocks("/multibloque")) == 4


def write_mbr(f):
    mbr = bytearray(SECTOR_SIZE)
    entry = bytearray(16)
    entry[0] = 0x00                                     # no booteable
    entry[1:4] = b"\xfe\xff\xff"                        # CHS: no se usa
    entry[4] = PARTITION_TYPE_LINUX
    entry[5:8] = b"\xfe\xff\xff"
    entry[8:12] = PARTITION_START_LBA.to_bytes(4, "little")
    entry[12:16] = PARTITION_SECTORS.to_bytes(4, "little")
    mbr[446:462] = entry
    mbr[510:512] = b"\x55\xaa"
    f.write(mbr)


def main():
    if len(sys.argv) != 2:
        sys.exit("Uso: %s salida.raw" % sys.argv[0])
    output = sys.argv[1]

    with tempfile.TemporaryDirectory() as workdir:
        fs_image = os.path.join(workdir, "partition.img")
        r = subprocess.run([
            MKE2FS, "-q", "-F", "-t", "ext2",
            "-b", str(BLOCK_SIZE), "-I", str(INODE_SIZE),
            "-g", str(BLOCKS_PER_GROUP), "-N", str(INODES), "-m", "0",
            # Sin índices de directorio (htree), sin inodo de resize y sin
            # atributos extendidos: el layout queda como lo describe el
            # enunciado.
            "-O", "^dir_index,^resize_inode,^ext_attr",
            "-L", "taller",
            fs_image, str(FS_BLOCKS),
        ], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("mke2fs falló:\n" + r.stderr)

        generate(Generator(workdir, fs_image))

        with open(output, "wb") as f:
            write_mbr(f)
            f.seek(PARTITION_START_LBA * SECTOR_SIZE)
            with open(fs_image, "rb") as p:
                f.write(p.read())

    print("escrito %s" % output)


if __name__ == "__main__":
    main()

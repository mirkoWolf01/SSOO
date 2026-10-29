#!/usr/bin/env python3
"""Tests del taller de filesystem.

Recorre todo el filesystem de la imagen y compara lo que devuelve la
implementación (a través de tests/probe_hdd.cpp) contra lo que dice debugfs
sobre la misma imagen. No hay valores esperados escritos a mano: funciona con
cualquier imagen generada por tests/gen_hdd.py.

Uso: python3 tests/test_hdd.py probe_hdd imagen.raw [all|imagen|ej1|ej2|ej3|e2e]
"""

import struct
import subprocess
import sys

DEBUGFS = "/sbin/debugfs"
TIMEOUT = 5                  # segundos por consulta
MAX_HANGS = 3                # cuelgues por grupo antes de saltear el resto
MAX_SHOWN_FAILURES = 10      # fallas que se muestran por grupo

SECTOR_SIZE = 512
PARTITION_TYPE_LINUX = 0x83
INODE_STRUCT_SIZE = 128      # sizeof(struct Ext2FSInode)
GROUP_DESC_SIZE = 32         # sizeof(struct Ext2FSBlockGroupDescriptor)
ROOT_INODE = 2

# Campos de struct Ext2FSInode, para decir cuál no coincide.
INODE_FIELDS = (
    [("mode", "H"), ("uid", "H"), ("size", "I"), ("atime", "I"),
     ("ctime", "I"), ("mtime", "I"), ("dtime", "I"), ("gid", "H"),
     ("links_count", "H"), ("blocks", "I"), ("flags", "I"),
     ("os_dependant_1", "I")]
    + [("block[%d]" % i, "I") for i in range(15)]
    + [("generation", "I"), ("file_acl", "I"), ("directory_acl", "I"),
       ("faddr", "I")]
    + [("os_dependant_2[%d]" % i, "I") for i in range(3)]
)


# ---------------------------------------------------------------------
# La imagen, vista por debugfs
# ---------------------------------------------------------------------

class Image:
    def __init__(self, path):
        self.path = path
        self.partition, start_lba = self._find_partition()
        self.offset = start_lba * SECTOR_SIZE
        self.device = "%s?offset=%d" % (path, self.offset)

        sb = self.read_bytes(self.offset + 1024, 1024)
        self.superblock = sb
        blocks_count, = struct.unpack_from("<I", sb, 4)
        first_data_block, log_block_size = struct.unpack_from("<II", sb, 20)
        blocks_per_group, = struct.unpack_from("<I", sb, 32)
        self.block_size = 1024 << log_block_size
        self.addrs_per_block = self.block_size // 4
        groups = -(-(blocks_count - first_data_block) // blocks_per_group)
        gdt = self.offset + (first_data_block + 1) * self.block_size
        self.groups = [self.read_bytes(gdt + i * GROUP_DESC_SIZE, GROUP_DESC_SIZE)
                       for i in range(groups)]

    def read_bytes(self, offset, length):
        with open(self.path, "rb") as f:
            f.seek(offset)
            return f.read(length)

    def _find_partition(self):
        mbr = self.read_bytes(0, SECTOR_SIZE)
        for i in range(4):
            entry = mbr[446 + 16 * i: 446 + 16 * (i + 1)]
            if entry[4] == PARTITION_TYPE_LINUX:
                return i, struct.unpack_from("<I", entry, 8)[0]
        sys.exit("%s: no tiene ninguna partición Linux (0x83)" % self.path)

    def debugfs(self, command, binary=False):
        r = subprocess.run([DEBUGFS, "-R", command, self.device], capture_output=True)
        if r.returncode != 0:
            sys.exit("debugfs -R '%s' falló:\n%s" % (command, r.stderr.decode()))
        return r.stdout if binary else r.stdout.decode()

    def debugfs_batch(self, commands):
        """Corre varios comandos en una sola invocación de debugfs y devuelve
        la salida de cada uno."""
        r = subprocess.run([DEBUGFS, "-f", "-", self.device], input="\n".join(commands),
                           capture_output=True, text=True)
        outputs = []
        for line in r.stdout.splitlines():
            if line.startswith("debugfs: "):
                outputs.append([])
            elif outputs:
                outputs[-1].append(line)
        if len(outputs) != len(commands):
            sys.exit("debugfs -f falló:\n%s" % r.stderr)
        return ["\n".join(o) for o in outputs]

    def list_dir(self, directory, deleted=False):
        """Entradas de un directorio: [(inodo, es_directorio, nombre, tamaño)].
        Con deleted=True incluye también las entradas borradas."""
        options = "-d -p" if deleted else "-p"
        entries = []
        for line in self.debugfs("ls %s %s" % (options, directory)).splitlines():
            # /inodo/modo/uid/gid/nombre/tamaño/
            fields = line.split("/")
            if len(fields) != 8:
                continue
            # Sin -d, debugfs igual muestra las entradas vacías (inodo 0, sin
            # nombre) que mke2fs deja en lost+found.
            if fields[1] == "0" and not deleted:
                continue
            mode = int(fields[2], 8)
            size = int(fields[6]) if fields[6] else 0
            entries.append((int(fields[1]), mode & 0o170000 == 0o040000, fields[5], size))
        return entries

    def inode(self, number):
        """Los primeros sizeof(struct Ext2FSInode) bytes del inodo. debugfs dice
        dónde está y los bytes se leen directamente de la imagen."""
        # "Inode 17 is part of block group 0\n\tlocated at block 7, offset 0x0000"
        words = self.debugfs("imap <%d>" % number).replace(",", "").split()
        block = int(words[words.index("located") + 3])
        offset = int(words[words.index("offset") + 1], 16)
        return self.read_bytes(self.offset + block * self.block_size + offset,
                               INODE_STRUCT_SIZE)

    def blocks(self, number, size):
        """Dirección de cada bloque de datos del inodo, en orden lógico."""
        count = -(-size // self.block_size)
        if count == 0:
            return []
        outputs = self.debugfs_batch(["bmap <%d> %d" % (number, i) for i in range(count)])
        return [int(o) for o in outputs]

    def content(self, path):
        return self.debugfs("cat %s" % path, binary=True)


class Tree:
    """Todo lo que hay en la imagen, recorriendo desde la raíz."""

    def __init__(self, image):
        self.dirs = []      # (path, inodo)
        self.files = []     # (path, inodo, tamaño)
        self._walk(image, "/", ROOT_INODE)

    def _walk(self, image, path, inode):
        self.dirs.append((path, inode))
        for number, is_dir, name, size in image.list_dir(path):
            if name in (".", ".."):
                continue
            child = path.rstrip("/") + "/" + name
            if is_dir:
                self._walk(image, child, number)
            else:
                self.files.append((child, number, size))

    def inodes(self):
        return [(p, n) for p, n in self.dirs] + [(p, n) for p, n, _ in self.files]


# ---------------------------------------------------------------------
# La implementación, vista por probe_hdd
# ---------------------------------------------------------------------

class ProbeFailure(Exception):
    pass


class ProbeHang(ProbeFailure):
    pass


class Probe:
    def __init__(self, binary, image):
        self.base = [binary, image.path, str(image.partition)]

    def __call__(self, *args):
        try:
            r = subprocess.run(self.base + [str(a) for a in args],
                               capture_output=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            raise ProbeHang("se colgó (más de %d s): ¿un loop infinito?" % TIMEOUT)
        if r.returncode < 0:
            raise ProbeFailure("se cayó con la señal %d%s" % (-r.returncode, stderr_tail(r)))
        if r.returncode != 0:
            raise ProbeFailure("terminó con código %d%s" % (r.returncode, stderr_tail(r)))
        return r.stdout.decode().strip()


def stderr_tail(r):
    lines = r.stderr.decode(errors="replace").strip().splitlines()
    if not lines:
        return ""
    return "\n       " + "\n       ".join(lines[-5:])


# ---------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------

class Group:
    def __init__(self, title):
        self.title = title
        self.cases = 0
        self.failures = []
        self.hangs = 0
        self.skipped = 0
        print("=== %s ===" % title)
        sys.stdout.flush()

    def case(self, description, check):
        """Corre un caso. check() devuelve None si está bien, o un texto
        explicando la diferencia."""
        self.cases += 1
        if self.hangs >= MAX_HANGS:
            # Cada cuelgue tarda TIMEOUT segundos: no tiene sentido seguir.
            self.skipped += 1
            self.failures.append((description, "salteado"))
            return
        try:
            difference = check()
        except ProbeHang as e:
            self.hangs += 1
            difference = str(e)
        except ProbeFailure as e:
            difference = str(e)
        if difference is not None:
            self.failures.append((description, difference))
            if len(self.failures) <= MAX_SHOWN_FAILURES:
                print("  FALLA: %s\n       %s" % (description, difference))
                sys.stdout.flush()

    def close(self):
        failed = len(self.failures) - self.skipped
        shown = min(failed, MAX_SHOWN_FAILURES)
        if failed > shown:
            print("  ... y %d fallas más" % (failed - shown))
        if self.skipped:
            print("  se saltearon los %d casos restantes después de %d cuelgues"
                  % (self.skipped, MAX_HANGS))
        print("  %d/%d casos bien\n" % (self.cases - len(self.failures), self.cases))
        return not self.failures


def compare_inodes(expected, hex_output):
    if hex_output == "NULL":
        return "devolvió NULL"
    actual = bytes.fromhex(hex_output)
    if actual == expected:
        return None
    if len(actual) != len(expected):
        return "devolvió %d bytes, esperaba %d" % (len(actual), len(expected))
    fmt = "<" + "".join(t for _, t in INODE_FIELDS)
    names = [n for n, _ in INODE_FIELDS]
    different = ["%s: esperaba %d, devolvió %d" % (n, e, a)
                 for n, e, a in zip(names, struct.unpack(fmt, expected),
                                    struct.unpack(fmt, actual)) if e != a]
    return "; ".join(different[:4]) + (" ..." if len(different) > 4 else "")


def block_kind(image, logical):
    if logical < 12:
        return "directo"
    if logical < 12 + image.addrs_per_block:
        return "indirecto simple"
    return "indirecto doble"


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------

def test_image(image, probe, tree):
    g = Group("Imagen: superbloque y block groups (código provisto)")

    def superblock():
        actual = bytes.fromhex(probe("superblock"))
        if actual != image.superblock:
            return "el superbloque leído no coincide con el del disco"

    def groups():
        actual = [bytes.fromhex(l) for l in probe("groups").splitlines()]
        if len(actual) != len(image.groups):
            return "%d block groups, esperaba %d" % (len(actual), len(image.groups))
        for i, (a, e) in enumerate(zip(actual, image.groups)):
            if a != e:
                return "el descriptor del block group %d no coincide" % i

    g.case("superbloque", superblock)
    g.case("descriptores de block groups", groups)
    return g.close()


def test_load_inode(image, probe, tree):
    g = Group("Ejercicio 1: load_inode")
    for path, number in tree.inodes():
        expected = image.inode(number)
        g.case("inodo %d (%s)" % (number, path),
               lambda: compare_inodes(expected, probe("inode", number)))
    return g.close()


def test_get_block_address(image, probe, tree):
    g = Group("Ejercicio 2: get_block_address")
    for path, number in tree.inodes():
        inode = image.inode(number)
        expected = image.blocks(number, struct.unpack_from("<I", inode, 4)[0])
        if not expected:
            continue

        def check():
            actual = [int(x) for x in probe("addresses", inode.hex(), len(expected)).split()]
            for logical, (e, a) in enumerate(zip(expected, actual)):
                if e != a:
                    return "bloque lógico %d (%s): esperaba %d, devolvió %d" % (
                        logical, block_kind(image, logical), e, a)
            if len(actual) != len(expected):
                return "devolvió %d direcciones, esperaba %d" % (len(actual), len(expected))

        g.case("%s (%d bloques)" % (path, len(expected)), check)
    return g.close()


def test_get_file_inode_from_dir_inode(image, probe, tree):
    g = Group("Ejercicio 3: get_file_inode_from_dir_inode")

    for path, number in tree.dirs:
        directory = image.inode(number).hex()
        entries = image.list_dir(path)
        existing = {name for _, _, name, _ in entries}

        # Cada entrada del directorio tiene que encontrarse.
        for child, _, name, _ in entries:
            expected = image.inode(child)
            g.case("buscar %r en %s" % (name, path),
                   lambda: compare_inodes(expected, probe("lookup", directory, name)))

        # Y estos no: las entradas borradas, y variantes de los nombres que
        # existen (un caracter de menos o de más).
        missing = {n for _, _, n, _ in image.list_dir(path, deleted=True)}
        for name in existing - {".", ".."}:
            missing |= {name[:-1], name + "x"}
        missing -= existing
        missing.discard("")
        for name in sorted(missing):
            def check():
                if probe("lookup", directory, name) != "NULL":
                    return "esperaba NULL, devolvió un inodo"
            g.case("buscar %r en %s (no existe)" % (name, path), check)

    # from == NULL busca en la raíz.
    for child, _, name, _ in image.list_dir("/"):
        expected = image.inode(child)
        g.case("buscar %r desde NULL (la raíz)" % name,
               lambda: compare_inodes(expected, probe("lookup", "NULL", name)))

    # open() resuelve paths completos con la función del ejercicio.
    for path, _, _ in tree.files:
        def check():
            fd = int(probe("open", path))
            if fd < 0:
                return "open() devolvió %d" % fd
        g.case("open(%s)" % path, check)

    some_file = tree.files[0][0]
    for path in ["/noexiste", "/noexiste" + some_file, some_file + "/noexiste"]:
        def check():
            fd = int(probe("open", path))
            if fd >= 0:
                return "open() devolvió %d, esperaba -1" % fd
        g.case("open(%s) (no existe)" % path, check)

    return g.close()


def test_e2e(image, probe, tree):
    g = Group("End to end: leer todos los archivos con open() y read()")
    for path, _, size in tree.files:
        def check():
            output = probe("read", path, size)
            if output == "NOT_FOUND":
                return "open() devolvió -1"
            actual = bytes.fromhex(output)
            expected = image.content(path)
            if actual == expected:
                return None
            for i, (a, e) in enumerate(zip(actual, expected)):
                if a != e:
                    logical = i // image.block_size
                    return "difiere desde el byte %d (bloque lógico %d, %s)" % (
                        i, logical, block_kind(image, logical))
            return "leyó %d bytes, esperaba %d" % (len(actual), len(expected))
        g.case("%s (%d bytes)" % (path, size), check)
    return g.close()


# En orden: cada ejercicio se apoya en los anteriores.
TESTS = [
    ("imagen", "imagen", test_image),
    ("ej1", "ejercicio 1", test_load_inode),
    ("ej2", "ejercicio 2", test_get_block_address),
    ("ej3", "ejercicio 3", test_get_file_inode_from_dir_inode),
    ("e2e", "end to end", test_e2e),
]


def main():
    names = ["all"] + [name for name, _, _ in TESTS]
    if len(sys.argv) not in (3, 4) or (len(sys.argv) == 4 and sys.argv[3] not in names):
        sys.exit("Uso: %s probe_hdd imagen.raw [%s]" % (sys.argv[0], "|".join(names)))
    selected = sys.argv[3] if len(sys.argv) == 4 else "all"

    image = Image(sys.argv[2])
    probe = Probe(sys.argv[1], image)
    tree = Tree(image)

    to_run = [t for t in TESTS if selected in ("all", t[0])]
    for i, (name, label, test) in enumerate(to_run):
        if test(image, probe, tree):
            continue
        print("Fallaron los tests de: %s." % label)
        pending = [l for _, l, _ in to_run[i + 1:]]
        if pending:
            # Los ejercicios se implementan en orden: si uno falla, los
            # siguientes también van a fallar.
            print("Se detuvo la corrida: faltan correr los tests de %s." % ", ".join(pending))
            print("Cada ejercicio se apoya en los anteriores, así que esos tests también")
            print("fallarían. Arreglá lo que falló y volvé a correr make test.")
        sys.exit(1)

    print("Todos los tests pasaron.")


if __name__ == "__main__":
    main()

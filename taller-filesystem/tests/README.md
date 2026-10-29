# Tests del taller (para docentes)

| Archivo | Qué es |
| --- | --- |
| `test_hdd.py` | Los tests. Comparan la implementación contra `debugfs`. |
| `probe_hdd.cpp` | Binario chico que se compila con `src/` y muestra lo que devuelve cada función de `Ext2FS`. No verifica nada. |
| `gen_hdd.py` | Genera `hdd.raw` con los casos que nos interesan. |
| `hdd.raw` | La imagen de disco: un MBR con una partición ext2 que empieza en el sector 2048. |

```
make test                        corre los tests contra src/
make test SRC_DIR=src-solucion   contra la solución de la cátedra
make hdd                         regenera hdd.raw
make debugfs CMD="ls -l /"        corre un comando de debugfs sobre la imagen
```

Todo corre adentro de la VM, porque usa `debugfs` y `mke2fs` (e2fsprogs, que ya
vienen en la imagen base de Debian).

## Filosofía

- **No hay valores esperados escritos a mano ni pre-generados.** La respuesta
  correcta sale de `debugfs`, una implementación de ext2 independiente de la
  nuestra, consultada en el momento sobre la misma imagen. Los tests funcionan
  con cualquier `hdd.raw` que genere `gen_hdd.py`.
- **Se recorre todo el filesystem**, no casos sueltos. Si la implementación no
  puede leer algún inodo, bloque, entrada o archivo de la imagen, falla.
- **La solución no queda expuesta.** Los alumnos ven los tests, pero ahí no hay
  ningún lector de ext2: solo llamadas a `debugfs` y a `probe_hdd`.
- **Siempre con sanitizers.** `probe_hdd` se compila con ASan y UBSan, y corre
  con la detección de leaks prendida. Una lectura fuera de un bloque, un uso de
  memoria liberada o un buffer sin su `delete[]` hacen fallar el caso, aunque
  el resultado sea correcto. Los tests tardan el doble, pero en un taller vale
  la pena.
- **Un error no corta la corrida.** Cada consulta a la implementación es una
  invocación separada de `probe_hdd`, con un timeout de 5 segundos. Si se cae
  (segfault, `assert`, error de ASan) o se cuelga, se informa en ese caso y se
  sigue con el siguiente. Después de 3 cuelgues en un mismo grupo se saltea el
  resto del grupo, para no esperar 5 segundos por cada caso.
- **Los ejercicios se corren en orden.** `make test` corre `imagen`, `ej1`,
  `ej2`, `ej3` y `e2e`, y se detiene en el primer grupo que falla, avisando qué
  grupos quedaron sin correr: los ejercicios se implementan en orden y cada uno
  se apoya en los anteriores. `make test-ejN` corre un solo grupo.
- **La imagen tiene los casos por construcción.** `gen_hdd.py` arma cada caso a
  propósito y verifica, mientras genera, lo que depende del allocator de ext2
  (por ejemplo, que los bloques queden no contiguos). Los tests no vuelven a
  chequear que la imagen tenga los casos.

## Qué prueba cada grupo

| Grupo | Para cada... | Compara contra |
| --- | --- | --- |
| `imagen` | superbloque y block group descriptor | los bytes del disco (es código provisto) |
| `ej1` | inodo en uso | sus bytes en la tabla de inodos (`debugfs imap` dice dónde están) |
| `ej2` | bloque lógico de cada archivo y directorio | `debugfs bmap` |
| `ej3` | entrada de cada directorio, más nombres que no existen | `debugfs ls` y el inodo de la entrada |
| `e2e` | archivo regular, leído con `open()` + `read()` | `debugfs cat` |

`ej2` no depende de `ej1`: el inodo que recibe `get_block_address()` lo arma
`probe_hdd` a partir de los bytes que da `debugfs`. Lo mismo pasa con el inodo
del directorio en `ej3`, aunque ahí el resultado sí lo carga la implementación
con `load_inode()` y lee el directorio con `get_block_address()`.

Los nombres que no existen en `ej3` salen de cada directorio: las entradas
borradas (`ls -d`) y, para cada nombre existente, el mismo nombre con un
caracter de menos y con uno de más. `ej3` también prueba `open()` sobre cada
archivo y sobre tres paths inexistentes: `/noexiste`, `/noexiste/<archivo>` y
`<archivo>/noexiste` (un archivo regular usado como directorio).

## Casos que genera `gen_hdd.py`

Bloques de 1 KiB, inodos de 128 bytes, 3 block groups de 1024 bloques y 384
inodos (la tabla de inodos de cada grupo ocupa varios bloques).

| Dónde | Caso |
| --- | --- |
| `/raiz.txt`, `/vacio` | Archivo en la raíz y directorio vacío. |
| `/fragmentado/no_contiguo.txt` | 12 bloques directos **no contiguos**: se llena el directorio con archivos de un bloque, se borra uno por medio y recién ahí se escribe el archivo, que ocupa los huecos. Detecta un `block[0] + n`. |
| `/archivos/vacio.txt` | 0 bytes, ningún bloque. |
| `/archivos/un_byte.txt`, `un_bloque.txt` | 1 byte y exactamente un bloque. |
| `/archivos/directos.txt` | Exactamente los 12 bloques directos. |
| `/archivos/indirecto_simple.txt` | 13 bloques: el primero que necesita indirección simple. |
| `/archivos/fin_indirecto_simple.txt` | 268 bloques: hasta el último de la indirección simple. |
| `/archivos/indirecto_doble.txt` | 269 bloques: el primero de la indirección doble. |
| `/archivos/cruce_tabla_doble.txt` | 525 bloques: agota la primera tabla de 2do nivel y pasa a la siguiente. También queda repartido en más de un block group. |
| `/prefijos/g10`, `g11`, `g1` | `g1` está **después** de `g10` en el directorio: comparar solo el prefijo devuelve el inodo equivocado. |
| `/prefijos/archivo_largo.txt` y `archivo` | El nombre largo antes que su prefijo. |
| `/prefijos/dato` y `dato.bak` | El nombre corto antes que el largo: comparar solo `name_length` caracteres devuelve el inodo equivocado. |
| `/anidado/a/b/c/hoja.txt` | Path de varios niveles. |
| `/multibloque` | Directorio de 4 bloques, con nombres de largo fijo para saber en qué bloque cae cada entrada. |
| `/multibloque/borrada_en_el_medio...` | Borrada del medio del bloque 0: la entrada anterior agranda su `record_length` y la absorbe, pero sus bytes (nombre e inodo) quedan en el bloque. Si se avanza de a `name_length` en vez de `record_length`, se "encuentra" un archivo que no existe. |
| `/multibloque/borrada_primera_del_bloque...` | Era la primera del bloque 1: queda una entrada con `inode == 0` que hay que saltear. |
| `/multibloque/solo_en_el_ultimo_bloque...` | La única entrada del último bloque: obliga a leer todos los bloques del directorio. |
| Todos los directorios | La última entrada de cada bloque tiene el `record_length` estirado hasta el final del bloque (padding). |
| `/fragmentado/relleno_*` | Los rellenos borrados son más entradas absorbidas, como `borrada_en_el_medio`. |
| `/lost+found` | Lo crea `mke2fs`: 12 bloques con entradas vacías. |

Cada bloque de cada archivo tiene un contenido distinto (`<path> bloque <n>`
repetido), así que en `e2e` un bloque leído de la dirección equivocada
se nota.

## Cómo agregar casos

1. En `generate()` de `gen_hdd.py`, agregar archivos y directorios con
   `g.mkdir(path)`, `g.file(path, tamaño)` y `g.rm(path)`. Los comandos se
   acumulan y se ejecutan con `debugfs -w` al llamar a `g.flush()`.
2. Si el caso depende de cómo ubica las cosas ext2 (qué bloques le toca a un
   archivo, en qué bloque del directorio cae una entrada), verificarlo al final
   de `generate()` con `g.blocks(path)` o `g.entry_logical_block(dir, nombre)`.
   Así, si el caso no se da, el generador falla en vez de dejar una imagen que
   no prueba lo que creemos.
3. Si hace falta más espacio o más inodos, ajustar `FS_BLOCKS` o `INODES`.
4. `make hdd` y después `make test SRC_DIR=src-solucion`.
5. Documentar el caso en la tabla de arriba.

En general no hace falta tocar `test_hdd.py`: como recorre toda la imagen, un
archivo o directorio nuevo queda cubierto solo.

## Casos que dejamos afuera a propósito

| Caso | Por qué |
| --- | --- |
| Indirección triple | El enunciado no la pide. Haría falta un archivo de más de 64 MiB. |
| Entradas de directorio que cruzan un bloque o lo superan | En ext2 no pasa, y el enunciado lo aclara. |
| Directorios indexados (htree, `dir_index`) | La imagen se genera sin esa feature. |
| Archivos con huecos (sparse) | `get_block_address()` devolvería 0 y el enunciado no habla de eso. |
| Tamaño de bloque distinto de 1 KiB | El enunciado pide leerlo del superbloque, pero la imagen no lo ejercita. Se podría generar con `-b 2048` o `-b 4096`. |
| `inode_size` distinto de `sizeof(struct Ext2FSInode)` | Con inodos de 128 bytes coinciden, así que no se detecta si se usa `sizeof` en lugar de `inode_size` para recorrer la tabla de inodos. Se podría generar con `-I 256`. |
| Links simbólicos, dispositivos, FIFOs | El taller solo trabaja con archivos regulares y directorios. |
| Escritura | `Ext2FS::write()` no está implementado y la imagen se abre en solo lectura. |

# Taller FileSystem

> El taller se compila y se ejecuta adentro de una VM Linux que levanta el
> propio `make`. Si todavía no la preparaste, arrancá por **[VM.md](https://github.com/SSOO-Exactas-2026-2C/taller-tools/blob/main/VM.md)**:
> ahí está el setup (`make install`, `make start-vm`, `make shell`) y los
> comandos generales del entorno.

En este taller vamos a completar la implementación de un sistema de archivos
ext2 de solo lectura.

Todo el trabajo se hace en `src/ext2fs.cpp`, donde está la lógica central del
sistema de archivos. El resto de los archivos de `src/` simulan el disco
(`hdd`), la tabla de particiones (`mbr`, `pentry`) y la interfaz genérica de un
filesystem (`fs.h`). Ya están provistos y no hace falta modificarlos.

## El filesystem de la imagen

Los tests corren contra la partición ext2 de `tests/hdd.raw`, que tiene estas
características:

| | |
| --- | --- |
| Tamaño de bloque | 1024 bytes |
| Tamaño de inodo | 128 bytes |
| Block groups | 3 |
| Tamaño de una dirección de bloque | 4 bytes |

Estos valores son para que tengas una idea de cómo es el disco, pero no los
pongas fijos en el código. Calculalos a partir del superbloque o con `sizeof`:

- tamaño de bloque: `1024 << _superblock->log_block_size`
- tamaño de inodo: `_superblock->inode_size`
- cantidad de block groups: `block_groups()`
- tamaño de una dirección de bloque: `sizeof(inode->block[0])`

Cada inodo tiene un arreglo `block[15]` con las direcciones de sus bloques de
datos:

| Entradas | Tipo |
| --- | --- |
| `block[0]` a `block[11]` | Directos |
| `block[12]` | Indirecto simple |
| `block[13]` | Indirecto doble |
| `block[14]` | Indirecto triple |

## Ejercicio 1: `load_inode`

Implementar:

```cpp
struct Ext2FSInode * Ext2FS::load_inode(unsigned int inode_number);
```

Dado un número de inodo, cargar el inodo correspondiente desde la tabla de
inodos de su block group y devolver un puntero a él. Quien llama libera la
memoria con `delete[]`, así que hay que reservarla con
`new unsigned char[sizeof(struct Ext2FSInode)]`.

## Ejercicio 2: `get_block_address`

Implementar:

```cpp
unsigned int Ext2FS::get_block_address(struct Ext2FSInode * inode, unsigned int block_number);
```

Dado un inodo y un número de bloque lógico dentro del archivo (`0` es el primer
bloque de datos, `1` el segundo, etc.), devolver la dirección del bloque en el
filesystem, es decir, el valor que se le pasa a `read_block()`.

Hay que implementar el direccionamiento de ext2 para:

- bloques directos,
- indirección simple,
- indirección doble.

**No hace falta implementar la indirección triple.**

## Ejercicio 3: `get_file_inode_from_dir_inode`

Implementar:

```cpp
struct Ext2FSInode * Ext2FS::get_file_inode_from_dir_inode(struct Ext2FSInode * from, const char * filename);
```

Dado el inodo de un directorio y un nombre de archivo, buscar la entrada con
ese nombre dentro del directorio. Si existe, devolver un puntero a su inodo.
Si no existe, devolver `NULL`.

Una entrada de directorio nunca ocupa más de un bloque ni cruza el límite entre
dos bloques, así que se puede recorrer el directorio bloque por bloque.

## Cómo se corren los tests

```
make test                 todos los ejercicios
make test-imagen          disco, superbloque y block groups (no depende de los ejercicios)
make test-ej1             carga de inodos
make test-ej2             direccionamiento de bloques
make test-ej3             búsqueda en directorios (necesita los ejercicios 1 y 2)
make test-e2e             lee todos los archivos con open() y read() (necesita los 3)
```

Los tests recorren todo el filesystem de `tests/hdd.raw` y comparan lo que
devuelve tu implementación contra lo que dice `debugfs`, una herramienta de
Linux que lee filesystems ext2. Si un caso falla, el mensaje dice qué se estaba
probando y qué diferencia hubo. Si tu implementación se cuelga o se cae, el
test lo informa y sigue con los demás casos.

Los ejercicios se implementan en orden, porque cada uno se apoya en los
anteriores. Por eso `make test` se detiene en el primer ejercicio que falla y
avisa cuáles quedaron sin correr.

`debugfs` también sirve para explorar la imagen por tu cuenta, por ejemplo:

```
make debugfs CMD="ls -l /"
make debugfs CMD="stat /archivos/directos.txt"
make debugfs CMD="ls -l /multibloque"
```

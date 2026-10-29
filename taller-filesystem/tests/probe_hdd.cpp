// Consulta la implementación de Ext2FS y muestra lo que devuelve.
//
// No verifica nada: lo usa tests/test_hdd.py, que compara cada respuesta
// contra lo que dice debugfs sobre la misma imagen. Cada invocación hace una
// sola consulta, así un cuelgue o un segfault en la implementación afecta
// solo a ese caso.
//
// Uso: probe_hdd imagen.raw particion comando [argumentos...]
//
//   superblock                  bytes del superbloque, en hexa
//   groups                      bytes de cada block group descriptor, uno por línea
//   inode N                     bytes de load_inode(N), en hexa, o NULL
//   addresses INODE COUNT       get_block_address() para los bloques lógicos
//                               0..COUNT-1 del inodo (INODE: sus bytes en hexa)
//   lookup DIR NAME             bytes de get_file_inode_from_dir_inode(), o NULL
//                               (DIR: bytes del inodo del directorio en hexa,
//                               o NULL para buscar desde la raíz)
//   open PATH                   lo que devuelve open()
//   read PATH SIZE              contenido leído con open() + read(), en hexa,
//                               o NOT_FOUND si open() falla

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "hdd.h"
#include "ext2fs.h"

using namespace std;

static void print_hex(const void * data, unsigned int length)
{
	const unsigned char * bytes = (const unsigned char *) data;
	for(unsigned int i = 0; i < length; i++)
		printf("%02x", bytes[i]);
	printf("\n");
}

// Arma un inodo a partir de sus bytes en hexa. Así addresses y lookup no
// dependen de que load_inode() ande.
static void inode_from_hex(const char * hex, struct Ext2FSInode * inode)
{
	unsigned char * bytes = (unsigned char *) inode;
	memset(inode, 0, sizeof(*inode));
	for(unsigned int i = 0; i < sizeof(*inode) && hex[2 * i] && hex[2 * i + 1]; i++)
	{
		char pair[3] = { hex[2 * i], hex[2 * i + 1], '\0' };
		bytes[i] = (unsigned char) strtoul(pair, NULL, 16);
	}
}

static void print_inode(struct Ext2FSInode * inode)
{
	if(inode == NULL)
		printf("NULL\n");
	else
		print_hex(inode, sizeof(*inode));
}

int main(int argc, char ** argv)
{
	if(argc < 4)
	{
		fprintf(stderr, "Uso: %s imagen.raw particion comando [argumentos...]\n", argv[0]);
		return 2;
	}

	HDD hdd(argv[1]);
	Ext2FS fs(hdd, (unsigned char) atoi(argv[2]));
	string command = argv[3];

	if(command == "superblock" && argc == 4)
	{
		print_hex(fs.superblock(), sizeof(struct Ext2FSSuperblock));
	}
	else if(command == "groups" && argc == 4)
	{
		for(unsigned int i = 0; i < fs.block_groups(); i++)
			print_hex(fs.block_group(i), sizeof(struct Ext2FSBlockGroupDescriptor));
	}
	else if(command == "inode" && argc == 5)
	{
		struct Ext2FSInode * inode = fs.load_inode(atoi(argv[4]));
		print_inode(inode);
		delete[] (unsigned char *) inode;
	}
	else if(command == "addresses" && argc == 6)
	{
		struct Ext2FSInode inode;
		inode_from_hex(argv[4], &inode);
		unsigned int count = atoi(argv[5]);
		for(unsigned int i = 0; i < count; i++)
			printf("%u%s", fs.get_block_address(&inode, i), i + 1 < count ? " " : "");
		printf("\n");
	}
	else if(command == "lookup" && argc == 6)
	{
		struct Ext2FSInode dir;
		struct Ext2FSInode * from = NULL;
		if(strcmp(argv[4], "NULL") != 0)
		{
			inode_from_hex(argv[4], &dir);
			from = &dir;
		}
		struct Ext2FSInode * inode = fs.get_file_inode_from_dir_inode(from, argv[5]);
		print_inode(inode);
		delete[] (unsigned char *) inode;
	}
	else if(command == "open" && argc == 5)
	{
		fd_t fd = fs.open(argv[4], "r");
		printf("%d\n", fd);
		if(fd >= 0)
			fs.close(fd);
	}
	else if(command == "read" && argc == 6)
	{
		fd_t fd = fs.open(argv[4], "r");
		if(fd < 0)
		{
			printf("NOT_FOUND\n");
			return 0;
		}

		unsigned int size = atoi(argv[5]);
		unsigned char * content = new unsigned char[size + 1];
		unsigned int total = 0;
		while(total < size)
		{
			fs.seek(fd, total);
			int bytes_read = fs.read(fd, content + total, size - total);
			if(bytes_read <= 0)
				break;
			total += bytes_read;
		}
		fs.close(fd);

		print_hex(content, total);
		delete[] content;
	}
	else
	{
		fprintf(stderr, "Comando desconocido o cantidad de argumentos incorrecta: %s\n", command.c_str());
		return 2;
	}

	return 0;
}

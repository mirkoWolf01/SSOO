#include "ext2fs.h"

#include <cassert>
#include <cstring>
#include <iomanip>
#include <iostream>

#include "hdd.h"
#include "pentry.h"

Ext2FS::Ext2FS(HDD & disk, unsigned char pnumber) : _hdd(disk), _partition_number(pnumber)
{
	assert(pnumber <= 3);

	// Load Superblock
	unsigned char * buffer = new unsigned char[2 * SECTOR_SIZE];

	// Get partition info
	const PartitionEntry & pentry = _hdd[_partition_number];

	// Skip first two sectors & read 3rd and 4th sectors
	// Warning: We assume common sector size of 512 bytes but it may not be true
	_hdd.read(pentry.start_lba() + 2, buffer);
	_hdd.read(pentry.start_lba() + 3, buffer + SECTOR_SIZE);

	// Warning: this only works in Little Endian architectures
	_superblock = (struct Ext2FSSuperblock *) buffer;

	// Load Block Group Table

	// Compute amount of block groups in FS
	_block_groups = _superblock->blocks_count / _superblock->blocks_per_group;
	if((_superblock->blocks_count % _superblock->blocks_per_group) != 0)
		_block_groups++;

	// Allocate enough memory to keep the table
	_bgd_table = new Ext2FSBlockGroupDescriptor[_block_groups];

	// Since the size of the table is not forced to be a factor of SECTOR_SIZE
	// we need to compute the amount of sectors we should read and then copy
	// one by one the descriptors into the table in the appropriate order.
	unsigned int size_of_bgd_table = sizeof(Ext2FSBlockGroupDescriptor) * _block_groups;
	unsigned int bgd_table_sectors = size_of_bgd_table / SECTOR_SIZE;
	if((size_of_bgd_table % SECTOR_SIZE) != 0)
		bgd_table_sectors++;

	buffer = new unsigned char[bgd_table_sectors * SECTOR_SIZE];
	for(unsigned int i = 0; i < bgd_table_sectors; i++)
		_hdd.read(pentry.start_lba() + 4 + i, buffer + SECTOR_SIZE * i);

	// Copy descriptors into table
	for(unsigned int i = 0; i < _block_groups; i++)
		_bgd_table[i] = *((Ext2FSBlockGroupDescriptor *) (buffer + i * sizeof(Ext2FSBlockGroupDescriptor)));
	delete[] buffer;
}

unsigned int Ext2FS::blockgroup_for_inode(unsigned int inode)
{
	assert(inode > 0);
	return (inode - 1) / _superblock->inodes_per_group;
}

unsigned int Ext2FS::blockgroup_inode_index(unsigned int inode)
{
	assert(inode > 0);
	return (inode - 1) % _superblock->inodes_per_group;
}

// Free allocated memory
Ext2FS::~Ext2FS()
{
	delete[] reinterpret_cast<unsigned char *>(_superblock);
	delete[] _bgd_table;
}

struct Ext2FSSuperblock * Ext2FS::superblock()
{
	return _superblock;
}

unsigned int Ext2FS::block_groups()
{
	return _block_groups;
}

struct Ext2FSBlockGroupDescriptor * Ext2FS::block_group(unsigned int index)
{
	assert(index < _block_groups);
	return &_bgd_table[index];
}

/**
 * Helpers para imprimir en hexa sin dejar output en ese modo.
 */
static void print_hex(std::ostream & output, const char * name, unsigned int value)
{
	std::ios::fmtflags flags = output.flags();
	output << name << ": 0x" << std::hex << value << std::endl;
	output.flags(flags);
}

static void print_hex_bytes(std::ostream & output, const char * name, const unsigned char * bytes, unsigned int count)
{
	std::ios::fmtflags flags = output.flags();
	char fill = output.fill('0');
	output << name << ": " << std::hex;
	for(unsigned int i = 0; i < count; i++)
		output << std::setw(2) << (unsigned int) bytes[i];
	output << std::endl;
	output.fill(fill);
	output.flags(flags);
}

std::ostream & operator<<(std::ostream & output, const struct Ext2FSInode & inode)
{
	print_hex(output, "mode", inode.mode);
	output << "uid: " << inode.uid << std::endl;
	output << "size: " << inode.size << std::endl;
	output << "atime: " << inode.atime << std::endl;
	output << "ctime: " << inode.ctime << std::endl;
	output << "mtime: " << inode.mtime << std::endl;
	output << "dtime: " << inode.dtime << std::endl;
	output << "gid: " << inode.gid << std::endl;
	output << "links_count: " << inode.links_count << std::endl;
	output << "blocks: " << inode.blocks << std::endl;
	print_hex(output, "flags", inode.flags);
	output << "os_dependant_1: " << inode.os_dependant_1 << std::endl;

	for(unsigned int i = 0; i < 15; i++)
		output << "block[" << i << "]: " << inode.block[i] << std::endl;

	output << "generation: " << inode.generation << std::endl;
	output << "file_acl: " << inode.file_acl << std::endl;
	output << "directory_acl: " << inode.directory_acl << std::endl;
	output << "faddr: " << inode.faddr << std::endl;
	for(unsigned int i = 0; i < 3; i++)
		output << "os_dependant_2[" << i << "]: " << inode.os_dependant_2[i] << std::endl;

	return output;
}

std::ostream & operator<<(std::ostream & output, const struct Ext2FSSuperblock & superblock)
{
	output << "inodes_count: " << superblock.inodes_count << std::endl;
	output << "blocks_count: " << superblock.blocks_count << std::endl;
	output << "reserved_blocks_count: " << superblock.reserved_blocks_count << std::endl;
	output << "free_blocks_count: " << superblock.free_blocks_count << std::endl;
	output << "free_inodes_count: " << superblock.free_inodes_count << std::endl;
	output << "first_data_block: " << superblock.first_data_block << std::endl;
	output << "log_block_size: " << superblock.log_block_size << std::endl;
	output << "log_fragment_size: " << superblock.log_fragment_size << std::endl;
	output << "blocks_per_group: " << superblock.blocks_per_group << std::endl;
	output << "fragments_per_group: " << superblock.fragments_per_group << std::endl;
	output << "inodes_per_group: " << superblock.inodes_per_group << std::endl;
	output << "mount_time: " << superblock.mount_time << std::endl;
	output << "write_time: " << superblock.write_time << std::endl;
	output << "mount_count: " << superblock.mount_count << std::endl;
	output << "max_mount_count: " << superblock.max_mount_count << std::endl;
	print_hex(output, "magic_bytes", superblock.magic_bytes);
	output << "state: " << superblock.state << std::endl;
	output << "errors: " << superblock.errors << std::endl;
	output << "minor_revision_level: " << superblock.minor_revision_level << std::endl;
	output << "lastcheck: " << superblock.lastcheck << std::endl;
	output << "checkinterval: " << superblock.checkinterval << std::endl;
	output << "creator_os: " << superblock.creator_os << std::endl;
	output << "revision_level: " << superblock.revision_level << std::endl;
	output << "default_reserved_userid: " << superblock.default_reserved_userid << std::endl;
	output << "default_reserved_groupid: " << superblock.default_reserved_groupid << std::endl;
	// -- EXT2_DYNAMIC_REV Specific --
	output << "first_inode: " << superblock.first_inode << std::endl;
	output << "inode_size: " << superblock.inode_size << std::endl;
	output << "block_group_number: " << superblock.block_group_number << std::endl;
	print_hex(output, "feature_compatibility", superblock.feature_compatibility);
	print_hex(output, "feature_incompatibility", superblock.feature_incompatibility);
	print_hex(output, "readonly_feature_compatibility", superblock.readonly_feature_compatibility);
	print_hex_bytes(output, "uuid", (const unsigned char *) superblock.uuid, sizeof(superblock.uuid));
	output << "volume_name: ";
	for(int i = 0; i < 16; i++)
		output << superblock.volume_name[i];
	output << std::endl;
	output << "last_mounted: ";
	for(int i = 0; i < 64; i++)
		output << superblock.last_mounted[i];
	output << std::endl;
	print_hex(output, "algo_bitmap", superblock.algo_bitmap);
	// Performance hints
	output << "prealloc_blocks: " << (unsigned int) superblock.prealloc_blocks << std::endl;
	output << "prealloc_dir_blocks: " << (unsigned int) superblock.prealloc_dir_blocks << std::endl;
	// Journaling support
	print_hex_bytes(output, "journal_uuid", (const unsigned char *) superblock.journal_uuid, sizeof(superblock.journal_uuid));
	output << "journal_inode: " << superblock.journal_inode << std::endl;
	output << "journal_device: " << superblock.journal_device << std::endl;
	output << "last_orphan: " << superblock.last_orphan << std::endl;
	// Directory indexing support
	print_hex_bytes(output, "hash_seed", (const unsigned char *) superblock.hash_seed, sizeof(superblock.hash_seed));
	output << "default_hash_version: " << (unsigned int) superblock.default_hash_version << std::endl;
	// Other options
	print_hex(output, "default_mount_options", superblock.default_mount_options);
	output << "first_meta_bg: " << superblock.first_meta_bg << std::endl;

	return output;
}

std::ostream & operator<<(std::ostream & output, const struct Ext2FSBlockGroupDescriptor & bg_descriptor)
{
	output << "block_bitmap: " << bg_descriptor.block_bitmap << std::endl;
	output << "inode_bitmap: " << bg_descriptor.inode_bitmap << std::endl;
	output << "inode_table: " << bg_descriptor.inode_table << std::endl;
	output << "free_blocks_count: " << bg_descriptor.free_blocks_count << std::endl;
	output << "free_inodes_count: " << bg_descriptor.free_inodes_count << std::endl;
	output << "used_dirs_count: " << bg_descriptor.used_dirs_count << std::endl;

	return output;
}

std::ostream & operator<<(std::ostream & output, const struct Ext2FSDirEntry & dent)
{
	output << "inode: " << dent.inode << std::endl;
	output << "record_length: " << dent.record_length << std::endl;
	output << "name_length: " << (unsigned short) dent.name_length << std::endl;
	output << "file_type: " << (unsigned short) dent.file_type << std::endl;

	// NULL terminate dent name
	char * dentname = new char[dent.name_length + 1];
	strncpy(dentname, dent.name, dent.name_length);
	dentname[dent.name_length] = '\0';

	output << "name: " << dentname << std::endl;

	delete[] dentname;

	return output;
}

/**
 * load_inode() reserva con "new unsigned char[]", así que hay que liberar
 * por el mismo camino. Un "delete inode" a secas es un mismatch.
 */
static void free_inode(struct Ext2FSInode * inode)
{
	delete[] reinterpret_cast<unsigned char *>(inode);
}

struct Ext2FSInode * Ext2FS::inode_for_path(const char * path)
{
	char * mypath = new char[strlen(path) + 1];
	mypath[strlen(path)] = '\0';
	strncpy(mypath, path, strlen(path));

	char * pathtok = strtok(mypath, PATH_DELIM);
	struct Ext2FSInode * inode = NULL;

	while(pathtok != NULL)
	{
		// Si todavía quedan componentes, el actual tiene que ser un
		// directorio. Si no, el path entero no existe (por ejemplo
		// "/grupos/g1/nota.txt/loquesea").
		if(inode != NULL && !INODE_ISDIR(inode))
		{
			free_inode(inode);
			inode = NULL;
			break;
		}

		struct Ext2FSInode * prev_inode = inode;
		inode = get_file_inode_from_dir_inode(prev_inode, pathtok);

		if(prev_inode != NULL)
			free_inode(prev_inode);

		// Este componente no existe: no seguimos. Si siguiéramos, la
		// próxima vuelta llamaría a get_file_inode_from_dir_inode(NULL,
		// ...), que por convención arranca de la raíz, y "/noexiste/grupos"
		// terminaría resolviendo a "/grupos".
		if(inode == NULL)
			break;

		pathtok = strtok(NULL, PATH_DELIM);
	}

	delete[] mypath;
	return inode;
}

unsigned int Ext2FS::blockaddr2sector(unsigned int block)
{
	// Get partition info
	const PartitionEntry & pentry = _hdd[_partition_number];

	// Compute block size by shifting the value 1024
	unsigned int block_size = 1024 << _superblock->log_block_size;
	unsigned int sectors_per_block = block_size / SECTOR_SIZE;

	return pentry.start_lba() + block * sectors_per_block;
}

void Ext2FS::read_block(unsigned int block_address, unsigned char * buffer)
{
	unsigned int block_size = 1024 << _superblock->log_block_size;
	unsigned int sectors_per_block = block_size / SECTOR_SIZE;
	for(unsigned int i = 0; i < sectors_per_block; i++)
		_hdd.read(blockaddr2sector(block_address) + i, buffer + i * SECTOR_SIZE);
}

/**
 * Warning: This method allocates memory that must be freed by the caller
 */
struct Ext2FSInode * Ext2FS::load_inode(unsigned int inode_number)
{
	// Ejercicio 1
	//
	// Dado un número de inodo, cargar y devolver un puntero al inodo
	// correspondiente.
	//
	// Pistas:
	//   - blockgroup_for_inode() y blockgroup_inode_index() ya están hechas.
	//   - El descriptor del block group (block_group(i)) dice en qué bloque
	//     empieza la tabla de inodos (campo inode_table).
	//   - ¿Cuántos inodos entran en un bloque de la tabla? ¿De dónde sale el
	//     tamaño de un inodo en disco?
	//   - read_block() lee un bloque entero a un buffer.
	//
	// Importante: la memoria que devuelvas la libera el que llama, con
	// delete[]. Reservala con "new unsigned char[sizeof(struct Ext2FSInode)]",
	// no con malloc().

	struct Ext2FSInode *inode = (struct Ext2FSInode *) new unsigned char[sizeof(struct Ext2FSInode)];

	// Number of group and index on group
	unsigned int group = blockgroup_for_inode(inode_number);
	unsigned int group_inode_index = blockgroup_inode_index(inode_number);

	// Start of our block
	unsigned int inode_table_start_dir = block_group(group)->inode_table;

	// Calculate inodes_per_block
	unsigned int block_size = (1024 << _superblock->log_block_size);
	unsigned int inode_size = _superblock->inode_size;
	unsigned int inodes_per_block = block_size / inode_size;

	// Block and offset address
	unsigned int block = inode_table_start_dir + (group_inode_index / inodes_per_block);
	unsigned int inode_offset = (group_inode_index % inodes_per_block) * inode_size;

	// Read whole block
	unsigned char *reading_buffer = new unsigned char[block_size];
	read_block(block, reading_buffer);

	// Copy the right inode and return
	memcpy(inode, reading_buffer + inode_offset, sizeof(struct Ext2FSInode));
	delete[] reading_buffer;
	
	return inode;
}

unsigned int Ext2FS::get_block_address(struct Ext2FSInode * inode, unsigned int block_number)
{
	// Si es un bloque directo, simplemente lo devuelvo.
	if(block_number < 12)
		return inode->block[block_number];

	
	// Calculo para ver si se encuentra en el primer indirecto simple.
	unsigned int block_size = (1024 << _superblock->log_block_size);

	unsigned int pointers_per_block = block_size / sizeof(unsigned int);
    unsigned int single_indirect_relative_index = block_number - 12;

	// Creo el buffer y me guardo la direccion donde se guarda.
	// El buffer contiene el array de los bloques que estaban dentro de la indireccion simple
	unsigned char* indirect_block_buffer = new unsigned char[block_size];
	unsigned int* indirect_block_addr = (unsigned int*) indirect_block_buffer;

	if(single_indirect_relative_index < pointers_per_block){
		// Leo el bloque asociado a la direccion del indirecto simple
		read_block(inode->block[12], indirect_block_buffer);

		// Dentro del bloque de punteros (porque es indirecto simple) tomo aquel del indice relativo
		unsigned int target_block_addr = indirect_block_addr[single_indirect_relative_index];

		delete[] indirect_block_buffer;
		return target_block_addr;
	}

	// Calculo para ver si esta en el indirecto doble
	unsigned int double_indirect_relative_index = single_indirect_relative_index - pointers_per_block;
	unsigned int first_level_indirect_index = double_indirect_relative_index / pointers_per_block;
	unsigned int second_level_indirect_index = double_indirect_relative_index % pointers_per_block;

	if(double_indirect_relative_index < (pointers_per_block * pointers_per_block)){
		// Leo el bloque de indireccion doble
		read_block(inode->block[13], indirect_block_buffer);
		unsigned int first_level_block_addr = indirect_block_addr[first_level_indirect_index];

		// Dentro del bloque de indireccion doble, leo el bloque indirecto y tomo aquel de indice relativo.
		read_block(first_level_block_addr, indirect_block_buffer);
		unsigned int second_level_block_addr = indirect_block_addr[second_level_indirect_index];

		delete[] indirect_block_buffer;
		return second_level_block_addr;
	}

	delete[] indirect_block_buffer;
	return 0;
}

struct Ext2FSInode * Ext2FS::get_file_inode_from_dir_inode(struct Ext2FSInode * from, const char * filename)
{
	// Si from es NULL arrancamos de la raíz. En ese caso el inodo lo
	// cargamos acá, así que también lo liberamos acá.
	bool from_is_root = (from == NULL);
	if(from_is_root)
		from = load_inode(EXT2_RDIR_INODE_NUMBER);
	assert(INODE_ISDIR(from));

	struct Ext2FSInode * result = NULL;

	unsigned int block_size = (1024 << _superblock->log_block_size);
	unsigned int filename_len = strlen(filename);

	unsigned char* block_buffer = new unsigned char[block_size];

	// Leo las entradas de la carpeta de a cachos (de tamaño de un bloque)
	// Por cada bloque compuesto por dir_entrys me fijo cual de todos ellos tiene el nombre que coincide con filename
	unsigned int total_bytes_read = 0, current_block_idx = 0;
	while(total_bytes_read < from->size && result == NULL){
		// Calculo la direccion del bloque a leer y la leo.
		unsigned int current_block_addr = get_block_address(from, current_block_idx);
		read_block(current_block_addr, block_buffer);

		unsigned int block_read_offset = 0;
		while(total_bytes_read < from->size && block_read_offset < block_size){
			// Dentro del bloque leido, me fijo que entrada de direcorio es la que busco y la guardo en result en tal caso.
			struct Ext2FSDirEntry* dir_entry = (struct Ext2FSDirEntry*) (block_buffer + block_read_offset);

			if(dir_entry->inode != 0 && dir_entry->name_length == filename_len && strncmp(dir_entry->name, filename, filename_len) == 0){
				result = load_inode(dir_entry->inode);
				break;
			}

			// Paso a la siguiente entrada del bloque actual.
			block_read_offset += dir_entry->record_length;
			total_bytes_read += dir_entry->record_length;
		}
		
		// Paso a leer el siguiente bloque de dir_entries de la carpeta
		current_block_idx++;
	}

	delete[] block_buffer;

	if(from_is_root)
		free_inode(from);

	return result;
}

fd_t Ext2FS::get_free_fd()
{
	for(fd_t fd = 0; fd < EXT2_MAX_OPEN_FILES; fd++)
	{
		// Warning: This is inefficient
		if(!(_fd_status[fd / sizeof(unsigned int)] & (1 << (fd % sizeof(unsigned int)))))
			return fd;
	}
	return -1;
}

void Ext2FS::mark_fd_as_used(fd_t fd)
{
	_fd_status[fd / sizeof(unsigned int)] |= (1 << (fd % sizeof(unsigned int)));
}

void Ext2FS::mark_fd_as_free(fd_t fd)
{
	_fd_status[fd / sizeof(unsigned int)] ^= (1 << (fd % sizeof(unsigned int)));
}

fd_t Ext2FS::open(const char * path, const char * mode)
{
	fd_t new_fd = get_free_fd();
	if(new_fd < 0)
		return -1;
	mark_fd_as_used(new_fd);

	// We ignore mode
	struct Ext2FSInode * inode = inode_for_path(path);
	if(inode == NULL)
	{
		mark_fd_as_free(new_fd);
		return -1;
	}

	_open_files[new_fd] = *inode;
	free_inode(inode);
	_seek_memory[new_fd] = 0;

	return new_fd;
}

int Ext2FS::read(fd_t filedesc, unsigned char * buffer, int size)
{
	int realsize = ((_seek_memory[filedesc] + size) >= _open_files[filedesc].size) ? _open_files[filedesc].size - _seek_memory[filedesc] : size;
	if(realsize > 0)
	{
		int seek = _seek_memory[filedesc];
		int read = 0;

		// Compute block size by shifting the value 1024
		unsigned int block_size = 1024 << _superblock->log_block_size;

		unsigned int start_block = seek / block_size;
		unsigned int end_block = (seek + realsize - 1) / block_size;

		unsigned char * block_buf = new unsigned char[block_size];
		for(unsigned int block = start_block; block <= end_block; block++)
		{
			unsigned int block_address = get_block_address(&_open_files[filedesc], block);
			read_block(block_address, block_buf);

			do
			{
				buffer[read++] = block_buf[seek++ % block_size];
			} while(((seek % block_size) != 0) && (read < realsize));
		}
		delete[] block_buf;
	}
	return realsize;
}

int Ext2FS::write(fd_t filedesc, const unsigned char * buffer, int size)
{
	return -1;
}

int Ext2FS::seek(fd_t filedesc, int offset)
{
	int position = offset;
	if(offset < 0)
		position = _open_files[filedesc].size + offset;
	if(position >= (int) _open_files[filedesc].size)
		position = _open_files[filedesc].size - 1;
	_seek_memory[filedesc] = position;
	return position;
}

int Ext2FS::tell(fd_t filedesc)
{
	return _seek_memory[filedesc];
}

void Ext2FS::close(fd_t filedesc)
{
	mark_fd_as_free(filedesc);
}

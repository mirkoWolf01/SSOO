#include "mbr.h"

#include <assert.h>
#include <string.h>

#define BOOTCODE_SIZE    446
#define SIGNATURE_OFFSET 510

MBR::MBR(const unsigned char * data) : raw_data(data)
{
}

PartitionEntry MBR::operator[](unsigned int partition_index) const
{
	assert(partition_index <= 3);

	return PartitionEntry(this->raw_data + BOOTCODE_SIZE + partition_index * PENTRY_SIZE);
}

unsigned short MBR::signature() const
{
	// Ojo con los paréntesis: "(unsigned short *) raw_data + 510"
	// avanza 510 *shorts*, no 510 bytes.
	unsigned short signature;
	memcpy(&signature, this->raw_data + SIGNATURE_OFFSET, sizeof(signature));
	return signature;
}

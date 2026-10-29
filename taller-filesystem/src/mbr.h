#ifndef __MBR_H__
#define __MBR_H__

#include "pentry.h"

class MBR
{
public:
	MBR(const unsigned char * data);
	PartitionEntry operator[](unsigned int partition_index) const;
	unsigned short signature() const;

private:
	const unsigned char * raw_data;
};

#endif

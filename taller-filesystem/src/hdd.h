#ifndef __HDD_H__
#define __HDD_H__

#include <stdio.h>

#include "pentry.h"

#define SECTOR_SIZE 512

// Error codes
#define HDD_SUCCESS                 0
#define HDD_ERROR_GENERAL_ERROR    -1
#define HDD_ERROR_DISK_ISNT_OPEN   -2
#define HDD_ERROR_DISK_ALREDY_OPEN -3

// HDD Interface
class HDD
{
public:
	HDD(const char * filename);
	~HDD();

	int read(unsigned int lba, unsigned char * buffer) const;
	int write(unsigned int lba, const unsigned char * buffer);

	PartitionEntry operator[](unsigned int index) const;

private:
	int open(const char * filename);
	int close();

	FILE * hdd_fp;
};

#endif

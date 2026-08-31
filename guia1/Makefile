CC = gcc
CFLAGS = -g -Wall -Wextra -Werror -pedantic


SRCS = $(wildcard *.c)
TARGETS = $(patsubst %.c,%,$(SRCS))

.PHONY: all clean

all: $(TARGETS)

%: %.c
	$(CC) $(CFLAGS) $< -o $@

clean:
	@rm -f $(TARGETS)
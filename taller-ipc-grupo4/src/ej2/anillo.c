/*
 * Ejercicio 2: One ring to rule them all (template).
 *
 * Se corre con: make run-anillo N=<n> S=<s> C=<c> P=<p>
 *
 *   n : cantidad de procesos del anillo (n >= 3)
 *   s : cuál de los hijos es el distinguido, el que arranca (1 <= s <= n)
 *   c : valor inicial del mensaje
 *   p : cota; el anillo para cuando el distinguido recibe un valor >= p (p > c)
 *
 * El parseo y la validación de los parámetros ya están resueltos: lo que
 * falta es armar el anillo de pipes, crear los hijos y programar la
 * ronda.
 */
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define READ 0
#define WRITE 1

static void usage(const char *prog)
{
	fprintf(stderr, "uso: %s <n> <s> <c> <p>\n", prog);
	fprintf(stderr, "  n : cantidad de procesos del anillo (n >= 3)\n");
	fprintf(stderr, "  s : hijo distinguido, el que arranca (1 <= s <= n)\n");
	fprintf(stderr, "  c : valor inicial del mensaje\n");
	fprintf(stderr, "  p : cota, tiene que ser mayor que c\n");
}

/* strtol con todos los chequeos puestos: que haya algún dígito, que no
 * sobre basura al final y que entre en un int. */
static int parse_int(const char *text, int *out)
{
	char *end;
	long value;

	errno = 0;
	value = strtol(text, &end, 10);
	if (end == text || *end != '\0')
		return -1;
	if (errno == ERANGE || value < INT_MIN || value > INT_MAX)
		return -1;

	*out = (int)value;
	return 0;
}

void rutina_hijo(int (*pipes)[2], int* pipe_padre, int n, int idx, int leader, int p){
	int next = (idx + 1) % n;
	int read_pipe = pipes[idx % n][READ];
	int write_pipe = pipes[next][WRITE];

	for(int i = 0; i < n; i++){
		if(i != idx)
			close(pipes[i][READ]);
		if(i != next)
			close(pipes[i][WRITE]);
		
	}

	while(1){
		int msg; 
		if(read(read_pipe, &msg, sizeof(msg)) == 0)
			break;
		
		printf("HIJO %d PID %d NUM %d\n", idx + 1, getpid(), msg);
		fflush(stdout);

		if(idx == leader && msg >= p){
			write(pipe_padre[WRITE], &msg, sizeof(msg));

			close(pipes[idx][READ]);
			close(pipe_padre[WRITE]);
			break;
		}

		msg++;
		write(write_pipe, &msg, sizeof(msg));
	}
	close(read_pipe);
	close(write_pipe);
	_exit(EXIT_SUCCESS);
}

int main(int argc, char **argv)
{
	int n, s, c, p, leader;

	if (argc != 5) {
		usage(argv[0]);
		return EXIT_FAILURE;
	}
	if (parse_int(argv[1], &n) < 0 || parse_int(argv[2], &s) < 0 ||
	    parse_int(argv[3], &c) < 0 || parse_int(argv[4], &p) < 0) {
		fprintf(stderr, "error: los cuatro parámetros tienen que ser números enteros\n");
		usage(argv[0]);
		return EXIT_FAILURE;
	}
	if (n < 3) {
		fprintf(stderr, "error: el anillo necesita al menos 3 procesos (n = %d)\n", n);
		return EXIT_FAILURE;
	}
	if (s < 1 || s > n) {
		fprintf(stderr, "error: s tiene que estar entre 1 y %d (s = %d)\n", n, s);
		return EXIT_FAILURE;
	}
	if (p <= c) {
		fprintf(stderr, "error: p tiene que ser mayor que c (c = %d, p = %d)\n", c, p);
		return EXIT_FAILURE;
	}

	/* Adentro trabajamos con índices desde 0; el enunciado numera los
	 * hijos desde 1, y así se imprimen. */
	leader = s - 1;

	/* TODO: crear los pipes del anillo. */
	int pipe_padre[2]; 
	pipe(pipe_padre);

	int (*pipes)[2] = calloc(n, sizeof(int[2]));
	for(int i = 0; i < n; i++)
		pipe(pipes[i]);
	
	/* TODO: crear los n hijos. */
	for(int i = 0; i < n; i++){
		if(fork() != 0)
			continue;
		if(i != leader){
			close(pipe_padre[WRITE]);
		}
		close(pipe_padre[READ]);
		rutina_hijo(pipes, pipe_padre, n, i, leader, p);
	}

	/* TODO: inyectar el valor inicial. */
	write(pipes[leader][WRITE], &c, sizeof(c));

	for(int i = 0; i < n; i++){
		close(pipes[i][READ]);
		close(pipes[i][WRITE]);
	}
	close(pipe_padre[WRITE]);


	/* TODO: Recibir el valor final del distinguido, esperar a que terminen
	 *       todos los hijos e imprimir el resultado final.
	 */
	for(int i = 0; i < n; i++)
		wait(NULL);
	
	int msg;
	read(pipe_padre[READ], &msg, sizeof(int));
	printf("PADRE RESULTADO %d\n", msg);

	close(pipe_padre[READ]);
	free(pipes);
	return EXIT_SUCCESS;
}

/*
 * Ejercicio 1: una mini shell (template).
 *
 * Se corre con: make run-minishell
 *
 * Abre un prompt, lee comandos de a una línea y los ejecuta, igual que
 * lo haría cualquier shell. Cada línea puede ser un solo programa con
 * sus argumentos, o varios unidos por pipes:
 *
 *     minishell> ls -al
 *     minishell> seq 1 10 | tail -n 3 | wc -l
 *
 * Se sale con Ctrl-D (fin de archivo) o con Ctrl-C.
 *
 * El main() y el parser ya están resueltos: lo que falta es
 * run_pipeline() y run_cmd(). Los comentarios numerados marcan un
 * orden posible.
 *
 * OJO: no se puede usar system() para resolver esto.
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include "parser.h"

#define READ 0
#define WRITE 1

#define PROMPT "minishell> "

/*
 * El código que corre cada proceso hijo: acomoda su entrada y su salida,
 * cierra lo que no usa, y se convierte en el programa pedido. Esta
 * función no vuelve nunca.
 *
 * El comando i-ésimo: ¿De qué pipe lee? ¿A cuál escribe?
 */
static void run_cmd(char **argv, int (*pipes)[2], int count, int i)
{
	/* 1. Conectar la entrada y la salida de este comando donde
	 *    corresponda. ¿Qué tienen de distinto la primera y la última? */
	if(i != 0)
		dup2(pipes[i-1][READ], STDIN_FILENO);
	if(i != count-1)
		dup2(pipes[i][WRITE], STDOUT_FILENO);

	/* 2. Este proceso heredó del fork() todos los extremos de todos los
	 *    pipes del pipeline. ¿Cuáles le sirven de acá en adelante? */

	for(int idx = 0; idx < count -1; idx++){
		close(pipes[idx][READ]);
		close(pipes[idx][WRITE]);
	}
	
	/* 3. Convertirse en el programa pedido. */
	execvp(argv[0], argv);

	/*
	 * Si el programa llegó hasta acá es porque el paso 3 falló: el
	 * comando no existe, no tiene permisos de ejecución, etc.
	 *
	 * Salimos con _exit() y no con exit() porque este proceso es una
	 * copia de la shell: exit() correría la limpieza de la shell (entre
	 * otras cosas, vaciaría los buffers de stdout heredados) y esa
	 * limpieza le toca al padre, que sigue vivo. 127 es lo que devuelve
	 * bash cuando no encuentra un comando.
	 */
	fprintf(stderr, "minishell: %s: %s\n", argv[0], strerror(errno));
	_exit(127);
}

/*
 * Ejecuta un pipeline completo y espera a que terminen todos sus comandos.
 */
static void run_pipeline(const pipeline_t *p)
{
	/* 1. Los pipes que hagan falta. Para n comandos, ¿cuántos son? Ojo
	 *    con n == 1. */
	int (*pipes)[2] = NULL;
	if(p->count > 1){
		pipes = calloc(p->count -1, sizeof(int[2]));

		for(int i = 0; i < p->count -1; i++)
			pipe(pipes[i]);
	}

	/* 2. Un proceso por comando. Cada uno corre run_cmd(). */
	for(int i = 0; i < p->count; i++){
		if(fork() != 0)
			continue;
		run_cmd(p->cmds[i], pipes, p->count, i);
	}

	/* 3. La mini shell también se quedó con extremos de esos pipes. */
	for(int i = 0; i < p->count -1; i++){
		close(pipes[i][READ]);
		close(pipes[i][WRITE]);
	}

	/* 4. Volver a mostrar el prompt recién cuando el pipeline terminó
	 *    de verdad. Evitar que se mezcle el output del comando con el
	 *    prompt. Asegurarse de limpiar la tabla de proceso. */
	for(int i = 0; i < p->count; i++)
		wait(NULL);
	free(pipes);
}

int main(void)
{
	char *line = NULL;
	size_t capacity = 0;

	/* El prompt se muestra solo si nos están hablando desde una
	 * terminal. Si nos pasan los comandos por un pipe o un archivo, la
	 * salida queda limpia (es lo mismo que hace bash). */
	int interactive = isatty(STDIN_FILENO);

	for (;;) {
		pipeline_t pipeline;

		if (interactive) {
			printf(PROMPT);
			fflush(stdout);
		}

		/* getline devuelve -1 al llegar al fin de archivo, que es lo
		 * que produce Ctrl-D en una terminal. */
		if (getline(&line, &capacity, stdin) < 0)
			break;

		if (parse_line(line, &pipeline) < 0) {
			fprintf(stderr, "minishell: error de sintaxis: "
			                "hay un pipe sin comando de algún lado\n");
			continue;
		}

		/* Una línea vacía no es un error: simplemente no hay nada que
		 * hacer y volvemos a mostrar el prompt. */
		if (pipeline.count > 0)
			run_pipeline(&pipeline);

		free_pipeline(&pipeline);
	}

	if (interactive)
		printf("\n");

	free(line);
	return 0;
}

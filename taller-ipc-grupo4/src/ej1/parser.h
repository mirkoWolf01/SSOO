/*
 * Parser de la línea de comandos de la mini shell.
 *
 * Esto te lo damos hecho: el ejercicio es sobre pipe/fork/dup2/exec, no
 * sobre pelearse con strtok. Igual leelo, que entender qué forma tiene
 * lo que te devuelve te va a ahorrar tiempo después.
 */
#ifndef PARSER_H
#define PARSER_H

/*
 * Una línea ya parseada: un pipeline de `count` comandos, donde cada
 * comando es un arreglo de argumentos terminado en NULL (o sea,
 * exactamente lo que espera execvp).
 *
 * Para la línea:
 *
 *     seq 1 10 | tail -n 3 | wc -l
 *
 * queda:
 *
 *     count   = 3
 *     cmds[0] = { "seq",  "1",  "10", NULL }
 *     cmds[1] = { "tail", "-n", "3",  NULL }
 *     cmds[2] = { "wc",   "-l",       NULL }
 */
typedef struct {
	char ***cmds;
	int count;
} pipeline_t;

/*
 * Parsea una línea de texto (con o sin el '\n' del final).
 *
 * Devuelve 0 si salió todo bien y -1 si la línea está mal formada (un
 * pipe con algún lado vacío, por ejemplo "ls |" o "| wc -l").
 *
 * Una línea vacía, o con puros espacios, NO es un error: parsea bien y
 * deja count == 0.
 *
 * Si devuelve 0, hay que liberar el resultado con free_pipeline().
 */
int parse_line(const char *line, pipeline_t *out);

/* Libera todo lo que reservó parse_line(). */
void free_pipeline(pipeline_t *p);

#endif /* PARSER_H */

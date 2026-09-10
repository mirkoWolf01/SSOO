/*
 * Parser de la línea de comandos de la mini shell. Provisto por la
 * cátedra: ver parser.h.
 *
 * La idea es simple: primero partimos la línea por los '|' para saber
 * cuántos comandos hay, y después partimos cada pedazo por espacios para
 * sacar el programa y sus argumentos.
 */
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

#include "parser.h"

/* Agranda un arreglo de punteros y le agrega un elemento al final. */
static void **push(void **array, int used, void *item)
{
	void **grown = realloc(array, sizeof(void *) * (used + 1));

	if (grown == NULL) {
		free(array);
		return NULL;
	}
	grown[used] = item;
	return grown;
}

static void free_words(char **words)
{
	int i;

	if (words == NULL)
		return;
	for (i = 0; words[i] != NULL; i++)
		free(words[i]);
	free(words);
}

/*
 * Parte un pedazo de línea en palabras separadas por espacios y las
 * devuelve en un arreglo terminado en NULL. Deja en *count cuántas
 * palabras encontró (sin contar el NULL).
 */
static char **split_words(const char *text, size_t len, int *count)
{
	char **words = NULL;
	size_t i = 0;
	int used = 0;

	*count = 0;
	while (i < len) {
		size_t start;
		char *word;

		while (i < len && isspace((unsigned char)text[i]))
			i++;
		if (i >= len)
			break;

		start = i;
		while (i < len && !isspace((unsigned char)text[i]))
			i++;

		word = strndup(text + start, i - start);
		if (word == NULL) {
			free_words(words);
			return NULL;
		}
		words = (char **)push((void **)words, used, word);
		if (words == NULL) {
			free(word);
			return NULL;
		}
		used++;
	}

	/* El NULL del final es lo que le dice a execvp dónde terminan los
	 * argumentos, así que no es opcional. */
	words = (char **)push((void **)words, used, NULL);
	if (words == NULL)
		return NULL;

	*count = used;
	return words;
}

int parse_line(const char *line, pipeline_t *out)
{
	const char *cursor = line;
	int used = 0;

	out->cmds = NULL;
	out->count = 0;

	for (;;) {
		const char *bar = strchr(cursor, '|');
		size_t len = (bar != NULL) ? (size_t)(bar - cursor) : strlen(cursor);
		char **words;
		int words_count;

		words = split_words(cursor, len, &words_count);
		if (words == NULL) {
			free_pipeline(out);
			return -1;
		}

		if (words_count == 0) {
			/* Un pedazo vacío solo se banca si la línea entera
			 * estaba vacía: "" está bien, pero "ls |" o "| wc" no. */
			free_words(words);
			if (bar == NULL && used == 0)
				return 0;
			free_pipeline(out);
			return -1;
		}

		out->cmds = (char ***)push((void **)out->cmds, used, words);
		if (out->cmds == NULL) {
			free_words(words);
			out->count = 0;
			return -1;
		}
		used++;
		out->count = used;

		if (bar == NULL)
			break;
		cursor = bar + 1;
	}

	return 0;
}

void free_pipeline(pipeline_t *p)
{
	int i;

	if (p == NULL || p->cmds == NULL) {
		if (p != NULL)
			p->count = 0;
		return;
	}
	for (i = 0; i < p->count; i++)
		free_words(p->cmds[i]);
	free(p->cmds);
	p->cmds = NULL;
	p->count = 0;
}

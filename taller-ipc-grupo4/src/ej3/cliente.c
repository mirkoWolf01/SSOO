/*
 * Ejercicio 3: el cliente del servidor HTTP de juguete (template).
 *
 * Se corre con: make run-cliente
 *
 * Lee líneas de la entrada y se las manda tal cual al servidor, después
 * muestra la respuesta:
 *
 *     $ make run-cliente
 *     > GET /hola.txt
 *     HTTP/1.1 200 OK
 *     hola mundo
 *     > Connection: close
 *     Connection: close
 *
 * Todo el cliente está resuelto salvo recv_body(), que es justamente la
 * parte interesante: como la conexión queda viva, hay que leer
 * EXACTAMENTE los bytes que dice Content-Length, ni uno más. Uno de más
 * y nos comeríamos el principio de la respuesta siguiente.
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>

#define MAX_LINE 4096
#define PROMPT "> "

/*
 * Lee del socket hasta el '\n' y devuelve la línea sin el fin de línea.
 *
 * Se lee de a un byte a propósito: si leyéramos de a bloques grandes nos
 * llevaríamos parte del cuerpo que viene después, y el cuerpo hay que
 * leerlo contando los bytes del Content-Length.
 *
 * Devuelve la cantidad de caracteres, o -1 si el servidor cerró.
 */
static ssize_t recv_line(int fd, char *out, size_t size)
{
	size_t used = 0;

	for (;;) {
		char c;
		ssize_t n = recv(fd, &c, 1, 0);

		if (n < 0) {
			if (errno == EINTR)
				continue;
			return -1;
		}
		if (n == 0)
			return -1;      /* el servidor cerró la conexión */
		if (c == '\n')
			break;
		if (c != '\r' && used < size - 1)
			out[used++] = c;
	}
	out[used] = '\0';
	return (ssize_t)used;
}

/*
 * Lee exactamente `len` bytes del socket y los escribe por salida
 * estándar (con fwrite(), y un fflush() al final para que se vean).
 *
 * Devuelve 0 si leyó los `len` bytes y -1 si el servidor cortó antes de
 * mandarlos todos. Ese -1 sube hasta el loop de main(), que termina el
 * programa: si nos quedamos a mitad de un cuerpo ya no sabemos dónde
 * empieza la respuesta siguiente, y todo lo que leamos de acá en
 * adelante va a estar corrido.
 *
 * Cosas a tener en cuenta:
 *
 *   - EXACTAMENTE `len` bytes, ni uno más. La conexión sigue viva, así
 *     que lo que viene atrás del cuerpo ya es la respuesta al pedido
 *     siguiente.
 *
 *   - recv() puede devolver MENOS bytes de los que le pediste: los datos
 *     van llegando de a chunks. Hay que insistir hasta juntar los `len`,
 *     y no confiarse de que una sola llamada alcance.
 *
 *   - `len` puede ser 0. Es lo que pasa con las respuestas sin cuerpo
 *     (un 404, un 400): no hay que leer nada.
 *
 *   - El cuerpo puede ser más grande que el buffer, así que hay que
 *     leerlo de a chunks e ir escribiendo cada chunk inmediatamente.
 *
 *   - recv() devuelve 0 cuando el servidor cerró la conexión, y -1 con
 *     errno == EINTR cuando lo interrumpió una señal. Lo primero es que
 *     se fue; lo segundo no es un error y hay que reintentar (fijate
 *     cómo lo resuelve recv_line() acá arriba).
 */
int min(int a, int b)
{
	if (a <= b)
		return a;
	return b;
}

static int recv_body(int fd, long long len)
{
    /* TODO */

	/* 1. Leer del socket de a chunks hasta juntar los `len` bytes,
	 *    pidiendo en cada recv() lo que falta pero nunca más de lo que
	 *    entra en el buffer. */
	char chunk[MAX_LINE];
	long long missing_b = len;
	if(missing_b <= 0)
		return 0;

	int n_b = recv(fd, &chunk, min(sizeof(chunk), missing_b), 0);
	if(n_b == -1)
		return -1;

	/* 2. Escribir por stdout lo que se haya leído, y descontarlo de lo
	 *    que falta. */
	fwrite(chunk, 1, n_b, stdout);
	missing_b -= n_b;

	/* 3. Vaciar el buffer de stdout: si no, la respuesta se puede
	 *    quedar sin mostrar. */
	fflush(stdout);

	recv_body(fd, missing_b);
	return 0;
}

/*
 * Lee una respuesta completa: línea de estado, headers hasta la línea en
 * blanco, y el cuerpo. Devuelve -1 si hay que cortar la conexión.
 */
static int recv_response(int fd)
{
	char line[MAX_LINE];
	long long length = 0;

	if (recv_line(fd, line, sizeof(line)) < 0)
		return -1;

	printf("%s\n", line);
	fflush(stdout);

	/* "Connection: close" no trae ni headers ni cuerpo: es la
	 * despedida del servidor, que enseguida cierra el socket. */
	if (strcmp(line, "Connection: close") == 0)
		return -1;

	/* Los headers, hasta la línea en blanco que los cierra. */
	for (;;) {
		if (recv_line(fd, line, sizeof(line)) < 0)
			return -1;
		if (line[0] == '\0')
			break;
		if (strncmp(line, "Content-Length:", 15) == 0)
			length = strtoll(line + 15, NULL, 10);
	}

	return recv_body(fd, length);
}

static int connect_to(const char *path)
{
	struct sockaddr_un addr;
	int fd;

	/* La ruta viaja adentro de sun_path, que es un arreglo de tamaño
	 * fijo (108 bytes en Linux). */
	if (strlen(path) >= sizeof(addr.sun_path)) {
		fprintf(stderr, "cliente: la ruta del socket no puede pasar de %zu "
		                "caracteres\n", sizeof(addr.sun_path) - 1);
		return -1;
	}

	fd = socket(AF_UNIX, SOCK_STREAM, 0);
	if (fd < 0) {
		perror("cliente: socket");
		return -1;
	}

	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);

	if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
		fprintf(stderr, "cliente: no me pude conectar a %s: %s\n",
		        path, strerror(errno));
		close(fd);
		return -1;
	}
	return fd;
}

int main(int argc, char **argv)
{
	char *line = NULL;
	size_t capacity = 0;
	int fd, interactive;

	if (argc != 2) {
		fprintf(stderr, "uso: %s <ruta-del-socket>\n", argv[0]);
		return EXIT_FAILURE;
	}

	fd = connect_to(argv[1]);
	if (fd < 0)
		return EXIT_FAILURE;

	/* Igual que la mini shell del ejercicio 1: el prompt se muestra
	 * solo si nos están hablando desde una terminal. */
	interactive = isatty(STDIN_FILENO);

	for (;;) {
		ssize_t len;

		if (interactive) {
			printf(PROMPT);
			fflush(stdout);
		}

		len = getline(&line, &capacity, stdin);
		if (len < 0)
			break;      /* Ctrl-D: nos vamos nosotros */

		/* Nos aseguramos de que el pedido termine en '\n', que es lo
		 * que el servidor usa para saber dónde termina. */
		if (len == 0 || line[len - 1] != '\n') {
			if (send(fd, line, (size_t)len, 0) < 0 ||
			    send(fd, "\n", 1, 0) < 0)
				break;
		} else if (send(fd, line, (size_t)len, 0) < 0) {
			break;
		}

		if (recv_response(fd) < 0)
			break;      /* el servidor cerró, o cortó la conexión */
	}

	if (interactive)
		printf("\n");

	close(fd);
	free(line);
	return EXIT_SUCCESS;
}

/*
 * Ejercicio 3: un servidor HTTP de juguete (template).
 *
 * Se corre con: make run-servidor
 *
 * Sirve archivos de texto plano de la carpeta public/ a través de un
 * socket UNIX. El protocolo está inspirado en HTTP/1.1 pero es mucho
 * más chico: el cliente manda UNA línea terminada en \n y el servidor le
 * contesta con una línea de estado, un Content-Length, una línea en
 * blanco y el cuerpo.
 *
 *     -> GET /hola.txt
 *     <- HTTP/1.1 200 OK
 *     <- Content-Length: 11
 *     <-
 *     <- hola mundo
 *
 * La conexión queda viva (keep-alive) hasta que el cliente manda
 * "Connection: close" o se va. Por eso el servidor tiene que poder
 * comunicarse con varios clientes al mismo tiempo: si no, mientras
 * atendemos a uno, los demás quedan esperando.
 *
 * El parseo del protocolo y el armado del socket ya están resueltos: lo
 * que falta es send_file() y el loop de main() que acepta conexiones y
 * las atiende.
 */
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

#define PUBLIC_DIR "public"
#define MAX_LINE 4096
#define BACKLOG 64

/* Una respuesta sin cuerpo: solo el estado y un Content-Length en cero. */
static int send_status(int fd, const char *status)
{
	char header[256];
	int len = snprintf(header, sizeof(header),
	                   "%s\nContent-Length: 0\n\n", status);


	printf("respondí con status: %s\n", status);
	fflush(stdout);

	return send(fd, header, (size_t)len, 0) < 0 ? -1 : 0;
}

/*
 * ¿La ruta pedida es segura?
 *
 * No puede contener ".." en ningún lado: si no, con "GET /../Makefile"
 * el cliente se saldría de public/ y podría leer cualquier archivo de la
 * máquina. Que empiece con '/' ya lo garantizó parse_request_line().
 */
static int path_is_safe(const char *path)
{
	const char *p;

	for (p = path; *p != '\0'; p++) {
		if (p[0] == '.' && p[1] == '.')
			return 0;
	}
	return 1;
}

/*
 * Manda por el socket el contenido de un archivo ya abierto: el cuerpo
 * de la respuesta, que va justo atrás de los headers que armó
 * send_response().
 *
 * Devuelve 0 si mandó el archivo entero y -1 si se cortó la conexión.
 * Ese -1 sube hasta handle_client(), que deja de atender a este cliente:
 * no tiene sentido seguir contestándole a alguien que ya no está.
 *
 * Cosas a tener en cuenta:
 *
 *   - El archivo puede ser más grande que la memoria, así que no se lee
 *     entero de una: se lee de a chunks en un buffer y se manda cada
 *     chunk apenas se lo tiene.
 *
 *   - fread() devuelve la cantidad de bytes que leyó, y 0 cuando ya no
 *     queda nada por leer. Ese es el final del loop.
 *
 *   - Si el cliente se fue en el medio, send() devuelve -1 (con errno ==
 *     EPIPE). No nos mata un SIGPIPE porque main() lo ignora, así que el
 *     corte hay que detectarlo mirando lo que devuelve send().
 *
 *   - El fclose() NO va acá: el archivo lo abrió send_response() y lo
 *     cierra send_response(), pase lo que pase.
 */
static int send_file(int fd, FILE *file)
{
    /* TODO */

	/* 1. Leer un chunk del archivo. */
	
	char chunk[MAX_LINE];
	int n_b = fread(&chunk, 1, sizeof(chunk), file);
	if(n_b == 0)
		return 0;
	
	/* 2. Mandarlo por el socket, atento a que el cliente se puede haber ido. */
	if(send(fd, &chunk, n_b, 0) == -1)
		return -1;

	/* 3. Repetir hasta que no quede nada por leer. */
	send_file(fd, file);
	return 0;
}

/*
 * Contesta un GET: abre el archivo dentro de public/, manda los headers
 * y después el contenido. Devuelve -1 si se cortó la conexión.
 */
static int send_response(int fd, const char *path)
{
	char full[PATH_MAX];
	char header[256];
	struct stat st;
	FILE *file;
	int len, ret;

	if (!path_is_safe(path))
		return send_status(fd, "HTTP/1.1 403 Forbidden");

	/* Si la ruta no entra en el buffer, snprintf() la trunca y nos deja
	 * el nombre de OTRO archivo, que podría existir: le terminaríamos
	 * sirviendo al cliente algo que no pidió. Cortamos acá con un 404,
	 * que es lo que contestaríamos igual: una ruta más larga que
	 * PATH_MAX no puede nombrar ningún archivo. */
	if (snprintf(full, sizeof(full), "%s%s", PUBLIC_DIR, path) >= (int)sizeof(full))
		return send_status(fd, "HTTP/1.1 404 Not Found");

	/* Que exista y que sea un archivo común: una carpeta no se puede
	 * servir como si fuera texto. */
	if (stat(full, &st) < 0 || !S_ISREG(st.st_mode))
		return send_status(fd, "HTTP/1.1 404 Not Found");

	file = fopen(full, "rb");
	if (file == NULL)
		return send_status(fd, "HTTP/1.1 404 Not Found");

	/* El Content-Length es lo que le permite al cliente saber dónde
	 * termina el cuerpo. Sin él, con keep-alive el cliente no tendría
	 * forma de distinguir el final de esta respuesta del principio de
	 * la siguiente. */
	len = snprintf(header, sizeof(header),
	               "HTTP/1.1 200 OK\nContent-Length: %lld\n\n",
	               (long long)st.st_size);
	if (send(fd, header, (size_t)len, 0) < 0) {
		fclose(file);
		return -1;
	}

	ret = send_file(fd, file);
	fclose(file);

	printf("respondí con status: HTTP/1.1 200 OK (%lld bytes)\n",
	       (long long)st.st_size);
	fflush(stdout);

	return ret;
}

/*
 * Parte la línea del pedido en verbo y ruta, modificándola en el lugar.
 * Devuelve 0 si el pedido está bien formado y -1 si no.
 *
 * Un pedido bien formado es exactamente "VERBO ruta": dos partes
 * separadas por UN espacio. Lo partimos a mano con strchr() en vez de
 * usar strtok() por dos motivos: strtok() se guarda la posición en una
 * variable global escondida, y además se come los espacios repetidos,
 * así que "GET  /hola.txt" le parecería un pedido perfectamente válido.
 */
static int parse_request_line(char *line, char **verb, char **path)
{
	char *space = strchr(line, ' ');

	/* Sin ningún espacio no hay dos partes: "hola", "GET". */
	if (space == NULL)
		return -1;

	/* Cortamos la línea en dos justo en el espacio: lo de antes es el
	 * verbo, lo de después la ruta. */
	*space = '\0';
	*verb = line;
	*path = space + 1;

	/* El verbo quedó vacío: la línea arrancaba con el espacio. */
	if ((*verb)[0] == '\0')
		return -1;

	/* La ruta tiene que ser absoluta: "GET hola.txt" no vale. De paso
	 * esto descarta la ruta vacía ("GET ") y el espacio de más ("GET
	 * /hola.txt" con dos espacios, donde la ruta arranca con uno). */
	if ((*path)[0] != '/')
		return -1;

	/* Sobra algo después de la ruta: "GET /hola.txt qué tal". */
	if (strchr(*path, ' ') != NULL)
		return -1;

	return 0;
}

/*
 * Procesa una línea del cliente. Devuelve 0 para seguir atendiéndolo y
 * -1 para cerrar la conexión.
 */
static int handle_request(int fd, char *line)
{
	char *verb, *path;

	/* "Connection: close" no es un header: en este protocolo es un
	 * mensaje en sí mismo, la forma que tiene el cliente de despedirse. */
	if (strcmp(line, "Connection: close") == 0) {
		send(fd, "Connection: close\n", strlen("Connection: close\n"), 0);
		return -1;
	}

	/* Primero la forma de la línea, después el método: una línea que
	 * no se entiende se rechaza antes de mirar qué verbo trae. */
	if (parse_request_line(line, &verb, &path) < 0)
		return send_status(fd, "HTTP/1.1 400 Bad Request");

	/* El pedido se entiende, pero lo único que sabemos hacer es GET. */
	if (strcmp(verb, "GET") != 0)
		return send_status(fd, "HTTP/1.1 405 Method Not Allowed");

	return send_response(fd, path);
}

/*
 * Atiende a un cliente hasta que se va. Corre en el proceso hijo.
 *
 * Se lee de a bytes hasta el \n en vez de usar un buffer grande.
 * Así no nos comemos parte del pedido siguiente, que es justamente
 * el problema de mantener la conexión viva.
 */
static void handle_client(int fd)
{
	char line[MAX_LINE];
	size_t used = 0;

	for (;;) {
		char c;
		// Como no estoy usando las flags, es lo mismo que usar read
		// Esto tambien ocurre para send y write
		ssize_t n = recv(fd, &c, 1, 0);

		if (n < 0) {
			if (errno == EINTR)
				continue;
			break;      /* se cortó la conexión de mala manera */
		}
		if (n == 0)
			break;      /* el cliente cerró prolijamente */

		if (c == '\n') {
			/* Un cliente que termina las líneas con \r\n (HTTP de
			 * verdad, telnet) nos dejó el \r adentro de la línea:
			 * lo sacamos antes de mirar lo que pidió. */
			if (used > 0 && line[used - 1] == '\r')
				used--;
			line[used] = '\0';
			if (handle_request(fd, line) < 0)
				break;
			used = 0;
			continue;
		}

		if (used < sizeof(line) - 1) {
			line[used++] = c;
		} else {
			/* Línea absurdamente larga. */
			line[used] = '\0';
			send_status(fd, "HTTP/1.1 400 Bad Request");
			used = 0;
		}
	}

	printf("cliente desconectado\n");
	fflush(stdout);

	close(fd);
}

/* Hace wait a los hijos que ya terminaron, para no dejar zombies. Se
 * llama desde el handler de SIGCHLD, así que solo puede usar cosas seguras:
 * waitpid con WNOHANG lo es. */
static void reap_children(int sig)
{
	int saved = errno;

	(void)sig;
	while (waitpid(-1, NULL, WNOHANG) > 0)
		;
	errno = saved;
}

int main(int argc, char **argv)
{
	struct sockaddr_un addr;
	int listen_fd;
	const char *path;

	if (argc != 2) {
		fprintf(stderr, "uso: %s <ruta-del-socket>\n", argv[0]);
		return EXIT_FAILURE;
	}
	path = argv[1];

	/* La ruta viaja adentro de sun_path, que es un arreglo de tamaño
	 * fijo (108 bytes en Linux). Si no entra, mejor avisar acá que
	 * dejar que se corte silenciosamente. */
	if (strlen(path) >= sizeof(addr.sun_path)) {
		fprintf(stderr, "error: la ruta del socket no puede pasar de %zu caracteres\n",
		        sizeof(addr.sun_path) - 1);
		return EXIT_FAILURE;
	}

	/*
	 * Si un cliente se va justo cuando le estamos mandando un archivo,
	 * el send() nos manda un SIGPIPE que, por defecto, MATA al
	 * proceso. Lo ignoramos: así send() devuelve -1 con EPIPE y lo
	 * manejamos como lo que es, un cliente que se fue.
	 */
	signal(SIGPIPE, SIG_IGN);

	/*
	 * Cada vez que muere un hijo lo esperamos, así no quedan zombies.
	 */
	signal(SIGCHLD, reap_children);

	/*
	 * Creamos el socket del servidor.
	 */
	listen_fd = socket(AF_UNIX, SOCK_STREAM, 0);
	if (listen_fd < 0) {
		perror("socket");
		return EXIT_FAILURE;
	}

	/*
	 * Un socket UNIX se identifica por una ruta del sistema de
	 * archivos, y el bind() la crea. Si el archivo ya existe (porque
	 * quedó de una corrida anterior que no terminó bien), bind() falla
	 * con EADDRINUSE, así que lo borramos antes.
	 *
	 * Si no existe, unlink() falla con ENOENT y no pasa nada: por eso
	 * no chequeamos lo que devuelve.
	 */
	unlink(path);

	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);

	if (bind(listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
		perror("bind");
		return EXIT_FAILURE;
	}
	if (listen(listen_fd, BACKLOG) < 0) {
		perror("listen");
		return EXIT_FAILURE;
	}

	printf("servidor escuchando en %s, sirviendo %s/\n", path, PUBLIC_DIR);
	fflush(stdout);

	for (;;) {
	    /* TODO */

		/* 1. Esperar una conexión nueva con accept(). Devuelve un fd
		 *    NUEVO, el que se usa para hablar con ESE cliente;
		 *    listen_fd sigue siendo el de escuchar y no se cierra acá.
		 *
		 *    accept() se queda bloqueado hasta que alguien se conecta,
		 *    y puede fallar con EINTR si en el medio llegó una señal.
		 *    Acá pasa seguido: cada vez que termina un cliente nos
		 *    llega un SIGCHLD. Eso no es un error, hay que volver a
		 *    intentar. Cualquier otro error sí lo es. */
		int client_fd = accept(listen_fd, NULL, NULL);
		if(client_fd == -1)
			continue;


		/* 2. Atender al cliente. Todo el trabajo lo hace
		 *    handle_client(client_fd), pero ojo con llamarla de una:
		 *    esa función no vuelve hasta que el cliente se desconecta, y
		 *    la conexión es keep-alive, así que puede tardar lo que
		 *    quiera. Mientras tanto no estaríamos en el accept(), y el
		 *    resto de los clientes quedaría esperando. ¿Cómo hacés
		 *    para atender a varios al mismo tiempo? */

		if(fork() == 0){
			close(listen_fd);
			handle_client(client_fd);
			_exit(EXIT_SUCCESS);
		}
			

		/* 3. Cerrar de cada lado lo que ya no se usa. Son dos cierres
		 *    distintos, y olvidarse de cualquiera de los dos tiene
		 *    consecuencias:
		 *
		 *      - el que atiende al cliente heredó el socket de
		 *        escucha, que no le sirve para nada;
		 *
		 *      - el que sigue aceptando conexiones se quedó con SU
		 *        copia del socket del cliente. Si no la cierra, se le
		 *        acumulan file descriptors hasta quedarse sin ninguno,
		 *        y además el cliente nunca ve que la conexión se
		 *        cerró, porque queda una punta abierta de este lado. */

		close(client_fd);
	}

	close(listen_fd);
	return EXIT_SUCCESS;
}

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdbool.h>
#include <time.h>
#include <signal.h>
#include <sys/wait.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/select.h>

#define SCK_PATH "/tmp/sck_chat_21"
#define MAX_CLIENTS 5
#define BUFFER_SIZE 512


void sv_child() {
    // Seteo el servidor
    int server_fd, new_socket;
    int client_sockets[MAX_CLIENTS] = {0};
    struct sockaddr_un serv_addr;
    char buffer[BUFFER_SIZE];
    fd_set readfds;

    server_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    serv_addr.sun_family = AF_UNIX;
    strcpy(serv_addr.sun_path, SCK_PATH);
    unlink(SCK_PATH);
    
    bind(server_fd, (struct sockaddr*)&serv_addr, sizeof(serv_addr));
    listen(server_fd, MAX_CLIENTS);

    printf("[Servidor] Iniciado. Esperando conexiones...\n");

    while (true) {
        // Configuro la mascara de bits
        FD_ZERO(&readfds);
        FD_SET(server_fd, &readfds);
        int max_sd = server_fd;

        for (int i = 0; i < MAX_CLIENTS; i++) {
            int sd = client_sockets[i];
            if (sd > 0) 
                FD_SET(sd, &readfds);
            if (sd > max_sd) 
                max_sd = sd;
        }

        // Permitea un unico proceso vigilar multiples canales
        pselect(max_sd + 1, &readfds, NULL, NULL, NULL, NULL);

        // 1. Nueva conexión
        if (FD_ISSET(server_fd, &readfds)) {
            new_socket = accept(server_fd, NULL, NULL);
            bool accepted = false;
            
            for (int i = 0; i < MAX_CLIENTS; i++) {
                if (client_sockets[i] == 0) {
                    client_sockets[i] = new_socket;
                    printf("[Servidor] Cliente conectado en el slot %d\n", i);
                    accepted = true;
                    break;
                }
            }
            if (!accepted) {
                close(new_socket);
            }
        }

        // 2. Mensaje entrante de un cliente
        for (int i = 0; i < MAX_CLIENTS; i++) {
            int sd = client_sockets[i];
            
            if (sd > 0 && FD_ISSET(sd, &readfds)) {
                int bytes = recv(sd, buffer, BUFFER_SIZE - 1, 0);
                
                if (bytes <= 0) {
                    printf("[Servidor] Cliente en slot %d desconectado.\n", i);
                    close(sd);
                    client_sockets[i] = 0;
                } else {
                    buffer[bytes] = '\0';
                    
                    // BROADCAST: Reenviar a los demás
                    for (int j = 0; j < MAX_CLIENTS; j++) {
                        int dest_sd = client_sockets[j];
                        if (dest_sd > 0 && dest_sd != sd) {
                            send(dest_sd, buffer, strlen(buffer), 0);
                        }
                    }
                }
            }
        }
    }
    exit(EXIT_SUCCESS);
}


void cli_child(int id) {
    int sock = socket(AF_UNIX, SOCK_STREAM, 0);
    struct sockaddr_un serv_addr;
    serv_addr.sun_family = AF_UNIX;
    strcpy(serv_addr.sun_path, SCK_PATH);

    // Esperar a que el servidor esté listo
    while (connect(sock, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) == -1)
        sleep(5); 

    char buffer[BUFFER_SIZE];
    fd_set readfds;
    struct timespec timeout;
    
    int messages_sent = 0;
    time_t start = time(NULL);
    srand(time(NULL) ^ (getpid() << 16));

    // El cliente participa en el chat durante 5 segundos
    while (time(NULL) - start < 5) {
        FD_ZERO(&readfds);
        FD_SET(sock, &readfds);
        
        // Timeout dinámico para simular escritura humana
        timeout.tv_sec = rand() % 2; 
        timeout.tv_nsec = (rand() % 999999999);

        int ready = pselect(sock + 1, &readfds, NULL, NULL, &timeout, NULL);

        if (ready > 0 && FD_ISSET(sock, &readfds)) {
            // Recibe mensaje reenviado por el servidor
            int bytes = recv(sock, buffer, BUFFER_SIZE - 1, 0);
            if (bytes <= 0) break;
            
            buffer[bytes] = '\0';
            printf("[Cliente %d escucha] >> %s", id, buffer);
            fflush(stdout);
            
        } else if (ready == 0) {
            // Si salta el timeout, es momento de mandar un mensaje
            if (messages_sent < 2) {
                snprintf(buffer, BUFFER_SIZE, "Hola a todos, soy el Cliente %d (msg %d)\n", id, messages_sent + 1);
                send(sock, buffer, strlen(buffer), 0);
                messages_sent++;
            }
        }
    }
    
    close(sock);
    exit(EXIT_SUCCESS);
}


int main() {
    // 1. Lanzar el Servidor en su propio subproceso
    pid_t server_pid = fork();
    if (server_pid == 0)
        sv_child();

    // Darle tiempo al servidor para hacer el bind y listen
    sleep(1);

    // 2. Lanzar los 5 Clientes simulados
    pid_t clients_pids[MAX_CLIENTS];
    for (int i = 0; i < MAX_CLIENTS; i++) {
        pid_t p = fork();
        if (p == 0) {
            cli_child(i + 1);
            exit(EXIT_SUCCESS);
        }
        clients_pids[i] = p;
    }

    // 3. El Padre se queda en el main esperando pasivamente que los clientes terminen su simulación
    for (int i = 0; i < MAX_CLIENTS; i++) {
        waitpid(clients_pids[i], NULL, 0);
    }
    
    printf("\n[Main] Todos los clientes finalizaron el chat.\n");

    // 4. Limpieza: Apagar el servidor bloqueado en pselect y borrar el socket
    kill(server_pid, SIGTERM);
    waitpid(server_pid, NULL, 0);
    unlink(SCK_PATH);
    
    printf("[Main] Servidor apagado limpiamente. Saliendo...\n");

    return 0;
}
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <sys/socket.h>
#include <sys/un.h>

int main(){
    // AF_UNIX hace referencia al dominio de Unix.
    int serv_fd = socket(AF_UNIX, SOCK_STREAM, 0);

    // Creo la direccion del socket y defino el tipo de familia del dominio.
    struct sockaddr_un serv_addr;
    serv_addr.sun_family = AF_UNIX;

    // Defino la ruta a la cual guardaran los valores
    strcpy(serv_addr.sun_path, "/tmp/socket_s1");

    unlink("/tmp/socket_s1");

    bind(serv_fd, (struct sockaddr*) &serv_addr, sizeof(serv_addr));
    listen(serv_fd, 1);

    // Espero a que el client se conecte
    int client_sck = accept(serv_fd, NULL, NULL);

    int msg = 0;
    while(msg < 50){
        recv(client_sck, &msg, sizeof(msg), 0);
        printf("[Server: %d] Recibi: %d \n", getpid(), msg);

        msg++;
        send(client_sck, &msg, sizeof(int), 0);
        sleep(1);
    }

    close(client_sck);
    close(serv_fd);
    return 0;
}
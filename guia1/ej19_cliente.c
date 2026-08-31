#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <sys/socket.h>
#include <sys/un.h>

int main(){
    // AF_UNIX hace referencia al dominio de Unix.
    int sock = socket(AF_UNIX, SOCK_STREAM, 0);

    // Creo la direccion del socket y defino el tipo de familia del dominio.
    struct sockaddr_un serv_addr;
    serv_addr.sun_family = AF_UNIX;

    // Apuntamos al mismo aarchivo que crea el cliente.
    strcpy(serv_addr.sun_path, "/tmp/socket_s1");

    // Hasta no poder conectarse, duerme.
    while(connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) == -1){
        sleep(1);
    }

    int msg = 0;

    while(msg < 50){
        // Envio y espero la respuesta.
        send(sock, &msg, sizeof(msg), 0);
        recv(sock, &msg, sizeof(msg), 0);

        printf("[Cliente: %d] Recibi: %d \n", getpid(), msg);
        msg++;
    }

    close(sock);
    return 0;
}
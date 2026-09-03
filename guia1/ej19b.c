#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <stdbool.h>

#include <sys/wait.h>
#include <sys/socket.h>
#include <sys/un.h>

#define SOCKET_BASE_PATH "/tmp/sck_ej19b_P"

int set_server(char* path){
    int serv_fd = socket(AF_UNIX, SOCK_STREAM, 0);

    struct sockaddr_un serv_addr;
    serv_addr.sun_family = AF_UNIX;

    strcpy(serv_addr.sun_path, path);
    unlink(path);

    bind(serv_fd, (struct sockaddr*) &serv_addr, sizeof(serv_addr));
    listen(serv_fd, 1);

    return serv_fd;
}

int set_client(char* path){
    int serv_fd = socket(AF_UNIX, SOCK_STREAM, 0);

    struct sockaddr_un serv_addr;
    serv_addr.sun_family = AF_UNIX;
    strcpy(serv_addr.sun_path, path);

    while(connect(serv_fd, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) == -1){
        sleep(1);
    }

    return serv_fd;
}

void rutina_hijo(char* read_path, char* write_path, int idx){
    int server_fd = set_server(read_path);
    int write_fd= set_client(write_path);

    int client_sck = accept(server_fd, NULL, NULL);

    int msg = 0;
    if(idx == 1){
        printf("[Proceso %d] envia a Proceso %d el valor %d\n", idx, idx % 3 + 1, msg);
        fflush(stdout);

        send(write_fd, &msg, sizeof(msg), 0);
    }
        
    while(msg < 50){
        int bytes_leidos = recv(client_sck, &msg, sizeof(msg), 0);

        if(bytes_leidos <= 0|| msg >= 50) break;

        msg++;

        printf("[Proceso %d] envia a Proceso %d el valor %d\n", idx, idx % 3 + 1, msg);
        fflush(stdout);
        send(write_fd, &msg, sizeof(msg), 0);  
    }

    close(client_sck);
    close(server_fd);
    close(write_fd);
    free(read_path);
    free(write_path);

    exit(EXIT_SUCCESS);
}


char* create_path_for(const char* process_idx){
    char* path = malloc(32 * sizeof(char));

    strcpy(path, SOCKET_BASE_PATH);
    strcat(path, process_idx);

    return path;
}

int main(){
    if(fork() == 0)
        rutina_hijo(create_path_for("1"), create_path_for("2"), 1);
    
    if(fork() == 0)
        rutina_hijo(create_path_for("2"), create_path_for("3"), 2);

    if(fork() == 0) 
        rutina_hijo(create_path_for("3"), create_path_for("1"), 3);
        
    for(int i = 0; i < 3; i++)
        wait(NULL);

    return 0;
}
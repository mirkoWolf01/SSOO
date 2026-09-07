#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <stdbool.h>

#include <signal.h>
#include <time.h>

#include <sys/wait.h>
#include <sys/socket.h>
#include <sys/un.h>

#define SCK_PATH "/tmp/sck_sv_20"
#define MAX_CLIENTS 100
#define MAX_WORKERS 5

int rand_num()
{
    srand(time(NULL) ^ (getpid() << 16));
    return rand();
}

bool is_prime(int n){
    if(n <= 1)
        return false;

    for (int i = 2; i * i <= n; i++) 
        if (n % i == 0)
            return false;
    return true;
}

void sv_worker(int server_fd, int worker_id){
    while(true){
        // Los 3 hijos competirán por este accept. El SO despierta solo a uno.
        int client_sck = accept(server_fd, NULL, NULL);

        if (client_sck < 0)
            continue;

        int primo;
        recv(client_sck, &primo, sizeof(primo), 0);
        printf("[Worker %d | PID: %d] recibio el numero %d\n", worker_id, getpid(), primo);
        fflush(stdout);

        int es_primo = (int) is_prime(primo);
        send(client_sck, &es_primo, sizeof(es_primo), 0);

        close(client_sck);
    }

    exit(EXIT_SUCCESS);
}

void cli_child(){
    int server_fd = socket(AF_UNIX, SOCK_STREAM, 0);

    struct sockaddr_un serv_addr;
    serv_addr.sun_family = AF_UNIX;

    strcpy(serv_addr.sun_path, SCK_PATH);

     while(connect(server_fd, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) == -1)
        sleep(1);

    int primo = rand_num();
    send(server_fd, &primo, sizeof(primo), 0);
    int is_prime;
    recv(server_fd, &is_prime, sizeof(is_prime), 0);

    if(is_prime)
        printf("[Cliente %d] el valor %d es primo \n", getpid(), primo);
    else
        printf("[Cliente %d] el valor %d no es primo  \n", getpid(), primo);
    fflush(stdout);

    close(server_fd);
    exit(EXIT_SUCCESS);
}


int main(){
    // El padre crea el socket pasivo
    int server_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    struct sockaddr_un serv_addr;
    serv_addr.sun_family = AF_UNIX;
    strcpy(serv_addr.sun_path, SCK_PATH);
    unlink(SCK_PATH);

    bind(server_fd, (struct sockaddr*) &serv_addr, sizeof(serv_addr));
    listen(server_fd, MAX_CLIENTS);


    pid_t workers_pids[MAX_WORKERS];
    // Creo a los trabajadores
    for(int i = 0; i < MAX_WORKERS; i++){
        pid_t worker = fork();
        if(worker == 0)
            sv_worker(server_fd, i + 1);
        workers_pids[i] = worker;
    }

    for(int i = 0; i < MAX_CLIENTS; i++)
        if(fork() == 0)
            cli_child();


    for(int i = 0; i < MAX_CLIENTS; i++)
        wait(NULL);
    
    for(int i = 0; i < MAX_WORKERS; i++){
        kill(workers_pids[i], SIGTERM);
        waitpid(workers_pids[i], NULL, 0);
    }

    close(server_fd);
    unlink(SCK_PATH);
    return 0;
}
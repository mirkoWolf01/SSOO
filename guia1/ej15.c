#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <sys/wait.h>

enum { READ, WRITE };
enum { LS, WC };

int comPipe[2];

void rutina_ls(){
    close(comPipe[READ]);

    dup2(comPipe[WRITE], STDOUT_FILENO);
    close(comPipe[WRITE]);

    // !!! Recordar poner el NULL al final.
    execlp("ls", "ls", "-al", NULL);

    // Si vuelve, es porque fallo.
    exit(EXIT_FAILURE);
}

void rutina_wc(){
    close(comPipe[WRITE]);

    dup2(comPipe[READ], STDIN_FILENO);
    close(comPipe[READ]);

    execlp("wc", "wc", "-l", NULL);

    // Si vuelve, es porque fallo.
    exit(EXIT_FAILURE);
}

int main(){
    pipe(comPipe);

    pid_t pid_ls = fork();
    if(pid_ls == 0)
        rutina_ls();

    pid_t pid_wc = fork();
    if(pid_wc == 0)
        rutina_wc();

    close(comPipe[READ]);
    close(comPipe[WRITE]);
    

    wait(NULL);
    wait(NULL);

    return 1;
}
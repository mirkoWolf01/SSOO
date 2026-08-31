#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>

#include <sys/types.h>
#include <sys/wait.h>

int tirar_dado()
{
    srand(time(NULL) ^ (getpid() << 16));
    return (rand() % 6) + 1;
}

enum { READ, WRITE };
enum { LESTER, ELIZA };

int pipe_eliza[2];
int pipe_lester[2];


void close_pipe(int* pipe){
    close(pipe[READ]);
    close(pipe[WRITE]);
}

void rutina_lester()
{
    close_pipe(pipe_eliza);
    close(pipe_lester[READ]);

    int valor_dado = tirar_dado();
    write(pipe_lester[WRITE], &valor_dado, sizeof(int));
    printf("[Lester: %d]   Mi valor es %d\n", getpid(), valor_dado);

    exit(EXIT_SUCCESS);
}

void rutina_eliza()
{
    close_pipe(pipe_lester);
    close(pipe_eliza[READ]);

    int valor_dado = tirar_dado();
    write(pipe_eliza[WRITE], &valor_dado, sizeof(int));
    printf("[Eliza: %d]   Mi valor es %d\n", getpid(), valor_dado);

    exit(EXIT_SUCCESS);
}

int main()
{
    pipe(pipe_eliza);
    pipe(pipe_lester);

 
    pid_t pid_eliza = fork();
    if (pid_eliza == 0)
        {rutina_eliza();}

    pid_t pid_lester = fork();
    if (pid_lester == 0)
        {rutina_lester();}

    close(pipe_eliza[WRITE]);
    close(pipe_lester[WRITE]);

    int value_eliza, value_lester; 
    read(pipe_eliza[READ], &value_eliza, sizeof(int));
    read(pipe_lester[READ], &value_lester, sizeof(int));

    close(pipe_eliza[READ]);
    close(pipe_lester[READ]);

    wait(NULL);
    wait(NULL);

    printf("[Humberto: %d]   ", getpid());

    if(value_eliza > value_lester)
        printf("GANO ELIZA DOU\n");
    else if(value_lester > value_eliza)
        printf("GANO LESTER DOU\n");
    else
        printf("EMPATARON\n");
}

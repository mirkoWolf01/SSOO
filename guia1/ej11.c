#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <stdbool.h>

#include <signal.h>
#include <time.h>

#include <sys/types.h>
#include <sys/wait.h>


void bsend(pid_t dst, int msg);
int breceive(pid_t src);

pid_t get_current_pid();

int msg = 0;

// TODO: Puede pasar que se termina dentro de uno de los hijos, y que tanto el padre como el hermano
//       Queden vivos y se trabe. Necesitaria implementar un handler de SIGCHILD para matar al proceso hermano y a si mismo si uno de los hijos termina
//       Pero me dia fiaca jajaja.

int main(){
    pid_t pid_hijo_a = fork();

    if(pid_hijo_a == 0){
        pid_t pid_brother = breceive(getppid());

        while(msg < 50){
            msg = breceive(getppid()) + 1;

            bsend(pid_brother, msg);
        }
        exit(EXIT_SUCCESS);
    }

    pid_t pid_hijo_b = fork();

    if(pid_hijo_b == 0){
        pid_t pid_brother = breceive(getppid());

        while(msg < 50){
            msg = breceive(pid_brother) + 1;

            bsend(getppid(), msg);
        }
        
        exit(EXIT_SUCCESS);
    }

    bsend(pid_hijo_a, pid_hijo_b);
    bsend(pid_hijo_b, pid_hijo_a);

    while(msg < 50){
        bsend(pid_hijo_a, msg);
        msg = breceive(pid_hijo_b) + 1;
    }

    kill(pid_hijo_a, SIGTERM);
    kill(pid_hijo_b, SIGTERM);

    wait(NULL);
    wait(NULL);

    exit(EXIT_SUCCESS);
}



/*
    A.

    pid_t pid_hijo = fork();
    int msg = 0;

    if(pid_hijo == 0){
        while(true){
            msg = breceive(getppid()) + 1;

            bsend(getppid(), msg);
        }



        exit(EXIT_SUCCESS);
    }
    else{
        while(true){
            bsend(pid_hijo, msg);

            msg = breceive(pid_hijo) + 1;
        }

    }
*/
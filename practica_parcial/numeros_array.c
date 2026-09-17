#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <sys/wait.h>

int *array;
int n, m;

enum {READ, WRITE};

void printArray(){
    for(int i = 0; i<m; i++)
        printf("%d: %d\n", i, array[i]);
}

int generar_valor(int i){
    return i*2;
}

void hijo(int (*pipes)[2], int idx){
    int rp = pipes[idx][READ];
    int wp = pipes[idx][WRITE];

    for(int i = idx; i < m; i += n){
        int val = generar_valor(i);
        printf("[%d] Valor generado: %d\n", getpid(), val);
        fflush(stdout);

        write(wp, &val, sizeof(val));
    }

    close(rp);
    close(wp);
    exit(0);
}

void padre(){
    int (*pipes)[2] = calloc(n, sizeof(int[2]));
    for(int i = 0; i < n; i++){
        pipe(pipes[i]);
        if(fork() == 0){
            for(int j = 0; j < i; j++){
                close(pipes[j][READ]);
                close(pipes[j][WRITE]);
            }
            hijo(pipes, i);
        }
    }
    for(int i = 0; i < m; i++){
        int val; 
        read(pipes[i % n][READ], &val, sizeof(val));
        array[i] = val;
    }

    for(int i = 0; i < n; i++){
        close(pipes[i][READ]);
        close(pipes[i][WRITE]);
        wait(NULL);
    }

    free(pipes);

    printArray();
}

int main(){
    printf("Amount of childs: \n");
    scanf("%d", &n);

    printf("\nm: \n");
    scanf("%d", &m);

    array = calloc(m, sizeof(int));

    padre();

    free(array);
    exit(0);
}


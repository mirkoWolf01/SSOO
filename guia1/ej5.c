#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <sys/types.h>
#include <sys/wait.h>

void declarar_nombre(char *nombre)
{
    printf("Soy %s, y mi pid es %d\n", nombre, getpid());
}

void create_child(char *nombre)
{
    pid_t pid_hijo = fork();

    if (pid_hijo == 0)
    {
        declarar_nombre(nombre);
        exit(EXIT_SUCCESS);
    }
    // wait(NULL);
    // waitpid(pid_hijo, NULL, 0);
}

int main()
{
    declarar_nombre("Abraham");

    pid_t pid_homero = fork();

    if (pid_homero == 0)
    {
        declarar_nombre("Homero");

        create_child("Bart");
        create_child("Lisa");
        create_child("Maggie");

        wait(NULL);
        wait(NULL);
        wait(NULL);

        printf("Homero termino!!! DOU\n");
        exit(EXIT_SUCCESS);
    }

    wait(NULL);
    printf("Abraham ha terminado, con pid %d\n", getpid());

    exit(EXIT_SUCCESS);
}
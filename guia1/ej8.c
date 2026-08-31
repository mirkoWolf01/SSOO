#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <sys/types.h>
#include <sys/wait.h>

/*
    Los resultados mostrados por la variable dato van a ser distintas (aunque solo se efectua el cambio cuando en algunos de los dos procesos cambian algo de los datos guardados),
    ya que solo se suma la variable desde el contexto del hijo.
    Y ocurre que cada uno tiene su propio sector de memoria, por lo que en el contexto del padre dato siempre es 0.
*/

int main()
{
    int dato = 0;
    pid_t pid = fork();
    // si no hay error, pid vale 0 para el hijo
    // y el valor del process id del hijo para el padre

    if (pid == -1)
        exit(EXIT_FAILURE);
    // si es -1, hubo un error
    else if (pid == 0)
    {
        for (int i = 0; i < 3; i++)
        {
            dato++;
            printf("Dato hijo: %d\n", dato);
        }
    }
    else
    {
        for (int i = 0; i < 3; i++)
        {
            printf("Dato padre: %d\n", dato);
        }
    }
    exit(EXIT_SUCCESS); // cada uno finaliza su proceso
}
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>

#include <sys/types.h>
#include <sys/wait.h>

int main()
{
    pid_t pid_julieta = fork();

    if (pid_julieta == 0)
    {
        write(STDOUT_FILENO, "Soy Julieta\n", 12);
        sleep(1);

        pid_t pid_jennifer = fork();

        if (pid_jennifer == 0)
        {
            write(STDOUT_FILENO, "Soy Jennifer\n\0", 14);
            sleep(1);
        }
        exit(EXIT_SUCCESS);
    }
    else
    {
        write(STDOUT_FILENO, "Soy Juan\n\0", 10);
        sleep(1);
        wait(NULL);

        pid_t pid_jorge = fork();

        if (pid_jorge == 0)
        {
            write(STDOUT_FILENO, "Soy Jorge\n", 10);
            sleep(1);
        }
        exit(EXIT_SUCCESS);
    }
}

// Se utilizo strace -f, que viene de follow para seguir lo que hacen
//  los procesos hijos
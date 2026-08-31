#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <unistd.h>
#include <signal.h>

#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>

volatile sig_atomic_t my_turn = false;

void await_signal()
{
    while (!my_turn)
    {
        pause();
    }
}

void receive_signal()
{
    my_turn = true;
}

int main()
{
    // Creo la señal a la cual va a mandar el mensaje
    signal(SIGUSR1, receive_signal);

    pid_t pid_child = fork();

    if (pid_child < 0)
    {
        perror("Fallo el fork");
        exit(EXIT_FAILURE);
    }

    if (pid_child == 0)
    {
        while (1)
        {
            await_signal();

            printf("[%d]  pong \n", getpid());
            my_turn = false;

            // Envio la señal al padre
            kill(getppid(), SIGUSR1);
        }
    }
    else
    {
        sleep(0.3);

        char keep_going = 'y';
        while (keep_going == 'y' || keep_going == 'Y')
        {
            // Testeo que  se este ejecutando en momentos distintos
            // time_t raw_time = time(NULL);
            // printf("Current Time: %s\n", ctime(&raw_time));

            for (int i = 0; i < 3; i++)
            {

                printf("[%d]  ping \n", getpid());
                my_turn = false;

                // Envio el mensaje y espero por la respuesta.
                kill(pid_child, SIGUSR1);
                await_signal();

                printf("\n");
            }

            printf("Keep Running [y/n]:");
            scanf(" %c", &keep_going);
            printf("\n");
        };

        kill(pid_child, SIGTERM);
        wait(NULL);
        exit(EXIT_SUCCESS);
    }
}
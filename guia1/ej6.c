#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <sys/types.h>
#include <sys/wait.h>

void sistem(const char *arg)
{
    pid_t pid_child = fork();

    if (pid_child == 0)
    {
        execl("/bin/sh", "sh", "-c", arg, (char *)NULL);

        // Si no cambia la ejecucion fallo
        exit(EXIT_FAILURE);
    }

    waitpid(pid_child, NULL, 0);
}

int main()
{
    sistem("ls -l");
    sistem("echo \"funciono lo pedido\"");
}
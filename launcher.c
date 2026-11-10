#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <string.h>

int main(int argc, char *argv[]) {
    const char *home = getenv("HOME");
    if (!home) return 1;

    char app_dir[1024];
    char python_path[1024];
    char gui_path[1024];
    char log_path[1024];

    snprintf(app_dir, sizeof(app_dir), "%s/.pyvault", home);
    snprintf(python_path, sizeof(python_path), "%s/.pyvault/venv/bin/python3", home);
    snprintf(gui_path, sizeof(gui_path), "%s/.pyvault/gui.py", home);
    snprintf(log_path, sizeof(log_path), "%s/Library/Logs/PyVault.log", home);

    // Redirect stdout and stderr to PyVault.log
    int log_fd = open(log_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (log_fd >= 0) {
        dup2(log_fd, STDOUT_FILENO);
        dup2(log_fd, STDERR_FILENO);
        close(log_fd);
    }

    setenv("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", 1);
    chdir(app_dir);

    char *new_argv[argc + 2];
    new_argv[0] = python_path;
    new_argv[1] = gui_path;
    for (int i = 1; i < argc; i++) {
        new_argv[i + 1] = argv[i];
    }
    new_argv[argc + 1] = NULL;

    execv(python_path, new_argv);
    perror("execv failed");
    return 1;
}

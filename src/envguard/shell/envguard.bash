#!/usr/bin/env bash

# EnvGuard Bash Hook

_envguard_hook_wrapper() {
    local cmd=$1
    shift
    
    # Find the real executable path of the command (bypass shell functions)
    local exe
    exe=$(type -P "$cmd" 2>/dev/null)
    
    if [ -n "$exe" ]; then
        # Call the Python envguard cli silently.
        # Check if envguard is installed and in PATH before calling it
        if command -v envguard >/dev/null 2>&1; then
            local active_python
            active_python=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
            if [ -n "$active_python" ]; then
                envguard hook-exec "$cmd" "$exe" --python "$active_python" "$@"
            else
                envguard hook-exec "$cmd" "$exe" "$@"
            fi
        fi
    fi
    
    # Execute the actual command
    command "$cmd" "$@"
}

if [ -f ~/.envguard/tools.cache ]; then
    TOOLS=$(cat ~/.envguard/tools.cache)
else
    TOOLS="pip pip3 pyinstaller pytest celery uvicorn uv uvx"
fi

for cmd in $TOOLS; do
    if ALIAS_DEF=$(alias "$cmd" 2>/dev/null); then
        echo -e "\033[93m[EnvGuard Warning] Detected alias for '$cmd' ($ALIAS_DEF). EnvGuard will NOT intercept this command to preserve your alias.\033[0m" >&2
    else
        eval "
        function $cmd() {
            _envguard_hook_wrapper $cmd \"\$@\"
        }
        "
    fi
done

# Wrapper to intercept 'envguard' commands for config sync warnings and hot-reloads
envguard() {
    # 1. Check for out-of-sync config if command is not 'init' or 'hook-exec'
    if [[ "$1" != "init" && "$1" != "hook-exec" ]]; then
        if [ -f ~/.envguard/config.json ] && [ ~/.envguard/config.json -nt ~/.envguard/tools.cache ]; then
            echo -e "\033[93m[EnvGuard HINT] 💡 config.json has been modified. Run 'envguard init' to hot-reload this terminal.\033[0m" >&2
        fi
    fi

    # 2. Execute the actual binary
    command envguard "$@"
    local ret=$?

    # 3. Hot-reload if the command was 'init' and it succeeded
    if [[ "$1" == "init" && $ret -eq 0 ]]; then
        source ~/.envguard/envguard.bash
        echo -e "\033[92m[EnvGuard] Hot-reloaded shell hooks for current terminal.\033[0m" >&2
    fi

    return $ret
}

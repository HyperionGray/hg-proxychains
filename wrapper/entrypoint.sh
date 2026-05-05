#!/usr/bin/env bash
# hg-proxychains wrapper entrypoint.
#
# All commands are run under proxychains4, which forces TCP and DNS through
# the local egressd CONNECT listener. egressd handles the multi-hop chain.
#
# Special behavior:
#   - no args / "shell"        -> spawn an interactive bash where every
#                                 forked program is wrapped automatically
#                                 via PROMPT_COMMAND (visible "[chained]"
#                                 prompt to make leakage obvious).
#   - "raw" <cmd ...>          -> run the command WITHOUT proxychains
#                                 (escape hatch, useful for debugging).
#   - anything else            -> proxychains4 -q "$@"
set -euo pipefail

PC_CONF="${PROXYCHAINS_CONF_FILE:-/etc/proxychains4.conf}"

run_chained() {
    exec proxychains4 -q -f "${PC_CONF}" "$@"
}

run_shell() {
    cat <<'EOF'
hg-proxychains wrapper shell

Every command you run here is forced through the proxy chain
(no DNS leaks, no direct TCP) via proxychains4.

Type 'exit' to leave. Use 'raw <cmd>' to bypass proxychains for
diagnostics (e.g. to talk to egressd's /health endpoint).
EOF
    export PS1='[chained:\w]$ '
    pc_runner='proxychains4 -q -f '"${PC_CONF}"
    tmpfile=$(mktemp)
    trap 'rm -f "$tmpfile"' EXIT
    cat >"$tmpfile" <<EOF
alias raw='env -u LD_PRELOAD'
pc() { ${pc_runner} "\$@"; }
PROMPT_COMMAND=':'
EOF
    exec bash --rcfile "$tmpfile" -i
}

if [ "$#" -eq 0 ]; then
    run_shell
fi

case "$1" in
    shell)
        shift
        if [ "$#" -eq 0 ]; then
            run_shell
        else
            run_chained "$@"
        fi
        ;;
    raw)
        shift
        if [ "$#" -eq 0 ]; then
            echo "raw requires a command" >&2
            exit 2
        fi
        exec "$@"
        ;;
    *)
        run_chained "$@"
        ;;
esac

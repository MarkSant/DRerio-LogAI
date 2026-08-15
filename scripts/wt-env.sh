# shellcheck shell=bash
# Point the shell at the main .venv's tools and THIS worktree's sources.
#
# Usage (from anywhere inside a worktree or the main repo):
#
#     source scripts/wt-env.sh
#
# Why this is needed at all
# -------------------------
# Git worktrees share the repository but not the environment, and two details
# of this project's setup make that bite:
#
# 1. The worktree's own .venv is a poetry stub: Python 3.14 with pip and
#    nothing else, while the project runs on 3.12. So `mypy`, `pytest` and
#    `ruff` are simply absent there, and every pre-commit / pre-push hook that
#    shells out to them dies with "'mypy' is not recognized".
#
# 2. The main .venv resolves `zebtrack` through
#    `site-packages/drerio_logai.pth`, which holds an ABSOLUTE path to the MAIN
#    repository's src/. Borrowing the main venv without correcting PYTHONPATH
#    therefore runs the main branch's code from inside your worktree. That
#    failure is silent: the suite goes green without having exercised one line
#    of your changes.
#
# Sourcing this fixes both, and because git hooks inherit the environment of
# the process that launched them, `git commit` and `git push` start working
# too — with the real gates running, not skipped.
#
# Idempotent: safe to source repeatedly in the same shell.

_wt_env_main() {
    local worktree main_git main_root venv_scripts

    worktree="$(git rev-parse --show-toplevel 2>/dev/null)" || {
        echo "wt-env: not inside a git repository" >&2
        return 1
    }

    # --git-common-dir points at the MAIN repo's .git even from a worktree.
    main_git="$(git rev-parse --git-common-dir)"
    case "$main_git" in
        /*|[A-Za-z]:*) ;;                      # already absolute
        *) main_git="$worktree/$main_git" ;;   # relative to the worktree
    esac
    main_root="$(cd "$main_git/.." && pwd)"
    venv_scripts="$main_root/.venv/Scripts"
    [ -d "$venv_scripts" ] || venv_scripts="$main_root/.venv/bin"   # POSIX layout

    if [ ! -x "$venv_scripts/python" ] && [ ! -x "$venv_scripts/python.exe" ]; then
        echo "wt-env: no usable venv at $main_root/.venv — run 'poetry install' in the main repo" >&2
        return 1
    fi

    case ":$PATH:" in
        *":$venv_scripts:"*) ;;
        *) PATH="$venv_scripts:$PATH" ;;
    esac
    export PATH

    # Prepended, so it wins over drerio_logai.pth in site-packages.
    case ":${PYTHONPATH:-}:" in
        *":$worktree/src:"*) ;;
        *) PYTHONPATH="$worktree/src${PYTHONPATH:+:$PYTHONPATH}" ;;
    esac
    export PYTHONPATH

    echo "wt-env: tools from $main_root/.venv"
    echo "wt-env: sources  from $worktree/src"

    if [ -f "$worktree/.venv/pyvenv.cfg" ] && [ "$worktree" != "$main_root" ]; then
        echo "wt-env: NOTE - this worktree has its own stub .venv." >&2
        echo "wt-env:        Avoid 'poetry run' here; it would select that one." >&2
    fi
}

_wt_env_main

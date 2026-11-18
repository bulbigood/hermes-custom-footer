#!/bin/sh
# Set the bundled Git footer as the command for an already installed plugin.
set -eu

case $# in
    0) profile= ;;
    2) if [ "$1" != '--profile' ] || [ -z "$2" ]; then
           printf 'Usage: %s [--profile NAME]\n' "$0" >&2; exit 2
       fi
       profile=$2 ;;
    *) printf 'Usage: %s [--profile NAME]\n' "$0" >&2; exit 2 ;;
esac

run_hermes() {
    if [ -n "$profile" ]; then hermes --profile "$profile" "$@"; else hermes "$@"; fi
}

config=$(run_hermes config path)
case "$config" in
    /*/config.yaml) ;;
    *) printf 'Could not resolve the Hermes profile config path.\n' >&2; exit 1 ;;
esac
script=${config%/*}/plugins/custom-footer/git_footer.py
if [ ! -f "$script" ]; then
    printf 'Install custom-footer in this Hermes profile first (missing %s).\n' "$script" >&2
    exit 1
fi
python=$(command -v python3) || { printf 'python3 is required.\n' >&2; exit 1; }
case "$python" in
    /*) ;;
    *) printf 'python3 must resolve to an absolute path.\n' >&2; exit 1 ;;
esac
command_json=$("$python" -c 'import json, sys; print(json.dumps(sys.argv[1:]))' "$python" "$script")
run_hermes config set plugins.entries.custom-footer.settings.command "$command_json"
run_hermes config set plugins.entries.custom-footer.settings.timeout_seconds 2.0
printf 'Configured the bundled Git footer in %s. Plugin enablement was not changed.\n' "$config"

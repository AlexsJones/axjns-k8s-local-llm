#!/usr/bin/env bash
# Usage: ./shot-k9s.sh <out.png> <k9s args...>
# Runs k9s in a detached tmux pane of a fixed size, waits for it to draw,
# captures the pane with colours and renders it to PNG with freeze.
set -euo pipefail
out=$1; shift
s=k9sshot$$
tmux new-session -d -s $s -x 150 -y 22 "TERM=xterm-256color k9s --kubeconfig $PWD/kubeconfig $*"
sleep ${WAIT:-6}
tmux capture-pane -e -p -t $s > shots/$(basename $out .png).ans
tmux kill-session -t $s
# rendered to PNG separately (freeze v0.2.2 segfaults on this machine)
echo "$out"

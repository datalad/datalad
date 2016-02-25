#!/bin/sh

set -e
set -u

# THIS THING MUST BE SILENT on stdout so that git process wouldn't take it as its input
# echo Running "$@"
if test "$1" = "-p"
then
	PORT=:$2
	shift 2
else
    PORT=""
fi
CONTROL_MASTER="/var/run/user/$(id -u)/datalad/$1$PORT $1"
shift 1
COMMAND="ssh -S $CONTROL_MASTER $@"
$COMMAND



#!/bin/sh
if test "$1" = "-p"
then
	PORT=$2
	shift 2
else
	PORT=22
fi
CONTROL_MASTER="/var/run/user/$(id -u)/datalad/$1:$PORT $1"
shift 1
COMMAND="ssh -S $CONTROL_MASTER $@"
$COMMAND



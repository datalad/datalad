# !/bin/sh
if test "$1" = "-p"
then
	PORT=$2
	shift 2
else
	PORT=22
fi
CONTROL_MASTER="$HOME/.ssh/controlmasters/$1:$PORT $1"
shift 1
ssh -S $CONTROL_MASTER "$@"


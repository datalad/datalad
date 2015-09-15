#!/bin/bash
# Helper to bring interfaces down/up for testing
set -eu
if [ $1 = "down" ]; then
    NONLO=$(ifconfig | awk '/^[a-z]/{print $1;}' | grep -v '^lo$' | tr '\n' ' ' | sed -e 's, *$,,g')
    for i in $NONLO; do
        echo "I: bringing down $i" >&2
        sudo ifdown $i >&2
    done
    echo "export DATALAD_NONLO='$NONLO'"
elif [ $1 = "up" ]; then
    for i in ${DATALAD_NONLO}; do
        echo "I: bringing up $i" >&2
        sudo ifup $i >&2
    done

fi
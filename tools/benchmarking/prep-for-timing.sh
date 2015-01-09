#!/bin/bash

set -eu

d=$1
d1=${d}-xx-yy-key
d2=${d}-xx-yy

for d_ in $d1 $d2; do
    [ -e $d_ ] || continue
    chmod +w -R $d_
    rm -rf $d_
done

echo "I: rsyncing"
rsync -a $d/ $d1
rsync -a $d/ $d2

echo "I: Remapping"
./remap-to-xx-yy.sh $d2


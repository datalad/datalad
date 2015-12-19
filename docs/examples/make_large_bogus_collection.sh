#!/bin/bash
# This generates arbitrarily large bogus collection with the specified in the command line number of handles
# which have some random very short description, author and license

set -eu

n=$1

rword() {
	WORDLINE=$((($RANDOM * $RANDOM) % $(wc -w /usr/share/dict/words | awk '{print $1}')))"p" && sed -n $WORDLINE /usr/share/dict/words
}

c=bogus-${n}_collection
datalad create-collection $c

for i in `seq 1 $n`; do
	h=bogus$i-$n
	datalad create-handle $h
	( cd $h;
	  git annex addurl "http://www.onerussian.com/tmp/banner.png" --file "Banner for $h"
	  git commit -m "Our banner for $h"

	  datalad describe \
			  --author "`rword` `rword`" \
			  --license "`rword`" \
			  --description "`rword` `rword`
`rword`
`rword` `rword` `rword`
"
	  cd ..
	  # add
	  datalad add-handle $h $c
	)
done

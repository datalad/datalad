#!/bin/bash
# This generates arbitrarily large bogus collection with the specified in the command line number of handles
# which have some random very short description, author and license

set -eu

n=$1

rword() {
	WORDLINE=$((($RANDOM * $RANDOM) % $(wc -w /usr/share/dict/words | awk '{print $1}')))"p" && sed -n $WORDLINE /usr/share/dict/words
}

c=bogus-${n}_collection
if ! ( datalad list-collections | grep -q "^$c\$" ); then
    echo "I: creating new collection $c"
    datalad create-collection $c
fi

for i in `seq 1 $n`; do
	h=bogus$i-$n
	[ ! -d $h ] || { echo "I: $h exists, skipping"; continue; }
    echo "I: creating $h"
	/usr/bin/time datalad --dbg create-handle $h
	( cd $h;
	  git annex addurl "http://www.onerussian.com/tmp/banner.png" --file "Banner for $h"
	  git commit -m "Our banner for $h"
      echo "I: describing"
	  /usr/bin/time datalad describe \
			  --author "`rword` `rword`" \
			  --license "`rword`" \
			  --description "`rword` `rword`
`rword`
`rword` `rword` `rword`
"
	  cd ..
	  echo "I: adding a handle"
	  /usr/bin/time datalad --dbg add-handle $h $c
	)
done

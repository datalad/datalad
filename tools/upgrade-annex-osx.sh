#!/bin/bash

curver=$(git annex version | awk '/version:/{print $3;}' | sed -e 's,-.*,,g')
annexdir=/Applications/git-annex.app
curverdir=$annexdir.$curver

rm -f git-annex.dmg
# release
# curl -O https://downloads.kitenet.net/git-annex/OSX/current/10.10_Yosemite/git-annex.dmg
# daily build
curl -O https://downloads.kitenet.net/git-annex/autobuild/x86_64-apple-yosemite/git-annex.dmg

hdiutil attach git-annex.dmg 

if [ ! -z "$curver" ] && [ ! -e "$curverdir" ]; then
	mv $annexdir $curverdir
fi

rsync -a /Volumes/git-annex/git-annex.app /Applications/
hdiutil  detach /Volumes/git-annex/

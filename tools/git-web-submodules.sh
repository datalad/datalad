#!/bin/bash
# Helper to replicate and demonstrate problem with git submodules being shared
# as non-bare repos on the web

set -eu

topd=/tmp/gitxxmsxYFO #$(tempfile --prefix gitxxx)
topd2=${topd}_
topd3=${topd}__
echo "I: directory $topd"
rm -rf "$topd" "$topd2" "$topd3"

gitcommit () {
    git commit "$@"
    # manually since we aren't pushing to it atm
    git update-server-info
}

gitinit () {
    git init
    # make it servable from the web
    mv .git/hooks/post-update.sample .git/hooks/post-update
}

gitaddfile() {
    echo $1 > $1
    git add $1
    gitcommit -m "added $1"
}

startwebserver() {
    python -m SimpleHTTPServer 8080 2>&1 | sed -e 's,^,  WEB: ,g' &
    sleep 1  # to give it time to start
}

# Initiate a repo with a submodule with relative path
mkdir $topd
cd $topd
mkdir -p $topd
gitinit
gitaddfile f1

mkdir sub1
cd sub1
gitinit
gitaddfile f2
cd ..

git submodule add ./sub1 sub1
gitcommit -m 'Added sub1 submodule' -a

# Expose under the webserver
startwebserver

# Try to clone and update submodule
git clone http://localhost:8080/.git $topd2
cd $topd2
# and initialize submodule
git submodule update --init || echo "E: FAILED!"

# but we can still do it if we adjust the url for already inited submodule
sed -i -e 's|/.git/sub1|/sub1/.git|g' .git/config
git submodule update --init
echo "I: SUCCESS and the content of file is ..."
cd sub1
cat f2
# so we could serve later as well
git update-server-info
cd ..
git update-server-info
# kill the webserver
kill %1
sleep 1

echo "I: now trying to serve the cloned repo which has a gitlink for sub1/.git"
# Expose under the webserver
startwebserver

# Try to clone and update submodule
git clone http://localhost:8080/.git $topd3
cd $topd3
# and initialize submodule
git submodule update --init || echo "E: FAILED!"

# but we can still do it if we adjust the url for already inited submodule
sed -i -e 's|/.git/sub1|/sub1/.git|g' .git/config
git submodule update --init || echo "E: Remains broken, I guess due to sub1/.git being a gitlink and git not following its pointer"
#echo "I: SUCCESS and the content of file is ..."
#cat sub1/f2

kill %1


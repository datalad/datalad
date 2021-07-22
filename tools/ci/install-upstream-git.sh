#!/bin/sh

target_dir="$PWD/git-src"
git clone https://github.com/git/git "$target_dir"
(
    cd "$target_dir"
    git checkout origin/master
    make --jobs 2
)
export PATH="$target_dir/bin-wrappers/:$PATH"
git version

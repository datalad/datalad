#!/bin/sh

git annex info | grep 'local annex keys' | cut -d ':' -f2

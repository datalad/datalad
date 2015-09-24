#!/bin/sh

set -e

# may want to run this before to level the playing field
#datalad unregister-collection demo_collection 
#datalad uninstall-handle demo_handle1 
#datalad uninstall-handle demo_handle2
#rm -rf demo_collection

datalad create-handle demo_handle1
cd demo_handle1

# take from https://commons.wikimedia.org/wiki/File:Nuclear_power_worldwide-2009.svg
git annex addurl "https://upload.wikimedia.org/wikipedia/commons/archive/3/31/20110619152312%21Nuclear_power_worldwide-2009.svg" --file Nuclear_power_worldwide.svg
git commit -m "map from 01:23, 22 March 2011"

git annex unlock Nuclear_power_worldwide.svg
git annex addurl "https://upload.wikimedia.org/wikipedia/commons/archive/3/31/20121116153131%21Nuclear_power_worldwide-2009.svg" --file Nuclear_power_worldwide.svg
git commit -m "Updated to state of 2011; Introduced new category"

git annex unlock Nuclear_power_worldwide.svg
git annex addurl "https://upload.wikimedia.org/wikipedia/commons/archive/3/31/20130815110526%21Nuclear_power_worldwide-2009.svg" --file Nuclear_power_worldwide.svg
git commit -m "Update November 2012"

git annex unlock Nuclear_power_worldwide.svg
git annex addurl "https://upload.wikimedia.org/wikipedia/commons/archive/3/31/20130815114601%21Nuclear_power_worldwide-2009.svg" --file Nuclear_power_worldwide.svg
git commit -m "Update to August 2013"

git annex unlock Nuclear_power_worldwide.svg
git annex addurl "https://upload.wikimedia.org/wikipedia/commons/archive/3/31/20130815115336%21Nuclear_power_worldwide-2009.svg" --file Nuclear_power_worldwide.svg
git commit -m "CZE and BUL switched to 'kein Ausbau' (no expansion)"

#
# Disable for now to keep it fast
#
## video from https://archive.org/details/BigBuckBunny_328
#git annex addurl "https://archive.org/download/BigBuckBunny_328/BigBuckBunny.avi"
#git mv archive.org_download_BigBuckBunny_328_BigBuckBunny.avi BigBuckBunny.avi
#git commit -m "Include big buck bunny from internet archive"
#
## public domain book Alice in Wonderland from https://archive.org/details/alicesadventures19033gut
#wget https://archive.org/download/alicesadventures19033gut/19033-h.zip 
#unzip 19033-h.zip
#mv 19033-h alice_in_wonderland
#rm *.zip
#mv alice_in_wonderland/19033-h.htm alice_in_wonderland/index.html
#git annex add alice_in_wonderland
#git commit -m "add public domain Alice in Wonderland from Gutenberg"


cd ..

# grab a plain git annex repo
datalad install-handle http://psydata.ovgu.de/forrest_gump/.git demo_handle2

# new plain collection
datalad create-collection demo_collection

# add all handles
datalad add-handle demo_handle1 demo_collection
datalad add-handle demo_handle2 demo_collection

# handle meta data
cd demo_handle1
datalad describe --author "Datalad demo people" --license 'CC0' --description "All these is to know about demos"
cd ..

cd demo_collection
# XXX this should pull in the new handle meta-data, but doesn't ???
datalad update
# this leads to all of .git being commited with the meta data change
datalad describe --author "Datalad demo people" --license 'CC0' --description "All my little handles"

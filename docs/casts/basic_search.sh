full_title="Demo of basic datasets meta-data search using DataLad"
#run "set -eu  # Fail early if any error happens"

say "DataLad allows to aggregate dataset-level meta-data, i.e. data describing the dataset (description, authors, etc), from a variety of formats (see http://docs.datalad.org/en/latest/metadata.html for more info)."
say 'In this example we will start from a point where someone who has not used datalad before decided to find datasets which related to "raiders" (after "Raiders of the Lost Ark" movie) and neuroimaging.'
say 'As you will see below, upon the very first invocation of "datalad search" command, DataLad will need first to acquire aggregated meta-data for our collection of datasets available at https://datasets.datalad.org and for that it will install that top level super-dataset (a pure git repository) under ~/datalad:'
( sleep 4; type yes; key Return; ) &
run "datalad search raiders neuroimaging"

say '"search" searches within current dataset (unless -d option is used), and if it is outside of any it would offer to search within the ~/datalad we have just installed'
( sleep 4; type yes; key Return; ) &
run "datalad search raiders neuroimaging"

say "To avoid interactive question, you can specify to search within that dataset by using -d /// . And now let's specialize the search to not only list the dataset location, but also report the fields where match was found.  This time let's search for datasets with Haxby among the authors"
run "datalad search -d /// -s author -R haxby"
say "For convenience let's switch to that directory, and now all result paths to datasets (not yet installed) would be relative to current directory"
run "cd ~/datalad"
run "datalad search -s author -R haxby"

say "Instead of listing all matching fields, you could specify which fields to report using -r option (using * would list all of them)"
run "datalad search -s author -r name -r author Haxby"

say "Enough of searching!  Let's actually get all those interesting datasets (for now without all the data) we found."
say "We could easily do that by passing those reported path as arguments to datalad install command"
run "datalad search -s author haxby | xargs datalad install"
say "and explore what we have got"
run "datalad ls -Lr . | grep -v 'not installed'"
run "cat openfmri/ds000105/dataset_description.json"
say "and get data we are interested in, e.g. all the anatomicals within those installed BIDS datasets"
run "datalad get -J4 openfmri/ds000*/sub-*/anat"
run "datalad ls -Lr . | grep -v 'not installed'"

say "Now it is your turn to find some interesting datasets for yourself!"
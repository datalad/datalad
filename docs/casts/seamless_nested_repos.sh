say "DataLad provides seamless management of nested Git repositories..."

say "Let's create a dataset"
run "datalad create demo"
run "cd demo"
say "A DataLad dataset is just a Git repo with some initial configuration"
run "git log --oneline"

say "We can generate nested datasets, by telling DataLad to register a new dataset in a parent dataset"
run "datalad create -d . sub1"
say "A subdataset is nothing more than regular Git submodule"
run "git submodule"

say "Of course subdatasets can be nested"
run "datalad create -d . sub1/justadir/sub2"

say "Unlike Git, DataLad automatically takes care of committing all changes associated with the added subdataset up to the given parent dataset"
run "git status"

say "Let's create some content in the deepest subdataset"
run "mkdir sub1/justadir/sub2/anotherdir"
run "touch sub1/justadir/sub2/anotherdir/afile"

say "Git can only tell us that something underneath the top-most subdataset was modified"
run "git status"

say "DataLad saves us from further investigation"
run "datalad diff -r"

say "Like Git, it can report individual untracked files, but also across repository boundaries"
run "datalad diff -r --report-untracked all"

say "Adding this new content with Git or git-annex would be an exercise"
run_expfail "git add sub1/justadir/sub2/anotherdir/afile"

say "DataLad does not require users to determine the correct repository in the tree"
run "datalad add -d . sub1/justadir/sub2/anotherdir/afile"

say "Again, all associated changes in the entire dataset tree, up to the given parent dataset, were committed"
run "git status"

say "DataLad's 'diff' is able to report the changes from these related commits throughout the repository tree"
run "datalad diff --revision @~1 -r"

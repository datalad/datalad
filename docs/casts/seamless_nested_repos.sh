say "DataLad makes a tree of nested Git repositories feel like a big monorepo..."

say "Let's create a root dataset"
run "datalad create demo"
run "cd demo"
say "Any DataLad dataset is just a Git repo with some initial configuration"
run "git log --oneline"

say "We can nest datasets, by telling DataLad to register a new dataset in a parent dataset"
run "datalad create -d . sub1"
say "A subdataset is a regular Git submodule"
run "git submodule"

say "Datasets can be nested arbitrarily deep"
run "datalad create -d . sub1/justadir/sub2"

say "Unlike Git, DataLad automatically takes care of committing all changes associated with the added subdataset up to the given parent dataset"
run "datalad status"

say "Let's create some content in the deepest subdataset"
run "mkdir sub1/justadir/sub2/anotherdir"
run "touch sub1/justadir/sub2/anotherdir/afile"

say "Git only reports changes within a repository, in the case the whole subdataset"
run "git status"

say "DataLad considers the entire tree"
run "datalad status -r"

say "Like Git, it can report individual untracked files, but also across repository boundaries"
run "datalad status -r --untracked all"

say "Adding this new content with Git or git-annex would be an exercise"
run_expfail "git add sub1/justadir/sub2/anotherdir/afile"

say "Again, DataLad does not require users to determine the correct repository"
run "datalad save -d . sub1/justadir/sub2/anotherdir/afile"

say "All associated changes in the entire dataset tree were committed"
run "datalad status"

say "DataLad's 'diff' is able to report the changes from these related commits throughout the repository tree"
run "datalad diff -r -f @~1"

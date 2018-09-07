say "It is often helpful to keep track of the origin of data files. When generating data from other data, it is also useful to know what process led to these new data and what inputs were used."
say "DataLad can be used to keep such a record..."

say "We start with a dataset"
run "datalad create demo"
run "cd demo"

say "Let's say we are taking a mosaic image composed of flowers from Wikimedia. We want extract some of them into individual files -- maybe to use them in an art project later."
say "We can use git-annex to obtain this image straight from the web"
run "git annex addurl https://upload.wikimedia.org/wikipedia/commons/a/a5/Flower_poster_2.jpg --file sources/flowers.jpg"

say "We save it in the dataset"
run "datalad save -m 'Added flower mosaic from wikimedia'"

say "Now we can use DataLad's 'run' command to process this image and extract one of the mosaic tiles into its own JPEG file.  Let's extract the St. Bernard's Lily from the upper left corner."
run "datalad run convert -extract 1522x1522+0+0 sources/flowers.jpg st-bernard.jpg"

say "All we have to do is prefix ANY command with 'datalad run'. DataLad will inspect the dataset after the command has finished and save all modifications."
say "In order to reliably detect modifications, a dataset must not contain unsaved modifications prior to running a command. For example, if we try to extract the Scarlet Pimpernel image with unsaved changes..."
run "touch dirt"
run_expfail "datalad run convert -extract 1522x1522+1470+1470 sources/flowers.jpg pimpernel.jpg"

say "It has to be clean"
run "rm dirt"
run "datalad run convert -extract 1522x1522+1470+1470 sources/flowers.jpg pimpernel.jpg"

say "Every processing step is saved in the dataset, including the exact command and the content that was changed."
run "git show --stat"

say "On top of that, the origin of any dataset content obtained from elsewhere is on record too"
run "git annex whereis sources/flowers.jpg"

say "Based on this information, we can always reconstruct how any data file came to be -- across the entire life-time of a project"
run "git log --oneline @~3..@"
run "datalad diff --revision @~3..@"

say "We can also rerun any previous commands with 'datalad rerun'. Without any arguments, the command from the last commit will be executed."
run "datalad rerun"
run "git log --oneline --graph --name-only @~3..@"

say "In this case, a new commit isn't created because the output file didn't change. But let's say we add a step that displaces the Lily's pixels by a random amount."
run "datalad run convert -spread 10 st-bernard.jpg st-bernard-displaced.jpg"

say "Now, if we rerun the previous command, a new commit is created because the output's content changed."
run "datalad rerun"
run "git log --graph --oneline --name-only @~2.."

say "(We don't actually want the repeated 'spread' command, so let's reset to the parent commit.)"
run "git reset --hard @^"

say "We can also rerun multiple commits (with '--since') and choose where HEAD is when we start rerunning from (with --onto). When both arguments are set to empty strings, it means 'rerun all command with HEAD at the parent of the first commit a command'."
say "In other words, you can 'replay' the commands."
run "datalad rerun --since= --onto= --branch=verify"

say "Now we're on a new branch, 'verify', that contains the replayed history."
run "git log --oneline --graph master verify"

say "Let's compare the two branches."
run "datalad diff --revision master..verify"

say "We can see that the step that involved a random component produced different results."
say "And these are just two branches, so you can compare them using normal Git operations. The next command, for example, marks which commits are 'patch-equivalent'."

run "git log --oneline --left-right --cherry-mark master...verify"

say "Notice that all commits are marked as equivalent (=) except the 'random spread' ones."

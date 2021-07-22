say "Fast forward through some prior work..."

say "Let's assume a student developed an algorithm, using Git."
run "mkdir code; cd code; git init; touch work; git add work ; git commit -m 'MSc thesis by student A done'; cd .."

say "An another student collected some data, tracked with Git-annex."
run "mkdir data; cd data; git init; git annex init; echo 'DATA!' > work; git annex add work ; git commit -m 'Data collection by student B done'; cd .."

say "A postdoc performed an analysis with the new algorithm on that data, results tracked with Git-annex."

run "mkdir analysis; cd analysis; git init && git annex init"

say "Git submodules are perfect for versioned tracking of dependencies, code or data."
run "git submodule add ../code"
run "git submodule add ../data"
run "git -C data annex init"
run "git commit -m 'Add dependencies'"

run "touch work; git add work && git commit -m 'Analysis by postdoc done'; cd .."

say "This happened in the past... Now the students left and the postdocs is on vacation. Time for the PI to write up the paper..."

say "The paper is nothing but a new project that depends on the analysis of the study it will describe."
run "mkdir paper"
run "cd paper"
run "git init"
run "git submodule add ../analysis study"
say "Need to remember what the postdoc said: If a repo uses git-annex, need to init it. Does it?"
run "git -C study branch -a | grep git-annex"
say "Ok, seems to be"
run "git -C study annex init"
run "git commit -m 'Add analysis'"

say "Let Git assemble the entire working tree"
run "git submodule update --init --recursive"

say "Arrgh, there is a bug in the code, and the postdoc isn't here to work the fix in. But hey, Git is all distributed -- let's apply it right here, so we can move on with the science..."
run "echo 'fix' >> study/code/work"

say "Quickly commit the fix, so it can be pushed upstream later..."
run "git add study/code/work"

say "Erm... Needs to happen in the repository that actually contains the file...Need to look up the boundaries..."
run "git diff --submodule=diff"

say "Ok, let's do this..."
run "cd study/code"
run "git add work && git commit -m 'Fix'"

say "Damn, detached HEAD. Need to fix, or it will be difficult to push."
run "git reset HEAD~1"
run "git checkout master"
run "git add work && git commit -m 'Fix'"

say "Still have to commit all the way up...one sec..."
run "cd .."
run "git add code && git commit -m 'Fix'"
run "cd .."
run "git add study && git commit -m 'Fix'"

say "All fixed and committed, ready to start. Hopefully, there are no more bugs..."

say "Just need to have one quick look at the data. Git-annex will obtain it in no time..."
run "git annex get study/data/work"

say "Ah, right. Also needs to be done in the repository that actually has the file. I still remember the boundaries...Gotta keep them in mind."
run "git -C study/data annex get work"

say "Good! Now back to writing!"


say "So far the story with Git/Git-annex. Let's see how the exact same looks with DataLad..."
say "But first clean up..."
run "cd .."
run "rm -rf paper"

say "Git-annex protects the files it manages. First a user needs to give enough permissions."
run "chmod -R u+rwx paper"
run "rm -rf paper"

say "Now DataLad. We can use the identical repositories for the prior student and postdoc work. DataLad does not require that everyone uses DataLad."
run "datalad create --no-annex paper"
run "cd paper"

say "Cloning a dataset INTO a specified (super)dataset makes it a subdataset."
run "datalad clone --dataset . ../analysis study"
say "Requesting a particular file automatically obtains all needed subdatasets"
run "datalad get study/code/work"

say "Apply the code fix, and have it be detected"
run "echo 'fix' >> study/code/work"
run "datalad status"

say "Unlike Git, DataLad makes nested datasets feel like a monorepo"
run "datalad status --recursive"

say "Not just for reporting, but also for modification"
run "datalad save --dataset . -m 'Fix' study/code/work"
run "datalad status"

say "All modifications are committed up to a specified superdataset".

say "Requesting an annex'ed files is no different from any other file"
run "datalad get study/data/work"
run "cat study/data/work"

say "When done, just remove"
run "cd .."
run "datalad remove --dataset paper --recursive"

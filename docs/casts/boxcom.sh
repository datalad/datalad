say "Many people that need to exchange data use cloud storage services."
say "One of these services is 'box.com' -- they offer similar features as dropbox, but provide more storage for free (10GB at the moment)"
say "Here is how DataLad can be configured to use box.com for data storage and exchange..."

say "For the purpose of this demo, we'll set up a dataset that contains a 1MB file with some random binary data"
run "datalad create demo"
run "cd demo"
run "datalad run dd if=/dev/urandom of=big.dat bs=1M count=1"

say "Next we configure box.com as a remote storage location, using a git-annex command."
say "Git-annex requires the login credentials to be given as environment variables WEBDAV_USERNAME and WEBDAV_PASSWORD. This demo uses a script that hides the real credentials"
run ". ~/box.com_work.sh"

say "Now for the actual box.com configuration."
say "Key argument is the access URL: 'team/project_one' is where the data will be stored in the box.com account."
run "git annex initremote box.com type=webdav url=https://dav.box.com/dav/team/project_one chunk=50mb encryption=none"
say "The 'chunk' and 'encryption' arguments further tailor the setup. Files will be automatically split into chunks less than 50MB. This make synchronization faster, and allows for storing really large files. File can be encrypted before upload to prevent access without a secure key -- for this demo we opted to not use encryption"

say "The next step is optional"
say "We set up a (possibly private) GitHub repo to exchange/synchronize the dataset itself (but not its data). If you just want to have off-site data storage, but no collaboration with others, this is not needed"
say "For this demo we opt to create the dataset at github.com/datalad/exchange-demo"
run "datalad create-sibling-github --github-organization datalad --publish-depends box.com --access-protocol ssh exchange-demo"
say "We configured DataLad to automatically copy data over to box.com when the dataset is published to GitHub, so we can achieve both in one step:"

run "datalad publish --to github big.dat"
run "git annex whereis"
say "The data file was automatically copied to box.com"

say "Now let's see how a collaborator could get access to the data(set)"
say "Anyone with permission to access the dataset on GitHub can install it"
run "cd ../"
run "datalad install -s git@github.com:datalad/exchange-demo.git fromgh"

say "DataLad has reported the presence of a storage sibling 'box.com'"
say "Anyone with permission to access a box.com account that the original box.com folder has been shared with can get access to the stored content"
run "datalad siblings -d ~/fromgh enable -s box.com"
say "If DataLad does not yet know about a user's box.com account, the above command would have prompted the user to provide access credentials"

say "Let's confirm that the newly installed dataset is only aware of the GitHub and box.com locations"
run "cd fromgh"
run "git remote -v"

say "Now we can obtain the data file, without having to worry about where exactly it is hosted"
run "datalad get big.dat"
run "ls -sLh big.dat"

say "Similar configurations are possible for any data storage solutions supported by git-annex. See https://git-annex.branchable.com/special_remotes for more info."

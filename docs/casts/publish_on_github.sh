# this cast requires the ability to create 'datalad/publish-demo' on Github (must not exist yet)
# it also require SSH access to the URL demo.datalad.org (can be localhost)

say "Sharing is best done on a platform that many people visit. One of them is GitHub."
say "However, Git is not designed to handle large data files directly, and GitHub will refuse large files"
say "One can either use GitHub's own LFS tool ... or use DataLad to flexibly combine many possible data hosting solutions with a repository hosted on GitHub"
say "Here is how this looks..."

say "It starts with a dataset. We give it a description to more easily keep track of where data are."
run "datalad create demo --description \"original dataset location\""
run "cd demo"

say "For this demo, we are generating a large (600MB file) comprised of random data. A file of this size cannot be hosted on GitHub directly."
run "datalad run dd if=/dev/urandom of=big.dat bs=1M count=600"

say "Publishing this dataset in a way that allows anyone to simply install it from GitHub, AND get the big data file, requires two steps"
say "1. Host the data file at some publicly accessible location"
say "2. Configure DataLad to make sure that getting data from GitHub transparently requests from this other location instead"

say "Here we use a personal webserver with SSH access, but, in principle, any hosting solution supported by git-annex is equally suitable"
say "We create a remote sibling of our dataset under the name 'myserver' via SSH, and tell datalad to track it as a common data source that is available for any future installation of this dataset. Access to this location will happen via the given http:// URL, and --ui true tells to install DataLad web UI as on https://datasets.datalad.org. Note that /.git in the URL most likely to be necessary in your case."
run "datalad create-sibling -s myserver demo.datalad.org:public_html/publish-demo --ui true --as-common-datasrc demo-server --target-url http://demo.datalad.org/publish-demo/.git"

say "With this configuration in place, we can now create a repository on GitHub, and configure the remote sibling on the SSH server as a publication dependency"
run "datalad create-sibling-github --github-organization datalad --publish-depends myserver --access-protocol ssh publish-demo"

say "Let's quickly recap that the data file is just in our local dataset"
run "git annex whereis"

say "From now on, we can simply 'publish to GitHub' and DataLad will take care of the rest"
run "datalad publish --to github --transfer-data all"

say "We can confirm that our data file ended up on our server"
run "git annex whereis big.dat"

say "Now we simulate how it would look for a random person to obtain the data in this dataset from GitHub -- by installing into a new location, straight from GitHub (this does not require a GitHub account)"
run "cd ../"
run "datalad install -s git@github.com:datalad/publish-demo.git fromgh"
run "cd fromgh"

say "This dataset does not know how to access the original dataset location, only GitHub and our server"
run "git remote -v"

say "There is no further setup necessary, anyone can get the data -- if they have permission to access the URL of our own server"
run "datalad get big.dat"
run "ls -sLh big.dat"

say "Go publish!"

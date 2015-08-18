# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from abc import ABCMeta, abstractmethod
from os.path import dirname, join as pathjoin, exists, pardir, realpath

from ..support.annexrepo import AnnexRepo
from ..cmd import Runner
from ..utils import get_local_file_url
from ..utils import swallow_outputs

#GH_ORG=datalad
#GH_PREFIX=testrepo--

topdir = pathjoin(dirname(__file__), pardir, pardir)
reposdir = pathjoin(dirname(__file__), 'testrepos')

#flavor="$1"
#name="$2"

# Repo specific variables
#descr="datalad test repo $flavor/$name"
#repodir=$reposdir/$flavor/$name
#ghrepo=${GH_ORG}/${GH_PREFIX}$flavor--$name

# Information about the system
#git_version = $(git --version | sed -e 's,.* \([0-9]\),\1,g')
#annex_version = $(dpkg -l git-annex | awk '/^ii/{print $3;}')

git_version = "X"
annex_version = "Y"

class TestRepo(object):

    __metaclass__ = ABCMeta

    def __init__(self, path, puke_if_exists=True):
        if puke_if_exists and exists(path):
            raise RuntimeError("Directory %s for test repo already exist" % path)
        self.repo = AnnexRepo(path)
        self.runner = Runner(cwd=self.repo.path)
        self.create()

    @property
    def path(self):
        return self.repo.path

    def create_file(self, name, content, annex=False):
        filename = pathjoin(self.path, name)
        with open(filename, 'wb') as f:
            f.write(content.encode())
        (self.repo.annex_add if annex else self.repo.git_add)(name)

    def create_info_file(self):
        self.create_file('INFO.txt', """\
    git: %s
    annex: %s
""" % (git_version, annex_version), annex=False)

    @abstractmethod
    def create(self):
        raise NotImplementedError("Should be implemented in ")

    """rm_repo() {
    _info "removing $repodir"
    chmod +w -R $repodir/.git  # inefficient but for us sufficient
    rm -rf $repodir
}"""

    """create_github_repo() {
    _info "creating github repo"
    cd $repodir
    # it wouldn't delete or complain in exit code if exists already
    hub create -d "$descr (otherwise userless)" $ghrepo
    git remote | grep -q '^origin' || git remote add origin git://github.com/$ghrepo
    git push --set-upstream --all -f origin
}"""

class BasicTestRepo(TestRepo):
    def create(self):
        self.create_info_file()
        self.create_file('test.dat', '123', annex=False)
        with swallow_outputs() as cmo: # we don't need those outputs at this point
            self.repo.git_commit("Adding a basic INFO file and rudimentary load file for annex testing")
            # create_github_repo
            #	cp test.dat test-annex.dat
            #	git annex add test-annex.dat
            # git annex addurl --file=test-annex.dat https://raw.githubusercontent.com/$ghrepo/master/test.dat
            # TODO: windows etc??
            self.repo.annex_addurl_to_file(
                "test-annex.dat",
                get_local_file_url(realpath(pathjoin(self.path, 'test.dat'))))
            self.repo.git_commit("Adding a rudimentary git-annex load file")
            self.repo.annex_drop("test-annex.dat") # since available from URL
        #  git push --all origin # and push again

"""
initremote_archive() {
    git annex initremote annexed-archives \
        encryption=none type=external externaltype=dl+archive
}

flavor_archive() {
    create_repo
    initremote_archive
    create_info_file
    mkdir -p d; echo "123" > d/test.dat; tar -czf d.tar.gz d;
    mv d/test.dat test2.dat; rm -rf d;
    git annex add d.tar.gz
    git commit -m "Added tarball"
    key=$(git annex lookupkey d.tar.gz)
    git annex add test2.dat
    git commit -m "Added the load file"
    git annex addurl --file test2.dat dl+archive:$key/d/test.dat
    _info "Added the dl+archive URL, committing"
    #git commit -m "Added a url for the file"
    git annex drop --force test2.dat # TODO -- should work without force
    git annex get test2.dat
}

if [ -e $repodir ]; then
    # TODO -- ask
    rm_repo
fi

register_repo_submodule() {
    cd $reposdir
    _info "registering git submodule"
    # TODO: verify if not registered already
    #git submodule ...
    git submodule add --force git://github.com/$ghrepo ./$flavor/$name && \
        git commit -m "Added test $flavor/$name" -a && \
        git push origin
}

# cd datalad/tests/testrepos
# hub create -d "Super-submodule collating test repositories for datalad" datalad/testrepos

eval flavor_$flavor

#register_repo_submodule
"""

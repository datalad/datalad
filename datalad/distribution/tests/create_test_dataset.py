# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A Helper to initiate arbitrarily small/large test meta-dataset

"""

__docformat__ = 'restructuredtext'


import random
import logging
import tempfile

from datalad.utils import get_tempfile_kwargs
import os
from os.path import join as opj, abspath, relpath, pardir, isabs, isdir, \
    exists, islink, sep
from datalad.distribution.dataset import Dataset, datasetmethod, \
    resolve_path, EnsureDataset
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureInt, \
    EnsureBool
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo, FileInGitError, \
    FileNotInAnnexError
from datalad.interface.base import Interface
from datalad.cmd import CommandError
from datalad.cmd import Runner
from datalad.utils import expandpath, knows_annex, assure_dir, \
    is_explicit_path, on_windows

lgr = logging.getLogger('datalad.distribution.tests')


def _parse_spec(spec):
    out = []   # will return a list of tuples (min, max) for each layer
    for ilevel, level in enumerate(spec.split('/')):
        minmax = level.split('-')
        if len(minmax) == 1:  # only abs number specified
            minmax = int(minmax[0])
            min_, max_ = (minmax, minmax)
        elif len(minmax) == 2:
            min_, max_ = minmax
            if not min_:  # might be omitted entirely
                min_ = 0
            if not max_:
                raise ValueError("Specify max number at level %d. Full spec was: %s"
                                 % (ilevel, spec))
            min_ = int(min_)
            max_ = int(max_)
        else:
            raise ValueError("Must have only min-max at level %d" % ilevel)
        out.append((min_, max_))
    return out


def test_parse_spec():
    from nose.tools import eq_
    eq_(_parse_spec('0/3/-1'), [(0, 0), (3, 3), (0, 1)])
    eq_(_parse_spec('4-10'), [(4, 10)])


def _makeds(path, levels, ds=None):
    # we apparently can't import api functionality within api
    from datalad.api import install

    # make it a git (or annex??) repository... ok - let's do randomly one or another ;)
    RepoClass = GitRepo if random.randint(0, 1) else AnnexRepo
    lgr.info("Generating repo of class %s under %s", RepoClass, path)
    repo = RepoClass(path, create=True)
    # let's create some dummy file and add it to the beast
    fn = opj(path, "file%d.dat" % random.randint(1, 1000))
    with open(fn, 'w') as f:
        f.write(fn)
    repo.git_add(fn)
    repo.git_commit("Added %s" % fn)
    if ds:
        rpath = os.path.relpath(path, ds.path)
        out = install(
            dataset=ds,
            path=rpath,
            source='./' + rpath,
        )
        # TODO: The following is to be adapted when refactoring AnnexRepo/GitRepo to make it uniform
        if isinstance(ds.repo, AnnexRepo):
            ds.repo.commit("subdataset %s installed." % rpath)
        else:
            ds.repo.git_commit("subdataset %s installed." % rpath)

    if not levels:
        return

    # make a dataset for that one since we want to add sub datasets
    ds_ = Dataset(path)
    level, levels_ = levels[0], levels[1:]
    nrepos = random.randint(*level)  # how many subds to generate
    for irepo in range(nrepos):
        # we would like to have up to 2 leading dirs
        subds_path = opj(*(['d%i' % i for i in range(random.randint(0, 3))] + ['r%i' % irepo]))
        subds_fpath = opj(path, subds_path)
        yield subds_fpath
        # and all under
        for d in _makeds(subds_fpath, levels_, ds=ds_):
            yield d


class CreateTestDataset(Interface):
    """Create test (meta-)dataset.
    """

    _params_ = dict(
        path=Parameter(
            args=("path",),
            doc="path/name where to create (if specified, must not exist)",
            constraints=EnsureStr() | EnsureNone()),
        spec=Parameter(
            args=("--spec",),
            doc="""\
            spec for hierarchy, defined as a min-max (min could be omitted to assume 0)
            defining how many (random number from min to max) of sub-datasets to generate
            at any given level of the hierarchy.  Each level separated from each other with /.
            Example:  1-3/-2  would generate from 1 to 3 subdatasets at the top level, and
            up to two within those at the 2nd level
            """,
            constraints=EnsureStr() | EnsureNone()),
        seed=Parameter(
            args=("--seed",),
            doc="""seed for rng""",
            constraints=EnsureInt() | EnsureNone()),

    )

    @staticmethod
    def __call__(path=None, spec=None, seed=None):
        if spec is None:
            spec = "10/1-3/-2"  # 10 on top level, some random number from 1 to 3 at the 2nd, up to 2 on 3rd
        levels = _parse_spec(spec)

        if seed is not None:
            # TODO: if to be used within a bigger project we shouldn't seed main RNG
            random.seed(seed)
        if path is None:
            kw = get_tempfile_kwargs({}, prefix="ds")
            path = tempfile.mktemp(mkdir=True, **kw)
        else:
            # so we don't override anything
            assert not exists(path)
            os.makedirs(path)

        # now we should just make it happen and return list of all the datasets
        return list(_makeds(path, levels))

    @staticmethod
    def result_renderer_cmdline(res):
        from datalad.ui import ui
        if res is None:
            res = []
        if not len(res):
            ui.message("No repos were created... oops")
            return
        items= '\n'.join(map(str, res))
        msg = "{n} installed {obj} available at\n{items}".format(
            obj='items are' if len(res) > 1 else 'item is',
            n=len(res),
            items=items)
        ui.message(msg)

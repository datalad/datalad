# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""A Helper to initiate arbitrarily small/large test meta-dataset

"""

__docformat__ = 'numpy'


import logging
import os
import random
import tempfile
from os.path import (
    abspath,
    exists,
    isabs,
)
from os.path import join as opj

from datalad.distribution.dataset import Dataset
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureInt,
    EnsureNone,
    EnsureStr,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
from datalad.utils import get_tempfile_kwargs

lgr = logging.getLogger('datalad.distribution.tests')


def _parse_spec(spec):
    out = []   # will return a list of tuples (min, max) for each layer
    if not spec:
        return out
    for ilevel, level in enumerate(spec.split('/')):
        if not level:
            continue
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


def _makeds(path, levels, ds=None, max_leading_dirs=2):
    """Create a hierarchy of datasets

    Used recursively, with current invocation generating datasets for the
    first level, and delegating sub-levels to recursive invocation

    Parameters
    ----------
    path : str
      Path to the top directory under which dataset will be created.
      If relative -- relative to current directory
    levels : list of list
      List of specifications for :func:`random.randint` call per each level.
    ds : Dataset, optional
      Super-dataset which would contain a new dataset (thus its path would be
      a parent of path. Note that ds needs to be installed.
    max_leading_dirs : int, optional
      Up to how many leading directories within a dataset could lead to a
      sub-dataset

    Yields
    ------
    str
       Path to the generated dataset(s)

    """
    # we apparently can't import api functionality within api
    from datalad.api import save

    # To simplify managing all the file paths etc
    if not isabs(path):
        path = abspath(path)
    # make it a git (or annex??) repository... ok - let's do randomly one or another ;)
    RepoClass = GitRepo if random.randint(0, 1) else AnnexRepo
    lgr.info("Generating repo of class %s under %s", RepoClass, path)
    repo = RepoClass(path, create=True)
    # let's create some dummy file and add it to the beast
    fn = opj(path, "file%d.dat" % random.randint(1, 1000))
    with open(fn, 'w') as f:
        f.write(fn)
    repo.add(fn, git=True)
    repo.commit(msg="Added %s" % fn)

    yield path

    if levels:
        # make a dataset for that one since we want to add sub datasets
        ds_ = Dataset(path)
        # Process the levels
        level, levels_ = levels[0], levels[1:]
        nrepos = random.randint(*level)  # how many subds to generate
        for irepo in range(nrepos):
            # we would like to have up to 2 leading dirs
            subds_path = opj(*(['d%i' % i
                                for i in range(random.randint(0, max_leading_dirs+1))]
                               + ['r%i' % irepo]))
            subds_fpath = opj(path, subds_path)
            # yield all under
            for d in _makeds(subds_fpath, levels_, ds=ds_):
                yield d

    if ds:
        assert ds.is_installed()
        out = save(
            path,
            dataset=ds,
        )


@build_doc
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
    def __call__(path=None, *, spec=None, seed=None):
        levels = _parse_spec(spec)

        if seed is not None:
            # TODO: if to be used within a bigger project we shouldn't seed main RNG
            random.seed(seed)
        if path is None:
            kw = get_tempfile_kwargs({}, prefix="ds")
            path = tempfile.mkdtemp(**kw)
        else:
            # so we don't override anything
            assert not exists(path)
            os.makedirs(path)

        # now we should just make it happen and return list of all the datasets
        return list(_makeds(path, levels))

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        if res is None:
            res = []
        if not len(res):
            ui.message("No repos were created... oops")
            return
        items = '\n'.join(map(str, res))
        msg = "{n} installed {obj} available at\n{items}".format(
            obj='items are' if len(res) > 1 else 'item is',
            n=len(res),
            items=items)
        ui.message(msg)

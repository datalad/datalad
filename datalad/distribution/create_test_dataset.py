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
    """Parse a hierarchy spec string into a list of level descriptors.

    Each level is separated by ``/`` and has the form::

        [d]min[-max][+Nf]

    ``d`` prefix makes entries plain directories instead of subdatasets.
    ``+Nf`` suffix adds N tracked files to each dataset at that level
    (default: 1 file per dataset, as before).

    Returns a list of dicts with keys: min, max, is_dir, nfiles.
    """
    out = []
    if not spec:
        return out
    for ilevel, level in enumerate(spec.split('/')):
        if not level:
            continue

        is_dir = False
        nfiles = None  # None means "use the nfiles parameter default"

        # Check for +Nf suffix (e.g., "2+100f")
        if '+' in level and level.endswith('f'):
            level, nf_str = level.rsplit('+', 1)
            nfiles = int(nf_str[:-1])  # strip trailing 'f'

        # Check for 'd' prefix (plain directory, not subdataset)
        if level.startswith('d'):
            is_dir = True
            level = level[1:]

        minmax = level.split('-')
        if len(minmax) == 1:  # only abs number specified
            minmax = int(minmax[0])
            min_, max_ = (minmax, minmax)
        elif len(minmax) == 2:
            min_, max_ = minmax
            if not min_:  # might be omitted entirely
                min_ = 0
            if not max_:
                raise ValueError(
                    "Specify max number at level %d. Full spec was: %s"
                    % (ilevel, spec))
            min_ = int(min_)
            max_ = int(max_)
        else:
            raise ValueError(
                "Must have only min-max at level %d" % ilevel)

        out.append(dict(min=min_, max=max_, is_dir=is_dir, nfiles=nfiles))
    return out


def _makeds(path, levels, ds=None, max_leading_dirs=2, nfiles=1):
    """Create a hierarchy of datasets

    Used recursively, with current invocation generating datasets for the
    first level, and delegating sub-levels to recursive invocation

    Parameters
    ----------
    path : str
      Path to the top directory under which dataset will be created.
      If relative -- relative to current directory
    levels : list of dict
      List of level descriptors from :func:`_parse_spec`.
    ds : Dataset, optional
      Super-dataset which would contain a new dataset (thus its path would be
      a parent of path. Note that ds needs to be installed.
    max_leading_dirs : int, optional
      Up to how many leading directories within a dataset could lead to a
      sub-dataset
    nfiles : int, optional
      Number of files to create in each dataset (default 1).  Per-level
      ``+Nf`` spec overrides this.

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
    # Create tracked files
    for fi in range(nfiles):
        fn = opj(path, "file%d.dat" % fi)
        with open(fn, 'w') as f:
            f.write(fn)
    repo.add('.', git=True)
    repo.commit(msg="Added %d file(s)" % nfiles)

    yield path

    if levels:
        # make a dataset for that one since we want to add sub datasets
        ds_ = Dataset(path)
        # Process the levels
        level, levels_ = levels[0], levels[1:]
        nchildren = random.randint(level['min'], level['max'])
        child_nfiles = level.get('nfiles') or nfiles

        for ichild in range(nchildren):
            if level['is_dir']:
                # Plain directory with files, not a subdataset
                dirname = "dir%d" % ichild
                dirpath = opj(path, dirname)
                os.makedirs(dirpath, exist_ok=True)
                for fi in range(child_nfiles):
                    fn = opj(dirpath, "file%d.dat" % fi)
                    with open(fn, 'w') as f:
                        f.write(fn)
                repo.add(dirname, git=True)
            else:
                # Subdataset
                # we would like to have up to 2 leading dirs
                subds_path = opj(
                    *(['d%i' % i
                       for i in range(
                           random.randint(0, max_leading_dirs + 1))]
                      + ['r%i' % ichild]))
                subds_fpath = opj(path, subds_path)
                # yield all under
                for d in _makeds(subds_fpath, levels_, ds=ds_,
                                 nfiles=child_nfiles):
                    yield d

        if level['is_dir']:
            # Commit the directories we just created
            repo.commit(msg="Added %d directories" % nchildren)

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
            spec for hierarchy.  Each level is separated by ``/`` and has
            the form ``[d]min[-max][+Nf]``.

            ``min-max`` defines how many (random from min to max)
            sub-datasets to generate at that level (min can be omitted
            to assume 0).

            Prefix ``d`` makes entries plain directories instead of
            subdatasets (e.g. ``d3`` creates 3 dirs with files).

            Suffix ``+Nf`` creates N tracked files per entry at that
            level (overrides --nfiles for that level).

            Examples::

                1-3/-2        1–3 subdatasets at L1, up to 2 at L2
                2+100f/-2     2 subs at L1 each with 100 files, up to 2 at L2
                10/d5+50f     10 subs, each containing 5 plain dirs with 50 files
            """,
            constraints=EnsureStr() | EnsureNone()),
        seed=Parameter(
            args=("--seed",),
            doc="""seed for rng""",
            constraints=EnsureInt() | EnsureNone()),
        nfiles=Parameter(
            args=("--nfiles",),
            doc="""number of files to create in each dataset (default 1).
            Per-level +Nf suffix in spec overrides this.""",
            constraints=EnsureInt() | EnsureNone()),
    )

    @staticmethod
    def __call__(path=None, *, spec=None, seed=None, nfiles=None):
        levels = _parse_spec(spec)

        if seed is not None:
            # TODO: if to be used within a bigger project we shouldn't seed main RNG
            random.seed(seed)
        if nfiles is None:
            nfiles = 1
        if path is None:
            kw = get_tempfile_kwargs({}, prefix="ds")
            path = tempfile.mkdtemp(**kw)
        else:
            # so we don't override anything
            assert not exists(path)
            os.makedirs(path)

        # now we should just make it happen and return list of all the datasets
        return list(_makeds(path, levels, nfiles=nfiles))

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

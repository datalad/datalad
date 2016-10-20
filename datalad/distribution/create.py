# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset creation

"""

import logging
import uuid

from os import listdir
from os.path import isdir, realpath, relpath

from datalad.interface.base import Interface
from datalad.interface.save import Save
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_init_opts
from datalad.interface.common_opts import dataset_description
from datalad.interface.common_opts import nosave_opt
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.utils import handle_dirty_dataset
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureDType
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo
from datalad.utils import getpwd
from datalad.utils import with_pathsep

from .dataset import Dataset
from .dataset import datasetmethod
from .dataset import EnsureDataset
from .dataset import resolve_path


__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.create')


class Create(Interface):
    """Create a new dataset from scratch.

    This command initializes a new :term:`dataset` at a given location, or the
    current directory. The new dataset can optionally be registered in an
    existing :term:`superdataset` (the new dataset's path needs to be located
    within the superdataset for that, and the superdataset needs to be given
    explicitly). It is recommended to provide a brief description to label
    the dataset's nature *and* location, e.g. "Michael's music on black
    laptop". This helps humans to identify data locations in distributed
    scenarios.  By default an identifier comprised of user and machine name,
    plus path will be generated.

    Plain Git repositories can be created via the [PY: `no_annex` PY][CMD: --no-annex CMD] flag.
    However, the result will not be a full dataset, and, consequently,
    not all features are supported (e.g. a description).

    || REFLOW >>
    To create a local version of a remote dataset use the
    :func:`~datalad.api.install` command instead.
    << REFLOW ||

    .. note::
      Power-user info: This command uses :command:`git init`, and
      :command:`git annex init` to prepare the new dataset. Registering to a
      superdataset is performed via a :command:`git submodule add` operation
      in the discovered superdataset.
    """

    _params_ = dict(
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""path where the dataset shall be created, directories
            will be created as necessary. If no location is provided, a dataset
            will be created in the current working directory. Either way the
            command will error if the target directory is not empty.
            Use `force` to create a dataset in a non-empty directory.""",
            nargs='?',
            # put dataset 2nd to avoid useless conversion
            constraints=EnsureStr() | EnsureDataset() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='PATH',
            doc="""specify the dataset to perform the create operation on. If
            a dataset is give, a new subdataset will be created in it.""",
            constraints=EnsureDataset() | EnsureNone()),
        force=Parameter(
            args=("-f", "--force",),
            doc="""enforce creation of a dataset in a non-empty directory""",
            action='store_true'),
        description=dataset_description,
        no_annex=Parameter(
            args=("--no-annex",),
            doc="""if set, a plain Git repository will be created without any
            annex""",
            action='store_true'),
        save=nosave_opt,
        if_dirty=if_dirty_opt,
        annex_version=Parameter(
            args=("--annex-version",),
            doc="""select a particular annex repository version. The
            list of supported versions depends on the available git-annex
            version. This should be left untouched, unless you know what
            you are doing""",
            constraints=EnsureDType(int) | EnsureNone()),
        annex_backend=Parameter(
            args=("--annex-backend",),
            constraints=EnsureStr() | EnsureNone(),
            # not listing choices here on purpose to avoid future bugs
            doc="""set default hashing backend used by the new dataset.
            For a list of supported backends see the git-annex
            documentation. The default is optimized for maximum compatibility
            of datasets across platforms (especially those with limited
            path lengths)""",
            nargs=1),
        native_metadata_type=Parameter(
            args=('--native-metadata-type',),
            metavar='LABEL',
            action='append',
            constraints=EnsureStr() | EnsureNone(),
            doc="""Metadata type label. Must match the name of the respective
            parser implementation in Datalad (e.g. "bids").[CMD:  This option
            can be given multiple times CMD]"""),
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_init_opts=annex_init_opts,
    )

    @staticmethod
    @datasetmethod(name='create')
    def __call__(
            path=None,
            force=False,
            description=None,
            dataset=None,
            no_annex=False,
            save=True,
            annex_version=None,
            annex_backend='MD5E',
            native_metadata_type=None,
            if_dirty='save-before',
            git_opts=None,
            annex_opts=None,
            annex_init_opts=None):

        # two major cases
        # 1. we got a `dataset` -> we either want to create it (path is None),
        #    or another dataset in it (path is not None)
        # 2. we got no dataset -> we want to create a fresh dataset at the
        #    desired location, either at `path` or PWD

        # sanity check first
        if no_annex:
            if description:
                raise ValueError("Incompatible arguments: cannot specify "
                                 "description for annex repo and declaring "
                                 "no annex repo.")
            if annex_opts:
                raise ValueError("Incompatible arguments: cannot specify "
                                 "options for annex and declaring no "
                                 "annex repo.")
            if annex_init_opts:
                raise ValueError("Incompatible arguments: cannot specify "
                                 "options for annex init and declaring no "
                                 "annex repo.")

        if not isinstance(force, bool):
            raise ValueError("force should be bool, got %r.  Did you mean to provide a 'path'?" % force)

        # straight from input arg, no messing around before this
        if path is None:
            if dataset is None:
                # nothing given explicity, assume create fresh right here
                path = getpwd()
            else:
                # no path, but dataset -> create that dataset
                path = dataset.path
        else:
            # resolve the path against a potential dataset
            path = resolve_path(path, ds=dataset)

        # we know that we need to create a dataset at `path`
        assert(path is not None)

        # check for sane subdataset path
        real_targetpath = with_pathsep(realpath(path))  # realpath OK
        if dataset is not None:
            # make sure we get to an expected state
            if dataset.is_installed():
                handle_dirty_dataset(dataset, if_dirty)
            if not real_targetpath.startswith(  # realpath OK
                    with_pathsep(realpath(dataset.path))):  # realpath OK
                raise ValueError("path {} outside {}".format(path, dataset))

        # important to use the given Dataset object to avoid spurious ID
        # changes with not-yet-materialized Datasets
        tbds = dataset if dataset is not None and dataset.path == path else Dataset(path)

        # don't create in non-empty directory without `force`:
        if isdir(tbds.path) and listdir(tbds.path) != [] and not force:
            raise ValueError("Cannot create dataset in directory %s "
                             "(not empty). Use option 'force' in order to "
                             "ignore this and enforce creation." % tbds.path)

        if no_annex:
            lgr.info("Creating a new git repo at %s", tbds.path)
            GitRepo(
                tbds.path,
                url=None,
                create=True,
                git_opts=git_opts)
        else:
            # always come with annex when created from scratch
            lgr.info("Creating a new annex repo at %s", tbds.path)
            AnnexRepo(
                tbds.path,
                url=None,
                create=True,
                backend=annex_backend,
                version=annex_version,
                description=description,
                git_opts=git_opts,
                annex_opts=annex_opts,
                annex_init_opts=annex_init_opts)

        if native_metadata_type is not None:
            if not isinstance(native_metadata_type, list):
                native_metadata_type = [native_metadata_type]
            for nt in native_metadata_type:
                tbds.config.add('datalad.metadata.nativetype', nt)

        # record an ID for this repo for the afterlife
        # to be able to track siblings and children
        id_var = 'datalad.dataset.id'
        if id_var in tbds.config:
            # make sure we reset this variable completely, in case of a re-create
            tbds.config.unset(id_var, where='dataset')
        tbds.config.add(
            id_var,
            tbds.id if tbds.id is not None else uuid.uuid1().urn.split(':')[-1],
            where='dataset')

        # save everthing
        tbds.repo.add('.datalad', git=True)

        if save:
            Save.__call__(
                message='[DATALAD] new dataset',
                dataset=tbds,
                auto_add_changes=False,
                recursive=False)

        if dataset is not None and dataset.path != tbds.path:
            # we created a dataset in another dataset
            # -> make submodule
            from datalad.distribution.utils import _install_subds_inplace
            subdsrelpath = relpath(realpath(tbds.path), realpath(dataset.path))  # realpath OK
            _install_subds_inplace(ds=dataset, path=tbds.path,
                                   relativepath=subdsrelpath)
            # this will have staged the changes in the superdataset already
            if save:
                Save.__call__(
                    message='[DATALAD] added subdataset',
                    dataset=dataset,
                    auto_add_changes=False,
                    recursive=False)

        return tbds

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        if res is None:
            ui.message("Nothing was created")
        elif isinstance(res, Dataset):
            ui.message("Created dataset at %s." % res.path)

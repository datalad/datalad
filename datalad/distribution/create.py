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
from os.path import isdir
from os.path import join as opj

from datalad.interface.base import Interface
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_init_opts
from datalad.interface.common_opts import location_description
from datalad.interface.common_opts import nosave_opt
from datalad.interface.common_opts import shared_access_opt
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureKeyChoice
from datalad.support.constraints import EnsureDType
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo
from datalad.utils import getpwd

from .dataset import Dataset
from .dataset import datasetmethod
from .dataset import EnsureDataset
from .subdatasets import Subdatasets


__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.create')


@build_doc
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

    This command only creates a new dataset, it does not add any content to it,
    even if the target directory already contains additional files or
    directories.

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

    # in general this command will yield exactly one result
    return_type = 'item-or-list'
    # in general users expect to get an instance of the created dataset
    result_xfm = 'datasets'
    # result filter
    result_filter = EnsureKeyChoice('action', ('create',)) & \
                    EnsureKeyChoice('status', ('ok', 'notneeded'))

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
        description=location_description,
        no_annex=Parameter(
            args=("--no-annex",),
            doc="""if set, a plain Git repository will be created without any
            annex""",
            action='store_true'),
        save=nosave_opt,
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
        shared_access=shared_access_opt,
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_init_opts=annex_init_opts,
    )

    @staticmethod
    @datasetmethod(name='create')
    @eval_results
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
            shared_access=None,
            git_opts=None,
            annex_opts=None,
            annex_init_opts=None):

        # two major cases
        # 1. we got a `dataset` -> we either want to create it (path is None),
        #    or another dataset in it (path is not None)
        # 2. we got no dataset -> we want to create a fresh dataset at the
        #    desired location, either at `path` or PWD

        # sanity check first
        if git_opts:
            lgr.warning(
                "`git_opts` argument is presently ignored, please complain!")
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
        annotated_paths = AnnotatePaths.__call__(
            # nothing given explicitly, assume create fresh right here
            path=path if path else getpwd() if dataset is None else None,
            dataset=dataset,
            recursive=False,
            action='create',
            # we need to know whether we have to check for potential
            # subdataset collision
            force_parentds_discovery=True,
            # it is absolutely OK to have something that does not exist
            unavailable_path_status='',
            unavailable_path_msg=None,
            # if we have a dataset given that actually exists, we want to
            # fail if the requested path is not in it
            nondataset_path_status='error' if dataset and dataset.is_installed() else '',
            on_failure='ignore')
        path = None
        for r in annotated_paths:
            if r['status']:
                # this is dealt with already
                yield r
                continue
            if path is not None:
                raise ValueError("`create` can only handle single target path or dataset")
            path = r

        if len(annotated_paths) and path is None:
            # we got something, we complained already, done
            return

        # we know that we need to create a dataset at `path`
        assert(path is not None)

        # prep for yield
        path.update({'logger': lgr, 'type': 'dataset'})
        # just discard, we have a new story to tell
        path.pop('message', None)

        if 'parentds' in path and path['path'] in Subdatasets.__call__(
                dataset=path['parentds'],
                # any known
                fulfilled=None,
                recursive=False,
                result_xfm='paths'):
            path.update({
                'status': 'error',
                'message': ('collision with known subdataset in dataset %s',
                            path['parentds'])})
            yield path
            return

        if git_opts is None:
            git_opts = {}
        if shared_access:
            # configure `git --shared` value
            git_opts['shared'] = shared_access

        # important to use the given Dataset object to avoid spurious ID
        # changes with not-yet-materialized Datasets
        tbds = dataset if dataset is not None and dataset.path == path['path'] \
            else Dataset(path['path'])

        # don't create in non-empty directory without `force`:
        if isdir(tbds.path) and listdir(tbds.path) != [] and not force:
            path.update({
                'status': 'error',
                'message':
                    'will not create a dataset in a non-empty directory, use '
                    '`force` option to ignore'})
            yield path
            return

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

        # make sure that v6 annex repos never commit content under .datalad
        with open(opj(tbds.path, '.datalad', '.gitattributes'), 'a') as gitattr:
            # TODO this will need adjusting, when annex'ed aggregate meta data
            # comes around
            gitattr.write('** annex.largefiles=nothing\n')

        # save everything, we need to do this now and cannot merge with the
        # call below, because we may need to add this subdataset to a parent
        # but cannot until we have a first commit
        tbds.add('.datalad', to_git=True, save=save,
                 message='[DATALAD] new dataset')

        # the next only makes sense if we saved the created dataset,
        # otherwise we have no committed state to be registered
        # in the parent
        if save and dataset is not None and dataset.path != tbds.path:
            # we created a dataset in another dataset
            # -> make submodule
            for r in dataset.add(
                    tbds.path,
                    save=True,
                    return_type='generator',
                    result_filter=None,
                    result_xfm=None,
                    on_failure='ignore'):
                yield r

        path.update({'status': 'ok'})
        yield path

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.ui import ui
        if res.get('action', None) == 'create' and \
               res.get('status', None) == 'ok' and \
               res.get('type', None) == 'dataset':
            ui.message("Created dataset at {}.".format(res['path']))
        else:
            ui.message("Nothing was created")

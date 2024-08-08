# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset creation

"""

import logging
import os
import os.path as op
import random
import uuid
import warnings
from argparse import REMAINDER
from os import listdir

from datalad import (
    _seed,
    cfg,
)
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    path_under_rev_dataset,
    require_dataset,
    resolve_path,
)
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.common_opts import location_description
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureKeyChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
from datalad.utils import (
    Path,
    ensure_list,
    get_dataset_root,
    getpwd,
)

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.core.local.create')


@build_doc
class Create(Interface):
    """Create a new dataset from scratch.

    This command initializes a new dataset at a given location, or the
    current directory. The new dataset can optionally be registered in an
    existing superdataset (the new dataset's path needs to be located
    within the superdataset for that, and the superdataset needs to be given
    explicitly via [PY: `dataset` PY][CMD: --dataset CMD]). It is recommended
    to provide a brief description to label the dataset's nature *and*
    location, e.g. "Michael's music on black laptop". This helps humans to
    identify data locations in distributed scenarios.  By default an identifier
    comprised of user and machine name, plus path will be generated.

    This command only creates a new dataset, it does not add existing content
    to it, even if the target directory already contains additional files or
    directories.

    Plain Git repositories can be created via [PY: `annex=False` PY][CMD: --no-annex CMD].
    However, the result will not be a full dataset, and, consequently,
    not all features are supported (e.g. a description).

    || REFLOW >>
    To create a local version of a remote dataset use the
    :func:`~datalad.api.install` command instead.
    << REFLOW ||

    .. note::
      Power-user info: This command uses :command:`git init` and
      :command:`git annex init` to prepare the new dataset. Registering to a
      superdataset is performed via a :command:`git submodule add` operation
      in the discovered superdataset.
    """

    # in general this command will yield exactly one result
    return_type = 'item-or-list'
    # in general users expect to get an instance of the created dataset
    result_xfm = 'datasets'
    # result filter
    result_filter = \
        EnsureKeyChoice('action', ('create',)) & \
        EnsureKeyChoice('status', ('ok', 'notneeded'))

    _examples_ = [
        dict(text="Create a dataset 'mydataset' in the current directory",
             code_py="create(path='mydataset')",
             code_cmd="datalad create mydataset"),
        dict(text="Apply the text2git procedure upon creation of a dataset",
             code_py="create(path='mydataset', cfg_proc='text2git')",
             code_cmd="datalad create -c text2git mydataset"),
        dict(text="Create a subdataset in the root of an existing dataset",
             code_py="create(dataset='.', path='mysubdataset')",
             code_cmd="datalad create -d . mysubdataset"),
        dict(text="Create a dataset in an existing, non-empty directory",
             code_py="create(force=True)",
             code_cmd="datalad create --force"),
        dict(text="Create a plain Git repository",
             code_py="create(path='mydataset', annex=False)",
             code_cmd="datalad create --no-annex mydataset"),
    ]

    _params_ = dict(
        path=Parameter(
            args=("path",),
            nargs='?',
            metavar='PATH',
            doc="""path where the dataset shall be created, directories
            will be created as necessary. If no location is provided, a dataset
            will be created in the location specified by [PY: `dataset`
            PY][CMD: --dataset CMD] (if given) or the current working
            directory. Either way the command will error if the target
            directory is not empty. Use [PY: `force` PY][CMD: --force CMD] to
            create a dataset in a non-empty directory.""",
            # put dataset 2nd to avoid useless conversion
            constraints=EnsureStr() | EnsureDataset() | EnsureNone()),
        initopts=Parameter(
            args=("initopts",),
            metavar='INIT OPTIONS',
            nargs=REMAINDER,
            doc="""options to pass to :command:`git init`. [PY: Options can be
            given as a list of command line arguments or as a GitPython-style
            option dictionary PY][CMD: Any argument specified after the
            destination path of the repository will be passed to git-init
            as-is CMD]. Note that not all options will lead to viable results.
            For example '--bare' will not yield a repository where DataLad
            can adjust files in its working tree."""),
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='DATASET',
            doc="""specify the dataset to perform the create operation on. If
            a dataset is given along with `path`, a new subdataset will be created
            in it at the `path` provided to the create command. If a dataset is
            given but `path` is unspecified, a new dataset will be created at the
            location specified by this option.""",
            constraints=EnsureDataset() | EnsureNone()),
        force=Parameter(
            args=("-f", "--force",),
            doc="""enforce creation of a dataset in a non-empty directory""",
            action='store_true'),
        description=location_description,
        annex=Parameter(
            args=("--no-annex",),
            dest='annex',
            doc="""if [CMD: set CMD][PY: disabled PY], a plain Git repository
            will be created without any annex""",
            action='store_false'),
        # TODO seems to only cause a config flag to be set, this could be done
        # in a procedure
        fake_dates=Parameter(
            args=('--fake-dates',),
            action='store_true',
            doc="""Configure the repository to use fake dates. The date for a
            new commit will be set to one second later than the latest commit
            in the repository. This can be used to anonymize dates."""),
        cfg_proc=Parameter(
            args=("-c", "--cfg-proc"),
            metavar="PROC",
            action='append',
            doc="""Run cfg_PROC procedure(s) (can be specified multiple times)
            on the created dataset. Use
            [PY: `run_procedure(discover=True)` PY][CMD: run-procedure --discover CMD]
            to get a list of available procedures, such as cfg_text2git.
            """
        )
    )

    @staticmethod
    @datasetmethod(name='create')
    @eval_results
    def __call__(
            path=None,
            initopts=None,
            *,
            force=False,
            description=None,
            dataset=None,
            annex=True,
            fake_dates=False,
            cfg_proc=None
    ):
        # we only perform negative tests below
        no_annex = not annex

        if dataset:
            if isinstance(dataset, Dataset):
                ds = dataset
            else:
                ds = Dataset(dataset)
            refds_path = ds.path
        else:
            ds = refds_path = None

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

        if (isinstance(initopts, (list, tuple)) and '--bare' in initopts) or (
                isinstance(initopts, dict) and 'bare' in initopts):
            raise ValueError(
                "Creation of bare repositories is not supported. Consider "
                "one of the create-sibling commands, or use "
                "Git to init a bare repository and push an existing dataset "
                "into it.")

        if path:
            path = resolve_path(path, dataset)

        path = path if path \
            else getpwd() if ds is None \
            else refds_path

        # we know that we need to create a dataset at `path`
        assert(path is not None)

        # assure cfg_proc is a list (relevant if used via Python API)
        cfg_proc = ensure_list(cfg_proc)

        # prep for yield
        res = dict(action='create', path=str(path),
                   logger=lgr, type='dataset',
                   refds=refds_path)

        refds = None
        if refds_path and refds_path != str(path):
            refds = require_dataset(
                refds_path, check_installed=True,
                purpose='create a subdataset')

            path_inrefds = path_under_rev_dataset(refds, path)
            if path_inrefds is None:
                yield dict(
                    res,
                    status='error',
                    message=(
                        "dataset containing given paths is not underneath "
                        "the reference dataset %s: %s",
                        ds, str(path)),
                )
                return

        # try to locate an immediate parent dataset
        # we want to know this (irrespective of whether we plan on adding
        # this new dataset to a parent) in order to avoid conflicts with
        # a potentially absent/uninstalled subdataset of the parent
        # in this location
        # it will cost some filesystem traversal though...
        parentds_path = get_dataset_root(
            op.normpath(op.join(str(path), os.pardir)))
        if parentds_path:
            prepo = GitRepo(parentds_path)
            parentds_path = Path(parentds_path)
            # we cannot get away with a simple
            # GitRepo.get_content_info(), as we need to detect
            # uninstalled/added subdatasets too
            check_path = Path(path)
            pstatus = prepo.status(
                untracked='no',
                # limit query to target path for a potentially massive speed-up
                paths=[check_path.relative_to(parentds_path)])
            if (not pstatus.get(check_path, {}).get("type") == "dataset" and
                any(check_path == p or check_path in p.parents
                    for p in pstatus)):
                # redo the check in a slower fashion, it is already broken
                # let's take our time for a proper error message
                conflict = [
                    p for p in pstatus
                    if check_path == p or check_path in p.parents]
                res.update({
                    'status': 'error',
                    'message': (
                        'collision with content in parent dataset at %s: %s',
                        str(parentds_path),
                        [str(c) for c in conflict])})
                yield res
                return
            if not force:
                # another set of check to see whether the target path is pointing
                # into a known subdataset that is not around ATM
                subds_status = {
                    parentds_path / k.relative_to(prepo.path)
                    for k, v in pstatus.items()
                    if v.get('type', None) == 'dataset'}
                check_paths = [check_path]
                check_paths.extend(check_path.parents)
                if any(p in subds_status for p in check_paths):
                    conflict = [p for p in check_paths if p in subds_status]
                    res.update({
                        'status': 'error',
                        'message': (
                            'collision with %s (dataset) in dataset %s',
                            str(conflict[0]),
                            str(parentds_path))})
                    yield res
                    return

        # important to use the given Dataset object to avoid spurious ID
        # changes with not-yet-materialized Datasets
        tbds = ds if isinstance(ds, Dataset) and \
            ds.path == path else Dataset(str(path))

        # don't create in non-empty directory without `force`:
        if op.isdir(tbds.path) and listdir(tbds.path) != [] and not force:
            res.update({
                'status': 'error',
                'message':
                    'will not create a dataset in a non-empty directory, use '
                    '`--force` option to ignore'})
            yield res
            return

        # Check if specified cfg_proc(s) can be discovered, storing
        # the results so they can be used when the time comes to run
        # the procedure. If a procedure cannot be found, raise an
        # error to prevent creating the dataset.
        cfg_proc_specs = []
        if cfg_proc:
            discovered_procs = tbds.run_procedure(
                discover=True,
                result_renderer='disabled',
                return_type='list',
            )
            for cfg_proc_ in cfg_proc:
                for discovered_proc in discovered_procs:
                    if discovered_proc['procedure_name'] == 'cfg_' + cfg_proc_:
                        cfg_proc_specs.append(discovered_proc)
                        break
                else:
                    raise ValueError("Cannot find procedure with name "
                                     "'%s'" % cfg_proc_)

        if initopts is not None and isinstance(initopts, list):
            initopts = {'_from_cmdline_': initopts}

        # Note for the code below:
        # OPT: be "smart" and avoid re-resolving .repo -- expensive in DataLad
        # Reuse tbrepo instance, do not use tbds.repo

        # create and configure desired repository
        # also provides initial set of content to be tracked with git (not annex)
        if no_annex:
            tbrepo, add_to_git = _setup_git_repo(path, initopts, fake_dates)
        else:
            tbrepo, add_to_git = _setup_annex_repo(
                path, initopts, fake_dates, description)

        # OPT: be "smart" and avoid re-resolving .repo -- expensive in DataLad
        # Note, must not happen earlier (before if) since "smart" it would not be
        tbds_config = tbds.config

        # record an ID for this repo for the afterlife
        # to be able to track siblings and children
        id_var = 'datalad.dataset.id'
        # Note, that Dataset property `id` will change when we unset the
        # respective config. Therefore store it before:
        tbds_id = tbds.id
        if id_var in tbds_config:
            # make sure we reset this variable completely, in case of a
            # re-create
            tbds_config.unset(id_var, scope='branch')

        if _seed is None:
            # just the standard way
            # use a fully random identifier (i.e. UUID version 4)
            uuid_id = str(uuid.uuid4())
        else:
            # Let's generate preseeded ones
            uuid_id = str(uuid.UUID(int=random.getrandbits(128)))
        tbds_config.add(
            id_var,
            tbds_id if tbds_id is not None else uuid_id,
            scope='branch',
            reload=False)

        # make config overrides permanent in the repo config
        # this is similar to what `annex init` does
        # we are only doing this for config overrides and do not expose
        # a dedicated argument, because it is sufficient for the cmdline
        # and unnecessary for the Python API (there could simply be a
        # subsequence ds.config.add() call)
        for k, v in tbds_config.overrides.items():
            tbds_config.add(k, v, scope='local', reload=False)

        # all config manipulation is done -> fll reload
        tbds_config.reload()

        # must use the repo.pathobj as this will have resolved symlinks
        add_to_git[tbrepo.pathobj / '.datalad'] = {
            'type': 'directory',
            'state': 'untracked'}

        # save everything, we need to do this now and cannot merge with the
        # call below, because we may need to add this subdataset to a parent
        # but cannot until we have a first commit
        tbrepo.save(
            message='[DATALAD] new dataset',
            git=True,
            # we have to supply our own custom status, as the repo does
            # not have a single commit yet and the is no HEAD reference
            # TODO make `GitRepo.status()` robust to this state.
            _status=add_to_git,
        )

        for cfg_proc_spec in cfg_proc_specs:
            yield from tbds.run_procedure(
                cfg_proc_spec,
                result_renderer='disabled',
                return_type='generator',
            )

        # the next only makes sense if we saved the created dataset,
        # otherwise we have no committed state to be registered
        # in the parent
        if isinstance(refds, Dataset) and refds.path != tbds.path:
            # we created a dataset in another dataset
            # -> make submodule
            yield from refds.save(
                path=tbds.path,
                return_type='generator',
                result_renderer='disabled',
            )
        else:
            # if we do not save, we touch the root directory of the new
            # dataset to signal a change in the nature of the directory.
            # this is useful for apps like datalad-gooey (or other
            # inotify consumers) to pick up on such changes.
            tbds.pathobj.touch()

        res.update({'status': 'ok'})
        yield res


def _setup_git_repo(path, initopts=None, fake_dates=False):
    """Create and configure a repository at `path`

    Parameters
    ----------
    path: str or Path
      Path of the repository
    initopts: dict, optional
      Git options to be passed to the GitRepo constructor
    fake_dates: bool, optional
      Passed to the GitRepo constructor

    Returns
    -------
    GitRepo, dict
      Created repository and records for any repo component that needs to be
      passed to git-add as a result of the setup procedure.
    """
    tbrepo = GitRepo(
        path,
        create=True,
        create_sanity_checks=False,
        git_opts=initopts,
        fake_dates=fake_dates)
    # place a .noannex file to indicate annex to leave this repo alone
    stamp_path = Path(tbrepo.path) / '.noannex'
    stamp_path.touch()
    add_to_git = {
        stamp_path: {
            'type': 'file',
            'state': 'untracked',
        }
    }
    return tbrepo, add_to_git


def _setup_annex_repo(path, initopts=None, fake_dates=False,
                      description=None):
    """Create and configure a repository at `path`

    This includes a default setup of annex.largefiles.

    Parameters
    ----------
    path: str or Path
      Path of the repository
    initopts: dict, optional
      Git options to be passed to the AnnexRepo constructor
    fake_dates: bool, optional
      Passed to the AnnexRepo constructor
    description: str, optional
      Passed to the AnnexRepo constructor

    Returns
    -------
    AnnexRepo, dict
      Created repository and records for any repo component that needs to be
      passed to git-add as a result of the setup procedure.
    """
    # always come with annex when created from scratch
    tbrepo = AnnexRepo(
        path,
        create=True,
        create_sanity_checks=False,
        # do not set backend here, to avoid a dedicated commit
        backend=None,
        # None causes version to be taken from config
        version=None,
        description=description,
        git_opts=initopts,
        fake_dates=fake_dates
    )
    # set the annex backend in .gitattributes as a staged change
    tbrepo.set_default_backend(
        cfg.obtain('datalad.repo.backend'),
        persistent=True, commit=False)
    add_to_git = {
        tbrepo.pathobj / '.gitattributes': {
            'type': 'file',
            'state': 'added',
        }
    }
    # make sure that v6 annex repos never commit content under .datalad
    attrs_cfg = (
        ('config', 'annex.largefiles', 'nothing'),
    )
    attrs = tbrepo.get_gitattributes(
        [op.join('.datalad', i[0]) for i in attrs_cfg])
    set_attrs = []
    for p, k, v in attrs_cfg:
        if not attrs.get(
                op.join('.datalad', p), {}).get(k, None) == v:
            set_attrs.append((p, {k: v}))
    if set_attrs:
        tbrepo.set_gitattributes(
            set_attrs,
            attrfile=op.join('.datalad', '.gitattributes'))

    # prevent git annex from ever annexing .git* stuff (gh-1597)
    attrs = tbrepo.get_gitattributes('.git')
    if not attrs.get('.git', {}).get(
            'annex.largefiles', None) == 'nothing':
        tbrepo.set_gitattributes([
            ('**/.git*', {'annex.largefiles': 'nothing'})])
        # must use the repo.pathobj as this will have resolved symlinks
        add_to_git[tbrepo.pathobj / '.gitattributes'] = {
            'type': 'file',
            'state': 'untracked'}
    return tbrepo, add_to_git

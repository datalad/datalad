# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset (component) installation

"""


import logging
from os import curdir
from os import linesep
from os.path import join as opj
from os.path import relpath
from os.path import pardir
from os.path import exists

from six.moves.urllib.parse import quote as urlquote

from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import dataset_description
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import git_clone_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_init_opts
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import nosave_opt
from datalad.interface.utils import handle_dirty_dataset
from datalad.support.constraints import EnsureNone
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import InstallFailedError
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.support.param import Parameter
from datalad.support.network import RI
from datalad.support.network import URL
from datalad.support.network import DataLadRI
from datalad.support.network import is_url
from datalad.support.network import get_local_file_url
from datalad.utils import knows_annex
from datalad.utils import swallow_logs
from datalad.utils import rmtree
from datalad.dochelpers import exc_str

from .dataset import Dataset
from .dataset import datasetmethod
from .dataset import resolve_path
from .dataset import require_dataset
from .dataset import EnsureDataset
from .get import Get
from .utils import _fixup_submodule_dotgit_setup

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.install')


def _get_git_url_from_source(source):
    """Return URL for cloning associated with a source specification

    For now just resolves DataLadRIs
    """
    # TODO: Probably RF this into RI.as_git_url(), that would be overridden
    # by subclasses or sth. like that
    if not isinstance(source, RI):
        source_ri = RI(source)
    else:
        source_ri = source
    if isinstance(source_ri, DataLadRI):
        # we have got our DataLadRI as the source, so expand it
        source = source_ri.as_git_url()
    else:
        source = str(source_ri)
    return source


def _get_installationpath_from_url(url):
    """Returns a relative path derived from the trailing end of a URL

    This can be used to determine an installation path of a Dataset
    from a URL, analog to what `git clone` does.
    """
    path = url.rstrip('/')
    if '/' in path:
        path = path.split('/')
        if path[-1] == '.git':
            path = path[-2]
        else:
            path = path[-1]
    if path.endswith('.git'):
        path = path[:-4]
    return path


def _get_flexible_url_candidates(url, base_url=None, url_suffix=''):
    candidates = []
    if url.startswith('/') or is_url(url):
        # this seems to be an absolute location -> take as is
        candidates.append(url)
        # additionally try to consider .git:
        if not url.rstrip('/').endswith('/.git'):
            candidates.append(
                '{0}/.git'.format(url.rstrip('/')))
    else:
        # need to resolve relative URL
        base_url_l = base_url.split('/')
        url_l = url.split('/')
        for i, c in enumerate(url_l):
            if c == pardir:
                base_url_l = base_url_l[:-1]
            else:
                candidates.append('{0}/{1}{2}'.format(
                    '/'.join(base_url_l),
                    '/'.join(url_l[i:]),
                    url_suffix))
                break
    # TODO:
    # here clone_urls might contain degenerate urls which should be
    # normalized and not added into the pool of the ones to try if already
    # there, e.g. I got
    #  ['http://datasets.datalad.org/crcns/aa-1/.git', 'http://datasets.datalad.org/crcns/./aa-1/.git']
    # upon  install aa-1

    # TODO:
    # We need to provide some error msg with InstallFailedError, since now
    # it just swallows everything.

    return candidates


def _clone_from_any_source(sources, dest):
    # should not be the case, but we need to distinguish between failure
    # of git-clone, due to existing target and an unsuccessful clone
    # attempt. See below.
    existed = dest and exists(dest)
    for source_ in sources:
        try:
            lgr.debug("Retrieving a dataset from URL: "
                      "{0}".format(source_))
            with swallow_logs():
                GitRepo(dest, url=source_, create=True)
            return source_  # do not bother with other sources if succeeded
        except GitCommandError as e:
            lgr.debug("Failed to retrieve from URL: "
                      "{0}".format(source_))
            if not existed and dest \
                    and exists(dest):
                lgr.debug("Wiping out unsuccessful clone attempt at "
                          "{}".format(dest))
                rmtree(dest)

            if source_ == sources[-1]:
                # Note: The following block is evaluated whenever we
                # fail even with the last try. Not nice, but currently
                # necessary until we get a more precise exception:
                ####################################
                # TODO: We may want to introduce a --force option to
                # overwrite the target.
                # TODO: Currently assuming if `existed` and there is a
                # GitCommandError means that these both things are connected.
                # Need newer GitPython to get stderr from GitCommandError
                # (already fixed within GitPython.)
                if existed:
                    # rudimentary check for an installed dataset at target:
                    # (TODO: eventually check for being the one, that this
                    # is about)
                    dest_ds = Dataset(dest)
                    if dest_ds.is_installed():
                        lgr.info("{0} appears to be installed already."
                                 "".format(dest_ds))
                        break
                    else:
                        lgr.warning("Target {0} already exists and is not "
                                    "an installed dataset. Skipped."
                                    "".format(dest))
                        # Keep original in debug output:
                        lgr.debug("Original failure:{0}"
                                  "{1}".format(linesep, exc_str(e)))
                        return None
                ##################

                # Re-raise if failed even with the last candidate
                lgr.debug("Unable to establish repository instance at "
                          "{0} from {1}"
                          "".format(dest, sources))
                raise


def _get_tracking_source(ds):
    """Returns name and url of a potential configured source
    tracking remote"""
    vcs = ds.repo
    repo = vcs.repo
    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule
    tracking_branch = repo.active_branch.tracking_branch()
    remote_name = None
    remote_url = ''
    if tracking_branch:
        # name of the default remote for the active branch
        remote_name = repo.active_branch.tracking_branch().remote_name
        remote_url = vcs.get_remote_url(remote_name, push=False)
    return remote_name, remote_url


def _install_subds_from_flexible_source(ds, sm_path, sm_url):
    """Tries to obtain a given subdataset from several meaningful locations"""
    # compose a list of candidate clone URLs
    clone_urls = []
    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule
    remote_name, remote_url = _get_tracking_source(ds)
    # remember suffix
    url_suffix = ''
    if remote_url:
        if remote_url.rstrip('/').endswith('/.git'):
            url_suffix = '/.git'
            remote_url = remote_url[:-5]
        # attempt: submodule checkout at parent remote URL
        # We might need to quote sm_path portion, e.g. for spaces etc
        if isinstance(RI(remote_url), URL):
            sm_path_url = urlquote(sm_path)
        else:
            sm_path_url = sm_path
        clone_urls.append('{0}/{1}{2}'.format(
            remote_url, sm_path_url, url_suffix))
    # attempt: configured submodule URL
    # TODO: consider supporting DataLadRI here?  or would confuse
    #  git and we wouldn't want that (i.e. not allow pure git clone
    #  --recursive)
    clone_urls += _get_flexible_url_candidates(
        sm_url,
        remote_url if remote_url else ds.path,
        url_suffix)

    # now loop over all candidates and try to clone
    subds = Dataset(opj(ds.path, sm_path))
    try:
        clone_url = _clone_from_any_source(clone_urls, subds.path)
    except GitCommandError as e:
        raise InstallFailedError(
            "Failed to install dataset %s from %s (%s)",
            subds, clone_urls, e)
    # do fancy update
    if sm_path in ds.get_subdatasets(absolute=False, recursive=False):
        lgr.debug("Update cloned subdataset {0} in parent".format(subds))
        ds.repo.update_submodule(sm_path, init=True)
    else:
        # submodule is brand-new and previously unknown
        ds.repo.add_submodule(sm_path, url=clone_url)
    _fixup_submodule_dotgit_setup(ds, sm_path)
    return subds


class Install(Interface):
    """Install a dataset from a (remote) source.

    This command creates a local :term:`sibling` of an existing dataset from a
    (remote) location identified via a URL or path. Optional recursion into
    potential subdatasets, and download of all referenced data is supported.
    The new dataset can be optionally registered in an existing
    :term:`superdataset` by identifying it via the `dataset` argument (the new
    dataset's path needs to be located within the superdataset for that).

    It is recommended to provide a brief description to label the dataset's
    nature *and* location, e.g. "Michael's music on black laptop". This helps
    humans to identify data locations in distributed scenarios.  By default an
    identifier comprised of user and machine name, plus path will be generated.

    When only partial dataset content shall be obtained, it is recommended to
    use this command without the `get-data` flag, followed by a
    :func:`~datalad.api.get` operation to obtain the desired data.

    .. note::
      Power-user info: This command uses :command:`git clone`, and
      :command:`git annex init` to prepare the dataset. Registering to a
      superdataset is performed via a :command:`git submodule add` operation
      in the discovered superdataset.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            # TODO: this probably changes to install into the dataset (add_to_super)
            # and to install the thing 'just there' without operating 'on' a dataset.
            # Adapt doc.
            # MIH: `shouldn't this be the job of `add`?
            doc="""specify the dataset to perform the install operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            in a parent directory of the current working directory and/or the
            `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""path/name of the installation target.  If no `path` is
            provided a destination path will be derived from a source URL
            similar to :command:`git clone`""",
            nargs='?'),
        source=Parameter(
            args=('source',),
            metavar='SOURCE',
            doc="URL or local path of the installation source"),
        get_data=Parameter(
            args=("-g", "--get-data",),
            doc="""if given, obtain all data content too""",
            action="store_true"),
        description=dataset_description,
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        if_dirty=if_dirty_opt,
        save=nosave_opt,
        reckless=Parameter(
            args=("--reckless",),
            action="store_true",
            doc="""Set up the dataset to be able to obtain content in the
            cheapest/fastest possible way, even if this poses a potential
            risk the data integrity (e.g. hardlink files from a local clone
            of the dataset). Use with care, and limit to "read-only" use
            cases. With this flag the installed dataset will be marked as
            untrusted."""),
        git_opts=git_opts,
        git_clone_opts=git_clone_opts,
        annex_opts=annex_opts,
        annex_init_opts=annex_init_opts)

    @staticmethod
    @datasetmethod(name='install')
    def __call__(
            source,
            path=None,
            dataset=None,
            get_data=False,
            description=None,
            recursive=False,
            recursion_limit=None,
            if_dirty='save-before',
            save=True,
            reckless=False,
            git_opts=None,
            git_clone_opts=None,
            annex_opts=None,
            annex_init_opts=None):

        # parameter constraints:
        if not source:
            raise InsufficientArgumentsError(
                "a `source` is required for installation")

        if source == path:
            # even if they turn out to be identical after resolving symlinks
            # and more sophisticated witchcraft, it would still happily say
            # "it appears to be already installed", so we just catch an
            # obviously pointless input combination
            raise ValueError(
                "installation `source` and destination `path` are identical. "
                "If you are trying to add a subdataset simply use `save` %s".format(
                    path))

        installed_items = []

        # did we explicitly get a dataset to install into?
        # if we got a dataset, path will be resolved against it.
        # Otherwise path will be resolved first.
        ds = None
        if dataset is not None:
            ds = require_dataset(dataset, check_installed=True,
                                 purpose='installation')
            handle_dirty_dataset(ds, if_dirty)

        # resolve the target location (if local) against the provided dataset
        # or CWD:
        if path is not None:
            # Should work out just fine for regular paths, so no additional
            # conditioning is necessary
            try:
                path_ri = RI(path)
            except Exception as e:
                raise ValueError(
                    "invalid path argument {}: ({})".format(path, exc_str(e)))
            try:
                # Wouldn't work for SSHRI ATM, see TODO within SSHRI
                path = resolve_path(path_ri.localpath, dataset)
                # any `path` argument that point to something local now
                # resolved and is no longer a URL
            except ValueError:
                    # `path` is not a local path.
                    # TODO: The only thing left is a known subdataset with a
                    # name, that is not a path; Once we correctly distinguish
                    # between path and name of a submodule, we need to consider
                    # this.
                    # For now: Just raise
                    raise ValueError(
                        "Invalid destination path {0}".format(path))

        # `path` resolved, if there was any.

        # Possibly do conversion from source into a git-friendly url
        # luckily GitRepo will undo any fancy file:/// url to make use of Git's
        # optimization for local clones....
        source = _get_git_url_from_source(source)
        lgr.debug("Resolved source: {0}".format(source))
        # TODO: we probably need to resolve source, if it is a local path;
        # expandpath, normpath, ... Where exactly is the point to do it?

        # derive target from source:
        if path is None:
            # we got nothing but a source. do something similar to git clone
            # and derive the path from the source and continue
            lgr.debug(
                "Neither dataset nor target installation path provided. "
                "Deriving destination path from given source %s",
                source)
            path = _get_installationpath_from_url(source)
            # since this is a relative `path`, resolve it:
            path = resolve_path(path, dataset)

        # there is no other way -- my intoxicated brain tells me
        assert(path is not None)

        lgr.debug("Resolved installation target: {0}".format(path))
        destination_dataset = Dataset(path)

        if destination_dataset.is_installed():
            # this should not be, check if this is an error, or a reinstall
            # from the same source
            # this is where we would have installed this from
            candidate_sources = _get_flexible_url_candidates(
                source, destination_dataset.path)
            # this is where it was installed from
            track_name, track_url = _get_tracking_source(destination_dataset)
            if track_url in candidate_sources or get_local_file_url(track_url):
                lgr.info(
                    "%s was already installed from %s. Use `update` to obtain "
                    "latest updates",
                    destination_dataset, track_url)
                return destination_dataset
            else:
                raise ValueError("There is already a dataset installed at the "
                                 "destination: %s", destination_dataset)

        ###########
        # we should know everything necessary by now
        # actual installation starts
        ###########

        # FLOW GUIDE:
        # four cases:
        # 1. install into a dataset
        #   1.1. we install a known subdataset
        #        => git submodule update --init
        #   1.2. we install an existing repo as a subdataset inplace
        #        => git submodule add + magic
        #   1.3. we (recursively) try to install implicit subdatasets between
        #        ds and path
        #   1.4. we install a new subdataset from an explicit source
        #        => git submodule add
        # 2. we "just" install from an explicit source
        #    => git clone

        if ds is not None:
            # FLOW GUIDE: 1.

            # express the destination path relative to the root of
            # the dataset
            relativepath = relpath(path, start=ds.path)
            if relativepath.startswith(pardir):
                raise ValueError("installation path outside dataset "
                                 "({0})".format(path))
            lgr.debug("Resolved installation target relative to dataset "
                      "{0}: {1}".format(ds, relativepath))

            # FLOW_GUIDE 1.4.
            lgr.info("Installing subdataset from '{0}' at: {0}".format(
                source, relativepath))
            destination_dataset = _install_subds_from_flexible_source(
                ds,
                relativepath,
                source)
        else:
            # FLOW GUIDE: 2.
            lgr.info("Installing dataset at: {0}".format(path))

            # Currently assuming there is nothing at the target to deal with
            # and rely on failures raising from the git call ...

            # We possibly need to consider /.git URL
            candidate_sources = _get_flexible_url_candidates(source)
            _clone_from_any_source(candidate_sources, destination_dataset.path)

        # FLOW GUIDE: All four cases done.
        if not destination_dataset.is_installed():
            lgr.error("Installation failed.")
            return None

        # in any case check whether we need to annex-init the installed thing:
        if knows_annex(destination_dataset.path):
            # init annex when traces of a remote annex can be detected
            if reckless:
                lgr.debug(
                    "Instruct annex to hardlink content in %s from local "
                    "sources, if possible (reckless)", destination_dataset.path)
                destination_dataset.config.add(
                    'annex.hardlink', 'true', where='local', reload=True)
            lgr.info("Initializing annex repo at %s", destination_dataset.path)
            repo = AnnexRepo(destination_dataset.path, init=True)
            if reckless:
                repo._run_annex_command('untrust', annex_options=['here'])

        lgr.debug("Installation of %s done.", destination_dataset)

        if not destination_dataset.is_installed():
            # log error and don't report as installed item, but don't raise,
            # since we might be in a process of recursive installation where
            # a lot of other datasets can still be installed successfully.
            lgr.error("Installation of {0} failed.".format(destination_dataset))
        else:
            installed_items.append(destination_dataset)

        # Now, recursive calls:
        if recursive:
            if description:
                lgr.warning("Description can't be assigned recursively.")
            subs = destination_dataset.get_subdatasets(
                recursive=True,
                recursion_limit=recursion_limit,
                absolute=False)

            if subs:
                lgr.debug("Obtaining subdatasets of %s: %s",
                          destination_dataset,
                          subs)
                rec_installed = Get.__call__(
                    subs,  # all at once
                    dataset=destination_dataset,
                    recursive=True,
                    recursion_limit=recursion_limit,
                    fulfill_datasets=get_data,
                    git_opts=git_opts,
                    annex_opts=annex_opts,
                    # TODO expose this
                    #annex_get_opts=annex_get_opts,
                )
                # TODO do we want to filter this so `install` only returns
                # the datasets?
                if isinstance(rec_installed, list):
                    installed_items.extend(rec_installed)
                else:
                    installed_items.append(rec_installed)

        if get_data:
            lgr.debug("Getting data of {0}".format(destination_dataset))
            destination_dataset.get(curdir)

        # everything done => save changes:
        if save and ds is not None:
            # Note: The only possible changes are installed subdatasets, we
            # didn't know before.
            lgr.info("Saving changes to {0}".format(ds))
            ds.save(
                message='[DATALAD] installed subdataset{0}:{1}'.format(
                    "s" if len(installed_items) > 1 else "",
                    linesep + linesep.join([str(i) for i in installed_items])),
                auto_add_changes=False,
                recursive=False)

        if len(installed_items) == 1:
            return installed_items[0]
        else:
            return installed_items

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        if res is None:
            res = []
        if not isinstance(res, list):
            res = [res]
        if not len(res):
            ui.message("Nothing was installed")
            return
        items = '\n'.join(map(str, res))
        msg = "{n} installed {obj} available at\n{items}".format(
            obj='items are' if len(res) > 1 else 'item is',
            n=len(res),
            items=items)
        ui.message(msg)

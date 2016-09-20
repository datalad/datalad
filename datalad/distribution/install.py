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
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.support.param import Parameter
from datalad.support.network import RI
from datalad.support.network import URL
from datalad.support.network import DataLadRI
from datalad.support.network import is_url
from datalad.support.network import is_datalad_compat_ri
from datalad.utils import knows_annex, swallow_logs
from datalad.utils import rmtree
from datalad.dochelpers import exc_str

from .dataset import Dataset
from .dataset import datasetmethod
from .dataset import resolve_path
from .dataset import EnsureDataset
from .utils import _install_subds_inplace
from .utils import _fixup_submodule_dotgit_setup

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.install')


def _get_git_url_from_source(source, none_ok=False):
    """Return URL for cloning associated with a source specification

    For now just resolves DataLadRIs
    """
    # TODO: Probably RF this into RI.as_git_url(), that would be overridden
    # by subclasses or sth. like that

    if source is None:
        if not none_ok:
            lgr.warning("received 'None' as 'source'.")
        return source

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


def _install_subds_from_flexible_source(ds, sm_path, sm_url, recursive):
    """Tries to obtain a given subdataset from several meaningful locations"""

    # shortcut
    vcs = ds.repo
    repo = vcs.repo
    # compose a list of candidate clone URLs
    clone_urls = []
    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule
    tracking_branch = repo.active_branch.tracking_branch()
    remote_url = ''
    # remember suffix
    url_suffix = ''
    if tracking_branch:
        # name of the default remote for the active branch
        remote_name = repo.active_branch.tracking_branch().remote_name
        remote_url = vcs.get_remote_url(remote_name, push=False)
        if remote_url.rstrip('/').endswith('/.git'):
            url_suffix = '/.git'
            remote_url = remote_url[:-5]
        # attempt: submodule checkout at parent remote URL
        # We might need to quote sm_path portion, e.g. for spaces etc
        if remote_url and isinstance(RI(remote_url), URL):
            sm_path_url = urlquote(sm_path)
        else:
            sm_path_url = sm_path
        clone_urls.append('{0}/{1}{2}'.format(
            remote_url, sm_path_url, url_suffix))
    # attempt: configured submodule URL
    # TODO: consider supporting DataLadRI here?  or would confuse
    #  git and we wouldn't want that (i.e. not allow pure git clone
    #  --recursive)
    if sm_url.startswith('/') or is_url(sm_url):
        # this seems to be an absolute location -> take as is
        clone_urls.append(sm_url)
    else:
        # need to resolve relative URL
        if not remote_url:
            # we have no remote URL, hence we need to go with the
            # local path
            remote_url = ds.path
        remote_url_l = remote_url.split('/')
        sm_url_l = sm_url.split('/')
        for i, c in enumerate(sm_url_l):
            if c == pardir:
                remote_url_l = remote_url_l[:-1]
            else:
                clone_urls.append('{0}/{1}{2}'.format(
                    '/'.join(remote_url_l),
                    '/'.join(sm_url_l[i:]),
                    url_suffix))
                break
    # now loop over all candidates and try to clone
    subds = Dataset(opj(ds.path, sm_path))
    for clone_url in clone_urls:
        lgr.debug("Attempt clone of subdataset from: {0}".format(clone_url))

        # Note: Condition is a special case handling for now, where install
        # is called to install an existing ds in place. Here it calls install
        # again, without a dataset to install it into, since the call is about
        # the cloning only, which isn't necessary in this case and the addition
        # is done afterwards.
        # TODO: RF this helper function; currently its logic is somewhat
        # conflicting with new install API
        if not subds.is_installed():
            try:
                GitRepo(path=subds.path, url=clone_url, create=True)

                # Note for RF'ing: The following was originally used and would
                # currently lead to doing several things twice, like annex init,
                # analyzing what to install where, etc. Additionally, atm
                # recursion is done outside anyway
                # subds = Install.__call__(
                #     path=subds.path, source=clone_url,
                #     recursive=recursive)
            except GitCommandError as e:
                lgr.debug("clone attempt failed:{0}{1}".format(linesep, exc_str(e)))
                # TODO: failed clone might leave something behind that causes the
                # next attempt to fail as well. Implement safe way to remove clone
                # attempt left-overs.
                # Note: Do in GitRepo.clone()!
                continue
        lgr.debug("Update cloned subdataset {0} in parent".format(subds))
        if sm_path in ds.get_subdatasets(absolute=False, recursive=False):
            ds.repo.update_submodule(sm_path, init=True)
        else:
            # submodule is brand-new and previously unknown
            ds.repo.add_submodule(sm_path, url=clone_url)
        _fixup_submodule_dotgit_setup(ds, sm_path)
        return subds


# TODO:  git_clone options
# use --shared by default? => option --no-shared


class Install(Interface):
    """Install a dataset or subdataset.

    This command creates a local :term:`sibling` of an existing dataset from a
    (remote) location identified via a URL or path, or by the name of a
    registered subdataset. Optional recursion into potential subdatasets, and
    download of all referenced data is supported. The new dataset can be
    optionally registered in an existing :term:`superdataset` (the new
    dataset's path needs to be located within the superdataset for that, and
    the superdataset will be detected automatically). It is recommended to
    provide a brief description to label the dataset's nature *and* location,
    e.g. "Michael's music on black laptop". This helps humans to identify data
    locations in distributed scenarios.  By default an identifier comprised of
    user and machine name, plus path will be generated.

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
            doc="""specify the dataset to perform the install operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            in a parent directory of the current working directory and/or the
            `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            doc="""path/name of the installation target.  If no `source` is
            provided, and no `dataset` is given or detected, this is
            interpreted as the source URL of a dataset and a destination
            path will be derived from the URL similar to :command:`git
            clone`""",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        source=Parameter(
            args=("-s", "--source",),
            doc="URL or local path of the installation source",
            constraints=EnsureStr() | EnsureNone()),
        get_data=Parameter(
            args=("-g", "--get-data",),
            doc="""if given, obtain all data content too""",
            action="store_true"),
        description=dataset_description,
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        if_dirty=if_dirty_opt,
        save=nosave_opt,
        git_opts=git_opts,
        git_clone_opts=git_clone_opts,
        annex_opts=annex_opts,
        annex_init_opts=annex_init_opts)

    @staticmethod
    @datasetmethod(name='install')
    def __call__(
            path=None,
            source=None,
            dataset=None,
            get_data=False,
            description=None,
            recursive=False,
            recursion_limit=None,
            if_dirty='save-before',
            save=True,
            git_opts=None,
            git_clone_opts=None,
            annex_opts=None,
            annex_init_opts=None):

        lgr.debug(
            "Installation attempt started. path=%r, source=%r, dataset=%r, "
            "get_data=%r, description=%r, recursive=%r, recursion_limit=%r, "
            "git_opts=%r, git_clone_opts=%r, annex_opts=%r, annex_init_opt=%r",
            path, source, dataset, get_data, description, recursive,
            recursion_limit, git_opts, git_clone_opts, annex_opts,
            annex_init_opts)

        # shortcut
        ds = dataset

        _install_into_ds = False  # default
        # did we explicitly get a dataset to install into?
        # if we got a dataset, path will be resolved against it.
        # Otherwise path will be resolved first.

        if ds is not None:
            _install_into_ds = True
            if not isinstance(ds, Dataset):
                ds = Dataset(ds)
            if not ds.is_installed():
                # TODO: possible magic: ds.install() for known subdataset 'ds'
                raise ValueError("{0} needs to be installed in order to "
                                 "install something into it.".format(ds))
            handle_dirty_dataset(ds, if_dirty)

        # resolve the target location (if local) against the provided dataset
        # or CWD:
        if path is not None:
            # Should work out just fine for regular paths, so no additional
            # conditioning is necessary
            path_ri = RI(path)
            try:
                # Wouldn't work for SSHRI ATM, see TODO within SSHRI
                path = resolve_path(path_ri.localpath, ds)
                # any `path` argument that point to something local now
                # resolved and is no longer a URL
            except ValueError:
                # URL doesn't point to a local something
                # so we have an actual URL in `path`. Since this is valid as a
                # single positional argument, `source` has to be None at this
                # point.

                if is_datalad_compat_ri(path) and source is None:
                    # we have an actual URL -> this should be the source
                    lgr.debug(
                        "Single argument given to install, that doesn't seem to "
                        "be a local path. "
                        "Assuming the argument identifies a source location.")
                    source = path
                    path = None

                else:
                    # `path` is neither a valid source nor a local path.
                    # TODO: The only thing left is a known subdataset with a
                    # name, that is not a path; Once we correctly distinguish
                    # between path and name of a submodule, we need to consider
                    # this.
                    # For now: Just raise
                    raise ValueError("Invalid path argument {0}".format(path))

        # `path` resolved, if there was any.

        # we need a source to install from. Either we have one in `source` or
        # it is implicit, since `path` is an already known subdataset or an
        # existing dataset, that should be installed into the given dataset as a
        # subdataset inplace.
        # Note: For now, we do not consider a subdataset beneath a not yet
        # installed level, since we do not know, whether this even is something
        # to install (an actual Dataset) the only thing we know would be,
        # that it is some path beneath it.
        _install_known_sub = False

        if _install_into_ds and source is None and path is not None:
            # Check for `path` being a known subdataset:
            if path in [opj(ds.path, sub)
                        for sub in ds.get_subdatasets(recursive=True)]:
                _install_known_sub = True
                lgr.debug("Identified {0} as subdataset to "
                          "install.".format(path))
            else:
                # the only option left is an existing repo to be added inplace:
                if exists(path) and GitRepo.is_valid_repo(path):
                    lgr.debug("No source given, but path points to an existing "
                              "repository and a dataset to install into was "
                              "given. Assuming we want to install {0} "
                              "inplace into {1}.".format(path, ds))
                    source = path

        if source is None and not _install_known_sub and path is not None:
            # we have no source and don't have a dataset to install into.
            # could be a single positional argument, that points to a known
            # subdataset.
            # So, test for that last remaining option:

            # if `path` was a known subdataset to be installed, let's assume
            # it would be one:
            assume_ds = Dataset(path)
            candidate_super_ds = assume_ds.get_superdataset()

            if candidate_super_ds and candidate_super_ds != assume_ds and \
                assume_ds.path in candidate_super_ds.get_subdatasets(absolute=True):

                # `path` has a potential superdataset and is known to this
                # candidate
                _install_known_sub = True
                _install_into_ds = True
                ds = candidate_super_ds

            else:
                # no match, we can't deal with that `path` argument
                # without a `source`:
                raise InsufficientArgumentsError(
                    "Got no source to install from.")

        _install_inplace = False
        from os.path import realpath
        # TODO: does it make sense to use realpath here or just normpath for
        #       comparison?
        #       Consider: If normpath wouldn't be equal, but realpath would -
        #       is there any use case, where such a setup would be benefitial
        #       instead of being troublesome?
        if source and path and realpath(source) == realpath(path):
            if _install_into_ds:
                _install_inplace = True
            else:
                raise InsufficientArgumentsError(
                    "Source and target are the same ({0}). This doesn't make "
                    "sense without a dataset to install into.".format(path))

        # Possibly do conversion from source into a git-friendly url
        source_url = _get_git_url_from_source(source, none_ok=True)
        lgr.debug("Resolved source: {0}".format(source_url))
        # TODO: we probably need to resolve source_url, if it is a local path;
        # expandpath, normpath, ... Where exactly is the point to do it?

        # derive target from source url:
        if path is None and source_url is not None:
            # we got nothing but a source. do something similar to git clone
            # and derive the path from the source_url and continue
            lgr.debug(
                "Neither dataset nor target installation path provided. "
                "Assuming installation of a remote dataset. "
                "Deriving destination path from given source {0}".format(
                    source_url))
            path = _get_installationpath_from_url(source_url)
            # since this is a relative `path`, resolve it:
            path = resolve_path(path, ds)

        if path is None:
            # still no target => fail
            raise InsufficientArgumentsError("Got no target to install to.")

        lgr.debug("Resolved installation target: {0}".format(path))
        current_dataset = Dataset(path)

        ###########
        # we should know everything necessary by now
        # actual installation starts
        ###########

        installed_items = []
        # FLOW GUIDE:
        # four cases:
        # 1. install into a dataset
        #   1.1. we install a known subdataset
        #        => git submodule update --init
        #   1.2. we install an existing repo as a subdataset inplace
        #        => git submodule add + magic
        #   1.3. we install a new subdataset from an explicit source
        #        => git submodule add
        # 2. we "just" install from an explicit source
        #    => git clone

        if _install_into_ds:
            # FLOW GUIDE: 1.
            lgr.info("Installing subdataset at: {0}".format(path))

            # express the destination path relative to the root of
            # the dataset
            relativepath = relpath(path, start=ds.path)
            if relativepath.startswith(pardir):
                raise ValueError("installation path outside dataset "
                                 "({0})".format(path))
            lgr.debug("Resolved installation target relative to dataset "
                      "{0}: {1}".format(ds, relativepath))

            if _install_known_sub:
                # FLOW_GUIDE: 1.1.
                submodule = [sm for sm in ds.repo.get_submodules()
                             if sm.path == relativepath][0]

                current_dataset = _install_subds_from_flexible_source(
                    ds,
                    submodule.path,
                    submodule.url,
                    recursive=False)

            elif _install_inplace:
                # FLOW GUIDE: 1.2.
                current_dataset = _install_subds_inplace(
                    ds,
                    path,
                    relpath(path, ds.path),
                    recursive=False)
            else:
                # FLOW_GUIDE 1.3.
                current_dataset = _install_subds_from_flexible_source(
                    ds,
                    relativepath,
                    source_url,
                    recursive=False)
        else:
            # FLOW GUIDE: 2.
            lgr.info("Installing dataset at: {0}".format(path))

            # Currently assuming there is nothing at the target to deal with
            # and rely on failures raising from the git call ...

            # should not be the case, but we need to distinguish between failure
            # of git-clone, due to existing target and an unsuccessful clone
            # attempt. See below.
            existed = current_dataset.path and exists(current_dataset.path)

            vcs = None
            # We possibly need to consider /.git URL
            candidate_source_urls = [source_url]
            if source_url and not source_url.rstrip('/').endswith('/.git'):
                candidate_source_urls.append(
                    '{0}/.git'.format(source_url.rstrip('/')))

            for source_url_ in candidate_source_urls:
                try:
                    lgr.debug("Retrieving a dataset from URL: "
                              "{0}".format(source_url_))
                    with swallow_logs():
                        vcs = Install._get_new_vcs(current_dataset, source_url_)
                    break  # do not bother with other sources if succeeded
                except GitCommandError:
                    lgr.debug("Failed to retrieve from URL: "
                              "{0}".format(source_url_))
                    if not existed and current_dataset.path \
                            and exists(current_dataset.path):
                        lgr.debug("Wiping out unsuccessful clone attempt at "
                                  "{}".format(current_dataset.path))
                        rmtree(current_dataset.path)
                    if source_url_ == candidate_source_urls[-1]:
                        # Re-raise if failed even with the last candidate
                        lgr.debug("Unable to establish repository instance at "
                                  "{0} from {1}"
                                  "".format(current_dataset.path,
                                            candidate_source_urls))
                        raise

            # cloning done

        # FLOW GUIDE: All four cases done.

        # in any case check whether we need to annex-init the installed thing:
        if knows_annex(current_dataset.path):
            # init annex when traces of a remote annex can be detected
            lgr.info("Initializing annex repo at %s", current_dataset.path)
            AnnexRepo(current_dataset.path, init=True)

        lgr.debug("Installation of {0} done.".format(current_dataset))

        if not current_dataset.is_installed():
            # log error and don't report as installed item, but don't raise,
            # since we might be in a process of recursive installation where
            # a lot of other datasets can still be installed successfully.
            lgr.error("Installation of {0} failed.".format(current_dataset))
        else:
            installed_items.append(current_dataset)

        # Now, recursive calls:
        if recursive and \
                (recursion_limit is None
                 or (recursion_limit and recursion_limit > 0)):
            if description:
                lgr.warning("Description can't be assigned recursively.")
            subs = [Dataset(p) for p in
                    current_dataset.get_subdatasets(recursive=True,
                                                    recursion_limit=1,
                                                    absolute=True)]
            for subds in subs:
                if subds.is_installed():
                    lgr.debug("subdataset {0} already installed."
                              " Skipped.".format(subds))
                else:
                    rec_installed = Install.__call__(
                        path=subds.path,
                        dataset=current_dataset,
                        recursive=True,
                        recursion_limit=recursion_limit - 1
                        if recursion_limit else None,
                        if_dirty=if_dirty,
                        save=save,
                        git_opts=git_opts,
                        git_clone_opts=git_clone_opts,
                        annex_opts=annex_opts,
                        annex_init_opts=annex_init_opts)
                    if isinstance(rec_installed, list):
                        installed_items.extend(rec_installed)
                    else:
                        installed_items.append(rec_installed)

        # get the content of installed (sub-)datasets:
        if get_data:
            for d in installed_items:
                lgr.debug("Getting data of {0}".format(d))
                if isinstance(d.repo, AnnexRepo):
                    d.get(curdir)

        # everything done => save changes:
        if save and _install_into_ds and not _install_known_sub:
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
    def _get_new_vcs(ds, source):
        if source is None:
            raise RuntimeError(
                "No `source` was provided. To create a new dataset "
                "use the `create` command.")
        else:
            # when obtained from remote, try with plain Git
            lgr.info("Creating a new git repo at %s", ds.path)
            vcs = GitRepo(ds.path, url=source, create=True)
            if knows_annex(ds.path):
                # init annex when traces of a remote annex can be detected
                lgr.info("Initializing annex repo at %s", ds.path)
                vcs = AnnexRepo(ds.path, init=True)
            else:
                lgr.debug("New repository clone has no traces of an annex")
        return vcs

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


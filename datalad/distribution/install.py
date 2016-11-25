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
from os.path import relpath
from os.path import pardir

from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import dataset_description
from datalad.interface.common_opts import jobs_opt
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import git_clone_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_init_opts
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import nosave_opt
from datalad.interface.common_opts import reckless_opt
from datalad.interface.utils import handle_dirty_dataset
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureStr
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import InstallFailedError
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.param import Parameter
from datalad.support.network import RI
from datalad.support.network import PathRI
from datalad.support.network import is_datalad_compat_ri
from datalad.support.network import get_local_file_url
from datalad.utils import assure_list
from datalad.dochelpers import exc_str
from datalad.dochelpers import single_or_plural

from .dataset import Dataset
from .dataset import datasetmethod
from .dataset import resolve_path
from .dataset import require_dataset
from .dataset import EnsureDataset
from .get import Get
from .utils import _get_git_url_from_source
from .utils import _install_subds_from_flexible_source
from .utils import _get_flexible_source_candidates
from .utils import _get_tracking_source
from .utils import _clone_from_any_source
from .utils import _handle_possible_annex_dataset
from .utils import _save_installed_datasets

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.install')


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
            nargs="*",
            # doc: TODO
            doc="""path/name of the installation target.  If no `path` is
            provided a destination path will be derived from a source URL
            similar to :command:`git clone`"""),
        source=Parameter(
            args=("-s", "--source"),
            metavar='SOURCE',
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
        reckless=reckless_opt,
        git_opts=git_opts,
        git_clone_opts=git_clone_opts,
        annex_opts=annex_opts,
        annex_init_opts=annex_init_opts,
        jobs=jobs_opt,
    )

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
            reckless=False,
            git_opts=None,
            git_clone_opts=None,
            annex_opts=None,
            annex_init_opts=None,
            jobs=None):

        # normalize path argument to be equal when called from cmdline and
        # python and nothing was passed into `path`
        path = assure_list(path)

        if not source and not path:
            raise InsufficientArgumentsError(
                "Please provide at least a source or a path")


        ## Common kwargs to pass to underlying git/install calls.
        #  They might need adjustments (e.g. for recursion_limit, but
        #  otherwise would be applicable throughout
        #
        # There should have been more of common options!
        # since underneath get could do similar installs, but now they
        # have duplicated implementations which differ (e.g. get does not
        # annex init installed annexes)
        common_kwargs = dict(
            get_data=get_data,
            recursive=recursive,
            recursion_limit=recursion_limit,
            git_opts=git_opts,
            annex_opts=annex_opts,
            reckless=reckless,
            jobs=jobs,
        )

        installed_items = []
        failed_items = []

        # did we explicitly get a dataset to install into?
        # if we got a dataset, path will be resolved against it.
        # Otherwise path will be resolved first.
        ds = None
        if dataset is not None:
            ds = require_dataset(dataset, check_installed=True,
                                 purpose='installation')
            handle_dirty_dataset(ds, if_dirty)

        # switch into scenario without --source:
        if source is None:
            # we need to collect URLs and paths
            to_install = []
            to_get = []
            for urlpath in path:
                ri = RI(urlpath)
                (to_get if isinstance(ri, PathRI) else to_install).append(urlpath)

            common_kwargs['dataset'] = dataset

            # first install, and then get
            for s in to_install:
                lgr.debug("Install passes into install source=%s", s)
                try:
                    result = Install.__call__(
                                    source=s,
                                    description=description,
                                    if_dirty=if_dirty,
                                    save=save,
                                    git_clone_opts=git_clone_opts,
                                    annex_init_opts=annex_init_opts,
                                    **common_kwargs
                                )
                    installed_items += assure_list(result)
                except Exception as exc:
                    lgr.warning("Installation of %s has failed: %s",
                                s, exc_str(exc))
                    failed_items.append(s)

            if to_get:
                lgr.debug("Install passes into get %d items", len(to_get))
                # all commented out hint on inability to pass those options
                # into underlying install-related calls.
                # Also need to pass from get:
                #  annex_get_opts
                try:
                    installed_datasets = Get.__call__(
                        to_get,
                        # description=description,
                        # if_dirty=if_dirty,
                        # save=save,
                        # git_clone_opts=git_clone_opts,
                        # annex_init_opts=annex_init_opts
                        _return_datasets=True,
                        **common_kwargs
                    )
                except IncompleteResultsError as exc:
                    exc_str_ = ': ' + exc_str(exc) if exc.results else ''
                    lgr.warning("Some items failed to install: %s",
                                exc_str_)
                    installed_datasets = exc.results
                    failed_items.extend(exc.failed)

                # compose content_by_ds into result
                for dspath in installed_datasets:
                    ds_ = Dataset(dspath)
                    if ds_.is_installed():
                        installed_items.append(ds_)
                    else:
                        lgr.warning("%s was not installed", ds_)

            return Install._handle_and_return_installed_items(
                ds, installed_items, failed_items, save)

        if source and path and len(path) > 1:
            raise ValueError(
                "install needs a single PATH when source is provided.  "
                "Was given mutliple PATHs: %s" % str(path))

        # parameter constraints:
        if not source:
            raise InsufficientArgumentsError(
                "a `source` is required for installation")

        # code below deals with a single path only
        path = path[0] if path else None

        if source == path:
            # even if they turn out to be identical after resolving symlinks
            # and more sophisticated witchcraft, it would still happily say
            # "it appears to be already installed", so we just catch an
            # obviously pointless input combination
            raise ValueError(
                "installation `source` and destination `path` are identical. "
                "If you are trying to add a subdataset simply use `save` %s".format(
                    path))

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
                # yoh: path should be a local path, and mapping note within
                #      SSHRI about mapping localhost:path to path is kinda
                #      a peculiar use-case IMHO
                path = resolve_path(path_ri.localpath, dataset)
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
            candidate_sources = _get_flexible_source_candidates(
                source, destination_dataset.path)
            # this is where it was installed from
            track_name, track_url = _get_tracking_source(destination_dataset)
            if track_url in candidate_sources or get_local_file_url(track_url):
                # TODO: this one breaks "promise" assumptions of the repeated
                # invocations of install.
                # yoh thinks that we actually should be the ones to run update
                # (without merge) after basic
                # check that it is clean and up-to-date with its super dataset
                # and if so, not return here but continue with errands (recursive
                # installation and get_data) so we could provide the same
                # result if we rerun the same install twice.
                lgr.info(
                    "%s was already installed from %s. Use `update` to obtain "
                    "latest updates, or `get` or `install` with a path, not URL, "
                    "to (re)fetch data and / or subdatasets",
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
                source,
                reckless)
        else:
            # FLOW GUIDE: 2.
            lgr.info("Installing dataset at {0} from {1}".format(path, source))

            # Currently assuming there is nothing at the target to deal with
            # and rely on failures raising from the git call ...

            # We possibly need to consider /.git URL
            candidate_sources = _get_flexible_source_candidates(source)
            _clone_from_any_source(candidate_sources, destination_dataset.path)

        # FLOW GUIDE: All four cases done.
        if not destination_dataset.is_installed():
            # XXX  shouldn't we just fail!? (unless some explicit --skip-failing?)
            lgr.error("Installation failed.")
            return None

        _handle_possible_annex_dataset(destination_dataset, reckless)

        lgr.debug("Installation of %s done.", destination_dataset)

        if not destination_dataset.is_installed():
            # log error and don't report as installed item, but don't raise,
            # since we might be in a process of recursive installation where
            # a lot of other datasets can still be installed successfully.
            lgr.error("Installation of {0} failed.".format(destination_dataset))
        else:
            installed_items.append(destination_dataset)

        # we need to decrease the recursion limit, relative to
        # subdatasets now
        subds_recursion_limit = max(0, recursion_limit - 1) \
                                  if isinstance(recursion_limit, int) \
                                  else recursion_limit
        # Now, recursive calls:
        if recursive:
            if description:
                # yoh: why?  especially if we somehow allow for templating them
                # with e.g. '%s' to catch the subdataset path
                lgr.warning("Description can't be assigned recursively.")

            subs = destination_dataset.get_subdatasets(
                # yes, it does make sense to combine no recursion with
                # recursion_limit: when the latter is 0 we get no subdatasets
                # reported, otherwise we always get the 1st-level subs
                recursive=False,
                recursion_limit=recursion_limit,
                absolute=False)

            if subs:
                lgr.debug("Obtaining subdatasets of %s: %s",
                          destination_dataset,
                          subs)

                kwargs = common_kwargs.copy()
                kwargs['recursion_limit'] = subds_recursion_limit
                rec_installed = Get.__call__(
                    subs,  # all at once
                    dataset=destination_dataset,
                    # TODO expose this
                    # yoh: exactly!
                    #annex_get_opts=annex_get_opts,
                    **kwargs
                )
                # TODO do we want to filter this so `install` only returns
                # the datasets?
                if isinstance(rec_installed, list):
                    installed_items.extend(rec_installed)
                else:
                    installed_items.append(rec_installed)

        if get_data:
            lgr.debug("Getting data of {0}".format(destination_dataset))
            kwargs = common_kwargs.copy()
            kwargs['recursive'] = False
            destination_dataset.get(curdir, **kwargs)

        return Install._handle_and_return_installed_items(
            ds, installed_items, failed_items, save)

    @staticmethod
    def _handle_and_return_installed_items(ds, installed_items, failed_items, save):
        if save and ds is not None:
            _save_installed_datasets(ds, installed_items)
        if failed_items:
            msg = ''
            for act, l in (("succeeded", installed_items), ("failed", failed_items)):
                if not l:
                    continue
                if msg:
                    msg += ', and '
                msg += "%s %s" % (
                  single_or_plural("dataset", "datasets", len(l),
                                   include_count=True),
                  act)
                if ds:
                    paths = [relpath(i.path, ds.path)
                             if hasattr(i, 'path')
                             else i if not i.startswith(ds.path) else relpath(i, ds.path)
                             for i in l]
                else:
                    paths = l
                msg += " (%s)" % (", ".join(map(str, paths)))
            msg += ' to install'

            # we were asked for multiple installations
            if installed_items or len(failed_items) > 1:
                raise IncompleteResultsError(
                    results=installed_items, failed=failed_items, msg=msg)
            else:
                raise InstallFailedError(msg=msg)

        return installed_items[0] \
            if len(installed_items) == 1 else installed_items

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

# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Plumbing command for dataset installation"""


import logging
from os import listdir
from os.path import relpath
from os.path import pardir
from os.path import exists

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import location_description
# from datalad.interface.common_opts import git_opts
# from datalad.interface.common_opts import git_clone_opts
# from datalad.interface.common_opts import annex_opts
# from datalad.interface.common_opts import annex_init_opts
from datalad.interface.common_opts import reckless_opt
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureKeyChoice
from datalad.support.param import Parameter
from datalad.support.network import get_local_file_url
from datalad.dochelpers import exc_str
from datalad.utils import rmtree
from datalad.utils import assure_list

from .dataset import Dataset
from .dataset import datasetmethod
from .dataset import resolve_path
from .dataset import require_dataset
from .dataset import EnsureDataset
from .utils import _get_git_url_from_source
from .utils import _get_tracking_source
from .utils import _get_flexible_source_candidates
from .utils import _handle_possible_annex_dataset
from .utils import _get_installationpath_from_url

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.clone')


@build_doc
class Clone(Interface):
    """Obtain a dataset copy from a URL or local source (path)

    The purpose of this command is to obtain a new clone (copy) of a dataset
    and place it into a not-yet-existing or empty directory. As such `clone`
    provides a strict subset of the functionality offered by `install`. Only a
    single dataset can be obtained, recursion is not supported. However, once
    installed, arbitrary dataset components can be obtained via a subsequent
    `get` command.

    Primary differences over a direct `git clone` call are 1) the automatic
    initialization of a dataset annex (pure Git repositories are equally
    supported); 2) automatic registration of the newly obtained dataset
    as a subdataset (submodule), if a parent dataset is specified;
    3) support for datalad's resource identifiers and automatic generation of
    alternative access URL for common cases (such as appending '.git' to the
    URL in case the accessing the base URL failed); and 4) ability to
    take additional alternative source locations as an argument.
    """
    # by default ignore everything but install results
    # i.e. no "add to super dataset"
    result_filter = EnsureKeyChoice('action', ('install',))

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""(parent) dataset to clone into. If given, the newly cloned
            dataset is registered as a subdataset of the parent. Also, if given,
            relative paths are interpreted as being relative to the parent
            dataset, and not relative to the working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        source=Parameter(
            args=("source",),
            metavar='SOURCE',
            doc="""URL, Datalad resource identifier, local path or instance of
            dataset to be cloned""",
            constraints=EnsureStr() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            nargs="?",
            doc="""path to clone into.  If no `path` is provided a
            destination path will be derived from a source URL
            similar to :command:`git clone`"""),
        description=location_description,
        reckless=reckless_opt,
        alt_sources=Parameter(
            args=('--alternative-sources',),
            metavar='SOURCE',
            nargs='+',
            doc="""Alternative sources to be tried if a dataset cannot
            be obtained from the main `source`""",
            constraints=EnsureStr() | EnsureNone()),
        # TODO next ones should be there, but cannot go anywhere
        # git_opts=git_opts,
        # git_clone_opts=git_clone_opts,
        # annex_opts=annex_opts,
        # annex_init_opts=annex_init_opts,
    )

    @staticmethod
    @datasetmethod(name='clone')
    @eval_results
    def __call__(
            source,
            path=None,
            dataset=None,
            description=None,
            reckless=False,
            alt_sources=None):
            # TODO next ones should be there, but cannot go anywhere
            # git_opts=None,
            # git_clone_opts=None,
            # annex_opts=None,
            # annex_init_opts=None

        # did we explicitly get a dataset to install into?
        # if we got a dataset, path will be resolved against it.
        # Otherwise path will be resolved first.
        dataset = require_dataset(
            dataset, check_installed=True, purpose='cloning') \
            if dataset is not None else dataset
        refds_path = dataset.path if dataset else None

        if isinstance(source, Dataset):
            source = source.path

        if source == path:
            # even if they turn out to be identical after resolving symlinks
            # and more sophisticated witchcraft, it would still happily say
            # "it appears to be already installed", so we just catch an
            # obviously pointless input combination
            raise ValueError(
                "clone `source` and destination `path` are identical [{}]. "
                "If you are trying to add a subdataset simply use `add`".format(
                    path))

        if path is not None:
            path = resolve_path(path, dataset)

        # Possibly do conversion from source into a git-friendly url
        # luckily GitRepo will undo any fancy file:/// url to make use of Git's
        # optimization for local clones....
        source_url = source
        source_ = _get_git_url_from_source(source)
        lgr.debug("Resolved clone source from '%s' to '%s'",
                  source, source_)
        source = source_

        # derive target from source:
        if path is None:
            # we got nothing but a source. do something similar to git clone
            # and derive the path from the source and continue
            path = _get_installationpath_from_url(source)
            # since this is a relative `path`, resolve it:
            path = resolve_path(path, dataset)
            lgr.debug("Determined clone target path from source")
        lgr.debug("Resolved clone target path to: '%s'", path)

        # there is no other way -- my intoxicated brain tells me
        assert(path is not None)

        destination_dataset = Dataset(path)
        dest_path = path

        status_kwargs = dict(
            action='install', ds=destination_dataset, logger=lgr,
            refds=refds_path, source_url=source_url)

        # important test! based on this `rmtree` will happen below after failed clone
        if exists(dest_path) and listdir(dest_path):
            if destination_dataset.is_installed():
                # check if dest was cloned from the given source before
                # this is where we would have installed this from
                guessed_sources = _get_flexible_source_candidates(
                    source, dest_path)
                # this is where it was actually installed from
                track_name, track_url = _get_tracking_source(destination_dataset)
                if track_url in guessed_sources or \
                        get_local_file_url(track_url) in guessed_sources:
                    yield get_status_dict(
                        status='notneeded',
                        message=("dataset %s was already cloned from '%s'",
                                 destination_dataset,
                                 source),
                        **status_kwargs)
                    return
            # anything else is an error
            yield get_status_dict(
                status='error',
                message='target path already exists and not empty, refuse to clone into target path',
                **status_kwargs)
            return

        if dataset is not None and relpath(path, start=dataset.path).startswith(pardir):
            yield get_status_dict(
                status='error',
                message=("clone target path '%s' not in specified target dataset '%s'",
                         path, dataset),
                **status_kwargs)
            return

        # generate candidate URLs from source argument to overcome a few corner cases
        # and hopefully be more robust than git clone
        candidate_sources = []
        # combine all given sources (incl. alternatives), maintain order
        for s in [source] + assure_list(alt_sources):
            candidate_sources.extend(_get_flexible_source_candidates(s))
        lgr.info("Cloning dataset from '%s' (trying %i location candidate(s)) to '%s'",
                 source, len(candidate_sources), dest_path)
        for source_ in candidate_sources:
            try:
                lgr.debug("Attempting to clone dataset from '%s' to '%s'",
                          source_, dest_path)
                GitRepo.clone(path=dest_path, url=source_, create=True)
                break  # do not bother with other sources if succeeded
            except GitCommandError as e:
                lgr.debug("Failed to clone from URL: %s (%s)",
                          source_, exc_str(e))
                if exists(dest_path):
                    lgr.debug("Wiping out unsuccessful clone attempt at: %s",
                              dest_path)
                    rmtree(dest_path)

        if not destination_dataset.is_installed():
            yield get_status_dict(
                status='error',
                message=("Failed to clone data from any candidate source URL: %s",
                         candidate_sources),
                **status_kwargs)
            return

        if dataset is not None:
            # we created a dataset in another dataset
            # -> make submodule
            for r in dataset.add(
                    dest_path, save=True, ds2super=True,
                    return_type='generator',
                    result_filter=None,
                    result_xfm=None,
                    on_failure='ignore'):
                yield r

        _handle_possible_annex_dataset(
            destination_dataset,
            reckless,
            description=description)

        # yield successful clone of the base dataset now, as any possible
        # subdataset clone down below will not alter the Git-state of the
        # parent
        yield get_status_dict(status='ok', **status_kwargs)

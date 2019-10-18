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
import os
import re
from collections import OrderedDict
from urllib.parse import unquote as urlunquote

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import (
    location_description,
    reckless_opt,
)
from datalad.support.gitrepo import (
    GitRepo,
    GitCommandError,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
    EnsureKeyChoice,
)
from datalad.support.param import Parameter
from datalad.support.network import (
    get_local_file_url,
    URL,
    RI,
    DataLadRI,
)
from datalad.dochelpers import (
    exc_str,
    single_or_plural,
)
from datalad.utils import (
    rmtree,
    assure_list,
    assure_bool,
    knows_annex,
)

from datalad.distribution.dataset import (
    Dataset,
    datasetmethod,
    resolve_path,
    require_dataset,
    EnsureDataset,
)
from datalad.distribution.utils import (
    _get_git_url_from_source,
    _get_flexible_source_candidates,
)

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
            doc="""URL, DataLad resource identifier, local path or instance of
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
            dest='alt_sources',
            metavar='SOURCE',
            nargs='+',
            doc="""Alternative sources to be tried if a dataset cannot
            be obtained from the main `source`""",
            constraints=EnsureStr() | EnsureNone()),
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

        # did we explicitly get a dataset to install into?
        # if we got a dataset, path will be resolved against it.
        # Otherwise path will be resolved first.
        ds = require_dataset(
            dataset, check_installed=True, purpose='cloning') \
            if dataset is not None else dataset
        refds_path = ds.path if ds else None

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

        status_kwargs = dict(
            action='install',
            logger=lgr,
            refds=refds_path,
            source_url=source_url)

        try:
            # this will implicitly cause pathlib to run a bunch of checks
            # whether the present path makes any sense on the platform
            # we are running on -- we don't care if the path actually
            # exists at this point, but we want to abort early if the path
            # spec is determined to be useless
            path.exists()
        except OSError as e:
            yield get_status_dict(
                status='error',
                path=path,
                message=('cannot handle target path: %s', exc_str(e)),
                **status_kwargs)
            return

        destination_dataset = Dataset(path)
        status_kwargs['ds'] = destination_dataset
        dest_path = path

        # important test! based on this `rmtree` will happen below after failed clone
        if dest_path.exists() and any(dest_path.iterdir()):
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

        if ds is not None and ds.pathobj not in dest_path.parents:
            yield get_status_dict(
                status='error',
                message=("clone target path '%s' not in specified target dataset '%s'",
                         dest_path, ds),
                **status_kwargs)
            return

        # generate candidate URLs from source argument to overcome a few corner cases
        # and hopefully be more robust than git clone
        candidate_sources = []
        # combine all given sources (incl. alternatives), maintain order
        for s in [source] + assure_list(alt_sources):
            candidate_sources.extend(_get_flexible_source_candidates(s))
        candidates_str = \
            " [%d other candidates]" % (len(candidate_sources) - 1) \
            if len(candidate_sources) > 1 \
            else ''
        lgr.info("Cloning %s%s into '%s'",
                 source, candidates_str, dest_path)
        dest_path_existed = dest_path.exists()
        error_msgs = OrderedDict()  # accumulate all error messages formatted per each url
        for isource_, source_ in enumerate(candidate_sources):
            try:
                lgr.debug("Attempting to clone %s (%d out of %d candidates) to '%s'",
                          source_, isource_ + 1, len(candidate_sources), dest_path)
                # TODO for now GitRepo.clone() cannot handle Path instances, and PY35
                # doesn't make it happen seemlessly
                GitRepo.clone(path=str(dest_path), url=source_, create=True)
                break  # do not bother with other sources if succeeded
            except GitCommandError as e:
                error_msgs[source_] = e
                lgr.debug("Failed to clone from URL: %s (%s)",
                          source_, exc_str(e))
                if dest_path.exists():
                    lgr.debug("Wiping out unsuccessful clone attempt at: %s",
                              dest_path)
                    # We must not just rmtree since it might be curdir etc
                    # we should remove all files/directories under it
                    # TODO stringification can be removed once patlib compatible
                    # or if PY35 is no longer supported
                    rmtree(str(dest_path), children_only=dest_path_existed)
                # Whenever progress reporting is enabled, as it is now,
                # we end up without e.stderr since it is "processed" out by
                # GitPython/our progress handler.
                e_stderr = e.stderr
                from datalad.support.gitrepo import GitPythonProgressBar
                if not e_stderr and GitPythonProgressBar._last_error_lines:
                    e_stderr = os.linesep.join(GitPythonProgressBar._last_error_lines)
                if 'could not create work tree' in e_stderr.lower():
                    # this cannot be fixed by trying another URL
                    re_match = re.match(r".*fatal: (.*)$", e_stderr,
                                        flags=re.MULTILINE | re.DOTALL)
                    yield get_status_dict(
                        status='error',
                        message=re_match.group(1) if re_match else "stderr: " + e_stderr,
                        **status_kwargs)
                    return

        if not destination_dataset.is_installed():
            if len(error_msgs):
                if all(not e.stdout and not e.stderr for e in error_msgs.values()):
                    # there is nothing we can learn from the actual exception,
                    # the exit code is uninformative, the command is predictable
                    error_msg = "Failed to clone from all attempted sources: %s"
                    error_args = list(error_msgs.keys())
                else:
                    error_msg = "Failed to clone from any candidate source URL. " \
                                "Encountered errors per each url were:\n- %s"
                    error_args = '\n- '.join(
                        '{}\n  {}'.format(url, exc_str(exc))
                        for url, exc in error_msgs.items()
                    )
            else:
                # yoh: Not sure if we ever get here but I felt that there could
                #      be a case when this might happen and original error would
                #      not be sufficient to troubleshoot what is going on.
                error_msg = "Awkward error -- we failed to clone properly. " \
                            "Although no errors were encountered, target " \
                            "dataset at %s seems to be not fully installed. " \
                            "The 'succesful' source was: %s"
                error_args = (destination_dataset.path, source_)
            yield get_status_dict(
                status='error',
                message=(error_msg, error_args),
                **status_kwargs)
            return

        if ds is not None:
            # we created a dataset in another dataset
            # -> make submodule
            for r in ds.save(
                    dest_path,
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


def _handle_possible_annex_dataset(dataset, reckless, description=None):
    """If dataset "knows annex" -- annex init it, set into reckless etc

    Provides additional tune up to a possibly an annex repo, e.g.
    "enables" reckless mode, sets up description
    """
    # in any case check whether we need to annex-init the installed thing:
    if not knows_annex(dataset.path):
        # not for us
        return

    # init annex when traces of a remote annex can be detected
    if reckless:
        lgr.debug(
            "Instruct annex to hardlink content in %s from local "
            "sources, if possible (reckless)", dataset.path)
        dataset.config.add(
            'annex.hardlink', 'true', where='local', reload=True)
    lgr.debug("Initializing annex repo at %s", dataset.path)
    # XXX this is rather convoluted, init does init, but cannot
    # set a description without `create=True`
    repo = AnnexRepo(dataset.path, init=True)
    # so do manually see #1403
    if description:
        repo._init(description=description)
    if reckless:
        repo._run_annex_command('untrust', annex_options=['here'])

    srs = {True: [], False: []}  # special remotes by "autoenable" key
    remote_uuids = None  # might be necessary to discover known UUIDs

    for uuid, config in repo.get_special_remotes().items():
        sr_name = config.get('name', None)
        sr_autoenable = config.get('autoenable', False)
        try:
            sr_autoenable = assure_bool(sr_autoenable)
        except ValueError:
            # Be resilient against misconfiguration.  Here it is only about
            # informing the user, so no harm would be done
            lgr.warning(
                'Failed to process "autoenable" value %r for sibling %s in '
                'dataset %s as bool.  You might need to enable it later '
                'manually and/or fix it up to avoid this message in the future.',
                sr_autoenable, sr_name, dataset.path)
            continue

        # determine either there is a registered remote with matching UUID
        if uuid:
            if remote_uuids is None:
                remote_uuids = {
                    repo.config.get('remote.%s.annex-uuid' % r)
                    for r in repo.get_remotes()
                }
            if uuid not in remote_uuids:
                srs[sr_autoenable].append(sr_name)

    if srs[True]:
        lgr.debug(
            "configuration for %s %s added because of autoenable,"
            " but no UUIDs for them yet known for dataset %s",
            # since we are only at debug level, we could call things their
            # proper names
            single_or_plural("special remote", "special remotes", len(srs[True]), True),
            ", ".join(srs[True]),
            dataset.path
        )

    if srs[False]:
        # if has no auto-enable special remotes
        lgr.info(
            'access to %s %s not auto-enabled, enable with:\n\t\tdatalad siblings -d "%s" enable -s %s',
            # but since humans might read it, we better confuse them with our
            # own terms!
            single_or_plural("dataset sibling", "dataset siblings", len(srs[False]), True),
            ", ".join(srs[False]),
            dataset.path,
            srs[False][0] if len(srs[False]) == 1 else "SIBLING",
        )


def _get_tracking_source(ds):
    """Returns name and url of a potential configured source
    tracking remote"""
    vcs = ds.repo
    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule

    remote_name, tracking_branch = vcs.get_tracking_branch()
    # TODO: better default `None`? Check where we might rely on '':
    remote_url = ''
    if remote_name:
        remote_url = vcs.get_remote_url(remote_name, push=False)

    return remote_name, remote_url


def _get_installationpath_from_url(url):
    """Returns a relative path derived from the trailing end of a URL

    This can be used to determine an installation path of a Dataset
    from a URL, analog to what `git clone` does.
    """
    ri = RI(url)
    if isinstance(ri, (URL, DataLadRI)):  # decode only if URL
        path = ri.path.rstrip('/')
        path = urlunquote(path) if path else ri.hostname
    else:
        path = url
    path = path.rstrip('/')
    if '/' in path:
        path = path.split('/')
        if path[-1] == '.git':
            path = path[-2]
        else:
            path = path[-1]
    if path.endswith('.git'):
        path = path[:-4]
    return path

# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface result handling functions

"""

from __future__ import annotations

__docformat__ = 'restructuredtext'

import logging
from collections.abc import (
    Iterable,
    Iterator,
)
from os.path import (
    isabs,
    isdir,
)
from os.path import join as opj
from os.path import (
    normpath,
    relpath,
)
from typing import (
    Any,
    Optional,
)

from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import (
    CapturedException,
    CommandError,
    format_oneline_tb,
)
from datalad.support.path import robust_abspath
from datalad.utils import (
    PurePosixPath,
    ensure_list,
    path_is_subpath,
)

lgr = logging.getLogger('datalad.interface.results')
lgr.log(5, "Importing datalad.interface.results")

# which status is a success , which is failure
success_status_map = {
    'ok': 'success',
    'notneeded': 'success',
    'impossible': 'failure',
    'error': 'failure',
}


def get_status_dict(
    action: Optional[str] = None,
    ds: Optional[Dataset] = None,
    path: Optional[str] = None,
    type: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    refds: Optional[str] = None,
    status: Optional[str] = None,
    message: str | tuple | None = None,
    exception: Exception | CapturedException | None = None,
    error_message: str | tuple | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    # `type` is intentionally not `type_` or something else, as a mismatch
    # with the dict key 'type' causes too much pain all over the place
    # just for not shadowing the builtin `type` in this function
    """Helper to create a result dictionary.

    Most arguments match their key in the resulting dict, and their given
    values are simply assigned to the result record under these keys.  Only
    exceptions are listed here.

    Parameters
    ----------
    ds
      If given, the `path` and `type` values are populated with the path of the
      datasets and 'dataset' as the type. Giving additional values for both
      keys will overwrite these pre-populated values.
    exception
      Exceptions that occurred while generating a result should be captured
      by immediately instantiating a CapturedException. This instance can
      be passed here to yield more comprehensive error reporting, including
      an auto-generated traceback (added to the result record under an
      'exception_traceback' key). Exceptions of other types are also supported.

    Returns
    -------
    dict
    """

    d: dict[str, Any] = {}
    if action is not None:
        d['action'] = action
    if ds:
        d['path'] = ds.path
        d['type'] = 'dataset'
    # now overwrite automatic
    if path is not None:
        d['path'] = path
    if type:
        d['type'] = type
    if logger:
        d['logger'] = logger
    if refds:
        d['refds'] = refds
    if status is not None:
        # TODO check for known status label
        d['status'] = status
    if message is not None:
        d['message'] = message
    if error_message is not None:
        d['error_message'] = error_message
    if exception is not None:
        d['exception'] = exception
        d['exception_traceback'] = exception.format_oneline_tb(
            include_str=False) \
            if isinstance(exception, CapturedException) \
            else format_oneline_tb(
                exception, include_str=False)
        if error_message is None and isinstance(exception, CapturedException):
            d['error_message'] = exception.message
        if isinstance(exception, CommandError):
            d['exit_code'] = exception.code
    if kwargs:
        d.update(kwargs)
    return d


def results_from_paths(
    paths: str | list[str],
    action: Optional[str] = None,
    type: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    refds: Optional[str]=None,
    status: Optional[str] = None,
    message: Optional[str] = None,
    exception: Exception | CapturedException | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Helper to yield analog result dicts for each path in a sequence.

    Parameters
    ----------
    message: str
      A result message. May contain `%s` which will be replaced by the
      respective `path`.

    Returns
    -------
    generator

    """
    for p in ensure_list(paths):
        yield get_status_dict(
            action, path=p, type=type, logger=logger, refds=refds,
            status=status, message=(message, p) if message is not None and '%s' in message else message,
            exception=exception
        )


def is_ok_dataset(r: dict) -> bool:
    """Convenience test for a non-failure dataset-related result dict"""
    return r.get('status', None) == 'ok' and r.get('type', None) == 'dataset'


class ResultXFM:
    """Abstract definition of the result transformer API"""

    def __call__(self, res: dict[str, Any]) -> Any:
        """This is called with one result dict at a time"""
        raise NotImplementedError


class YieldDatasets(ResultXFM):
    """Result transformer to return a Dataset instance from matching result.

    If the `success_only` flag is given only dataset with 'ok' or 'notneeded'
    status are returned'.

    `None` is returned for any other result.
    """
    def __init__(self, success_only: bool = False) -> None:
        self.success_only = success_only

    def __call__(self, res: dict[str, Any]) -> Optional[Dataset]:
        if res.get('type', None) == 'dataset':
            if not self.success_only or \
                    res.get('status', None) in ('ok', 'notneeded'):
                return Dataset(res['path'])
            else:
                return None
        else:
            lgr.debug('rejected by return value configuration: %s', res)
            return None


class YieldRelativePaths(ResultXFM):
    """Result transformer to return relative paths for a result

    Relative paths are determined from the 'refds' value in the result. If
    no such value is found, `None` is returned.
    """
    def __call__(self, res: dict[str, Any]) -> Optional[str]:
        refpath = res.get('refds', None)
        if refpath:
            return relpath(res['path'], start=refpath)
        else:
            return None


class YieldField(ResultXFM):
    """Result transformer to return an arbitrary value from a result dict"""
    def __init__(self, field: str) -> None:
        """
        Parameters
        ----------
        field : str
          Key of the field to return.
        """
        self.field = field

    def __call__(self, res: dict[str, Any]) -> Any:
        if self.field in res:
            return res[self.field]
        else:
            lgr.debug('rejected by return value configuration: %s', res)
            return None


# a bunch of convenience labels for common result transformers
# the API `result_xfm` argument understand any of these labels and
# applied the corresponding callable
known_result_xfms = {
    'datasets': YieldDatasets(),
    'successdatasets-or-none': YieldDatasets(success_only=True),
    'paths': YieldField('path'),
    'relpaths': YieldRelativePaths(),
    'metadata': YieldField('metadata'),
}

translate_annex_notes = {
    '(Use --force to override this check, or adjust numcopies.)':
        'configured minimum number of copies not found',
}


def annexjson2result(d: dict[str, Any], ds: Dataset, **kwargs: Any) -> dict[str, Any]:
    """Helper to convert an annex JSON result to a datalad result dict

    Info from annex is rather heterogeneous, partly because some of it
    our support functions are faking.

    This helper should be extended with all needed special cases to
    homogenize the information.

    Parameters
    ----------
    d : dict
      Annex info dict.
    ds : Dataset instance
      Used to determine absolute paths for `file` results. This dataset
      is not used to set `refds` in the result, pass this as a separate
      kwarg if needed.
    **kwargs
      Passes as-is to `get_status_dict`. Must not contain `refds`.
    """
    lgr.debug('received JSON result from annex: %s', d)
    messages = []
    res = get_status_dict(**kwargs)
    res['status'] = 'ok' if d.get('success', False) is True else 'error'
    # we cannot rely on any of these to be available as the feed from
    # git annex (or its wrapper) is not always homogeneous
    if d.get('file'):
        res['path'] = str(ds.pathobj / PurePosixPath(d['file']))
    if 'command' in d:
        res['action'] = d['command']
    if 'key' in d:
        res['annexkey'] = d['key']
    if 'fields' in d:
        # this is annex metadata, filter out timestamps
        res['metadata'] = {k: v[0] if isinstance(v, list) and len(v) == 1 else v
                           for k, v in d['fields'].items()
                           if not k.endswith('lastchanged')}
    if d.get('error-messages', None):
        res['error_message'] = '\n'.join(m.strip() for m in d['error-messages'])
    # avoid meaningless standard messages, and collision with actual error
    # messages
    elif 'note' in d:
        note = "; ".join(ln for ln in d['note'].splitlines()
                         if ln != 'checksum...'
                         and not ln.startswith('checking file'))
        if note:
            messages.append(translate_annex_notes.get(note, note))
    if messages:
        res['message'] = '\n'.join(m.strip() for m in messages)
    return res


def count_results(res: Iterable[dict[str, Any]], **kwargs: Any) -> int:
    """Return number of results that match all property values in kwargs"""
    return sum(
        all(k in r and r[k] == v for k, v in kwargs.items()) for r in res)


def only_matching_paths(res: dict[str, Any], **kwargs: Any) -> bool:
    # TODO handle relative paths by using a contained 'refds' value
    paths = ensure_list(kwargs.get('path', []))
    respath = res.get('path', None)
    return respath in paths


# needs decorator, as it will otherwise bind to the command classes that use it
@staticmethod  # type: ignore[misc]
def is_result_matching_pathsource_argument(res: dict[str, Any], **kwargs: Any) -> bool:
    # we either have any non-zero number of "paths" (that could be anything), or
    # we have one path and one source
    # we don't do any error checking here, done by the command itself
    if res.get('action', None) not in ('install', 'get'):
        # this filter is only used in install, reject anything that comes
        # in that could not possibly be a 'install'-like result
        # e.g. a sibling being added in the process
        return False
    source = kwargs.get('source', None)
    if source is not None:
        # we want to be able to deal with Dataset instances given as 'source':
        if isinstance(source, Dataset):
            source = source.path
        # if there was a source, it needs to be recorded in the result
        # otherwise this is not what we are looking for
        return source == res.get('source_url', None)
    # the only thing left is a potentially heterogeneous list of paths/URLs
    paths = ensure_list(kwargs.get('path', []))
    # three cases left:
    # 1. input arg was an absolute path -> must match 'path' property
    # 2. input arg was relative to a dataset -> must match refds/relpath
    # 3. something nifti with a relative input path that uses PWD as the
    #    reference
    respath = res.get('path', None)
    if respath in paths:
        # absolute match, pretty sure we want this
        return True
    elif isinstance(kwargs.get('dataset', None), Dataset) and \
            YieldRelativePaths()(res) in paths:
        # command was called with a reference dataset, and a relative
        # path of a result matches in input argument -- not 100% exhaustive
        # test, but could be good enough
        return True
    elif any(robust_abspath(p) == respath for p in paths):
        # one absolutified input path matches the result path
        # I'd say: got for it!
        return True
    elif any(p == res.get('source_url', None) for p in paths):
        # this was installed from a URL that was given, we'll take that too
        return True
    else:
        return False


def results_from_annex_noinfo(
    ds: Dataset,
    requested_paths: list[str],
    respath_by_status: dict[str, list[str]],
    dir_fail_msg: str,
    noinfo_dir_msg: str,
    noinfo_file_msg: str,
    noinfo_status: str = 'notneeded',
    **kwargs: Any
) -> Iterator[dict[str, Any]]:
    """Helper to yield results based on what information git annex did no give us.

    The helper assumes that the annex command returned without an error code,
    and interprets which of the requested paths we have heard nothing about,
    and assumes that git annex was happy with their current state.

    Parameters
    ==========
    ds : Dataset
      All results have to be concerning this single dataset (used to resolve
      relpaths).
    requested_paths : list
      List of path arguments sent to `git annex`
    respath_by_status : dict
      Mapping of 'success' or 'failure' labels to lists of result paths
      reported by `git annex`. Everything that is not in here, we assume
      that `git annex` was happy about.
    dir_fail_msg : str
      Message template to inject into the result for a requested directory where
      a failure was reported for some of its content. The template contains two
      string placeholders that will be expanded with 1) the path of the
      directory, and 2) the content failure paths for that directory
    noinfo_dir_msg : str
      Message template to inject into the result for a requested directory that
      `git annex` was silent about (incl. any content). There must be one string
      placeholder that is expanded with the path of that directory.
    noinfo_file_msg : str
      Message to inject into the result for a requested file that `git
      annex` was silent about.
    noinfo_status : str
      Status to report when annex provides no information
    **kwargs
      Any further kwargs are included in the yielded result dictionary.
    """
    for p in requested_paths:
        # any relpath is relative to the currently processed dataset
        # not the global reference dataset
        p = p if isabs(p) else normpath(opj(ds.path, p))
        if any(p in ps for ps in respath_by_status.values()):
            # we have a report for this path already
            continue
        common_report = dict(path=p, **kwargs)
        if isdir(p):
            # `annex` itself will not report on directories, but if a
            # directory was requested, we want to say something about
            # it in the results.  we are inside a single, existing
            # repo, hence all directories are already present, if not
            # we had an error
            # do we have any failures in a subdir of the requested dir?
            failure_results = [
                fp for fp in respath_by_status.get('failure', [])
                if path_is_subpath(fp, p)]
            if failure_results:
                # we were not able to process all requested_paths, let's label
                # this 'impossible' to get a warning-type report
                # after all we have the directory itself, but not
                # (some) of its requested_paths
                yield get_status_dict(
                    status='impossible', type='directory',
                    message=(dir_fail_msg, p, failure_results),
                    **common_report)
            else:
                # otherwise cool, but how cool?
                success_results = [
                    fp for fp in respath_by_status.get('success', [])
                    if path_is_subpath(fp, p)]
                yield get_status_dict(
                    status='ok' if success_results else noinfo_status,
                    message=None if success_results else (noinfo_dir_msg, p),
                    type='directory', **common_report)
            continue
        else:
            # not a directory, and we have had no word from `git annex`,
            # yet no exception, hence the file was most probably
            # already in the desired state
            yield get_status_dict(
                status=noinfo_status, type='file',
                message=noinfo_file_msg,
                **common_report)


lgr.log(5, "Done importing datalad.interface.results")

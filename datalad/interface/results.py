# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface result handling functions

"""

__docformat__ = 'restructuredtext'

import logging

from os.path import isdir
from os.path import isabs
from os.path import join as opj
from os.path import relpath
from os.path import abspath
from os.path import normpath
from datalad.utils import assure_list
from datalad.utils import with_pathsep as _with_sep
from datalad.distribution.dataset import Dataset


lgr = logging.getLogger('datalad.interface.results')


# which status is a success , which is failure
success_status_map = {
    'ok': 'success',
    'notneeded': 'success',
    'impossible': 'failure',
    'error': 'failure',
}


def get_status_dict(action=None, ds=None, path=None, type=None, logger=None,
                    refds=None, status=None, message=None, **kwargs):
    # `type` is intentionally not `type_` or something else, as a mismatch
    # with the dict key 'type' causes too much pain all over the place
    # just for not shadowing the builtin `type` in this function
    """Helper to create a result dictionary.

    Most arguments match their key in the resulting dict. Only exceptions are
    listed here.

    Parameters
    ----------
    ds : Dataset instance
      If given, the `path` and `type` values are populated with the path of the
      datasets and 'dataset' as the type. Giving additional values for both
      keys will overwrite these pre-populated values.

    Returns
    -------
    dict
    """

    d = {}
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
    if kwargs:
        d.update(kwargs)
    return d


def results_from_paths(paths, action=None, type=None, logger=None, refds=None,
                       status=None, message=None):
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
    for p in assure_list(paths):
        yield get_status_dict(
            action, path=p, type=type, logger=logger, refds=refds,
            status=status, message=(message, p) if '%s' in message else message)


def is_ok_dataset(r):
    """Convenience test for a non-failure dataset-related result dict"""
    return r.get('status', None) == 'ok' and r.get('type', None) == 'dataset'


class ResultXFM(object):
    """Abstract definition of the result transformer API"""
    def __call__(self, res):
        """This is called with one result dict at a time"""
        raise NotImplementedError


class YieldDatasets(ResultXFM):
    """Result transformer to return a Dataset instance from matching result.

    If the `success_only` flag is given only dataset with 'ok' or 'notneeded'
    status are returned'.

    `None` is returned for any other result.
    """
    def __init__(self, success_only=False):
        self.success_only = success_only

    def __call__(self, res):
        if res.get('type', None) == 'dataset':
            if not self.success_only or \
                    res.get('status', None) in ('ok', 'notneeded'):
                return Dataset(res['path'])
        else:
            lgr.debug('rejected by return value configuration: %s', res)


class YieldRelativePaths(ResultXFM):
    """Result transformer to return relative paths for a result

    Relative paths are determined from the 'refds' value in the result. If
    no such value is found, `None` is returned.
    """
    def __call__(self, res):
        refpath = res.get('refds', None)
        if refpath:
            return relpath(res['path'], start=refpath)


class YieldField(ResultXFM):
    """Result transformer to return an arbitrary value from a result dict"""
    def __init__(self, field):
        """
        Parameters
        ----------
        field : str
          Key of the field to return.
        """
        self.field = field

    def __call__(self, res):
        if self.field in res:
            return res[self.field]
        else:
            lgr.debug('rejected by return value configuration: %s', res)


# a bunch of convenience labels for common result transformers
# the API `result_xfm` argument understand any of these labels and
# applied the corresponding callable
known_result_xfms = {
    'datasets': YieldDatasets(),
    'successdatasets-or-none': YieldDatasets(success_only=True),
    'paths': YieldField('path'),
    'relpaths': YieldRelativePaths(),
}

translate_annex_notes = {
    '(Use --force to override this check, or adjust numcopies.)':
        'configured minimum number of copies not found',
}


def annexjson2result(d, ds, **kwargs):
    """Helper to convert an annex JSON result to a datalad result dict

    Info from annex is rather heterogenous, partly because some of it
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
    res = get_status_dict(**kwargs)
    res['status'] = 'ok' if d.get('success', False) is True else 'error'
    # we cannot rely on any of these to be available as the feed from
    # git annex (or its wrapper) is not always homogeneous
    if 'file' in d:
        res['path'] = opj(ds.path, d['file'])
    if 'command' in d:
        res['action'] = d['command']
    if 'key' in d:
        res['annexkey'] = d['key']
    # avoid meaningless standard messages
    if 'note' in d and (
            d['note'] != 'checksum...' and
            not d['note'].startswith('checking file')):
        res['message'] = translate_annex_notes.get(d['note'], d['note'])
    return res


def count_results(res, **kwargs):
    """Return number if results that match all property values in kwargs"""
    return sum(
        all(k in r and r[k] == v for k, v in kwargs.items()) for r in res)


def only_matching_paths(res, **kwargs):
    # TODO handle relative paths by using a contained 'refds' value
    paths = assure_list(kwargs.get('path', []))
    respath = res.get('path', None)
    return respath in paths


# needs decorator, as it will otherwise bind to the command classes that use it
@staticmethod
def is_result_matching_pathsource_argument(res, **kwargs):
    # we either have any non-zero number of "paths" (that could be anything), or
    # we have one path and one source
    # we don't do any error checking here, done by the command itself
    source = kwargs.get('source', None)
    if source is not None:
        # if there was a source, it needs to be recorded in the result
        # otherwise this is not what we are looking for
        return source == res.get('source_url', None)
    # the only thing left is a potentially heterogeneous list of paths/URLs
    paths = assure_list(kwargs.get('path', []))
    # three cases left:
    # 1. input arg was an absolute path -> must match 'path' property
    # 2. input arg was relative to a dataset -> must match refds/relpath
    # 3. something nifti with a relative input path that uses PWD as the
    #    reference
    respath = res.get('path', None)
    if respath in paths:
        # absolute match, pretty sure we want this
        return True
    elif kwargs.get('dataset', None) and YieldRelativePaths()(res) in paths:
        # command was called with a reference dataset, and a relative
        # path of a result matches in input argument -- not 100% exhaustive
        # test, but could be good enough
        return True
    elif any(abspath(p) == respath for p in paths):
        # one absolutified input path matches the result path
        # I'd say: got for it!
        return True
    elif any(p == res.get('source_url', None) for p in paths):
        # this was installed from a URL that was given, we'll take that too
        return True
    else:
        False


def results_from_annex_noinfo(ds, requested_paths, respath_by_status, dir_fail_msg,
                              noinfo_dir_msg, noinfo_file_msg, **kwargs):
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
                if fp.startswith(_with_sep(p))]
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
                    if fp.startswith(_with_sep(p))]
                yield get_status_dict(
                    status='ok' if success_results else 'notneeded',
                    message=None if success_results else (noinfo_dir_msg, p),
                    type='directory', **common_report)
            continue
        else:
            # not a directory, and we have had no word from `git annex`,
            # yet no exception, hence the file was most probably
            # already in the desired state
            yield get_status_dict(
                status='notneeded', type='file',
                message=noinfo_file_msg,
                **common_report)

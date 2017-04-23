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

from os.path import join as opj
from os.path import relpath
from datalad.utils import assure_list
from datalad.distribution.dataset import Dataset


lgr = logging.getLogger('datalad.interface.results')


def get_status_dict(action=None, ds=None, path=None, type_=None, logger=None,
                    refds=None, status=None, message=None, **kwargs):
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
    if action:
        d['action'] = action
    if ds:
        d['path'] = ds.path
        d['type'] = 'dataset'
    # now overwrite automatic
    if path:
        d['path'] = path
    if type_:
        d['type'] = type_
    if logger:
        d['logger'] = logger
    if refds:
        d['refds'] = refds
    if status:
        # TODO check for known status label
        d['status'] = status
    if message:
        d['message'] = message
    if kwargs:
        d.update(kwargs)
    return d


def results_from_paths(paths, action=None, type_=None, logger=None, refds=None,
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
            action, path=p, type_=type_, logger=logger, refds=refds,
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

    `None` is return for any other result.
    """
    def __call__(self, res):
        if res.get('type', None) == 'dataset':
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
    'paths': YieldField('path'),
    'relpaths': YieldRelativePaths(),
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

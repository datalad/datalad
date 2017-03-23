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
                    refds=None, status=None, message=None):
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
    return d


def results_from_paths(paths, action=None, type_=None, logger=None, refds=None,
                       status=None, message=None):
    """
    Parameters
    ----------
    message: str
      A result message. May contain `%s` which will be replaced by the
      respective `path`.
    """
    for p in assure_list(paths):
        yield get_status_dict(
            action, path=p, type_=type_, logger=logger, refds=refds,
            status=status, message=(message, p) if '%s' in message else message)


def is_ok_dataset(r):
    return r.get('status', None) == 'ok' and r.get('type', None) == 'dataset'


class ResultXFM(object):
    def __call__(self, res):
        raise NotImplementedError


class YieldDatasets(ResultXFM):
    def __call__(self, res):
        if res.get('type', None) == 'dataset':
            return Dataset(res['path'])
        else:
            lgr.debug('rejected by return value configuration: %s', res)


class YieldRelativePaths(ResultXFM):
    def __call__(self, res):
        refpath = res.get('refds', None)
        if refpath:
            return relpath(res['path'], start=refpath)


class YieldField(ResultXFM):
    def __init__(self, field):
        self.field = field

    def __call__(self, res):
        if self.field in res:
            return res[self.field]
        else:
            lgr.debug('rejected by return value configuration: %s', res)


known_result_xfms = {
    'datasets': YieldDatasets(),
    'paths': YieldField('path'),
    'relpaths': YieldRelativePaths(),
}


def annexjson2result(d, ds, **kwargs):
    res = get_status_dict(**kwargs)
    res['status'] = 'ok' if d.get('success', False) is True else 'error'
    res['path'] = opj(ds.path, d['file'])
    res['action'] = d['command']
    res['annexkey'] = d['key']
    return res


def count_results(res, **kwargs):
    """Return number if results that match all property values in kwargs"""
    return sum(
        all(k in r and r[k] == v for k, v in kwargs.items()) for r in res)

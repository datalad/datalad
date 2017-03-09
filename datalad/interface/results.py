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

from datalad.utils import assure_list
from datalad.distribution.dataset import Dataset


lgr = logging.getLogger('datalad.interface.results')


def get_status_dict(action, ds=None, path=None, type_=None, logger=None,
                    refds=None, status=None, message=None):
    d = {'action': action}
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


class YieldField(ResultXFM):
    def __init__(self, field):
        self.field = field

    def __call__(self, res):
        if self.field in res:
            return res[field]
        else:
            lgr.debug('rejected by return value configuration: %s', res)


known_result_xfms = {
    'datasets': YieldDatasets(),
    'paths': YieldField('path'),
}

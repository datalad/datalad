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

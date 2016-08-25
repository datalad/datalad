# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Simple wrappers to get uniform JSON input and output
"""


from io import open
import codecs

# wrapped below
from simplejson import load as jsonload
from simplejson import dump as jsondump
# simply mirrored for now
from simplejson import loads
from simplejson import dumps


# TODO think about minimizing the JSON output by default
json_dump_kwargs = dict(indent=2, sort_keys=True, ensure_ascii=False, encoding='utf-8')


def dump(obj, fname):
    return jsondump(
        obj,
        codecs.getwriter('utf-8')(open(fname, 'wb')),
        **json_dump_kwargs)


def load(fname):
    return jsonload(open(fname, 'r', encoding='utf-8'))

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
from simplejson import JSONDecodeError


# TODO think about minimizing the JSON output by default
json_dump_kwargs = dict(indent=2, sort_keys=True, ensure_ascii=False, encoding='utf-8')

# Let's just reuse top level one for now
from ..log import lgr
from ..dochelpers import exc_str


def dump(obj, fname):
    with open(fname, 'wb') as f:
        return jsondump(
            obj,
            codecs.getwriter('utf-8')(f),
            **json_dump_kwargs)


def load(fname, fixup=True, **kw):
    """Load JSON from a file, possibly fixing it up if initial load attempt fails

    Parameters
    ----------
    fixup : bool
      In case of failed load, apply a set of fixups with hope to resolve issues
      in JSON
    **kw
      Passed into the load (and loads after fixups) function
    """
    with open(fname, 'r', encoding='utf-8') as f:
        try:
            return jsonload(f, **kw)
        except JSONDecodeError as exc:
            if not fixup:
                raise
            lgr.warning("Failed to decode content in %s: %s. Trying few tricks", fname, exc_str(exc))

    # Load entire content and replace common "abusers" which break JSON comprehension but in general
    # are Ok
    with open(fname, 'r', encoding='utf-8') as f:
        s_orig = s = f.read()

    for o, r in {
        u"\xa0": " ",  # non-breaking space
    }.items():
        s = s.replace(o, r)

    if s == s_orig:
        # we have done nothing, so just reraise previous exception
        raise
    return loads(s, **kw)

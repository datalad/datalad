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


import io
import lzma
import codecs
from os.path import dirname
from os.path import exists
from os import makedirs

# wrapped below
from simplejson import load as jsonload
from simplejson import dump as jsondump
# simply mirrored for now
from simplejson import loads as json_loads
from simplejson import JSONDecodeError


# produce relatively compact, but also diff-friendly format
json_dump_kwargs = dict(
    indent=0,
    separators=(',', ':\n'),
    sort_keys=True,
    ensure_ascii=False,
    encoding='utf-8', )

# achieve minimal representation, but still deterministic
compressed_json_dump_kwargs = dict(
    json_dump_kwargs,
    indent=None,
    separators=(',', ':'))


# Let's just reuse top level one for now
from ..log import lgr
from ..dochelpers import exc_str


def dump(obj, fname):
    indir = dirname(fname)
    if not exists(indir):
        makedirs(indir)
    with io.open(fname, 'wb') as f:
        return dump2fileobj(obj, f)


def dump2fileobj(obj, fileobj):
    return jsondump(
        obj,
        codecs.getwriter('utf-8')(fileobj),
        **json_dump_kwargs)


def LZMAFile(*args, **kwargs):
    """A little decorator to overcome a bug in lzma

    A unique to yoh and some others bug with pyliblzma
    calling dir() helps to avoid AttributeError __exit__
    see https://bugs.launchpad.net/pyliblzma/+bug/1219296
    """
    lzmafile = lzma.LZMAFile(*args, **kwargs)
    dir(lzmafile)
    return lzmafile


def dump2stream(obj, fname, compressed=False):

    _open = LZMAFile if compressed else open

    with _open(fname, mode='wb') as f:
        jwriter = codecs.getwriter('utf-8')(f)
        for o in obj:
            jsondump(o, jwriter, **compressed_json_dump_kwargs)
            f.write(b'\n')


def dump2xzstream(obj, fname):
    dump2stream(obj, fname, compressed=True)


def load_stream(fname, compressed=False):

    _open = LZMAFile if compressed else open
    with _open(fname, mode='r') as f:
        for line in f:
            yield loads(line)


def load_xzstream(fname):
    for o in load_stream(fname, compressed=True):
        yield o


def loads(s, *args, **kwargs):
    """Helper to log actual value which failed to be parsed"""
    try:
        return json_loads(s, *args, **kwargs)
    except:
        lgr.error(
            "Failed to load content from %r with args=%r kwargs=%r"
            % (s, args, kwargs)
        )
        raise


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
    with io.open(fname, 'r', encoding='utf-8') as f:
        try:
            return jsonload(f, **kw)
        except JSONDecodeError as exc:
            if not fixup:
                raise
            lgr.warning("Failed to decode content in %s: %s. Trying few tricks", fname, exc_str(exc))

    # Load entire content and replace common "abusers" which break JSON comprehension but in general
    # are Ok
    with io.open(fname, 'r', encoding='utf-8') as f:
        s_orig = s = f.read()

    for o, r in {
        u"\xa0": " ",  # non-breaking space
    }.items():
        s = s.replace(o, r)

    if s == s_orig:
        # we have done nothing, so just reraise previous exception
        raise
    return loads(s, **kw)

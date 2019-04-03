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
import codecs
from six import PY2
from os.path import (
    dirname,
    exists,
    lexists,
)
from os import makedirs
import os
import os.path as op

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


def dump(obj, fname, compressed=False):
    """Dump a JSON-serializable objects into a file

    Parameters
    ----------
    obj : object
      Structure to serialize.
    fname : str
      Name of the file to dump into.
    compressed : bool
      Flag whether to use LZMA compression for file content.
    """

    _open = LZMAFile if compressed else io.open

    indir = dirname(fname)
    if not exists(indir):
        makedirs(indir)
    if lexists(fname):
        os.unlink(fname)
    with _open(fname, 'wb') as f:
        return dump2fileobj(
            obj,
            f,
            **(compressed_json_dump_kwargs if compressed else json_dump_kwargs)
        )


def dump2fileobj(obj, fileobj, **kwargs):
    """Dump a JSON-serializable objects into a file-like

    Parameters
    ----------
    obj : object
      Structure to serialize.
    fileobj : file
      Writeable file-like object to dump into.
    **kwargs
      Keyword arguments to be passed on to simplejson.dump()
    """
    return jsondump(
        obj,
        codecs.getwriter('utf-8')(fileobj),
        **kwargs)


def LZMAFile(*args, **kwargs):
    """A little decorator to overcome a bug in lzma

    A unique to yoh and some others bug with pyliblzma
    calling dir() helps to avoid AttributeError __exit__
    see https://bugs.launchpad.net/pyliblzma/+bug/1219296
    """
    from .lzma import lzma
    lzmafile = lzma.LZMAFile(*args, **kwargs)
    dir(lzmafile)
    return lzmafile


def dump2stream(obj, fname, compressed=False):

    _open = LZMAFile if compressed else open

    indir = dirname(fname)

    if op.lexists(fname):
        os.remove(fname)
    elif indir and not exists(indir):
        makedirs(indir)
    with _open(fname, mode='wb') as f:
        jwriter = codecs.getwriter('utf-8')(f)
        for o in obj:
            jsondump(o, jwriter, **compressed_json_dump_kwargs)
            f.write(b'\n')


def dump2xzstream(obj, fname):
    dump2stream(obj, fname, compressed=True)


def load_stream(fname, compressed=None):
    _open = LZMAFile \
        if compressed or compressed is None and fname.endswith('.xz') \
        else io.open

    with _open(fname, mode='rb') as f:
        jreader = codecs.getreader('utf-8')(f)
        for line in jreader:
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


def load(fname, fixup=True, compressed=None, **kw):
    """Load JSON from a file, possibly fixing it up if initial load attempt fails

    Parameters
    ----------
    fixup : bool
      In case of failed load, apply a set of fixups with hope to resolve issues
      in JSON
    compressed : bool or None
      Flag whether to treat the file as XZ compressed. If None, this decision
      is made automatically based on the presence of a '.xz' extension in the
      filename
    **kw
      Passed into the load (and loads after fixups) function
    """
    _open = LZMAFile \
        if compressed or compressed is None and fname.endswith('.xz') \
        else io.open

    with _open(fname, 'rb') as f:
        try:
            jreader = codecs.getreader('utf-8')(f)
            return jsonload(jreader, **kw)
        except JSONDecodeError as exc:
            if not fixup:
                raise
            lgr.warning("Failed to decode content in %s: %s. Trying few tricks", fname, exc_str(exc))

            # Load entire content and replace common "abusers" which break JSON
            # comprehension but in general
            # are Ok
            with _open(fname,'rb') as f:
                s_orig = s = codecs.getreader('utf-8')(f).read()

            for o, r in {
                u"\xa0": " ",  # non-breaking space
            }.items():
                s = s.replace(o, r)

            if s == s_orig:
                # we have done nothing, so just reraise previous exception
                raise
            return loads(s, **kw)

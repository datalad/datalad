# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Utils to help with docstrings etc.

Largerly borrowed from PyMVPA (as of upstream/2.4.1-23-g170496e).  Copyright of
the same developers as DataLad
"""

import logging
import re
import textwrap
import os
import sys
import traceback


lgr = logging.getLogger("datalad.docutils")

__add_init2doc = False
__in_ipython = False  # TODO: determine exists('running ipython env')

# if ran within IPython -- might need to add doc to init
if __in_ipython:
    __rst_mode = False                       # either to do ReST links at all
    # if versions['ipython'] <= '0.8.1':
    #     __add_init2doc = True
else:
    __rst_mode = True

#
# Predefine some sugarings depending on syntax convention to be used
#
# XXX Might need to be removed or become proper cfg parameter
__rst_conventions = 'numpy'
if __rst_conventions == 'epydoc':
    _rst_sep = "`"
    _rst_indentstr = "  "

    def _rst_section(section_name):
        """Provide section heading"""
        return ":%s:" % section_name
elif __rst_conventions == 'numpy':
    _rst_sep = ""
    _rst_indentstr = ""

    def _rst_section(section_name):
        """Provide section heading"""
        return "%s\n%s" % (section_name, '-' * len(section_name))
else:
    raise ValueError("Unknown convention %s for RST" % __rst_conventions)


def _rst(s, snotrst=''):
    """Produce s only in __rst mode"""
    if __rst_mode:
        return s
    else:
        return snotrst


def _rst_underline(text, markup):
    """Add and underline RsT string matching the length of the given string.
    """
    return text + '\n' + markup * len(text)


def single_or_plural(single, plural, n, include_count=False):
    """Little helper to spit out single or plural version of a word.
    """
    ni = int(n)
    msg = "%d " % ni if include_count else ""
    if ni > 1 or ni == 0:
        # 1 forest, 2 forests, 0 forests
        return msg + plural
    else:
        return msg + single


def handle_docstring(text, polite=True):
    """Take care of empty and non existing doc strings."""
    if text is None or not len(text):
        if polite:
            return ''  # No documentation found. Sorry!'
        else:
            return ''
    else:
        # Problem is that first line might often have no offset, so might
        # need to be ignored from dedent call
        if not text.startswith(' '):
            lines = text.split('\n')
            text2 = '\n'.join(lines[1:])
            return lines[0] + "\n" + textwrap.dedent(text2)
        else:
            return textwrap.dedent(text)


def _indent(text, istr=_rst_indentstr):
    """Simple indenter
    """
    return '\n'.join(istr + s for s in text.split('\n'))


__parameters_str_re = re.compile("[\n^]\s*:?Parameters?:?\s*\n(:?\s*-+\s*\n)?")
"""regexp to match :Parameter: and :Parameters: stand alone in a line
or
Parameters
----------
in multiple lines"""


def _split_out_parameters(initdoc):
    """Split documentation into (header, parameters, suffix)

    Parameters
    ----------
    initdoc : string
      The documentation string
    """

    # TODO: bind it to the only word in the line
    p_res = __parameters_str_re.search(initdoc)
    if p_res is None:
        return initdoc, "", ""
    else:
        # Could have been accomplished also via re.match

        # where new line is after :Parameters:
        # parameters header index
        ph_i = p_res.start()

        # parameters body index
        pb_i = p_res.end()

        # end of parameters
        try:
            pe_i = initdoc.index('\n\n', pb_i)
        except ValueError:
            pe_i = len(initdoc)

        result = (initdoc[:ph_i].rstrip('\n '),
                  initdoc[pb_i:pe_i],
                  initdoc[pe_i:])

    # XXX a bit of duplication of effort since handle_docstring might
    # do splitting internally
    return handle_docstring(result[0], polite=False).strip('\n'), \
           textwrap.dedent(result[1]).strip('\n'), \
           textwrap.dedent(result[2]).strip('\n')


__re_params = re.compile('(?:\n\S.*?)+$')
__re_spliter1 = re.compile('\n(?=\S)')
__re_spliter2 = re.compile('[\n:]')


def _parse_parameters(paramdoc):
    """Parse parameters and return list of (name, full_doc_string)

    It is needed to remove multiple entries for the same parameter
    like it could be with adding parameters from the parent class

    It assumes that previously parameters were unwrapped, so their
    documentation starts at the beginning of the string, like what
    should it be after _split_out_parameters
    """
    entries = __re_spliter1.split(paramdoc)
    result = [(__re_spliter2.split(e)[0].strip(), e)
              for e in entries if e != '']
    lgr.debug('parseParameters: Given "%s", we split into %s' %
              (paramdoc, result))
    return result


def get_docstring_split(f):
    """Given a function, break it up into portions

    Parameters
    ----------
    f : function

    Returns
    -------

    (initial doc string, params (as list of tuples), suffix string)
    """

    if not hasattr(f, '__doc__') or f.__doc__ in (None, ""):
        return None, None, None
    initdoc, params, suffix = _split_out_parameters(
        f.__doc__)
    params_list = _parse_parameters(params)
    return initdoc, params_list, suffix


def borrowdoc(cls, methodname=None):
    """Return a decorator to borrow docstring from another `cls`.`methodname`

    It should not be used for __init__ methods of classes derived from
    ClassWithCollections since __doc__'s of those are handled by the
    AttributeCollector anyways.

    Common use is to borrow a docstring from the class's method for an
    adapter function (e.g. sphere_searchlight borrows from Searchlight)

    Examples
    --------
    To borrow `__repr__` docstring from parent class `Mapper`, do::

       @borrowdoc(Mapper)
       def __repr__(self):
           ...

    Parameters
    ----------
    cls
      Usually a parent class
    methodname : None or str
      Name of the method from which to borrow.  If None, would use
      the same name as of the decorated method
    """

    def _borrowdoc(method):
        """Decorator which assigns to the `method` docstring from another
        """
        if methodname is None:
            other_method = getattr(cls, method.__name__)
        else:
            other_method = getattr(cls, methodname)
        if hasattr(other_method, '__doc__'):
            method.__doc__ = other_method.__doc__
        return method
    return _borrowdoc


def borrowkwargs(cls=None, methodname=None, exclude=None):
    """Return  a decorator which would borrow docstring for ``**kwargs``

    Notes
    -----
    TODO: take care about ``*args`` in  a clever way if those are also present

    Examples
    --------
    In the simplest scenario -- just grab all arguments from parent class::

           @borrowkwargs(A)
           def met1(self, bu, **kwargs):
               pass

    Parameters
    ----------
    methodname : None or str
      Name of the method from which to borrow.  If None, would use
      the same name as of the decorated method
    exclude : None or list of arguments to exclude
      If function does not pass all ``**kwargs``, you would need to list
      those here to be excluded from borrowed docstring
    """

    def _borrowkwargs(method):
        """Decorator which borrows docstrings for ``**kwargs`` for the `method`
        """
        if cls:
            if methodname is None:
                other_method = getattr(cls, method.__name__)
            else:
                other_method = getattr(cls, methodname)
        elif methodname:
            other_method = methodname

        # TODO:
        # method.__doc__ = enhanced_from(other_method.__doc__)

        mdoc, odoc = method.__doc__, other_method.__doc__
        if mdoc is None:
            mdoc = ''

        mpreamble, mparams, msuffix = _split_out_parameters(mdoc)
        opreamble, oparams, osuffix = _split_out_parameters(odoc)
        mplist = _parse_parameters(mparams)
        oplist = _parse_parameters(oparams)
        known_params = set([i[0] for i in mplist])

        # !!! has to not rebind exclude variable
        skip_params = exclude or []         # handle None
        skip_params = set(['kwargs', '**kwargs'] + skip_params)

        # combine two and filter out items to skip
        aplist = [i for i in mplist if not i[0] in skip_params]
        aplist += [i for i in oplist
                   if not i[0] in skip_params.union(known_params)]

        docstring = mpreamble
        if len(aplist):
            params_ = '\n'.join([i[1].rstrip() for i in aplist])
            docstring += "\n\n%s\n" \
                         % _rst_section('Parameters') + _indent(params_)

        if msuffix != "":
            docstring += "\n\n" + msuffix

        docstring = handle_docstring(docstring)

        # Finally assign generated doc to the method
        method.__doc__ = docstring
        return method
    return _borrowkwargs


# TODO: make limit respect config/environment parameter
# TODO: document, what limit even is about ;-)
def exc_str(exc=None, limit=None):
    """Enhanced str for exceptions.  Should include original location

    Parameters
    ----------
    Exception to
    """
    out = str(exc)
    if limit is None:
        # TODO: config logging.exceptions.traceback_levels = 1
        limit = int(os.environ.get('DATALAD_EXC_STR_TBLIMIT', '1'))
    try:
        exctype, value, tb = sys.exc_info()
        if not exc:
            exc = value
            out = str(exc)
        # verify that it seems to be the exception we were passed
        #assert(isinstance(exc, exctype))
        if exc:
            assert(exc is value)
        entries = traceback.extract_tb(tb)
        if entries:
            out += " [%s]" % (','.join(['%s:%s:%d' % (os.path.basename(x[0]), x[2], x[1]) for x in entries[-limit:]]))
    except:  # MIH: TypeError?
        return out  # To the best of our abilities
    finally:
        # As the bible teaches us:
        # https://docs.python.org/2/library/sys.html#sys.exc_info
        del tb
    return out

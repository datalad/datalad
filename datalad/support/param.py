# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##g
"""Parameter representation"""

__docformat__ = 'restructuredtext'

import re
import textwrap
from .constraints import expand_contraint_spec

_whitespace_re = re.compile('\n\s+|^\s+')


class Parameter(object):
    """This class shall serve as a representation of a parameter.
    """

    def __init__(self, constraints=None, doc=None, args=None, **kwargs):
        """Add contraints (validator) specifications and a docstring for
        a parameter.

        Parameters
        ----------
        constraints : callable
          A functor that takes any input value, performs checks or type
          conversions and finally returns a value that is appropriate for a
          parameter or raises an exception. This will also be used to set up
          the ``type`` functionality of argparse.add_argument.
        doc : str
          Documentation about the purpose of this parameter.
        args : tuple or None
          Any additional positional args for argparser.add_argument. This is
          most useful for assigned multiple alternative argument names or
          create positional arguments.
        **kwargs :
          Any additional keyword args for argparser.add_argument.

        Examples
        --------
        Ensure a parameter is a float
        >>> from datalad.support.param import Parameter
        >>> from datalad.support.constraints import (EnsureFloat, EnsureRange,
        ...                              AltConstraints, Constraints)
        >>> C = Parameter(constraints=EnsureFloat())

        Ensure a parameter is of type float or None:
        >>> C = Parameter(constraints=AltConstraints(EnsureFloat(), None))

        Ensure a parameter is None or of type float and lies in the inclusive
        range (7.0,44.0):
        >>> C = Parameter(
        ...         AltConstraints(
        ...             Constraints(EnsureFloat(),
        ...                         EnsureRange(min=7.0,max=44.0)),
        ...             None))
        """
        self.constraints = expand_contraint_spec(constraints)
        self._doc = doc
        self.cmd_args = args
        self.cmd_kwargs = kwargs

    def get_autodoc(self, name, indent="  ", width=70, default=None, has_default=False):
        """Docstring for the parameter to be used in lists of parameters

        Returns
        -------
        string or list of strings (if indent is None)
        """
        paramsdoc = '%s' % name
        if not self.constraints is None:
            sdoc = self.constraints.short_description()
            if not sdoc is None:
                if sdoc[0] == '(' and sdoc[-1] == ')':
                    sdoc = sdoc[1:-1]
                paramsdoc += " : %s" % sdoc
                if has_default:
                    paramsdoc += ", optional"
        paramsdoc = [paramsdoc]

        doc = self._doc
        if doc is None:
            doc = ''
        doc.strip()
        if len(doc) and not doc.endswith('.'):
            doc += '.'
        if self.constraints is not None:
            cdoc = self.constraints.long_description()
            if cdoc[0] == '(' and cdoc[-1] == ')':
                cdoc = cdoc[1:-1]
            doc += ' Constraints: %s.' % cdoc
        if has_default:
            doc += " [Default: %r]" % (default,)
        # Explicitly deal with multiple spaces, for some reason
        # replace_whitespace is non-effective
        doc = _whitespace_re.sub(' ', doc)
        paramsdoc += [indent + x
                      for x in textwrap.wrap(doc, width=width - len(indent),
                                             replace_whitespace=True)]
        return '\n'.join(paramsdoc)

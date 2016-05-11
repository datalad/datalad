# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper for parameter validation, documentation and conversion"""

__docformat__ = 'restructuredtext'

import re
from six.moves import map as map


def _strip_typerepr(s):
    """Strip away <class '...'> and <type '...'> decorations for docstrings
    """
    return re.sub("<(class|type) '(\S+)'>", r'\2', s)


def _type_str(t):
    """Get string human-readable representation of a data type

    If type (t) is given as a tuple, assume ability to choose any of the
    listed types, so those types listing get joined with |
    """
    if isinstance(t, tuple):
        s = ' or '.join(map(_type_str, t))
        return ("(%s)" % s) if len(t) > 1 else s
    return _strip_typerepr(str(t))


class Constraint(object):
    """Base class for input value conversion/validation.

    These classes are also meant to be able to generate appropriate
    documentation on an appropriate parameter value.
    """

    # TODO: __str__ and/or __repr__ for every one of them

    def __and__(self, other):
        return Constraints(self, other)

    def __or__(self, other):
        return AltConstraints(self, other)

    def __call__(self, value):
        # do any necessary checks or conversions, potentially catch exceptions
        # and generate a meaningful error message
        raise NotImplementedError("abstract class")

    def long_description(self):
        # return meaningful docs or None
        # used as a comprehensive description in the parameter list
        return self.short_description()

    def short_description(self):
        # return meaningful docs or None
        # used as a condensed primer for the parameter lists
        raise NotImplementedError("abstract class")


class EnsureDType(Constraint):
    """Ensure that an input (or several inputs) are of a particular data type.
    """
    # TODO extend to support numpy-like dtype specs, e.g. 'int64'
    # in addition to functors
    def __init__(self, dtype):
        """
        Parameters
        ----------
        dtype : functor
        """
        self._dtype = dtype

    def __call__(self, value):
        from six import binary_type, text_type
        if hasattr(value, '__iter__') and \
                not (isinstance(value, (binary_type, text_type))):
            return list(map(self._dtype, value))
        else:
            return self._dtype(value)

    def short_description(self):
        return _type_str(self._dtype)

    def long_description(self):
        return "value must be convertible to type '%s'" % self.short_description()


class EnsureInt(EnsureDType):
    """Ensure that an input (or several inputs) are of a data type 'int'.
    """
    def __init__(self):
        """Initializes EnsureDType with int"""
        EnsureDType.__init__(self, int)


class EnsureFloat(EnsureDType):
    """Ensure that an input (or several inputs) are of a data type 'float'.
    """
    def __init__(self):
        """Initializes EnsureDType with float"""
        EnsureDType.__init__(self, float)


class EnsureListOf(Constraint):
    """Ensure that an input is a list of a particular data type
    """
    def __init__(self, dtype):
        """
        Parameters
        ----------
        dtype : functor
        """
        self._dtype = dtype
        super(EnsureListOf, self).__init__()

    def __call__(self, value):
        return list(map(self._dtype, value))

    def short_description(self):
        return 'list(%s)' % _type_str(self._dtype)

    def long_description(self):
        return "value must be convertible to %s" % self.short_description()


class EnsureTupleOf(Constraint):
    """Ensure that an input is a tuple of a particular data type
    """
    def __init__(self, dtype):
        """
        Parameters
        ----------
        dtype : functor
        """
        self._dtype = dtype
        super(EnsureTupleOf, self).__init__()

    def __call__(self, value):
        return tuple(map(self._dtype, value))

    def short_description(self):
        return 'tuple(%s)' % _type_str(self._dtype)

    def long_description(self):
        return "value must be convertible to %s" % self.short_description()


class EnsureBool(Constraint):
    """Ensure that an input is a bool.

    A couple of literal labels are supported, such as:
    False: '0', 'no', 'off', 'disable', 'false'
    True: '1', 'yes', 'on', 'enable', 'true'
    """
    def __call__(self, value):
        from six import binary_type, text_type
        if isinstance(value, bool):
            return value
        elif isinstance(value, (binary_type, text_type)):
            value = value.lower()
            if value in ('0', 'no', 'off', 'disable', 'false'):
                return False
            elif value in ('1', 'yes', 'on', 'enable', 'true'):
                return True
        raise ValueError("value must be converted to boolean")

    def long_description(self):
        return 'value must be convertible to type bool'

    def short_description(self):
        return 'bool'


class EnsureStr(Constraint):
    """Ensure an input is a string.

    No automatic conversion is attempted.
    """
    def __init__(self, min_len=0):
        """
        Parameters
        ----------
        min_len: int, optional
           Minimal length for a string.
        """
        assert(min_len >= 0)
        self._min_len = min_len
        super(EnsureStr, self).__init__()

    def __call__(self, value):
        from six import binary_type, text_type
        if not isinstance(value, (binary_type, text_type)):
            # do not perform a blind conversion ala str(), as almost
            # anything can be converted and the result is most likely
            # unintended
            raise ValueError("%s is not a string" % repr(value))
        if len(value) < self._min_len:
            raise ValueError("%r is shorter than of minimal length %d"
                             % (value, self._min_len))
        return value

    def long_description(self):
        return 'value must be a string'

    def short_description(self):
        return 'str'


class EnsureNone(Constraint):
    """Ensure an input is of value `None`"""
    def __call__(self, value):
        if value is None:
            return None
        else:
            raise ValueError("value must be `None`")

    def short_description(self):
        return 'None'

    def long_description(self):
        return 'value must be `None`'


class EnsureChoice(Constraint):
    """Ensure an input is element of a set of possible values"""

    def __init__(self, *values):
        """
        Parameters
        ----------
        *values
           Possible accepted values.
        """
        self._allowed = values
        super(EnsureChoice, self).__init__()

    def __call__(self, value):
        if value not in self._allowed:
            raise ValueError("value is not one of %s" % (self._allowed,))
        return value

    def long_description(self):
        return 'value must be one of %s' % (str(self._allowed),)

    def short_description(self):
        return '{%s}' % ', '.join([str(c) for c in self._allowed])


class EnsureRange(Constraint):
    """Ensure an input is within a particular range

    No type checks are performed.
    """
    def __init__(self, min=None, max=None):
        """
        Parameters
        ----------
        min
            Minimal value to be accepted in the range
        max
            Maximal value to be accepted in the range
        """
        self._min = min
        self._max = max
        super(EnsureRange, self).__init__()

    def __call__(self, value):
        if self._min is not None:
            if value < self._min:
                raise ValueError("value must be at least %s" % (self._min,))
        if self._max is not None:
            if value > self._max:
                raise ValueError("value must be at most %s" % (self._max,))
        return value

    def long_description(self):
        min_str = '-inf' if self._min is None else str(self._min)
        max_str = 'inf' if self._max is None else str(self._max)
        return 'value must be in range [%s, %s]' % (min_str, max_str)

    def short_description(self):
        None


class AltConstraints(Constraint):
    """Logical OR for constraints.

    An arbitrary number of constraints can be given. They are evaluated in the
    order in which they were specified. The value returned by the first
    constraint that does not raise an exception is the global return value.

    Documentation is aggregated for all alternative constraints.
    """
    def __init__(self, *constraints):
        """
        Parameters
        ----------
        *constraints
           Alternative constraints
        """
        super(AltConstraints, self).__init__()
        self.constraints = [EnsureNone() if c is None else c for c in constraints]

    def __or__(self, other):
        if isinstance(other, AltConstraints):
            self.constraints.extend(other.constraints)
        else:
            self.constraints.append(other)
        return self

    def __call__(self, value):
        e_list = []
        for c in self.constraints:
            try:
                return c(value)
            except Exception as e:
                e_list.append(e)
        raise ValueError("all alternative constraints (%s) violated while testing value %r"
                         % (self.constraints, value))

    def long_description(self):
        cs = [c.long_description() for c in self.constraints if hasattr(c, 'long_description')]
        doc = ', or '.join(cs)
        if len(cs) > 1:
            return '(%s)' % doc
        else:
            return doc

    def short_description(self):
        cs = [c.short_description() for c in self.constraints
              if hasattr(c, 'short_description') and not c.short_description() is None]
        doc = ' or '.join(cs)
        if len(cs) > 1:
            return '(%s)' % doc
        else:
            return doc


class Constraints(Constraint):
    """Logical AND for constraints.

    An arbitrary number of constraints can be given. They are evaluated in the
    order in which they were specified. The return value of each constraint is
    passed an input into the next. The return value of the last constraint
    is the global return value. No intermediate exceptions are caught.

    Documentation is aggregated for all constraints.
    """
    def __init__(self, *constraints):
        """
        Parameters
        ----------
        *constraints
           Constraints all of which must be satisfied
        """
        super(Constraints, self).__init__()
        self.constraints = [EnsureNone() if c is None else c for c in constraints]

    def __and__(self, other):
        if isinstance(other, Constraints):
            self.constraints.extend(other.constraints)
        else:
            self.constraints.append(other)
        return self

    def __call__(self, value):
        for c in (self.constraints):
            value = c(value)
        return value

    def long_description(self):
        cs = [c.long_description() for c in self.constraints if hasattr(c, 'long_description')]
        doc = ', and '.join(cs)
        if len(cs) > 1:
            return '(%s)' % doc
        else:
            return doc

    def short_description(self):
        cs = [c.short_description() for c in self.constraints
              if hasattr(c, 'short_description') and not c.short_description() is None]
        doc = ' and '.join(cs)
        if len(cs) > 1:
            return '(%s)' % doc
        else:
            return doc

constraint_spec_map = {
    'float': EnsureFloat(),
    'int': EnsureInt(),
    'bool': EnsureBool(),
    'str': EnsureStr(),
}


def expand_contraint_spec(spec):
    """Helper to translate literal contraint specs into functional ones

    e.g. 'float' -> EnsureFloat()
    """
    if spec is None or hasattr(spec, '__call__'):
        return spec
    else:
        try:
            return constraint_spec_map[spec]
        except KeyError:
            raise ValueError("unsupport constraint specification '%r'" % (spec,))

"""Render results in a terminal"""

import string
from collections import defaultdict

from datalad.ui import ui

NA_STRING = 'N/A'  # we might want to make it configurable via config


class nagen(object):
    """A helper to provide a desired missing value if no value is known

    Usecases

    - could be used as a generator for `defaultdict`
    - since it returns itself upon getitem, should work even for complex
      nested dictionaries/lists .format templates
    """
    def __init__(self, missing=NA_STRING):
        self.missing = missing

    def __repr__(self):
        cls = self.__class__.__name__
        args = str(self.missing) if self.missing != NA_STRING else ''
        return '%s(%s)' % (cls, args)

    def __str__(self):
        return self.missing

    def __getitem__(self, *args):
        return self

    def __getattr__(self, item):
        return self


def nadict(*items):
    """A generator of default dictionary with the default nagen"""
    dd = defaultdict(nagen)
    dd.update(*items)
    return dd


class DefaultOutputFormatter(string.Formatter):
    """A custom formatter for default output rendering using .format
    """
    # TODO: make missing configurable?
    def __init__(self, missing=nagen()):
        """
        Parameters
        ----------
        missing: string, optional
          What to output for the missing values
        """
        super(DefaultOutputFormatter, self).__init__()
        self.missing = missing

    def _d(self, msg, *args):
        # print("   HERE %s" % (msg % args))
        pass

    def get_value(self, key, args, kwds):
        assert not args
        self._d("get_value: %r %r %r", key, args, kwds)
        return kwds.get(key, self.missing)

    # def get_field(self, field_name, args, kwds):
    #     assert not args
    #     self._d("get_field: %r args=%r kwds=%r" % (field_name, args, kwds))
    #     try:
    #         out = string.Formatter.get_field(self, field_name, args, kwds)
    #     except Exception as exc:
    #         # TODO needs more than just a value
    #         return "!ERR %s" % exc


class DefaultOutputRenderer(object):
    """A default renderer for .format'ed output line
    """
    def __init__(self, format):
        self.format = format
        # We still need custom output formatter since at the "first level"
        # within .format template all items there is no `nadict`
        self.formatter = DefaultOutputFormatter()

    @classmethod
    def _dict_to_nadict(cls, v):
        """Traverse datastructure and replace any regular dict with nadict"""
        if isinstance(v, list):
            return [cls._dict_to_nadict(x) for x in v]
        elif isinstance(v, dict):
            return nadict((k, cls._dict_to_nadict(x)) for k, x in v.items())
        else:
            return v

    def __call__(self, x, **kwargs):
        dd = nadict(
            (k, nadict({k_.replace(':', '#'): self._dict_to_nadict(v_)
             for k_, v_ in v.items()})
             if isinstance(v, dict) else v)
            for k, v in x.items()
        )

        msg = self.formatter.format(self.format, **dd)
        return ui.message(msg)

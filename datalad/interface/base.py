# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface generation

"""

__docformat__ = 'restructuredtext'


def update_docstring_with_parameters(func, params):
    """Generate a useful docstring from a parameter spec

    Amends any existing docstring of a callable with a textual
    description of its parameters. The Parameter spec needs to match
    the number and names of the callables arguments.
    """
    from inspect import getargspec
    # get the signature
    ndefaults = 0
    args, varargs, varkw, defaults = getargspec(func)
    if not defaults is None:
        ndefaults = len(defaults)
    # start documentation with what the callable brings with it
    doc = func.__doc__
    if doc is None:
        doc = u''
    if len(args):
        doc += "Parameters\n----------\n"
        for i, arg in enumerate(args):
            if arg == 'self':
                continue
            # we need a parameter spec for each argument
            if not arg in params:
                raise ValueError("function has argument '%s' not described as a parameter" % arg)
            param = params[arg]
            # validate the default -- to make sure that the parameter description is
            # somewhat OK
            defaults_idx = ndefaults - len(args) + i
            if defaults_idx >= 0:
                if not param.constraints is None:
                    param.constraints(defaults[defaults_idx])
            doc += param.get_autodoc(
                arg,
                default=defaults[defaults_idx] if defaults_idx >= 0 else None,
                has_default=defaults_idx >= 0)
            doc += '\n'
    # assign the ammended docs
    func.__doc__ = doc
    return func


class Interface(object):
    """Base class for interface implementations"""
    def __init__(self):
        pass

    def setup_parser(self, parser):
        # XXX needs safety check for name collisions
        # XXX allow for parser kwargs customization
        parser_kwargs = {}
        from inspect import getargspec
        # get the signature
        ndefaults = 0
        args, varargs, varkw, defaults = getargspec(self.__call__)
        if not defaults is None:
            ndefaults = len(defaults)
        for i, arg in enumerate(args):
            if arg == 'self':
                continue
            param = self._params_[arg]
            defaults_idx = ndefaults - len(args) + i
            cmd_args = param.cmd_args
            if cmd_args is None:
                cmd_args = []
            if not len(cmd_args):
                if defaults_idx >= 0:
                    # dealing with a kwarg
                    template = '--%s'
                else:
                    # positional arg
                    template = '%s'
                # use parameter name as default argument name
                parser_args = (template % arg.replace('_', '-'),)
            else:
                parser_args = cmd_args
            parser_kwargs = param.cmd_kwargs
            if defaults_idx >= 0:
                parser_kwargs['default'] = defaults[defaults_idx]
            help = param._doc
            if param.constraints is not None:
                parser_kwargs['type'] = param.constraints
                # include value contraint description and default
                # into the help string
                cdoc = param.constraints.long_description()
                if cdoc[0] == '(' and cdoc[-1] == ')':
                    cdoc = cdoc[1:-1]
                help += ' Constraints: %s.' % cdoc
            # create the parameter, using the constraint instance for type
            # conversion
            parser.add_argument(*parser_args, help=help,
                                **parser_kwargs)

    def call_from_parser(self, args):
        # XXX needs safety check for name collisions
        from inspect import getargspec
        argnames = getargspec(self.__call__)[0]
        kwargs = {k: getattr(args, k) for k in argnames if k != 'self'}
        return self(**kwargs)

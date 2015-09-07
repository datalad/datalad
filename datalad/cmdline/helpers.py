# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""

__docformat__ = 'restructuredtext'

import argparse
import re
import sys

from ..log import is_interactive


class HelpAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
#        import pydb; pydb.debugger()

        if is_interactive() and option_string == '--help':
            # lets use the manpage on mature systems ...
            try:
                import subprocess
                subprocess.check_call(
                    'man %s 2> /dev/null' % parser.prog.replace(' ', '-'),
                    shell=True)
                sys.exit(0)
            except (subprocess.CalledProcessError, OSError):
                # ...but silently fall back if it doesn't work
                pass
        if option_string == '-h':
            helpstr = "%s\n%s" % (
                parser.format_usage(),
                "Use '--help' to get more comprehensive information.")
        else:
            helpstr = parser.format_help()
        # better for help2man
        helpstr = re.sub(r'optional arguments:', 'options:', helpstr)
        # yoh: TODO for datalad + help2man
        #helpstr = re.sub(r'positional arguments:\n.*\n', '', helpstr)
        # convert all heading to have the first character uppercase
        headpat = re.compile(r'^([a-z])(.*):$',  re.MULTILINE)
        helpstr = re.subn(
            headpat,
            lambda match: r'{0}{1}:'.format(match.group(1).upper(),
                                            match.group(2)),
            helpstr)[0]
        # usage is on the same line
        helpstr = re.sub(r'^usage:', 'Usage:', helpstr)
        if option_string == '--help-np':
            usagestr = re.split(r'\n\n[A-Z]+', helpstr, maxsplit=1)[0]
            usage_length = len(usagestr)
            usagestr = re.subn(r'\s+', ' ', usagestr.replace('\n', ' '))[0]
            helpstr = '%s\n%s' % (usagestr, helpstr[usage_length:])
        print(helpstr)
        sys.exit(0)


class LogLevelAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        from ..log import LoggerHelper
        LoggerHelper().set_level(level=values)


def parser_add_common_args(parser, pos=None, opt=None, **kwargs):
    from . import common_args
    for i, args in enumerate((pos, opt)):
        if args is None:
            continue
        for arg in args:
            arg_tmpl = getattr(common_args, arg)
            arg_kwargs = arg_tmpl[2].copy()
            arg_kwargs.update(kwargs)
            if i:
                parser.add_argument(*arg_tmpl[i], **arg_kwargs)
            else:
                parser.add_argument(arg_tmpl[i], **arg_kwargs)


def parser_add_common_opt(parser, opt, names=None, **kwargs):
    from . import common_args
    opt_tmpl = getattr(common_args, opt)
    opt_kwargs = opt_tmpl[2].copy()
    opt_kwargs.update(kwargs)
    if names is None:
        parser.add_argument(*opt_tmpl[1], **opt_kwargs)
    else:
        parser.add_argument(*names, **opt_kwargs)


class RegexpType(object):
    """Factory for creating regular expression types for argparse

    DEPRECATED AFAIK -- now things are in the config file...
    but we might provide a mode where we operate solely from cmdline
    """
    def __call__(self, string):
        if string:
            return re.compile(string)
        else:
            return None


def get_repo_instance_from_cwd(class_=None):
    """Returns an instance of appropriate datalad repository for cwd.

    Raises
    ------
    RuntimeError, in case cwd is not inside a known repository.
    """
    # TODO: After PR #195 is merged, use/create proper Exceptions

    from os import getcwd
    from os.path import join as opj, ismount, exists
    from git.exc import InvalidGitRepositoryError
    from ..support.gitrepo import GitRepo
    from ..support.annexrepo import AnnexRepo
    from ..support.handlerepo import HandleRepo
    from ..support.collectionrepo import CollectionRepo
    from ..support.exceptions import CollectionBrokenError

    dir_ = getcwd()
    if class_ is not None:
        if class_ == CollectionRepo:
            type_ = "collection"
        elif class_ == HandleRepo:
            type_ = "handle"
        elif class_ == AnnexRepo:
            type_ = "annex"
        elif class_ == GitRepo:
            type_ = "git"
        else:
            raise RuntimeError("Unknown class %s." % str(class_))

    while not ismount(dir_):  # TODO: always correct termination?
        if exists(opj(dir_, '.git')):
            # found git dir
            if class_ is None:
                # detect repo type:
                try:
                    return HandleRepo(dir_)
                except RuntimeError as e:
                    pass
                try:
                    return AnnexRepo(dir_)
                except RuntimeError as e:
                    pass
                try:
                    return CollectionRepo(dir_)
                except CollectionBrokenError as e:
                    pass
                try:
                    return GitRepo(dir_)
                except InvalidGitRepositoryError as e:
                    raise RuntimeError("No datalad repository found in %s" %
                                       getcwd())
            else:
                try:
                    return class_(dir_)
                except (RuntimeError, InvalidGitRepositoryError) as e:
                    raise RuntimeError("No %s repository found in %s" %
                                       (type_, getcwd()))
        else:
            dir_ = opj(dir_, "..")
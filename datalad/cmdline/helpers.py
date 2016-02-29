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
import os
import re
import sys

from ..log import is_interactive


class HelpAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
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
        # For main command -- should be different sections. And since we are in
        # heavy output massaging mode...
        if "commands for collection" in helpstr.lower():
            opt_args_str = '*Global options*'
            pos_args_str = '*Commands*'
            # tune up usage -- default one is way too heavy
            helpstr = re.sub('^[uU]sage: .*?\n\s*\n',
                             'Usage: datalad [global-opts] command [command-opts]\n\n',
                             helpstr,
                             flags=re.MULTILINE | re.DOTALL)
            # And altogether remove section with long list of commands
            helpstr = re.sub(r'positional arguments:\s*\n\s*{.*}\n', '', helpstr)
        else:
            opt_args_str = "*Options*"
            pos_args_str = "*Arguments*"
        helpstr = re.sub(r'optional arguments:', opt_args_str, helpstr)
        helpstr = re.sub(r'positional arguments:', pos_args_str, helpstr)
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

        if os.environ.get('DATALAD_HELP2MAN'):
            # Convert 1-line command descriptions to remove leading -
            helpstr = re.sub('\n\s*-\s*([-a-z0-9]*):\s*?([^\n]*)', r"\n'\1':\n  \2\n", helpstr)
        else:
            # Those *s intended for man formatting do not contribute to readability in regular text mode
            helpstr = helpstr.replace('*', '')

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


# TODO: useful also outside of cmdline, move to support/
from os import curdir
def get_repo_instance(path=curdir, class_=None):
    """Returns an instance of appropriate datalad repository for path.

    Check whether a certain path is inside a known type of repository and
    returns an instance representing it. May also check for a certain type
    instead of detecting the type of repository.

    Parameters
    ----------
    path: str
      path to check; default: current working directory

    class_: class
      if given, check whether path is inside a repository, that can be
      represented as an instance of the passed class.

    Raises
    ------
    RuntimeError, in case cwd is not inside a known repository.
    """

    from os.path import join as opj, ismount, exists, abspath, expanduser, \
        expandvars, normpath, isabs
    from git.exc import InvalidGitRepositoryError
    from ..support.gitrepo import GitRepo
    from ..support.annexrepo import AnnexRepo
    from ..support.handlerepo import HandleRepo
    from ..support.collectionrepo import CollectionRepo
    from ..support.exceptions import CollectionBrokenError

    dir_ = abspath(expandvars(expanduser(path)))
    abspath_ = path if isabs(path) else dir_
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
                    return HandleRepo(dir_, create=False)
                except RuntimeError as e:
                    pass
                try:
                    return AnnexRepo(dir_, create=False)
                except RuntimeError as e:
                    pass
                try:
                    return CollectionRepo(dir_, create=False)
                except CollectionBrokenError as e:
                    pass
                try:
                    return GitRepo(dir_, create=False)
                except InvalidGitRepositoryError as e:
                    raise RuntimeError("No datalad repository found in %s" %
                                       abspath_)
            else:
                try:
                    return class_(dir_, create=False)
                except (RuntimeError, InvalidGitRepositoryError) as e:
                    raise RuntimeError("No %s repository found in %s." %
                                       (type_, abspath_))
        else:
            dir_ = normpath(opj(dir_, ".."))

    if class_ is not None:
        raise RuntimeError("No %s repository found in %s" % (type_, abspath_))
    else:
        raise RuntimeError("No datalad repository found in %s" % abspath_)


# Do some centralizing of things needed by the datalad API:
# TODO: May be there should be a dedicated class for the master collection.
# For now just use helper functions to clean up the implementations of the API.
# Design decision about this also depends on redesigning the handle/collection
# classes (Metadata class => Backends => Repos).
# The local master used by datalad is not a technically special
# collection, but a collection with a special purpose for its "user",
# who is datalad. So, deriving a class from Collection(Repo) and make common
# tasks methods of this class might be an option either way. Also might become
# handy, once we decide to have several "masters" (user-level, sys-level, etc.)


from appdirs import AppDirs
from os.path import join as opj

dirs = AppDirs("datalad", "datalad.org")


def get_datalad_master():
    """Return "master" collection on which all collection operations will be done
    """
    # Delay imports to not load rdflib until necessary
    from ..support.collectionrepo import CollectionRepo
    from ..consts import DATALAD_COLLECTION_NAME

    # Allow to have "master" collection be specified by environment variable
    env_path = os.environ.get('DATALAD_COLLECTION_PATH', None)
    return CollectionRepo(
        env_path or opj(dirs.user_data_dir, DATALAD_COLLECTION_NAME),
        create=True
    )


def POC_get_root_handle(root_dir=None):
    """Return "master" handle.

    Parameter
    ---------
    dir: str
      path to the root handle. If None, datalad's default is used.
      The default root handle lives in a sub directory
      of user_data_dir as returned by appdirs. The default name of this
      subdirectory is set by datalad.consts.DATALAD_ROOT_HANDLE_NAME.
      Alternatively, a different default root handle can be set by the
      environment variable DATALAD_ROOT_HANDLE, which then is expected to
      contain the full path the desired root handle.

    Note
    ----
    This is a temporary version of the above get_datalad_master, marked by the prefix POC.
     Not for general use in datalad yet.
    """

    from ..consts import DATALAD_ROOT_HANDLE_NAME
    if root_dir is None:
        root_dir = os.environ.get('DATALAD_ROOT_HANDLE', None) or \
                   opj(dirs.user_data_dir, DATALAD_ROOT_HANDLE_NAME)

    from ..support.gitrepo import GitRepo
    return GitRepo(root_dir, create=True)



# Notes:
# ------
# collection:
# handle at 'path'? => return Handle/HandleRepo
#
# is 'handle' in collection?, get Handle/HandleRepo
#
# same for collections
#   - is_registered?
#   - get the instance
#   - get the path/url
#   - get registered Collections
#
# register collection? (remote add (check for duplicates); fetch)
#
# "register" handle? (and add metadata to master) => integrate the latter into
# add_handle (CollectionRepo)
#
# get handle's path; list of handles paths => could be done via
# Handle instances.
#
#
# what to do about addressing the local master itself via its name?
#  - when is it needed?
#  - when it should be showed, when it shouldn't?
#
#
# check whether 'handle' is a key ("{collection}/{handle}")
# or a local path or an url

# Tasks:
# ------
#
# - get a handle by its name or path or url => different type of return value?
# - (un)register a collection
# - check what type of repo is at path and return it (see get_repo_instance)

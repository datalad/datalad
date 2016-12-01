# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" utility classes for repositories

"""

import logging
from os.path import normpath

from .network import RI


lgr = logging.getLogger('datalad.repo')


class WeakRefSingletonRepo(type):
    """Metaclass for repo classes, providing singletons.

    This integrates the singleton mechanic into the actual classes, which need
    to have a class attribute `unique_repos` (WeakValueDictionary).
    By providing an implementation of __call__, you don't need to call a
    factory's get_xy_repo() method to get a singleton. Instead this is called
    when you simply instantiate via XYRepo(). So, you basically don't even need
    to know there were singletons. Therefore it is also less likely to sabotage
    the concept by not being aware of how to get an appropriate object.

    Multiple instances, pointing to the same physical repository can cause a
    lot of trouble. This is why this class exists. You should be very aware of
    the implications, if you want to circumvent the singleton mechanic.

    Note:
        ATM the identifying key for the singletons is the given path in its
        canonical form. Symlinks are not resolved!
    """

    def __call__(cls, path, *args, **kwargs):

        if len(args) >= 1 or ('url' in kwargs and kwargs['url'] is not None):
            # TEMP: (mis-)use wrapper class to raise exception to ease RF'ing;
            # keep in master when merging and remove in second PR, so other PRs
            # benefit from it, when merging/rebasing atm
            raise RuntimeError("RF: call clone() instead!")

        # TODO: Figure out, what to do in case of cloning in order to do (try)
        # the actual cloning but don't end up with multiple instances;
        # clone() might call Annex/GitRepo(), but we might need to pass
        # GitPython's Repo in addition ...

        #     if args:
        #         url = args[0]
        #         args = args[1:]
        #     else:
        #         url = kwargs.pop('url')
        #     return cls.clone(url, path, *args, **kwargs)
        else:
            # TODO: Not sure yet, if and where to resolve symlinks or use
            # abspath and whether to pass the resolved path. May be have an
            # additional layer, where we can address the same repo with
            # different paths (links).
            # For now just make sure it's a "singleton" if addressed the
            # same way. When caring for this, consider symlinked submodules ...
            # (look for issue by mih)

            # Sanity check for argument `path`:
            # raise if we cannot deal with `path` at all or
            # if it is not a local thing:
            path = RI(path).localpath

            # use canonical paths only:
            path = normpath(path)

            repo = cls._unique_repos.get(path, None)

            if repo is None or not cls.is_valid_repo(path):
                repo = type.__call__(cls, path, *args, **kwargs)
                cls._unique_repos[path] = repo

            return repo


# TODO: see issue #1100
class RepoInterface(object):
    """common operations for annex and plain git repositories

    Especially provides "annex operations" on plain git repos, that just do
    (or return) the "right thing"
    """

    def sth_like_file_has_content(self):
        return # the real thing in case of annex and True in case of git

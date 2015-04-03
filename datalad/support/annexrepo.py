# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to git-annex by Joey Hess.

For further information on git-annex see https://git-annex.branchable.com/.

"""
import os

from os.path import join, exists
import logging

from ConfigParser import NoOptionError

from gitrepo import GitRepo
from datalad.cmd import Runner as Runner

from ..utils import has_content

lgr = logging.getLogger('datalad.annex')


class AnnexRepo(GitRepo):
    """Representation of an git-annex repository.

    """

    def __init__(self, path, url=None, runner=None):
        """Creates representation of git-annex repository at `path`.

        AnnexRepo is initialized by giving a path to the annex.
        If no annex exists at that location, a new one is created.
        Optionally give url to clone from.

        Parameters:
        -----------
        path: str
          path to git-annex repository

        url: str
          url to the to-be-cloned repository.
          valid git url according to http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS required.

        runner: Runner
           Provide a Runner in case AnnexRepo shall not create it's own. This is especially needed in case of
           desired dry runs.
        """
        super(AnnexRepo, self).__init__(path, url)

        self.cmd_call_wrapper = runner or Runner()
        # TODO: Concept of when to set to "dry". Includes: What to do in gitrepo class?
        #       Now: setting "dry" means to give a dry-runner to constructor.
        #       => Do it similar in gitrepo/dataset. Still we need a concept of when to set it
        #       and whether this should be a single instance collecting everything or more
        #       fine grained.

        # Check whether an annex already exists at destination
        if not exists(join(self.path, '.git', 'annex')):
            lgr.debug('No annex found in %s. Creating a new one ...' % self.path)
            self._annex_init()

    def is_direct_mode(self):
        """Indicates whether or not annex is in direct mode

        Returns
        -------
        True if in direct mode, False otherwise.
        """

        try:
            dm = self.repo.config_reader().get_value("annex", "direct")
        except NoOptionError, e:
            #If .git/config lacks an entry "direct" it's actually indirect mode.
            dm = False

        return dm

    def set_direct_mode(self, enable_direct_mode=True):
        """Switch to direct or indirect mode

        Parameters
        ----------
        enable_direct_mode: bool
            True means switch to direct mode,
            False switches to indirect mode
        """

        if enable_direct_mode:
            self.cmd_call_wrapper.run(['git', 'annex', 'direct'], cwd=self.path)
        else:
            self.cmd_call_wrapper.run(['git', 'annex', 'indirect'], cwd=self.path)
            #TODO: 1. Where to handle failure? 2. On crippled filesystem don't even try.

    def _annex_init(self):
        """Initializes an annex repository.

        Note: This is intended for private use in this class by now.
        If you have an object of this class already, there shouldn't be a need to 'init' again.

        """
        # TODO: provide git and git-annex options.
        # TODO: Document (or implement respectively) behaviour in special cases like direct mode (if it's different),
        # not existing paths, etc.

        status = self.cmd_call_wrapper.run(['git', 'annex', 'init'], cwd=self.path)
        if status not in [0, None]:
            lgr.error('git annex init returned status %d.' % status)


    def annex_get(self, files, **kwargs):
        """Get the actual content of files

        Parameters:
        -----------
        files: list
            list of paths to get

        kwargs: options for the git annex get command. For example `from='myremote'` translates to annex option
            "--from=myremote"
        """

        # Since files is a list of paths, we have to care for escaping special characters, etc.
        # at this point. For now just quote all of them (at least this should handle spaces):
        paths = '"' + '" "'.join(files) + '"'

        options = ''
        for key in kwargs.keys():
            options += " --%s=%s" % (key, kwargs.get(key))
        #TODO: May be this should go in a decorator for use in every command.

        cmd_str = 'git annex get %s %s' % (options, paths)
        # TODO: make it a list instead of a string
        # TODO: Do we want to cd to self.path first? This would lead to expand paths, if
        # cwd is deeper in repo.


        #don't capture stderr, since it provides progress display
        status = self.cmd_call_wrapper.run(cmd_str, log_stderr=False)

        if status not in [0, None]:
            # TODO: Actually this doesn't make sense. Runner raises exception in this case,
            # which leads to: Runner doesn't have to return it at all.
            lgr.error('git annex get returned status: %s' % status)
            raise RuntimeError

    def __too_complicated_traverse_for_content(self,
                             do_empty=None,
                             do_non_empty=None,
                             do_full=None,
                             initial=os.curdir,
                             ):
        """Traverse and perform actions depending on either given tree carries any content

        """
        # Ad-hoc recursive implementation could have been easier/more
        # straightforward but lets try this way the os.walk provides.  There
        # is also os.path.walk with does
        prev_split = None
        prev_level = 0
        def handle_prev():

        for root, dirs, files in os.walk(path):
            root_split = os.path.split(root)
            if prev_split is not None:
                if len(prev_split) < len(root_split):
                    # Went into a child
                    # we visit parent first
                    assert(len(prev_split)+1 == len(root_split))
                    assert(prev_split == root_split[:-1])
                    # we need to collect all the crap there
                    type_ = child_deeper
                elif len(prev_split) == len(root_split):
                    # Must be a directory at the same level
                    assert(prev_split[:-1] == root_split[:-1])
                    type_ = child_same
                else:
                    # Could have went all the way up
                    assert(prev_split[:-1] == root_split[:-1])
                    # and we would need to handle at each level...
                    # COMPLICATED!
            for f in files:
                fullf = opj(root, f)
                # might be the "broken" symlink which would fail to stat etc
                if exists(fullf):
                    chmod(fullf)
        xxx(root)


    def traverse_for_content(path,
                             do_none=None,
                             do_any=None,
                             do_all=None,
                             # TODO: we might want some better function
                             check=has_content
                             ):
        """Traverse and perform actions depending on either given tree carries any content

        Note: do_some is judged at the level of a directory, i.e. children
        directories are assessed only either they are full.

        Returns
        -------
        None if initial == os.curdir, else either the directory is empty (True)
        """
        # Naive recursive implementation, still using os.walk though

        # Get all elements of current directory
        root, dirs, files = os.walk(path).next()
        assert(root == path)

        # TODO: I feel like in some cases we might want to stop descent earlier
        # and not even bother with kids, but I could be wrong
        status_dirs = [
            self.traverse_for_content(do_none=do_none,
                                      do_any=do_any,
                                      do_all=do_all,
                                      initial=os.path.join(root, d),
                                      check=check)
            for d in dirs
        ]

        # TODO: Theoretically we could sophisticate it. E.g. if only do_some
        # or do_none defined and already we have some of status_dirs, no need
        # to verify files. Also if some are not defined in dirs and we have
        # only do_all -- no need to check files.  For now -- KISS

        # Now verify all the files
        status_files = [
            check(os.path.join(root, f))
            for f in files
        ]

        def some(i):
            return any(i) and not all(i)

        status_all = status_dirs + status_files

        # TODO: may be there is a point to pass those files into do_
        # callbacks -- add option  pass_files?
        all_present = all(status_all)
        if all_present:
            if do_all: do_all(root)
        elif any(status_all):
            if do_any: do_any(root)
        else:
            if do_none: do_none(root)

        return all_present


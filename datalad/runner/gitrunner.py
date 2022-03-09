# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Runner for command execution within the context of a Git repo
"""

import logging
import os
import os.path as op

from datalad.dochelpers import borrowdoc
from datalad.utils import generate_file_chunks

from .runner import (
    GeneratorMixIn,
    WitlessRunner,
)


lgr = logging.getLogger('datalad.runner.gitrunner')

# We use custom ssh runner while interacting with git
GIT_SSH_COMMAND = "datalad sshrun"


class GitRunnerBase(object):
    """
    Mix-in class for Runners to be used to run git and git annex commands

    Overloads the runner class to check & update GIT_DIR and
    GIT_WORK_TREE environment variables set to the absolute path
    if is defined and is relative path
    """
    _GIT_PATH = None

    @staticmethod
    def _check_git_path():
        """If using bundled git-annex, we would like to use bundled with it git

        Thus we will store _GIT_PATH a path to git in the same directory as annex
        if found.  If it is empty (but not None), we do nothing
        """
        if GitRunnerBase._GIT_PATH is None:
            from shutil import which

            # with all the nesting of config and this runner, cannot use our
            # cfg here, so will resort to dark magic of environment options
            if (os.environ.get('DATALAD_USE_DEFAULT_GIT', '0').lower()
                    in ('1', 'on', 'true', 'yes')):
                git_fpath = which("git")
                if git_fpath:
                    GitRunnerBase._GIT_PATH = ''
                    lgr.log(9, "Will use default git %s", git_fpath)
                    return  # we are done - there is a default git avail.
                # if not -- we will look for a bundled one
            GitRunnerBase._GIT_PATH = GitRunnerBase._get_bundled_path()
            lgr.log(9, "Will use git under %r (no adjustments to PATH if empty "
                       "string)", GitRunnerBase._GIT_PATH)
            assert(GitRunnerBase._GIT_PATH is not None)  # we made the decision!

    @staticmethod
    def _get_bundled_path():
        from shutil import which
        annex_fpath = which("git-annex")
        if not annex_fpath:
            # not sure how to live further anyways! ;)
            alongside = False
        else:
            annex_path = op.dirname(op.realpath(annex_fpath))
            bundled_git_path = op.join(annex_path, 'git')
            # we only need to consider bundled git if it's actually different
            # from default. (see issue #5030)
            alongside = op.lexists(bundled_git_path) and \
                        bundled_git_path != op.realpath(which('git'))

        return annex_path if alongside else ''

    @staticmethod
    def get_git_environ_adjusted(env=None):
        """
        Replaces GIT_DIR and GIT_WORK_TREE with absolute paths if relative path and defined
        """
        # if env set copy else get os environment
        git_env = env.copy() if env else os.environ.copy()
        if GitRunnerBase._GIT_PATH:
            git_env['PATH'] = op.pathsep.join([GitRunnerBase._GIT_PATH, git_env['PATH']]) \
                if 'PATH' in git_env \
                else GitRunnerBase._GIT_PATH

        for varstring in ['GIT_DIR', 'GIT_WORK_TREE']:
            var = git_env.get(varstring)
            if var:                                    # if env variable set
                if not op.isabs(var):                   # and it's a relative path
                    git_env[varstring] = op.abspath(var)  # to absolute path
                    lgr.log(9, "Updated %s to %s", varstring, git_env[varstring])

        if 'GIT_SSH_COMMAND' not in git_env:
            git_env['GIT_SSH_COMMAND'] = GIT_SSH_COMMAND
            git_env['GIT_SSH_VARIANT'] = 'ssh'
        git_env['GIT_ANNEX_USE_GIT_SSH'] = '1'

        # We are parsing error messages and hints. For those to work more
        # reliably we are doomed to sacrifice i18n effort of git, and enforce
        # consistent language of the messages
        git_env['LC_MESSAGES'] = 'C'
        # But since LC_ALL takes precedence, over LC_MESSAGES, we cannot
        # "leak" that one inside, and are doomed to pop it
        git_env.pop('LC_ALL', None)

        return git_env


class GitWitlessRunner(WitlessRunner, GitRunnerBase):
    """A WitlessRunner for git and git-annex commands.

    See GitRunnerBase it mixes in for more details
    """

    @borrowdoc(WitlessRunner)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._check_git_path()

    def _get_adjusted_env(self, env=None, cwd=None, copy=True):
        env = GitRunnerBase.get_git_environ_adjusted(env=env)
        return super()._get_adjusted_env(
            env=env,
            cwd=cwd,
            # git env above is already a copy, so we have no choice,
            # but we can prevent duplication
            copy=False,
        )

    def _get_chunked_results(self,
                             cmd,
                             files,
                             protocol=None,
                             cwd=None,
                             env=None,
                             **kwargs):

        assert isinstance(cmd, list)

        file_chunks = generate_file_chunks(files, cmd)
        for i, file_chunk in enumerate(file_chunks):
            # do not pollute with message when there only ever is a single chunk
            if len(file_chunk) < len(files):
                lgr.debug(
                    'Process file list chunk %i (length %i)', i, len(file_chunk))

            yield self.run(
                cmd=cmd + ['--'] + file_chunk,
                protocol=protocol,
                cwd=cwd,
                env=env,
                **kwargs)

    def run_on_filelist_chunks(self,
                                cmd,
                                files,
                                protocol=None,
                                cwd=None,
                                env=None,
                                **kwargs):
        """
        Run a git-style command multiple times if `files` is too long,
        using a non-generator protocol, i.e. a protocol that is not
        derived from `datalad.runner.protocol.GeneratorMixIn`.

        Parameters
        ----------
        cmd : list
          Sequence of program arguments.
        files : list
          List of files.
        protocol : WitlessProtocol, optional
          Protocol class handling interaction with the running process
          (e.g. output capture). A number of pre-crafted classes are
          provided (e.g `KillOutput`, `NoCapture`, `GitProgress`).
        cwd : path-like, optional
          If given, commands are executed with this path as PWD,
          the PWD of the parent process is used otherwise. Overrides
          any `cwd` given to the constructor.
        env : dict, optional
          Environment to be used for command execution. If `cwd`
          was given, 'PWD' in the environment is set to its value.
          This must be a complete environment definition, no values
          from the current environment will be inherited. Overrides
          any `env` given to the constructor.
        kwargs :
          Passed to the Protocol class constructor.

        Returns
        -------
        dict
          At minimum there will be keys 'stdout', 'stderr' with
          unicode strings of the cumulative standard output and error
          of the process as values.

        Raises
        ------
        CommandError
          On execution failure (non-zero exit code) this exception is
          raised which provides the command (cmd), stdout, stderr,
          exit code (status), and a message identifying the failed
          command, as properties.
        FileNotFoundError
          When a given executable does not exist.
        """

        assert not issubclass(protocol, GeneratorMixIn), \
            "cannot use GitWitlessRunner.run_on_filelist_chunks() " \
            "with a protocol that inherits GeneratorMixIn, use " \
            "GitWitlessRunner.run_on_filelist_chunks_items_() instead"

        results = None
        for res in self._get_chunked_results(cmd=cmd,
                                             files=files,
                                             protocol=protocol,
                                             cwd=cwd,
                                             env=env,
                                             **kwargs):
            if results is None:
                results = res
            else:
                for k, v in res.items():
                    results[k] += v
        return results

    def run_on_filelist_chunks_items_(self,
                                      cmd,
                                      files,
                                      protocol=None,
                                      cwd=None,
                                      env=None,
                                      **kwargs):
        """
        Run a git-style command multiple times if `files` is too long,
        using a generator protocol, i.e. a protocol that is
        derived from `datalad.runner.protocol.GeneratorMixIn`.

        Parameters
        ----------
        see GitWitlessRunner.run_on_filelist_chunks() for a definition
        of parameters

        Returns
        -------
        Generator that yields output of the cmd
        """

        assert issubclass(protocol, GeneratorMixIn), \
            "cannot use GitWitlessRunner.run_on_filelist_chunks_items_() " \
            "with a protocol that does not inherits GeneratorMixIn, use " \
            "GitWitlessRunner.run_on_filelist_chunks() instead"

        for chunk_generator in self._get_chunked_results(cmd=cmd,
                                                         files=files,
                                                         protocol=protocol,
                                                         cwd=cwd,
                                                         env=env,
                                                         **kwargs):
            yield from chunk_generator

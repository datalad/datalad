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

from os import linesep
from os.path import join as opj, exists, relpath
import logging
import json
import re
import shlex
from subprocess import Popen, PIPE
#import pexpect

from functools import wraps

from six import string_types, PY3
from six.moves.configparser import NoOptionError
from six.moves.urllib.parse import quote as urlquote

from ..utils import auto_repr
from .gitrepo import GitRepo, normalize_path, normalize_paths, GitCommandError
from .exceptions import CommandNotAvailableError, CommandError, \
    FileNotInAnnexError, FileInGitError
from ..utils import on_windows, getpwd

lgr = logging.getLogger('datalad.annex')


def kwargs_to_options(func):
    """Decorator to provide convenient way to pass options to command calls.

    Any keyword argument "foo='bar'" translates to " --foo=bar".
    All of these are collected in a list and then passed to keyword argument
    `options` of the decorated function.

    Note
    ----

    This is meant to especially decorate the methods of AnnexRepo-class and
    therefore returns a class method.
    """

    @wraps(func)
    def newfunc(self, *args, **kwargs):
        option_list = []
        for key in kwargs:
            option_list.extend([" --%s=%s" % (key, kwargs.get(key))])

        return func(self, *args, options=option_list)
    return newfunc

# TODO: Depending on decision about options, implement common annex-options,
# like --force and specific ones for all annex commands


class AnnexRepo(GitRepo):
    """Representation of an git-annex repository.

    Paths given to any of the class methods will be interpreted as relative
    to PWD, in case this is currently beneath AnnexRepo's base dir
    (`self.path`). If PWD is outside of the repository, relative paths
    will be interpreted as relative to `self.path`. Absolute paths will be
    accepted either way.
    """

    __slots__ = GitRepo.__slots__ + ['always_commit', '_batched']

    # TODO: pass description
    def __init__(self, path, url=None, runner=None,
                 direct=False, backend=None, always_commit=True, create=True, init=False):
        """Creates representation of git-annex repository at `path`.

        AnnexRepo is initialized by giving a path to the annex.
        If no annex exists at that location, a new one is created.
        Optionally give url to clone from.

        Parameters
        ----------
        path: str
          path to git-annex repository. In case it's not an absolute path, it's
          relative to PWD

        url: str, optional
          url to the to-be-cloned repository. Requires valid git url
          according to
          http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS .

        runner: Runner, optional
          Provide a Runner in case AnnexRepo shall not create it's own.
          This is especially needed in case of desired dry runs.

        direct: bool, optional
          If True, force git-annex to use direct mode

        backend: str, optional
          Set default backend used by this annex. This does NOT affect files,
          that are already annexed nor will it automatically migrate files,
          hat are 'getted' afterwards.

        create: bool, optional
          Create and initializes an annex repository at path, in case
          there is none. If set to False, and this repository is not an annex
          repository (initialized or not), an exception is raised.

        init: bool, optional
          Initialize git-annex repository (run "git annex init") if path is an
          annex repository which just was not yet initialized by annex (e.g. a
          fresh git clone). Note that if `create=True`, then initialization
          would happen
        """
        fix_it = False
        try:
            super(AnnexRepo, self).__init__(path, url, runner=runner,
                                            create=create)
        except GitCommandError as e:
            if create and "Clone succeeded, but checkout failed." in str(e):
                lgr.warning("Experienced issues while cloning. "
                            "Trying to fix it, using git-annex-fsck.")
                fix_it = True
            else:
                raise e

        self.always_commit = always_commit
        if fix_it:
            self._annex_init()
            self.annex_fsck()

        # Check whether an annex already exists at destination
        if not exists(opj(self.path, '.git', 'annex')):
            # so either it is not annex at all or just was not yet initialized
            if any((b.endswith('/git-annex') for b in self.git_get_remote_branches())):
                # it is an annex repository which was not initialized yet
                if create or init:
                    lgr.debug('Annex repository was not yet initialized at %s.'
                              ' Initializing ...' % self.path)
                    self._annex_init()
            elif create:
                lgr.debug('Initializing annex repository at %s...' % self.path)
                self._annex_init()
            else:
                raise RuntimeError("No annex found at %s." % self.path)

        # only force direct mode; don't force indirect mode
        if direct and not self.is_direct_mode():
            self.set_direct_mode()

        # set default backend for future annex commands:
        # TODO: Should the backend option of __init__() also migrate
        # the annex, in case there are annexed files already?
        if backend:
            lgr.debug("Setting annex backend to %s", backend)
            # Must be done with explicit release, otherwise on Python3 would end up
            # with .git/config wiped out
            # see https://github.com/gitpython-developers/GitPython/issues/333#issuecomment-126633757
            writer = self.repo.config_writer()
            writer.set_value("annex", "backends", backend)
            writer.release()

        self._batched = BatchedAnnexes()

    def __repr__(self):
        return "<AnnexRepo path=%s (%s)>" % (self.path, type(self))

    def _run_annex_command(self, annex_cmd, git_options=None, annex_options=None,
                           backend=None, **kwargs):
        """Helper to run actual git-annex calls

        Unifies annex command calls.

        Parameters
        ----------
        annex_cmd: str
            the actual git-annex command, like 'init' or 'add'
        git_options: list of str
            options to be passed to git
        annex_options: list of str
            options to be passed to the git-annex command
        backend: str
            backend to be used by this command; Currently this can also be
            achieved by having an item '--backend=XXX' in annex_options.
            This may change.
        **kwargs
            these are passed as additional kwargs to datalad.cmd.Runner.run()

        Raises
        ------
        CommandNotAvailableError
            if an annex command call returns "unknown command"
        """

        debug = ['--debug'] if lgr.getEffectiveLevel() <= logging.DEBUG else []
        backend = ['--backend=%s' % backend] if backend else []

        git_options = (git_options[:] if git_options else []) + self._GIT_COMMON_OPTIONS
        annex_options = annex_options[:] if annex_options else []

        if not self.always_commit:
            git_options += ['-c', 'annex.alwayscommit=false']

        if git_options:
            cmd_list = ['git'] + git_options + ['annex']
        else:
            cmd_list = ['git-annex']
        cmd_list += [annex_cmd] + backend + debug + annex_options

        try:
            return self.cmd_call_wrapper.run(cmd_list, **kwargs)
        except CommandError as e:
            if "git-annex: Unknown command '%s'" % annex_cmd in e.stderr:
                raise CommandNotAvailableError(str(cmd_list),
                                               "Unknown command:"
                                               " 'git-annex %s'" % annex_cmd,
                                               e.code, e.stdout, e.stderr)
            else:
                raise e

    def is_direct_mode(self):
        """Indicates whether or not annex is in direct mode

        Returns
        -------
        True if in direct mode, False otherwise.
        """

        try:
            return self.repo.config_reader().get_value("annex", "direct")
        except NoOptionError as e:
            # If .git/config lacks an entry "direct",
            # it's actually indirect mode.
            return False

    def is_crippled_fs(self):
        """Indicates whether or not git-annex considers current filesystem 'crippled'.

        Returns
        -------
        True if on crippled filesystem, False otherwise
        """

        try:
            return self.repo.config_reader().get_value("annex",
                                                       "crippledfilesystem")
        except NoOptionError as e:
            # If .git/config lacks an entry "crippledfilesystem",
            # it's actually not crippled.
            return False

    def set_direct_mode(self, enable_direct_mode=True):
        """Switch to direct or indirect mode

        Parameters
        ----------
        enable_direct_mode: bool
            True means switch to direct mode,
            False switches to indirect mode

        Raises
        ------
        CommandNotAvailableError
            in case you try to switch to indirect mode on a crippled filesystem
        """
        if self.is_crippled_fs() and not enable_direct_mode:
            raise CommandNotAvailableError(
                cmd="git-annex indirect",
                msg="Can't switch to indirect mode on that filesystem.")

        self._run_annex_command('direct' if enable_direct_mode else 'indirect',
                                expect_stderr=True)

    def _annex_init(self):
        """Initializes an annex repository.

        Note: This is intended for private use in this class by now.
        If you have an object of this class already,
        there shouldn't be a need to 'init' again.

        """
        # TODO: provide git and git-annex options.
        # TODO: Document (or implement respectively) behaviour in special cases
        # like direct mode (if it's different), not existing paths, etc.

        self._run_annex_command('init')
        # TODO: When to expect stderr?
        # on crippled filesystem for example (think so)?

    @normalize_paths
    def annex_get(self, files, options=None):
        """Get the actual content of files

        Parameters
        ----------
        files: list of str
            list of paths to get

        kwargs: options for the git annex get command.
            For example `from='myremote'` translates to
            annex option "--from=myremote".
        """
        options = options[:] if options else []

        # don't capture stderr, since it provides progress display
        self._run_annex_command('get', annex_options=options + files,
                                log_stdout=True, log_stderr=False,
                                log_online=True, expect_stderr=True)

    # TODO: Moved from HandleRepo. Just a temporary alias.
    # When renaming is done, melt with annex_get
    def get(self, files):
        """get the actual content of files

        This command gets the actual content of the files in `list`.
        """
        self.annex_get(files)

    @normalize_paths
    def annex_add(self, files, backend=None, options=None):
        """Add file(s) to the annex.

        Parameters
        ----------
        files: list of str
            list of paths to add to the annex
        """
        options = options[:] if options else []

        self._run_annex_command('add', annex_options=options + files,
                                backend=backend)

    def annex_proxy(self, git_cmd, **kwargs):
        """Use git-annex as a proxy to git

        This is needed in case we are in direct mode, since there's no git
        working tree, that git can handle.

        Parameters
        ----------
        git_cmd: str
            the actual git command
        **kwargs: dict, optional
            passed to _run_annex_command

        Returns
        -------
        (stdout, stderr)
            output of the command call
        """

        cmd_str = "git annex proxy -- %s" % git_cmd
        # TODO: By now git_cmd is expected to be string.
        # Figure out how to deal with a list here. Especially where and how to
        # treat paths.

        if not self.is_direct_mode():
            lgr.warning("annex_proxy() called in indirect mode: %s" % cmd_str)
            raise CommandNotAvailableError(cmd=cmd_str,
                                           msg="Proxy doesn't make sense"
                                               " if not in direct mode.")
        # Temporarily use shlex, until calls use lists for git_cmd
        return self._run_annex_command('proxy',
                                       annex_options=['--'] +
                                                     shlex.split(
                                                         git_cmd,
                                                         posix=not on_windows),
                                       **kwargs)

    @normalize_path
    def get_file_key(self, file_):
        """Get key of an annexed file.

        Parameters
        ----------
        file_: str
            file to look up

        Returns
        -------
        str
            keys used by git-annex for each of the files
        """

        cmd_str = 'git annex lookupkey %s' % file_  # have a string for messages

        try:
            out, err = self._run_annex_command('lookupkey',
                                               annex_options=[file_],
                                               expect_fail=True)
        except CommandError as e:
            if e.code == 1:
                if not exists(opj(self.path, file_)):
                    raise IOError(e.code, "File not found.", file_)
                elif file_ in self.get_indexed_files():
                    # if we got here, the file is present and in git,
                    # but not in the annex
                    raise FileInGitError(cmd=cmd_str,
                                         msg="File not in annex, but git: %s"
                                             % file_,
                                         filename=file_)
                else:
                    raise FileNotInAnnexError(cmd=cmd_str,
                                              msg="File not in annex: %s"
                                                  % file_,
                                              filename=file_)
            else:
                # Not sure, whether or not this can actually happen
                raise e

        return out.rstrip(linesep).splitlines()[0]

    @normalize_paths
    def file_has_content(self, files):
        """ Check whether files have their content present under annex.

        Parameters
        ----------
        files: list of str
            file(s) to check for being actually present.

        Returns
        -------
        list of bool
            Per each input file states either file has content locally
        """
        # TODO: Also provide option to look for key instead of path

        try:
            out, err = self._run_annex_command('find', annex_options=files,
                                               expect_fail=True)
        except CommandError as e:
            if e.code == 1 and "not found" in e.stderr:
                if len(files) > 1:
                    lgr.debug("One of the files was not found, so performing "
                              "'find' operation per each file")
                    # we need to go file by file since one of them is non
                    # existent and annex pukes on it
                    return [self.file_has_content(file_) for file_ in files]
                return [False]
            else:
                raise

        found_files = {f for f in out.splitlines() if f}
        found_files_new = set(found_files) - set(files)
        if found_files_new:
            raise RuntimeError("'annex find' returned entries for files which "
                               "we did not expect: %s" % (found_files_new,))

        return [file_ in found_files for file_ in files]

    @normalize_paths
    def annex_add_to_git(self, files):
        # TODO: This may be should simply override GitRepo.git_add
        """Add file(s) directly to git

        Parameters
        ----------
        files: list of str
            list of paths to add to git
        """

        if self.is_direct_mode():
            cmd_list = ['git', '-c', 'core.bare=false', 'add'] + files
            self.cmd_call_wrapper.run(cmd_list, expect_stderr=True)
            # TODO: use options with git_add instead!
        else:
            self.git_add(files)

    # TODO: Just moved from HandleRepo. Melt with annex_add_to_git and rename.
    @normalize_paths
    def add_to_git(self, files, commit_msg="Added file(s) to git."):
        """Add file(s) directly to git

        Adds files directly to git and commits.

        Parameters
        ----------
        commit_msg: str
            commit message
        files: list
            list of paths to add to git; Can also be a str, in case of a single
            path.
        """
        self.annex_add_to_git(files)
        self.commit(commit_msg)

    @normalize_paths
    def add_to_annex(self, files, commit_msg="Added file(s) to annex."):
        """Add file(s) to the annex.

        Adds files to the annex and commits.

        Parameters
        ----------
        commit_msg: str
            commit message
        files: list
            list of paths to add to the annex; Can also be a str, in case of a
            single path.
        """

        self.annex_add(files)
        self.commit(commit_msg)


    def annex_initremote(self, name, options):
        """Creates a new special remote

        Parameters
        ----------
        name: str
            name of the special remote
        """
        # TODO: figure out consistent way for passing options + document

        self._run_annex_command('initremote', annex_options=[name] + options)

    def annex_enableremote(self, name):
        """Enables use of an existing special remote

        Parameters
        ----------
        name: str
            name, the special remote was created with
        """

        self._run_annex_command('enableremote', annex_options=[name])

    @normalize_path
    def annex_addurl_to_file(self, file_, url, options=None, backend=None, batch=False):
        """Add file from url to the annex.

        Downloads `file` from `url` and add it to the annex.
        If annex knows `file` already,
        records that it can be downloaded from `url`.

        Parameters
        ----------
        file_: str

        url: str

        options: list
            options to the annex command
        """
        options = options[:] if options else []
        #if file_ == 'about.txt':
        #    import pdb; pdb.set_trace()
        kwargs = dict(backend=backend)
        if not batch:
            self._run_annex_command('addurl',
                                    annex_options=options + ['--file=%s' % file_] + [url],
                                    log_online=True, log_stderr=False,
                                    **kwargs)
            # Don't capture stderr, since download progress provided by wget uses
            # stderr.
        else:
            if backend:
                options += ['--backend=%s' % backend]
            # Initializes (if necessary) and obtains the batch process
            out = self._batched.get(
                # Since backend will be critical for non-existing files
                'addurl_to_file_backend:%s' % backend,
                annex_cmd='addurl',
                annex_options=['--with-files'] + options,  # --raw ?
                path=self.path,
                output_proc=readlines_until_ok_or_failed
            )((url, file_))
            if not out.endswith('ok'):
                raise ValueError("Error, output from annex was %s, whenever we expected it to end with ' ok'"
                                 % out)
            # due to annex needing closing its pipe to actually add addurl'ed file
            # to index, we will do it manually here for now
            # see
            # http://git-annex.branchable.com/bugs/addurl_--batch__--with-files_doesn__39__t_add_file_into_git_until_pipe_is_closed/

            # no normalization since we are dealing with normalized paths already
            # and might reside within repo's subdir
            self.git_add(file_, normalize_paths=False)


    def annex_addurls(self, urls, options=None, backend=None, cwd=None):
        """Downloads each url to its own file, which is added to the annex.

        Parameters
        ----------
        urls: list

        options: list, optional
            options to the annex command

        cwd: string, optional
            working directory from within which to invoke git-annex
        """
        options = options[:] if options else []

        self._run_annex_command('addurl', annex_options=options + urls,
                                backend=backend, log_online=True,
                                log_stderr=False, cwd=cwd)
        # Don't capture stderr, since download progress provided by wget uses
        # stderr.

    @normalize_path
    def annex_rmurl(self, file_, url):
        """Record that the file is no longer available at the url.

        Parameters
        ----------
        file_: str

        url: str
        """

        self._run_annex_command('rmurl', annex_options=[file_] + [url])

    @normalize_paths
    def annex_drop(self, files, options=None):
        """Drops the content of annexed files from this repository.

        Drops only if possible with respect to required minimal number of
        available copies.

        Parameters
        ----------
        files: list of str
        """
        options = options[:] if options else []

        self._run_annex_command('drop', annex_options=options + files)


    # TODO: a dedicated unit-test
    def _whereis_json_to_dict(self, j):
        """Convert json record returned by annex whereis --json to our dict representation for it
        """
        assert (j.get('success', True) is True)
        # process 'whereis' containing list of remotes
        remotes = {remote['description']: {'here': remote['here'], 'uuid': remote['uuid']}
                   for remote in j.get('whereis')}
        if 'web' in remotes:
            # will be replaced with a list of urls
            remotes['web']['urls'] = []
        # process 'note' which would contain urls for 'web' remote
        note = j.get('note', '')
        if note:
            for note_record in filter(bool, note.split('\n')):
                # format remote: url ?
                note_split = note_record.split(':', 1)
                if len(note_split) != 2:
                    lgr.debug("Skipping note record %r for file %s", note_record, j['file'])
                    continue
                remote, url = map(lambda x: x.strip(), note_split)
                if remote not in remotes:
                    lgr.warning("Remote %r not found among remotes %s. Skipping", remote, remotes.keys())
                assert remote == 'web', "ATM can understand only notes for web remote"
                remotes['web']['urls'].append(url)
        return remotes


    def _run_annex_command_json(self, command, args=[]):
        """Run an annex command with --json and load output results into a tuple of dicts
        """
        try:
            # TODO: refactor to account for possible --batch ones
            out, err = self._run_annex_command(
                    command,
                    annex_options=['--json'] + args)
        except CommandError as e:
            # if multiple files, whereis may technically fail,
            # but still returns correct response
            if command == 'whereis' and e.code == 1 and e.stdout.startswith('{'):
                out = e.stdout
            else:
                raise e
        json_objects = (json.loads(line)
                        for line in out.splitlines() if line.startswith('{'))
        return json_objects


    # TODO: reconsider having any magic at all and maybe just return a list/dict always
    @normalize_paths
    def annex_whereis(self, files, output='remotes'):
        """Lists repositories that have actual content of file(s).

        Parameters
        ----------
        files: list of str
            files to look for
        output: {'remotes', 'full'}, optional
            If 'remotes', a list of remotes returned per each file. If full,
            per each file a dictionary returned with "web" also containing
            'urls' list with all the urls for that file

        Returns
        -------
        list of list of unicode  or dict
            if output == 'remotes', contains a list of descriptions per
            each input file, describing the remote for each remote, which
            was found by git-annex whereis, like:

            u'me@mycomputer:~/where/my/repo/is [origin]' or
            u'web' or
            u'me@mycomputer:~/some/other/clone'

            if output == 'full', returns a dictionary with filenames as keys
            and values a detailed record, e.g.

                {'web': {
                  'uuid': '00000000-0000-0000-0000-000000000001',
                  'here': False,
                  'urls': ['http://127.0.0.1:43442/about.txt', 'http://example.com/someurl']
                }}
        """

        json_objects = self._run_annex_command_json('whereis', args=files)

        if output == 'remotes':
            return [
                [remote.get('description') for remote in j.get('whereis')]
                if j.get('success') else []
                for j in json_objects]
        elif output == 'full':
            # TODO: we might want to optimize storage since many remotes entries will be the
            # same so we could just reuse them instead of brewing copies
            return {j['file']: self._whereis_json_to_dict(j)
                    for j in json_objects}
        else:
            raise ValueError("Unknown value output=%r. Known are remotes and full" % output)

    # TODO:
    #  I think we should make interface cleaner and less ambigious for those annex
    #  commands which could operate on globs, files, and entire repositories, separating
    #  those out, e.g. annex_info_repo, annex_info_files at least.
    #  If we make our calling wrappers work without relying on invoking from repo topdir,
    #  then returned filenames would not need to be mapped, so we could easily work on dirs
    #  and globs.
    # OR if explicit filenames list - return list of matching entries, if globs/dirs -- return dict?
    @normalize_paths(map_filenames_back=True)
    def annex_info(self, files):
        """Provide annex info for file(s).

        Parameters
        ----------
        files: list of str
            files to look for

        Returns
        -------
        dict
          Info per each file
        """

        json_objects = self._run_annex_command_json('info', args=['--bytes'] + files)

        # Some aggressive checks. ATM info can be requested only per file
        # json_objects is a generator, let's keep it that way
        # assert(len(json_objects) == len(files))
        # and that they all have 'file' equal to the passed one
        out = {}
        for j, f in zip(json_objects, files):
            assert(j['file'] == f)
            assert(j.pop('success') == True)
            # convert size to int
            j['size'] = int(j['size']) if 'unknown' not in j['size'] else None
            # and pop the "command" field
            j.pop("command")
            out[j.pop("file")] = j
        return out

    def get_annexed_files(self):
        """Get a list of files in annex
        """
        # TODO: Review!

        out, err = self._run_annex_command('find')
        return out.splitlines()

    # TODO: oh -- API for this better gets RFed sooner than later!
    #       by overloading commit in GitRepo
    def commit(self, msg):
        """

        Parameters
        ----------
        msg: str
        """
        if self.is_direct_mode():
            self.annex_proxy('git commit -m "%s"' % msg)
        else:
            self.git_commit(msg)

    def get_contentlocation(self, key):
        """Get location of the key content

        Normally under .git/annex objects in indirect mode and within file
        tree in direct mode.

        Unfortunately there is no (easy) way to discriminate situations
        when given key is simply incorrect (not known to annex) or its content
        not currently present -- in both cases annex just silently exits with -1


        Parameters
        ----------
        key: str
            key

        Returns
        -------
        str
            path relative to the top directory of the repository
        """

        # TODO: batchable

        cmd_str = 'git annex contentlocation %s' % key  # have a string for messages

        out, err = self._run_annex_command('contentlocation',
                                           annex_options=[key],
                                           expect_fail=True)
        path = out.rstrip(linesep).splitlines()[0]
        return path


# TODO: ---------------------------------------------------------------------
    @normalize_paths(match_return_type=False)
    def _annex_custom_command(self, files, cmd_str,
                           log_stdout=True, log_stderr=True, log_online=False,
                           expect_stderr=False, cwd=None, env=None,
                           shell=None):
        """Allows for calling arbitrary commands.

        Helper for developing purposes, i.e. to quickly implement git-annex
        commands for proof of concept.

        Parameters
        ----------
        files: list of files
        cmd_str: str
            arbitrary command str. `files` is appended to that string.

        Returns
        -------
        stdout, stderr
        """
        cmd = shlex.split(cmd_str + " " + " ".join(files), posix=not on_windows) \
            if isinstance(cmd_str, string_types) \
            else cmd_str + files
        return self.cmd_call_wrapper.run(cmd, log_stderr=log_stderr,
                                  log_stdout=log_stdout, log_online=log_online,
                                  expect_stderr=expect_stderr, cwd=cwd,
                                  env=env, shell=shell)


    @normalize_paths
    def migrate_backend(self, files, backend=None):
        """Changes the backend used for `file`.

        The backend used for the key-value of `files`. Only files currently
        present are migrated.
        Note: There will be no notification if migrating fails due to the
        absence of a file's content!

        Parameters
        ----------
        files: list
            files to migrate.
        backend: str
            specify the backend to migrate to. If none is given, the
            default backend of this instance will be used.
        """

        if self.is_direct_mode():
            raise CommandNotAvailableError(
                'git-annex migrate',
                "Command 'migrate' is not available in direct mode.")
        self._run_annex_command('migrate',
                                annex_options=files,
                                backend=backend)

    @normalize_paths
    def get_file_backend(self, files):
        """Get the backend currently used for file(s).

        Parameters
        ----------
        files: list of str

        Returns
        -------
        list of str
            Per each file in input list indicates the used backend by a str
            like "SHA256E" or "MD5".
        """

        return [self.get_file_key(f).split('-')[0] for f in files]

    def annex_fsck(self):
        self._run_annex_command('fsck')


#@auto_repr
class BatchedAnnexes(dict):
    """Class to contain the registry of active batch'ed instances of annex for a repository
    """
#    def __init__(self):
#        self.processes = {}  # codename -> process

    def get(self, codename, annex_cmd=None, **kwargs):
        if annex_cmd is None:
            annex_cmd = codename

        if codename not in self:
            # Create a new git-annex process we will keep around
            self[codename] = BatchedAnnex(annex_cmd, **kwargs)
        return self[codename]


def readline_rstripped(stdout):
    return stdout.readline().rstrip()


def readlines_until_ok_or_failed(stdout):
    """Read stdout until line ends with ok or failed"""
    out = ''
    lgr.log(3, "Trying to receive from %s" % stdout)
    while not stdout.closed:
        lgr.log(1, "Expecting a line")
        line = stdout.readline()
        lgr.log(1, "Received line %r" % line)
        out += line
        if re.match(r'^.*\b(failed|ok)$', line.rstrip()):
            break
    return out.rstrip()


@auto_repr
class BatchedAnnex(object):
    """Container for an annex process which would allow for persistent communication
    """

    def __init__(self, annex_cmd, annex_options=[], path=None,
                 output_proc=readline_rstripped):
        self.annex_cmd = annex_cmd
        self.annex_options = annex_options
        self.path = path
        self.output_proc = output_proc
        self._process = None

    def _initialize(self):
        lgr.debug("Initiating a new process for %s" % repr(self))
        cmd = ['git'] + AnnexRepo._GIT_COMMON_OPTIONS + \
              ['annex', self.annex_cmd] + self.annex_options + ['--batch'] # , '--debug']
        lgr.log(5, "Command: %s" % cmd)
        # TODO: look into _run_annex_command  to support default options such as --debug
        #
        # according to the internet wisdom there is no easy way with subprocess
        # while avoid deadlocks etc.  We would need to start a thread/subprocess
        # to timeout etc
        # kwargs = dict(bufsize=1, universal_newlines=True) if PY3 else {}
        self._process = Popen(cmd, stdin=PIPE, stdout=PIPE
                              # , stderr=PIPE
                              , cwd=self.path
                              , bufsize=1, universal_newlines=True #**kwargs
                              )

    def __call__(self, input_):
        """

        Parameters
        ----------
        input_ : str or tuple or list of (str or tuple)
        output_proc : callable
          To provide handling

        Returns
        -------
        str or list
          Output received from annex.  list in case if input_ was a list
        """
        # TODO: add checks -- may be process died off and needs to be reinitiated
        if not self._process:
            self._initialize()

        input_multiple = isinstance(input_, list)
        if not input_multiple:
            input_ = [input_]

        output = []
        process = self._process
        for entry in input_:
            if not isinstance(entry, string_types):
                entry = ' '.join(entry)
            entry = entry + '\n'
            lgr.log(5, "Sending %r to batched annex %s" % (entry, self))
            # apparently communicate is just a one time show
            # stdout, stderr = self._process.communicate(entry)
            # according to the internet wisdom there is no easy way with subprocess
            process.stdin.write(entry)#.encode())
            lgr.log(5, "Done sending.")
            # TODO: somehow do catch stderr which might be there or not
            #stderr = str(process.stderr) if process.stderr.closed else None
            if process.returncode:
                lgr.warning("Process %s for %s returned %s" % (process, self, process.returncode))
            # We are expecting a single line output
            # TODO: timeouts etc
            stdout = self.output_proc(process.stdout) if not process.stdout.closed else None
            #if stderr:
            #    lgr.warning("Received output in stderr: %r" % stderr)
            lgr.log(5, "Received output: %r" % stdout)
            output.append(stdout)

        return output if input_multiple else output[0]

    def __del__(self):
        if self._process:
            process = self._process
            lgr.debug("Closing stdin of %s and waiting process to finish" % process)
            process.stdin.close()
            process.wait()
            self._process = None
"""Amendment of the DataLad `GitRepo` base class"""
__docformat__ = 'restructuredtext'


import os
import os.path as op
from collections import OrderedDict
import logging
import re
from six import (
    iteritems,
    PY2,
)
from weakref import WeakValueDictionary

from datalad.utils import assure_list

from datalad.dochelpers import exc_str
from . import utils as ut
from datalad.support.gitrepo import (
    GitRepo,
    InvalidGitRepositoryError,
    to_options,
)
from datalad.support.exceptions import CommandError
from datalad.interface.results import get_status_dict

lgr = logging.getLogger('datalad.revolution.gitrepo')

obsolete_methods = (
    'is_dirty',
)


class RevolutionGitRepo(GitRepo):

    # Begin Flyweight:
    _unique_instances = WeakValueDictionary()
    # End Flyweight:

    def __init__(self, *args, **kwargs):
        super(RevolutionGitRepo, self).__init__(*args, **kwargs)
        # the sole purpose of this init is to add a pathlib
        # native path object to the instance
        # XXX this relies on the assumption that self.path as managed
        # by the base class is always a native path
        self.pathobj = ut.Path(self.path)

    def _create_empty_repo(self, path, **kwargs):
        cmd = ['git', 'init']
        cmd.extend(kwargs.pop('_from_cmdline_', []))
        cmd.extend(to_options(**kwargs))
        lgr.debug(
            "Initialize empty Git repository at '%s'%s",
            path,
            ' %s' % cmd[2:] if cmd[2:] else '')
        if not op.exists(path):
            os.makedirs(path)
        try:
            stdout, stderr = self._git_custom_command(
                None,
                cmd,
                cwd=path,
                log_stderr=True,
                log_stdout=True,
                log_online=False,
                expect_stderr=False,
                shell=False,
                # we don't want it to scream on stdout
                expect_fail=True)
        except CommandError as exc:
            lgr.error(exc_str(exc))
            raise
        # we want to return None and have lazy eval take care of
        # the rest
        return

    def get_content_info(self, paths=None, ref=None, untracked='all'):
        """Get identifier and type information from repository content.

        This is simplified front-end for `git ls-files/tree`.

        Both commands differ in their behavior when queried about subdataset
        paths. ls-files will not report anything, ls-tree will report on the
        subdataset record. This function uniformly follows the behavior of
        ls-tree (report on the respective subdataset mount).

        Parameters
        ----------
        paths : list(patlib.PurePath)
          Specific paths, relative to the (resolved repository root, to query
          info for. Paths must be normed to match the reporting done by Git,
          i.e. no parent dir components (ala "some/../this").
          If none are given, info is reported for all content.
        ref : gitref or None
          If given, content information is retrieved for this Git reference
          (via ls-tree), otherwise content information is produced for the
          present work tree (via ls-files).
        untracked : {'no', 'normal', 'all'}
          If and how untracked content is reported when no `ref` was given:
          'no': no untracked files are reported; 'normal': untracked files
          and entire untracked directories are reported as such; 'all': report
          individual files even in fully untracked directories.

        Returns
        -------
        dict
          Each content item has an entry under its relative path within
          the repository. Each value is a dictionary with properties:

          `type`
            Can be 'file', 'symlink', 'dataset', 'directory'

            Note that the reported type will not always match the type of
            content commited to Git, rather it will reflect the nature
            of the content minus platform/mode-specifics. For example,
            a symlink to a locked annexed file on Unix will have a type
            'file', reported, while a symlink to a file in Git or directory
            will be of type 'symlink'.

          `gitshasum`
            SHASUM of the item as tracked by Git, or None, if not
            tracked. This could be different from the SHASUM of the file
            in the worktree, if it was modified.

        Raises
        ------
        ValueError
          In case of an invalid Git reference (e.g. 'HEAD' in an empty
          repository)
        """
        # TODO limit by file type to replace code in subdatasets command
        info = OrderedDict()

        mode_type_map = {
            '100644': 'file',
            '100755': 'file',
            '120000': 'symlink',
            '160000': 'dataset',
        }
        if paths:
            # path matching will happen against what Git reports
            # and Git always reports POSIX paths
            # any incoming path has to be relative already, so we can simply
            # convert unconditionally
            paths = [ut.PurePosixPath(p) for p in paths]

        # this will not work in direct mode, but everything else should be
        # just fine
        if not ref:
            # --exclude-standard will make sure to honor and standard way
            # git can be instructed to ignore content, and will prevent
            # crap from contaminating untracked file reports
            cmd = ['git', 'ls-files',
                   '--stage', '-z', '-d', '-m', '--exclude-standard']
            # untracked report mode, using labels from `git diff` option style
            if untracked == 'all':
                cmd.append('-o')
            elif untracked == 'normal':
                cmd += ['-o', '--directory']
            elif untracked == 'no':
                pass
            else:
                raise ValueError(
                    'unknown value for `untracked`: %s', untracked)
        else:
            cmd = ['git', 'ls-tree', ref, '-z', '-r', '--full-tree']
        # works for both modes
        props_re = re.compile(r'([0-9]+) (.*) (.*)\t(.*)$')

        try:
            stdout, stderr = self._git_custom_command(
                # specifically always ask for a full report and
                # filter out matching path later on to
                # homogenize wrt subdataset content paths across
                # ls-files and ls-tree
                None,
                cmd,
                log_stderr=True,
                log_stdout=True,
                # not sure why exactly, but log_online has to be false!
                log_online=False,
                expect_stderr=False,
                shell=False,
                # we don't want it to scream on stdout
                expect_fail=True)
        except CommandError as exc:
            if "fatal: Not a valid object name" in str(exc):
                raise ValueError("Git reference '{}' invalid".format(ref))
            raise

        for line in stdout.split('\0'):
            if not line:
                continue
            inf = {}
            props = props_re.match(line)
            if not props:
                # not known to Git, but Git always reports POSIX
                path = ut.PurePosixPath(line)
                inf['gitshasum'] = None
            else:
                # again Git reports always in POSIX
                path = ut.PurePosixPath(props.group(4))
                inf['gitshasum'] = props.group(2 if not ref else 3)
                inf['type'] = mode_type_map.get(
                    props.group(1), props.group(1))
                if inf['type'] == 'symlink' and \
                        '.git/annex/objects' in \
                        ut.Path(
                            op.realpath(op.join(
                                # this is unicode
                                self.path,
                                # this has to become unicode on older Pythons
                                # it doesn't only look ugly, it is ugly
                                # and probably wrong
                                unicode(str(path), 'utf-8')
                                if PY2 else str(path)))).as_posix():
                    # ugly thing above could be just
                    #  (self.pathobj / path).resolve().as_posix()
                    # but PY3.5 does not support resolve(strict=False)

                    # report locked annexed files as file, their
                    # symlink-nature is a technicality that is dependent
                    # on the particular mode annex is in
                    inf['type'] = 'file'

            # the function assumes that any `path` is a relative path lib
            # instance if there were path constraints given, we need to reject
            # paths now
            # reject anything that is:
            # - not a direct match with a constraint
            # - has no constraint as a parent
            #   (relevant to find matches of regular files in a repository)
            # - is not a parent of a constraint
            #   (relevant for finding the matching subds entry for
            #    subds-content paths)
            if paths \
                and not any(
                    path == c or path in c.parents or c in path.parents
                    for c in paths):
                continue

            # join item path with repo path to get a universally useful
            # path representation with auto-conversion and tons of other
            # stuff
            path = self.pathobj.joinpath(path)
            if 'type' not in inf:
                # be nice and assign types for untracked content
                inf['type'] = 'symlink' if path.is_symlink() \
                    else 'directory' if path.is_dir() else 'file'
            info[path] = inf

        return info

    def status(self, paths=None, untracked='all', ignore_submodules='no'):
        """Simplified `git status` equivalent.

        Parameters
        ----------
        paths : list or None
          If given, limits the query to the specified paths. To query all
          paths specify `None`, not an empty list. If a query path points
          into a subdataset, a report is made on the subdataset record
          within the queried dataset only (no recursion).
        untracked : {'no', 'normal', 'all'}
          If and how untracked content is reported when no `ref` was given:
          'no': no untracked files are reported; 'normal': untracked files
          and entire untracked directories are reported as such; 'all': report
          individual files even in fully untracked directories.
        ignore_submodules : {'no', 'other', 'all'}

        Returns
        -------
        dict
          Each content item has an entry under its relative path within
          the repository. Each value is a dictionary with properties:

          `type`
            Can be 'file', 'symlink', 'dataset', 'directory'
          `state`
            Can be 'added', 'untracked', 'clean', 'deleted', 'modified'.
        """
        lgr.debug('Query status of %r for %s paths',
                  self, len(paths) if paths else 'all')
        return self.diffstatus(
            fr='HEAD' if self.get_hexsha() else None,
            to=None,
            paths=paths,
            untracked=untracked,
            ignore_submodules=ignore_submodules)

    def diff(self, fr, to, paths=None, untracked='all',
             ignore_submodules='no'):
        """Like status(), but reports changes between to arbitrary revisions

        Parameters
        ----------
        fr : str
          Revision specification (anything that Git understands). Passing
          `None` considers anything in the target state as new.
        to : str or None
          Revision specification (anything that Git understands), or None
          to compare to the state of the work tree.
        paths : list or None
          If given, limits the query to the specified paths. To query all
          paths specify `None`, not an empty list.
        untracked : {'no', 'normal', 'all'}
          If and how untracked content is reported when no `ref` was given:
          'no': no untracked files are reported; 'normal': untracked files
          and entire untracked directories are reported as such; 'all': report
          individual files even in fully untracked directories.
        ignore_submodules : {'no', 'other', 'all'}

        Returns
        -------
        dict
          Each content item has an entry under its relative path within
          the repository. Each value is a dictionary with properties:

          `type`
            Can be 'file', 'symlink', 'dataset', 'directory'
          `state`
            Can be 'added', 'untracked', 'clean', 'deleted', 'modified'.
        """
        return {k: v for k, v in iteritems(self.diffstatus(
            fr=fr, to=to, paths=paths,
            untracked=untracked,
            ignore_submodules=ignore_submodules))
            if v.get('state', None) != 'clean'}

    def diffstatus(self, fr, to, paths=None, untracked='all',
                   ignore_submodules='no', _cache=None):
        """Like diff(), but reports the status of 'clean' content too"""
        def _get_cache_key(label, paths, ref, untracked=None):
            return self.path, label, tuple(paths) if paths else None, \
                ref, untracked

        if _cache is None:
            _cache = {}

        if paths:
            # at this point we must normalize paths to the form that
            # Git would report them, to easy matching later on
            paths = [ut.Path(p) for p in paths]
            paths = [
                p.relative_to(self.pathobj) if p.is_absolute() else p
                for p in paths
            ]

        # TODO report more info from get_content_info() calls in return
        # value, those are cheap and possibly useful to a consumer
        status = OrderedDict()
        # we need (at most) three calls to git
        if to is None:
            # everything we know about the worktree, including os.stat
            # for each file
            key = _get_cache_key('ci', paths, None, untracked)
            if key in _cache:
                to_state = _cache[key]
            else:
                to_state = self.get_content_info(
                    paths=paths, ref=None, untracked=untracked)
                _cache[key] = to_state
            # we want Git to tell us what it considers modified and avoid
            # reimplementing logic ourselves
            key = _get_cache_key('mod', paths, None)
            if key in _cache:
                modified = _cache[key]
            else:
                modified = set(
                    self.pathobj.joinpath(ut.PurePosixPath(p))
                    for p in self._git_custom_command(
                        # low-level code cannot handle pathobjs
                        [str(p) for p in paths] if paths else None,
                        ['git', 'ls-files', '-z', '-m'])[0].split('\0')
                    if p)
                _cache[key] = modified
        else:
            key = _get_cache_key('ci', paths, to)
            if key in _cache:
                to_state = _cache[key]
            else:
                to_state = self.get_content_info(paths=paths, ref=to)
                _cache[key] = to_state
            # we do not need worktree modification detection in this case
            modified = None
        # origin state
        key = _get_cache_key('ci', paths, fr)
        if key in _cache:
            from_state = _cache[key]
        else:
            if fr:
                from_state = self.get_content_info(paths=paths, ref=fr)
            else:
                # no ref means from nothing
                from_state = {}
            _cache[key] = from_state

        for f, to_state_r in iteritems(to_state):
            props = None
            if f not in from_state:
                # this is new, or rather not known to the previous state
                props = dict(
                    state='added' if to_state_r['gitshasum'] else 'untracked',
                    type=to_state_r['type'],
                )
            elif to_state_r['gitshasum'] == from_state[f]['gitshasum'] and \
                    (modified is None or f not in modified):
                if ignore_submodules != 'all' or to_state_r['type'] != 'dataset':
                    # no change in git record, and no change on disk
                    props = dict(
                        state='clean' if f.exists() or
                              f.is_symlink() else 'deleted',
                        type=to_state_r['type'],
                    )
            else:
                # change in git record, or on disk
                props = dict(
                    # TODO we could have a new file that is already staged
                    # but had subsequent modifications done to it that are
                    # unstaged. Such file would presently show up as 'added'
                    # ATM I think this is OK, but worth stating...
                    state='modified' if f.exists() or
                    f.is_symlink() else 'deleted',
                    # TODO record before and after state for diff-like use
                    # cases
                    type=to_state_r['type'],
                )
            if props['state'] in ('clean', 'added', 'modified'):
                props['gitshasum'] = to_state_r['gitshasum']
            if props['state'] in ('clean', 'modified', 'deleted'):
                props['prev_gitshasum'] = from_state[f]['gitshasum']
            status[f] = props

        for f, from_state_r in iteritems(from_state):
            if f not in to_state:
                # we new this, but now it is gone and Git is not complaining
                # about it being missing -> properly deleted and deletion
                # stages
                status[f] = dict(
                    state='deleted',
                    type=from_state_r['type'],
                    # report the shasum to distinguish from a plainly vanished
                    # file
                    gitshasum=from_state_r['gitshasum'],
                )

        if ignore_submodules == 'all':
            return status

        # loop over all subdatasets and look for additional modifications
        for f, st in iteritems(status):
            if not (st['type'] == 'dataset' and st['state'] == 'clean' and
                    GitRepo.is_valid_repo(str(f))):
                # no business here
                continue
            # we have to recurse into the dataset and get its status
            subrepo = RevolutionGitRepo(str(f))
            # subdataset records must be labeled clean up to this point
            if st['gitshasum'] != subrepo.get_hexsha():
                # current commit in subdataset deviates from what is
                # recorded in the dataset, cheap test
                st['state'] = 'modified'
            else:
                # the recorded commit did not change, so we need to make
                # a more expensive traversal
                rstatus = subrepo.diffstatus(
                    # we can use 'HEAD' because we know that the commit
                    # did not change. using 'HEAD' will facilitate
                    # caching the result
                    fr='HEAD',
                    to=None,
                    paths=None,
                    untracked=untracked,
                    ignore_submodules='other',
                    _cache=_cache)
                if any(v['state'] != 'clean'
                       for k, v in iteritems(rstatus)):
                    st['state'] = 'modified'
            if ignore_submodules == 'other' and st['state'] == 'modified':
                # we know for sure that at least one subdataset is modified
                # go home quick
                break
        return status

    def _save_pre(self, paths, _status, **kwargs):
        # helper to get an actionable status report
        if paths is not None and not paths and not _status:
            return
        if _status is None:
            if 'untracked' not in kwargs:
                kwargs['untracked'] = 'normal'
            status = self.status(
                paths=paths,
                **{k: kwargs[k] for k in kwargs
                   if k in ('untracked', 'ignore_submodules')})
        else:
            # we want to be able to add items down the line
            # make sure to detach from prev. owner
            status = _status.copy()
        status = OrderedDict(
            (k, v) for k, v in iteritems(status)
            if v.get('state', None) != 'clean'
        )
        return status

    def get_staged_paths(self):
        """Returns a list of any stage repository path(s)

        This is a rather fast call, as it will not depend on what is going on
        in the worktree.
        """
        try:
            stdout, stderr = self._git_custom_command(
                None,
                ['git', 'diff', '--name-only', '--staged'],
                cwd=self.path,
                log_stderr=True,
                log_stdout=True,
                log_online=False,
                expect_stderr=False,
                expect_fail=True)
        except CommandError as e:
            lgr.debug(exc_str(e))
            stdout = ''
        return [f for f in stdout.split('\n') if f]

    def _save_post(self, message, status, partial_commit):
        # helper to commit changes reported in status
        _datalad_msg = False
        if not message:
            message = 'Recorded changes'
            _datalad_msg = True

        # TODO remove pathobj stringification when commit() can
        # handle it
        to_commit = [str(f.relative_to(self.pathobj))
                     for f, props in iteritems(status)] \
                    if partial_commit else None
        if not partial_commit or to_commit:
            # we directly call GitRepo.commit() to avoid a whole slew
            # if direct-mode safeguards and workarounds in the AnnexRepo
            # implementation (which also run an additional dry-run commit
            GitRepo.commit(
                self,
                files=to_commit,
                msg=message,
                _datalad_msg=_datalad_msg,
                options=None,
                # do not raise on empty commit
                # it could be that the `add` in this save-cycle has already
                # brought back a 'modified' file into a clean state
                careless=True,
            )

    def save(self, message=None, paths=None, _status=None, **kwargs):
        """Save dataset content.

        Parameters
        ----------
        message : str or None
          A message to accompany the changeset in the log. If None,
          a default message is used.
        paths : list or None
          Any content with path matching any of the paths given in this
          list will be saved. Matching will be performed against the
          dataset status (GitRepo.status()), or a custom status provided
          via `_status`. If no paths are provided, ALL non-clean paths
          present in the repo status or `_status` will be saved.
        ignore_submodules : {'no', 'all'}
          If `_status` is not given, will be passed as an argument to
          Repo.status(). With 'all' no submodule state will be saved in
          the dataset. Note that submodule content will never be saved
          in their respective datasets, as this function's scope is
          limited to a single dataset.
        _status : dict or None
          If None, Repo.status() will be queried for the given `ds`. If
          a dict is given, its content will be used as a constraint.
          For example, to save only modified content, but no untracked
          content, set `paths` to None and provide a `_status` that has
          no entries for untracked content.
        **kwargs :
          Additional arguments that are passed to underlying Repo methods.
          Supported:

          - git : bool (passed to Repo.add()
          - ignore_submodules : {'no', 'other', 'all'} passed to Repo.status()
          - untracked : {'no', 'normal', 'all'} - passed to Repo.satus()
        """
        return list(
            self.save_(
                message=message,
                paths=paths,
                _status=_status,
                **kwargs
            )
        )

    def save_(self, message=None, paths=None, _status=None, **kwargs):
        """Like `save()` but working as a generator."""
        status = self._save_pre(paths, _status, **kwargs)
        if not status:
            # all clean, nothing todo
            lgr.debug('Nothing to save in %r, exiting early', self)
            return

        # three things are to be done:
        # - remove (deleted if not already staged)
        # - add (modified/untracked)
        # - commit (with all paths that have been touched, to bypass
        #   potential pre-staged bits)

        need_partial_commit = True if self.get_staged_paths() else False

        # remove first, because removal of a subds would cause a
        # modification of .gitmodules to be added to the todo list
        to_remove = [
            # TODO remove pathobj stringification when delete() can
            # handle it
            str(f.relative_to(self.pathobj))
            for f, props in iteritems(status)
            if props.get('state', None) == 'deleted' and
            # staged deletions have a gitshasum reported for them
            # those should not be processed as git rm will error
            # due to them being properly gone already
            not props.get('gitshasum', None)]
        vanished_subds = any(
            props.get('type', None) == 'dataset' and
            props.get('state', None) == 'deleted'
            for f, props in iteritems(status))
        if to_remove:
            for r in self.remove(
                    to_remove,
                    # we would always see individual files
                    recursive=False):
                # TODO normalize result
                yield r

        # TODO this additonal query should not be, base on status as given
        # if anyhow possible, however, when paths are given, status may
        # not contain all required information. In case of path=None AND
        # _status=None, we should be able to avoid this, because
        # status should have the full info already
        # looks for contained repositories
        to_add_submodules = [sm for sm, sm_props in iteritems(
            self.get_content_info(
                # get content info for any untracked directory
                [f.relative_to(self.pathobj) for f, props in iteritems(status)
                 if props.get('state', None) == 'untracked' and
                 props.get('type', None) == 'directory'],
                ref=None,
                # request exhaustive list, so that everything that is
                # still reported as a directory must be its own repository
                untracked='all'))
            if sm_props.get('type', None) == 'directory']
        added_submodule = False
        for cand_sm in to_add_submodules:
            try:
                self.add_submodule(
                    str(cand_sm.relative_to(self.pathobj)),
                    url=None, name=None)
            except (CommandError, InvalidGitRepositoryError) as e:
                yield get_status_dict(
                    action='add_submodule',
                    ds=self,
                    path=self.pathobj / ut.PurePosixPath(cand_sm),
                    status='error',
                    message=e.stderr if hasattr(e, 'stderr')
                    else ('not a Git repository: %s', exc_str(e)),
                    logger=lgr)
                continue
            added_submodule = True
        if not need_partial_commit:
            # without a partial commit an AnnexRepo would ignore any submodule
            # path in its add helper, hence `git add` them explicitly
            to_stage_submodules = {
                str(f.relative_to(self.pathobj)): props
                for f, props in iteritems(status)
                if props.get('state', None) in ('modified', 'untracked')
                and props.get('type', None) == 'dataset'}
            if to_stage_submodules:
                lgr.debug(
                    '%i submodule path(s) to stage in %r %s',
                    len(to_stage_submodules), self,
                    to_stage_submodules
                    if len(to_stage_submodules) < 10 else '')
                for r in RevolutionGitRepo._save_add(
                        self,
                        to_stage_submodules,
                        git_opts=None):
                    # TODO the helper can yield proper dicts right away
                    yield get_status_dict(
                        action=r.get('command', 'add'),
                        refds=self.pathobj,
                        type='file',
                        path=(self.pathobj / ut.PurePosixPath(r['file']))
                        if 'file' in r else None,
                        status='ok' if r.get('success', None) else 'error',
                        key=r.get('key', None),
                        logger=lgr)

        if added_submodule or vanished_subds:
            # need to include .gitmodules in what needs saving
            status[self.pathobj.joinpath('.gitmodules')] = dict(
                type='file', state='modified')
        to_add = {
            # TODO remove pathobj stringification when add() can
            # handle it
            str(f.relative_to(self.pathobj)): props
            for f, props in iteritems(status)
            if props.get('state', None) in ('modified', 'untracked')}
        if to_add:
            lgr.debug(
                '%i path(s) to add to %r %s',
                len(to_add), self, to_add if len(to_add) < 10 else '')
            for r in self._save_add(
                    to_add,
                    git_opts=None,
                    **{k: kwargs[k] for k in kwargs
                       if k in (('git',) if hasattr(self, 'annexstatus')
                                else tuple())}):
                # TODO the helper can yield proper dicts right away
                yield get_status_dict(
                    action=r.get('command', 'add'),
                    refds=self.pathobj,
                    type='file',
                    path=(self.pathobj / ut.PurePosixPath(r['file']))
                    if 'file' in r else None,
                    status='ok' if r.get('success', None) else 'error',
                    key=r.get('key', None),
                    logger=lgr)

        self._save_post(message, status, need_partial_commit)
        # TODO yield result for commit, prev helper checked hexsha pre
        # and post...

    def _save_add(self, files, git_opts=None):
        """Simple helper to add files in save()"""
        try:
            # without --verbose git 2.9.3  add does not return anything
            add_out = self._git_custom_command(
                list(files.keys()),
                ['git', 'add'] + assure_list(git_opts) + ['--verbose']
            )
            # get all the entries
            for o in self._process_git_get_output(*add_out):
                yield o
        except OSError as e:
            lgr.error("add: %s" % e)
            raise

    # run() needs this ATM, but should eventually be RF'ed to a
    # status(recursive=True) call
    @property
    def dirty(self):
        return len([
            p for p, props in iteritems(self.status(
                untracked='normal', ignore_submodules='other'))
            if props.get('state', None) != 'clean' and
            # -core ignores empty untracked directories, so shall we
            not (p.is_dir() and len(list(p.iterdir())) == 0)]) > 0


# remove deprecated methods from API
for m in obsolete_methods:
    if hasattr(RevolutionGitRepo, m):
        setattr(RevolutionGitRepo, m, ut.nothere)

"""Amendment of the DataLad `AnnexRepo` base class"""
__docformat__ = 'restructuredtext'

import os
import os.path as op
from collections import OrderedDict
import logging
from six import iteritems
from weakref import WeakValueDictionary

from datalad.utils import on_windows
from datalad.ui import ui

from . import utils as ut

from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CommandError

from .gitrepo import (
    RevolutionGitRepo,
    obsolete_methods as gitrepo_obsolete_methods,
)

lgr = logging.getLogger('datalad.revolution.annexrepo')

obsolete_methods = (
    # next two are only needed by 'ok_clean_git'
    # 'untracked_files',
    # 'get_status',
    'is_dirty',
)


class RevolutionAnnexRepo(AnnexRepo, RevolutionGitRepo):

    # Begin Flyweight:
    _unique_instances = WeakValueDictionary()
    # End Flyweight:

    def _mark_content_availability(self, info):
        objectstore = self.pathobj.joinpath(
            self.path, RevolutionGitRepo.get_git_dir(self), 'annex', 'objects')
        for f, r in iteritems(info):
            if 'key' not in r or 'has_content' in r:
                # not annexed or already processed
                continue
            # test hashdirmixed first, as it is used in non-bare repos
            # which be a more frequent target
            # TODO optimize order based on some check that reveals
            # what scheme is used in a given annex
            r['has_content'] = False
            key = r['key']
            for testpath in (
                    # ATM git-annex reports hashdir in native path
                    # conventions and the actual file path `f` in
                    # POSIX, weired...
                    # we need to test for the actual key file, not
                    # just the containing dir, as on windows the latter
                    # may not always get cleaned up on `drop`
                    objectstore.joinpath(
                        ut.Path(r['hashdirmixed']), key, key),
                    objectstore.joinpath(
                        ut.Path(r['hashdirlower']), key, key)):
                if testpath.exists():
                    r.pop('hashdirlower', None)
                    r.pop('hashdirmixed', None)
                    r['objloc'] = str(testpath)
                    r['has_content'] = True
                    break

    def get_content_annexinfo(
            self, paths=None, init='git', ref=None, eval_availability=False,
            key_prefix='', **kwargs):
        """
        Parameters
        ----------
        paths : list
          Specific paths to query info for. In none are given, info is
          reported for all content.
        init : 'git' or dict-like or None
          If set to 'git' annex content info will ammend the output of
          GitRepo.get_content_info(), otherwise the dict-like object
          supplied will receive this information and the present keys will
          limit the report of annex properties. Alternatively, if `None`
          is given, no initialization is done, and no limit is in effect.
        ref : gitref or None
          If not None, annex content info for this Git reference will be
          produced, otherwise for the content of the present worktree.
        eval_availability : bool
          If this flag is given, evaluate whether the content of any annex'ed
          file is present in the local annex.
        **kwargs :
          Additional arguments for GitRepo.get_content_info(), if `init` is
          set to 'git'.

        Returns
        -------
        dict
          Each content item has an entry under its relative path within
          the repository. Each value is a dictionary with properties:

          `type`
            Can be 'file', 'symlink', 'dataset', 'directory'
          `revision`
            SHASUM is last commit affecting the item, or None, if not
            tracked.
          `key`
            Annex key of a file (if an annex'ed file)
          `bytesize`
            Size of an annexed file in bytes.
          `has_content`
            Bool whether a content object for this key exists in the local
            annex (with `eval_availability`)
          `objloc`
            pathlib.Path of the content object in the local annex, if one
            is available (with `eval_availability`)
        """
        if init is None:
            info = OrderedDict()
        elif init == 'git':
            info = super(AnnexRepo, self).get_content_info(
                paths=paths, ref=ref, **kwargs)
        else:
            info = init
        # use this funny-looking option with both find and findref
        # it takes care of git-annex reporting on any known key, regardless
        # of whether or not it actually (did) exist in the local annex
        opts = ['--copies', '0']
        if ref:
            cmd = 'findref'
            opts.append(ref)
        else:
            cmd = 'find'
            # stringify any pathobjs
            opts.extend([str(p) for p in paths]
                        if paths else ['--include', '*'])
        for j in self._run_annex_command_json(cmd, opts=opts):
            path = self.pathobj.joinpath(ut.PurePosixPath(j['file']))
            rec = info.get(path, None)
            if init is not None and rec is None:
                # init constraint knows nothing about this path -> skip
                continue
            rec.update({'{}{}'.format(key_prefix, k): j[k]
                       for k in j if k != 'file'})
            info[path] = rec
            # TODO make annex availability checks optional and move in here
            if not eval_availability:
                # not desired, or not annexed
                continue
            self._mark_content_availability(info)
        return info

    def annexstatus(self, paths=None, untracked='all'):
        info = self.get_content_annexinfo(
            paths=paths,
            eval_availability=False,
            init=self.get_content_annexinfo(
                paths=paths,
                ref='HEAD',
                eval_availability=False,
                init=self.status(
                    paths=paths,
                    ignore_submodules='other')
            )
        )
        self._mark_content_availability(info)
        return info

    def _save_add(self, files, git=None, git_opts=None):
        """Simple helper to add files in save()"""
        # alter default behavior of git-annex by considering dotfiles
        # too
        # however, this helper is controlled by save() which itself
        # operates on status() which itself honors .gitignore, so
        # there is a standard mechanism that is uniform between Git
        # Annex repos to decide on the behavior on a case-by-case
        # basis
        # TODO have a dedicated test for this
        options = ['--include-dotfiles']
        # if None -- leave it to annex to decide
        if git is not None:
            options += [
                '-c',
                'annex.largefiles=%s' % (('anything', 'nothing')[int(git)])
            ]
        if on_windows:
            # git-annex ignores symlinks on windows
            # https://github.com/datalad/datalad/issues/2955
            # check if there are any and pass them to git-add
            symlinks_toadd = {
                p: props for p, props in iteritems(files)
                if props.get('type', None) == 'symlink'}
            if symlinks_toadd:
                for r in RevolutionGitRepo._save_add(
                        self,
                        symlinks_toadd,
                        git_opts=git_opts):
                    yield r
            # trim `files` of symlinks
            files = {
                p: props for p, props in iteritems(files)
                if props.get('type', None) != 'symlink'}

        expected_additions = None
        if ui.is_interactive:
            # without an interactive UI there is little benefit from
            # progressbar info, hence save the stat calls
            def _get_file_size(relpath):
                path = op.join(self.path, relpath)
                return 0 if not op.exists(path) else os.stat(path).st_size

            expected_additions = {p: _get_file_size(p) for p in files}

        for r in self._run_annex_command_json(
                'add',
                opts=options,
                files=list(files.keys()),
                backend=None,
                expect_fail=True,
                # TODO
                jobs=None,
                expected_entries=expected_additions,
                expect_stderr=True):
            yield r


# remove deprecated methods from API
for m in obsolete_methods + gitrepo_obsolete_methods:
    if hasattr(RevolutionAnnexRepo, m):
        setattr(RevolutionAnnexRepo, m, ut.nothere)

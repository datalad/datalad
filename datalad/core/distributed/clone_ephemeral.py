""""""

__docformat__ = 'restructuredtext'

import logging

from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import CapturedException
from datalad.support.gitrepo import GitRepo
from datalad.support.network import RI
from datalad.utils import (
    Path,
    check_symlink_capability,
    rmtree,
)

from . import clone as mod_clone

# we need to preserve the original functions to be able to call them
# in the patch
orig_pre_annex_init_processing_ = mod_clone._pre_annex_init_processing_
orig_post_annex_init_processing_ = mod_clone._post_annex_init_processing_

lgr = logging.getLogger('datalad.core.distributed.clone')


def _pre_annex_init_processing_(
    *,
    destds: Dataset,
    reckless: None or str,
    **kwargs
):
    if reckless == 'ephemeral':
        # In ephemeral clones we set annex.private=true. This would prevent the
        # location itself being recorded in uuid.log. With a private repo,
        # declaring dead (see below after annex-init) seems somewhat
        # superfluous, but on the other hand:
        # If an older annex that doesn't support private yet touches the
        # repo, the entire purpose of ephemeral would be sabotaged if we did
        # not declare dead in addition. Hence, keep it regardless of annex
        # version.
        destds.config.set('annex.private', 'true', scope='local')

    yield from orig_pre_annex_init_processing_(
        destds=destds, reckless=reckless, **kwargs)


def _post_annex_init_processing_(
        *,
        destds: Dataset,
        remote: str,
        reckless: None or str,
        **kwargs
):

    if reckless == 'ephemeral':
        _setup_ephemeral_annex(destds, remote)

    yield from orig_post_annex_init_processing_(
        destds=destds, remote=remote, reckless=reckless,
        **kwargs)


def _setup_ephemeral_annex(ds: Dataset, remote: str):
    # with ephemeral we declare 'here' as 'dead' right away, whenever
    # we symlink the remote's annex, since availability from 'here' should
    # not be propagated for an ephemeral clone when we publish back to
    # the remote.
    # This will cause stuff like this for a locally present annexed file:
    # % git annex whereis d1
    # whereis d1 (0 copies) failed
    # BUT this works:
    # % git annex find . --not --in here
    # % git annex find . --in here
    # d1

    # we don't want annex copy-to <remote>
    ds.config.set(
        f'remote.{remote}.annex-ignore', 'true',
        scope='local')
    ds.repo.set_remote_dead('here')

    if check_symlink_capability(ds.repo.dot_git / 'dl_link_test',
                                ds.repo.dot_git / 'dl_target_test'):
        # symlink the annex to avoid needless copies in an ephemeral clone
        annex_dir = ds.repo.dot_git / 'annex'
        origin_annex_url = ds.config.get(f"remote.{remote}.url", None)
        origin_git_path = None
        if origin_annex_url:
            try:
                # Deal with file:// scheme URLs as well as plain paths.
                # If origin isn't local, we have nothing to do.
                origin_git_path = Path(RI(origin_annex_url).localpath)

                if not origin_git_path.is_absolute():
                    # relative path would be relative to the ds, not pwd!
                    origin_git_path = ds.pathobj / origin_git_path

                # we are local; check for a bare repo first to not mess w/
                # the path
                if GitRepo(origin_git_path, create=False).bare:
                    # origin is a bare repo -> use path as is
                    pass
                elif origin_git_path.name != '.git':
                    origin_git_path /= '.git'
            except ValueError as e:
                CapturedException(e)
                # Note, that accessing localpath on a non-local RI throws
                # ValueError rather than resulting in an AttributeError.
                # TODO: Warning level okay or is info level sufficient?
                # Note, that setting annex-dead is independent of
                # symlinking .git/annex. It might still make sense to
                # have an ephemeral clone that doesn't propagate its avail.
                # info. Therefore don't fail altogether.
                lgr.warning("reckless=ephemeral mode: %s doesn't seem "
                            "local: %s\nno symlinks being used",
                            remote, origin_annex_url)
        if origin_git_path:
            # TODO make sure that we do not delete any unique data
            rmtree(str(annex_dir)) \
                if not annex_dir.is_symlink() else annex_dir.unlink()
            annex_dir.symlink_to(origin_git_path / 'annex',
                                 target_is_directory=True)
    else:
        # TODO: What level? + note, that annex-dead is independent
        lgr.warning("reckless=ephemeral mode: Unable to create symlinks on "
                    "this file system.")


def _apply():
    # apply patch in a function, to be able to easily patch it out
    # and turn off the patch
    lgr.debug(
        'Apply ephemeral patch to clone.py:_pre_annex_init_processing_')
    mod_clone._pre_annex_init_processing_ = _pre_annex_init_processing_
    lgr.debug(
        'Apply ephemeral patch to clone.py:_post_annex_init_processing_')
    mod_clone._post_annex_init_processing_ = _post_annex_init_processing_


_apply()

#!/usr/bin/env python3
"""Procedure to uninit Git-annex (if initialized), and create/save .noannex file to prevent annex initialization

If there are git-annex'ed files already, git annex uninit and this procedure will fail.

"""

from datalad import lgr
from datalad.distribution.dataset import require_dataset
from datalad.support.annexrepo import AnnexRepo


def no_annex(ds):
    ds = require_dataset(
        ds,
        check_installed=True,
        purpose='configuration')

    if isinstance(ds.repo, AnnexRepo):
        repo = ds.repo
        # TODO: if procedures can have options -- add --force handling/passing
        #
        # annex uninit unlocks files for which there is content (nice) but just proceeds
        # and leaves broken symlinks for files without content.  For the current purpose
        # of this procedure we just prevent "uninit" of any annex with some files already
        # annexed.
        if any(repo.call_annex_items_(['whereis', '--all'])):
            raise RuntimeError("Annex has some annexed files, unsafe")
        # remove annex
        repo.call_annex(['uninit'])

    noannex_file = ds.pathobj / ".noannex"
    if not noannex_file.exists():
        lgr.info("Creating and committing a .noannex file")
        noannex_file.touch()
        ds.save(noannex_file,
                message="Added .noannex to prevent accidental initialization of git-annex",
                result_renderer='disabled')


if __name__ == '__main__':
    import sys
    no_annex(sys.argv[1])

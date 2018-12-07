import os
import os.path as op

from datalad.utils import (
    chpwd,
    getpwd,
)

from datalad.tests.utils import (
    with_tempfile,
    eq_,
    on_windows,
)

from datalad_revolution.dataset import (
    RevolutionDataset as Dataset,
    resolve_path,
)

import datalad_revolution.utils as ut


@with_tempfile(mkdir=True)
def test_resolve_path(path):
    # initially ran into on OSX https://github.com/datalad/datalad/issues/2406
    opath = op.join(path, "origin")
    os.makedirs(opath)
    if not on_windows:
        lpath = op.join(path, "linked")
        os.symlink('origin', lpath)

    ds_global = Dataset(path)
    # path resolution of absolute paths is not influenced by symlinks
    # ignore the linked path on windows, it is not a symlink in the POSIX sense
    for d in (opath,) if on_windows else (opath, lpath):
        ds_local = Dataset(d)
        # no symlink resolution
        eq_(str(resolve_path(d)), d)
        with chpwd(d):
            # be aware: knows about cwd, but this CWD has symlinks resolved
            eq_(str(resolve_path(d).cwd()), opath)
            # using pathlib's `resolve()` will resolve any
            # symlinks
            # also resolve `opath`, as on old windows systems the path might
            # come in crippled (e.g. C:\Users\MIKE~1/...)
            # and comparison would fails unjustified
            eq_(resolve_path('.').resolve(), ut.Path(opath).resolve())
            # no norming, but absolute paths, without resolving links
            eq_(resolve_path('.'), ut.Path(d))
            eq_(str(resolve_path('.')), d)

            eq_(str(resolve_path(op.join(os.curdir, 'bu'), ds=ds_global)),
                op.join(d, 'bu'))
            eq_(str(resolve_path(op.join(os.pardir, 'bu'), ds=ds_global)),
                op.join(d, os.pardir, 'bu'))

        # resolve against a dataset
        eq_(str(resolve_path('bu', ds=ds_local)), op.join(d, 'bu'))
        eq_(str(resolve_path('bu', ds=ds_global)), op.join(path, 'bu'))
        # but paths outside the dataset are left untouched
        eq_(str(resolve_path(op.join(os.curdir, 'bu'), ds=ds_global)),
            op.join(getpwd(), 'bu'))
        eq_(str(resolve_path(op.join(os.pardir, 'bu'), ds=ds_global)),
            op.join(getpwd(), os.pardir, 'bu'))

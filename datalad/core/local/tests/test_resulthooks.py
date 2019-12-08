# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test result hooks"""

from datalad.utils import (
    on_windows,
)
from datalad.tests.utils import (
    with_tempfile,
    eq_,
    ok_,
    assert_result_count,
)
from datalad.api import (
    Dataset,
    install,
)


@with_tempfile()
@with_tempfile()
def test_basics(src, dst):
    # dataset with subdataset, not specific configuration
    ds = Dataset(src).create()
    (ds.pathobj / 'file1').write_text('some')
    ds.save()
    sub = ds.create('subds')
    eq_(sub.config.get('datalad.metadata.nativetype'), None)

    # now clone the super
    clone = install(source=src, path=dst)
    # and configure it, such that it modifies each obtained subdataset
    # on install to have 'bids' listed as a metadata type
    clone.config.set(
        'datalad.result-hook.alwaysbids.proc',
        # the spec is like --proc-post/pre, but has the dataset to run on as
        # the first element
        # string substitutions based on the result record are supported
        'run_procedure {{"dataset":"{path}","spec":"cfg_metadatatypes bids"}}',
        where='local',
    )
    # config on which kind of results this hook should operate
    clone.config.set(
        'datalad.result-hook.alwaysbids.match',
        # any successfully installed dataset
        '{"type":"dataset","action":"install","status":["eq", "ok"]}',
        where='local',
    )
    # configure another one that will unlock any obtained file
    # {dsarg} is substituted by the dataset arg of the command that
    # the eval_func() decorator belongs too
    # but it may not have any, as this is not the outcome of a
    # require_dataset(), but rather the verbatim input
    # it could be more useful to use {refds}
    clone.config.set(
        'datalad.result-hook.unlockfiles.proc',
        'unlock {{"dataset":"{dsarg}","path":"{path}"}}',
        where='local',
    )
    clone.config.set(
        'datalad.result-hook.unlockfiles.match',
        '{"type":"file","action":"get","status":"ok"}',
        where='local',
    )
    if not on_windows:
        # and one that runs a shell command on any notneeded file-get
        clone.config.set(
            'datalad.result-hook.annoy.proc',
            'run {{"cmd":"touch {path}_annoyed",'
            '"dataset":"{dsarg}","explicit":true}}',
            where='local',
        )
        clone.config.set(
            'datalad.result-hook.annoy.match',
            '{"type":["in", ["file"]],"action":"get","status":"notneeded"}',
            where='local',
        )
    # TODO resetting of detached HEAD seem to come after the install result
    # and wipes out the change
    clone.get('subds')
    clone_sub = Dataset(clone.pathobj / 'subds')
    eq_(clone_sub.config.get('datalad.metadata.nativetype'), 'bids')

    # hook auto-unlocks the file
    if not on_windows:
        ok_((clone.pathobj / 'file1').is_symlink())
    # we get to see the results from the hook too!
    assert_result_count(
        clone.get('file1'), 1, action='unlock', path=str(clone.pathobj / 'file1'))
    ok_(not (clone.pathobj / 'file1').is_symlink())

    if not on_windows:
        # different hook places annoying file next to a file that was already present
        annoyed_file = clone.pathobj / 'file1_annoyed'
        ok_(not annoyed_file.exists())
        clone.get('file1')
        ok_(annoyed_file.exists())

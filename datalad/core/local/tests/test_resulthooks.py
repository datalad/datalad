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
    assert_result_count,
    eq_,
    ok_,
    with_tempfile,
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
    # second one for a result_xfm test below
    ds.create('subds2')
    eq_(sub.config.get('datalad.metadata.nativetype'), None)

    # now clone the super
    clone = install(source=src, path=dst)
    # and configure it, such that it modifies each obtained subdataset
    # on install to have 'bids' listed as a metadata type
    clone.config.set(
        'datalad.result-hook.alwaysbids.call-json',
        # string substitutions based on the result record are supported
        'run_procedure {{"dataset":"{path}","spec":"cfg_metadatatypes bids dicom"}}',
        where='local',
    )
    # config on which kind of results this hook should operate
    clone.config.set(
        'datalad.result-hook.alwaysbids.match-json',
        # any successfully installed dataset
        '{"type":"dataset","action":"install","status":["eq", "ok"]}',
        where='local',
    )
    # a smoke test to see if a hook definition without any call args works too
    clone.config.set('datalad.result-hook.wtf.call-json',
                     'wtf {{"result_renderer": "disabled"}}',
                     where='local')
    clone.config.set(
        'datalad.result-hook.wtf.match-json',
        '{"type":"dataset","action":"install","status":["eq", "ok"]}',
        where='local',
    )
    # configure another one that will unlock any obtained file
    # {dsarg} is substituted by the dataset arg of the command that
    # the eval_func() decorator belongs to
    # but it may not have any, as this is not the outcome of a
    # require_dataset(), but rather the verbatim input
    # it could be more useful to use {refds}
    clone.config.set(
        'datalad.result-hook.unlockfiles.call-json',
        'unlock {{"dataset":"{dsarg}","path":"{path}"}}',
        where='local',
    )
    clone.config.set(
        'datalad.result-hook.unlockfiles.match-json',
        '{"type":"file","action":"get","status":"ok"}',
        where='local',
    )
    if not on_windows:
        # and one that runs a shell command on any notneeded file-get
        clone.config.set(
            'datalad.result-hook.annoy.call-json',
            'run {{"cmd":"touch {path}_annoyed",'
            '"dataset":"{dsarg}","explicit":true}}',
            where='local',
        )
        clone.config.set(
            'datalad.result-hook.annoy.match-json',
            '{"type":["in", ["file"]],"action":"get","status":"notneeded"}',
            where='local',
        )
    # setup done, now see if it works
    clone.get('subds')
    clone_sub = Dataset(clone.pathobj / 'subds')
    eq_(clone_sub.config.get('datalad.metadata.nativetype', get_all=True),
        ('bids', 'dicom'))
    # now the same thing with a result_xfm, should make no difference
    clone.get('subds2')
    clone_sub2 = Dataset(clone.pathobj / 'subds2')
    eq_(clone_sub2.config.get('datalad.metadata.nativetype', get_all=True),
        ('bids', 'dicom'))

    # hook auto-unlocks the file
    if not clone.repo.is_managed_branch():
        ok_((clone.pathobj / 'file1').is_symlink())
    res = clone.get('file1')
    if not clone.repo.is_managed_branch():
        # we get to see the results from the hook too!
        assert_result_count(
            res, 1, action='unlock', path=str(clone.pathobj / 'file1'))
    ok_(not (clone.pathobj / 'file1').is_symlink())

    if not clone.repo.is_managed_branch():
        # different hook places annoying file next to a file that was already present
        annoyed_file = clone.pathobj / 'file1_annoyed'
        ok_(not annoyed_file.exists())
        clone.get('file1')
        ok_(annoyed_file.exists())

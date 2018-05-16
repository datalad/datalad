# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import hashlib
import json as js
import logging
from genericpath import exists
from nose.tools import assert_equal, assert_raises, assert_in, assert_false, \
    assert_not_in
from os.path import join as opj

from datalad.distribution.dataset import Dataset
from datalad.interface.ls_webui import machinesize, ignored, fs_traverse, \
    _ls_json
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils import with_tree
from datalad.utils import swallow_logs, swallow_outputs, _path_
# needed below as bound dataset method
from datalad.api import add


def test_machinesize():
    assert_equal(1.0, machinesize(1))
    for key, value in {'Byte': 0, 'Bytes': 0, 'kB': 1, 'MB': 2, 'GB': 3, 'TB': 4, 'PB': 5}.items():
        assert_equal(1.0*(1000**value), machinesize('1 ' + key))
    assert_raises(ValueError, machinesize, 't byte')


@with_tree(
    tree={'dir': {'file1.txt': '123', 'file2.txt': '456'},
          '.hidden': {'.hidden_file': '121'}})
def test_ignored(topdir):
    # create annex, git repos
    AnnexRepo(opj(topdir, 'annexdir'), create=True)
    GitRepo(opj(topdir, 'gitdir'), create=True)

    # non-git or annex should not be ignored
    assert_equal(ignored(topdir), False)
    # git, annex and hidden nodes should be ignored
    for subdir in ["annexdir", "gitdir", ".hidden"]:
        assert_equal(ignored(opj(topdir, subdir)), True)
    # ignore only hidden nodes(not git or annex repos) flag should work
    assert_equal(ignored(opj(topdir, "annexdir"), only_hidden=True), False)


@with_tree(
    tree={'dir': {'.fgit': {'ab.txt': '123'},
                  'subdir': {'file1.txt': '124', 'file2.txt': '123'},
                  'subgit': {'fgit.txt': '123'}},
          'topfile.txt': '123',
          '.hidden': {'.hidden_file': '123'}})
def test_fs_traverse(topdir):
    # setup temp directory tree for testing
    annex = AnnexRepo(topdir)
    AnnexRepo(opj(topdir, 'annexdir'), create=True)
    GitRepo(opj(topdir, 'gitdir'), create=True)
    GitRepo(opj(topdir, 'dir', 'subgit'), create=True)
    annex.add(opj(topdir, 'dir'))
    annex.commit()
    annex.drop(opj(topdir, 'dir', 'subdir', 'file2.txt'), options=['--force'])

    # traverse file system in recursive and non-recursive modes
    for recursive in [True, False]:
        # test fs_traverse in display mode
        with swallow_logs(new_level=logging.INFO) as log, swallow_outputs() as cmo:
            fs = fs_traverse(topdir, AnnexRepo(topdir), recurse_directories=recursive, json='display')
            if recursive:
                # fs_traverse logs should contain all not ignored subdirectories
                for subdir in [opj(topdir, 'dir'), opj(topdir, 'dir', 'subdir')]:
                    assert_in('Directory: ' + subdir, log.out)
                # fs_traverse stdout contains subdirectory
                assert_in(('file2.txt' and 'dir'), cmo.out)

            # extract info of the top-level child directory
            child = [item for item in fs['nodes'] if item['name'] == 'dir'][0]
            # size of dir type child in non-recursive modes should be 0 Bytes(default) as
            # dir type child's size currently has no metadata file for traverser to pick its size from
            # and would require a recursive traversal w/ write to child metadata file mode
            assert_equal(child['size']['total'], {True: '6 Bytes', False: '0 Bytes'}[recursive])

    for recursive in [True, False]:
        # run fs_traverse in write to json 'file' mode
        fs = fs_traverse(topdir, AnnexRepo(topdir), recurse_directories=recursive, json='file')
        # fs_traverse should return a dictionary
        assert_equal(isinstance(fs, dict), True)
        # not including git and annex folders
        assert_equal([item for item in fs['nodes'] if ('gitdir' or 'annexdir') == item['name']], [])
        # extract info of the top-level child directory
        child = [item for item in fs['nodes'] if item['name'] == 'dir'][0]
        # verify node type
        assert_equal(child['type'], 'dir')
        # same node size on running fs_traversal in recursive followed by non-recursive mode
        # verifies child's metadata file being used to find its size
        # running in reverse order (non-recursive followed by recursive mode) will give (0, actual size)
        assert_equal(child['size']['total'], '6 Bytes')

        # verify subdirectory traversal if run in recursive mode
        # In current RF 'nodes' are stripped away during recursive traversal
        # for now... later we might reincarnate them "differently"
        # TODO!
        if False:  # recursive:
            # sub-dictionary should not include git and hidden directory info
            assert_equal([item for item in child['nodes'] if ('subgit' or '.fgit') == item['name']], [])
            # extract subdirectory dictionary, else fail
            subchild = [subitem for subitem in child["nodes"] if subitem['name'] == 'subdir'][0]
            # extract info of file1.txts, else fail
            link = [subnode for subnode in subchild["nodes"] if subnode['name'] == 'file1.txt'][0]
            # verify node's sizes and type
            assert_equal(link['size']['total'], '3 Bytes')
            assert_equal(link['size']['ondisk'], link['size']['total'])
            assert_equal(link['type'], 'link')
            # extract info of file2.txt, else fail
            brokenlink = [subnode for subnode in subchild["nodes"] if subnode['name'] == 'file2.txt'][0]
            # verify node's sizes and type
            assert_equal(brokenlink['type'], 'link-broken')
            assert_equal(brokenlink['size']['ondisk'], '0 Bytes')
            assert_equal(brokenlink['size']['total'], '3 Bytes')


@with_tree(
    tree={'dir': {'.fgit': {'ab.txt': '123'},
                  'subdir': {'file1.txt': '123',
                             'file2.txt': '123',
                             },
                  'subgit': {'fgit.txt': '123'},
                  'subds2': {'file': '124'}},
          '.hidden': {'.hidden_file': '123'}})
def test_ls_json(topdir):
    annex = AnnexRepo(topdir, create=True)
    dsj = Dataset(topdir)
    # create some file and commit it
    with open(opj(dsj.path, 'subdsfile.txt'), 'w') as f:
        f.write('123')
    dsj.add(path='subdsfile.txt')
    dsj.save("Hello!", version_tag=1)

    # add a subdataset
    dsj.install('subds', source=topdir)

    subdirds = dsj.create(_path_('dir/subds2'), force=True)
    subdirds.add('file')

    git = GitRepo(opj(topdir, 'dir', 'subgit'), create=True)                    # create git repo
    git.add(opj(topdir, 'dir', 'subgit', 'fgit.txt'))              # commit to git to init git repo
    git.commit()
    annex.add(opj(topdir, 'dir', 'subgit'))                        # add the non-dataset git repo to annex
    annex.add(opj(topdir, 'dir'))                                  # add to annex (links)
    annex.commit()
    annex.drop(opj(topdir, 'dir', 'subdir', 'file2.txt'), options=['--force'])  # broken-link

    meta_dir = opj('.git', 'datalad', 'metadata')
    meta_path = opj(topdir, meta_dir)

    def get_metahash(*path):
        if not path:
            path = ['/']
        return hashlib.md5(opj(*path).encode('utf-8')).hexdigest()

    def get_metapath(dspath, *path):
        return _path_(dspath, meta_dir, get_metahash(*path))

    def get_meta(dspath, *path):
        with open(get_metapath(dspath, *path)) as f:
            return js.load(f)

    for all_ in [True, False]:  # recurse directories
        for recursive in [True, False]:
            for state in ['file', 'delete']:
                # subdataset should have its json created and deleted when
                # all=True else not
                subds_metapath = get_metapath(opj(topdir, 'subds'))
                exists_prior = exists(subds_metapath)

                #with swallow_logs(), swallow_outputs():
                dsj = _ls_json(
                    topdir, json=state,
                    all_=all_,
                    recursive=recursive
                )

                exists_post = exists(subds_metapath)
                # print("%s %s -> %s" % (state, exists_prior, exists_post))
                assert_equal(exists_post, (state == 'file' and recursive))

                # root should have its json file created and deleted in all cases
                ds_metapath = get_metapath(topdir)
                assert_equal(exists(ds_metapath), state == 'file')

                # children should have their metadata json's created and deleted only when recursive=True
                child_metapath = get_metapath(topdir, 'dir', 'subdir')
                assert_equal(exists(child_metapath), (state == 'file' and all_))

                # ignored directories should not have json files created in any case
                for subdir in [('.hidden',), ('dir', 'subgit')]:
                    assert_false(exists(get_metapath(topdir, *subdir)))

                # check if its updated in its nodes sublist too. used by web-ui json. regression test
                assert_equal(dsj['nodes'][0]['size']['total'], dsj['size']['total'])

                # check size of subdataset
                subds = [item for item in dsj['nodes'] if item['name'] == ('subdsfile.txt' or 'subds')][0]
                assert_equal(subds['size']['total'], '3 Bytes')

                # dir/subds2 must not be listed among nodes of the top dataset:
                topds_nodes = {x['name']: x for x in dsj['nodes']}

                assert_in('subds', topds_nodes)
                # XXX
                # # condition here is a bit a guesswork by yoh later on
                # # TODO: here and below clear destiny/interaction of all_ and recursive
                # assert_equal(dsj['size']['total'],
                #              '15 Bytes' if (recursive and all_) else
                #              ('9 Bytes' if (recursive or all_) else '3 Bytes')
                # )

                # https://github.com/datalad/datalad/issues/1674
                if state == 'file' and all_:
                    dirj = get_meta(topdir, 'dir')
                    dir_nodes = {x['name']: x for x in dirj['nodes']}
                    # it should be present in the subdir meta
                    assert_in('subds2', dir_nodes)
                # and not in topds
                assert_not_in('subds2', topds_nodes)

                # run non-recursive dataset traversal after subdataset metadata already created
                # to verify sub-dataset metadata being picked up from its metadata file in such cases
                if state == 'file' and recursive and not all_:
                    dsj = _ls_json(topdir, json='file', all_=False)
                    subds = [
                        item for item in dsj['nodes']
                        if item['name'] == ('subdsfile.txt' or 'subds')
                    ][0]
                    assert_equal(subds['size']['total'], '3 Bytes')

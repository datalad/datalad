import os
from os.path import join as opj
from nose.tools import eq_, assert_in, assert_not_in
from datalad.tests.utils import with_tree, with_tempfile, ok_clean_git, \
    ok_file_under_git
from datalad.utils import chpwd
from datalad.api import crawl, crawl_init
from datalad.api import create
from datalad.tests.utils import known_failure_direct_mode
from ....tests.utils import serve_path_via_http

# Note: resembles test_simple_with_archivespy:test_crawl_autoaddtext
@with_tree(tree={
    '1.tar.gz': {
        'd': {"textfile": "1\n",
              "tooshort": "1"
              },
    "anothertext": "1 2 3"
    }
}, archives_leading_dir=False)
@serve_path_via_http
@with_tempfile
def test_crawl_direct_links_remote(ind, topurl, outd):
    ds = create(outd, text_no_annex=True)
    with chpwd(outd):  # TODO -- dataset argument
        crawl_init(
            {'paths': topurl + '1.tar.gz'}
            , save=True
            , template='direct_links')
        crawl()
    ok_clean_git(outd)
    ok_file_under_git(outd, "anothertext", annexed=False)
    ok_file_under_git(outd, "d/textfile", annexed=False)
    ok_file_under_git(outd, "d/tooshort", annexed=True)


@with_tree(tree={
    '1.tar.gz': {
        'd': {"textfile": "1\n",
              "tooshort": "1"
              },
    }
}, archives_leading_dir=False)
@with_tree(tree={
    '1.tar.gz': {
        'd': {"textfile": "1\nadditional content",
              "tooshort": "1"
              },
    }
}, archives_leading_dir=False)
@with_tempfile(mkdir=True)
def test_crawl_direct_links_local(src_path, updated, repo_path):
    from datalad.support.network import get_local_file_url
    tar_url = get_local_file_url(opj(src_path, '1.tar.gz'))
    ds = create(repo_path, text_no_annex=True)

    # first import:
    with chpwd(repo_path):
        crawl_init(
            {'paths': tar_url},
            save=True,
            template='direct_links'
        )
        crawl()

        ok_clean_git(repo_path)
        # TODO: leading dirs? should be d/textfile, ...
        ok_file_under_git(repo_path, "textfile", annexed=False)
        with open(opj(repo_path, "textfile"), 'r') as f:
            eq_("1\n", f.read())
        ok_file_under_git(repo_path, "tooshort", annexed=True)
        branches = ds.repo.get_branches()
        assert_in('incoming', branches)
        assert_in('incoming-processed', branches)
        [assert_not_in('1.tar.gz', f) for f in os.listdir(repo_path)]

        # get an update:
        os.unlink(opj(src_path, '1.tar.gz'))
        from shutil import copyfile
        copyfile(opj(updated, '1.tar.gz'), opj(src_path, '1.tar.gz'))

        crawl()

        with open(opj(repo_path, "textfile"), 'r') as f:
            eq_("1\nadditional content", f.read())

        ok_clean_git(repo_path)
        ok_file_under_git(repo_path, "textfile", annexed=False)
        ok_file_under_git(repo_path, "tooshort", annexed=True)
        branches = ds.repo.get_branches()
        assert_in('incoming', branches)
        assert_in('incoming-processed', branches)
        [assert_not_in('1.tar.gz', f) for f in os.listdir(repo_path)]

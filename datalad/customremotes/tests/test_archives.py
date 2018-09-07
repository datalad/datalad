# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for customremotes archives providing dl+archive URLs handling"""

from datalad.tests.utils import known_failure_v6
from datalad.tests.utils import known_failure_direct_mode


from ..archives import ArchiveAnnexCustomRemote
from ..base import AnnexExchangeProtocol
from ...support.annexrepo import AnnexRepo
from ...consts import ARCHIVES_SPECIAL_REMOTE
from ...tests.utils import *
from ...cmd import Runner, GitRunner
from ...utils import _path_

from . import _get_custom_runner

# both files will have the same content
# fn_inarchive_obscure = 'test.dat'
# fn_extracted_obscure = 'test2.dat'
fn_inarchive_obscure = get_most_obscure_supported_name()
fn_archive_obscure = fn_inarchive_obscure.replace('a', 'b') + '.tar.gz'
fn_extracted_obscure = fn_inarchive_obscure.replace('a', 'z')

#import line_profiler
#prof = line_profiler.LineProfiler()

# TODO: with_tree ATM for archives creates this nested top directory
# matching archive name, so it will be a/d/test.dat ... we don't want that probably
@with_direct
@with_tree(
    tree=(('a.tar.gz', {'d': {fn_inarchive_obscure: '123'}}),
          ('simple.txt', '123'),
          (fn_archive_obscure, (('d', ((fn_inarchive_obscure, '123'),)),)),
          (fn_extracted_obscure, '123')))
@with_tempfile()
def test_basic_scenario(direct, d, d2):
    fn_archive, fn_extracted = fn_archive_obscure, fn_extracted_obscure
    annex = AnnexRepo(d, runner=_get_custom_runner(d), direct=direct)
    annex.init_remote(
        ARCHIVES_SPECIAL_REMOTE,
        ['encryption=none', 'type=external', 'externaltype=%s' % ARCHIVES_SPECIAL_REMOTE,
         'autoenable=true'
         ])
    assert annex.is_special_annex_remote(ARCHIVES_SPECIAL_REMOTE)
    # We want two maximally obscure names, which are also different
    assert(fn_extracted != fn_inarchive_obscure)
    annex.add(fn_archive)
    annex.commit(msg="Added tarball")
    annex.add(fn_extracted)
    annex.commit(msg="Added the load file")

    # Operations with archive remote URL
    annexcr = ArchiveAnnexCustomRemote(path=d)
    # few quick tests for get_file_url

    eq_(annexcr.get_file_url(archive_key="xyz", file="a.dat"), "dl+archive:xyz#path=a.dat")
    eq_(annexcr.get_file_url(archive_key="xyz", file="a.dat", size=999), "dl+archive:xyz#path=a.dat&size=999")

    # see https://github.com/datalad/datalad/issues/441#issuecomment-223376906
    # old style
    eq_(annexcr._parse_url("dl+archive:xyz/a.dat#size=999"), ("xyz", "a.dat", {'size': 999}))
    eq_(annexcr._parse_url("dl+archive:xyz/a.dat"), ("xyz", "a.dat", {}))  # old format without size
    # new style
    eq_(annexcr._parse_url("dl+archive:xyz#path=a.dat&size=999"), ("xyz", "a.dat", {'size': 999}))
    eq_(annexcr._parse_url("dl+archive:xyz#path=a.dat"), ("xyz", "a.dat", {}))  # old format without size

    file_url = annexcr.get_file_url(
        archive_file=fn_archive,
        file=fn_archive.replace('.tar.gz', '') + '/d/'+fn_inarchive_obscure)

    annex.add_url_to_file(fn_extracted, file_url, ['--relaxed'])
    annex.drop(fn_extracted)

    list_of_remotes = annex.whereis(fn_extracted, output='descriptions')
    in_('[%s]' % ARCHIVES_SPECIAL_REMOTE, list_of_remotes)

    assert_false(annex.file_has_content(fn_extracted))
    annex.get(fn_extracted)
    assert_true(annex.file_has_content(fn_extracted))

    annex.rm_url(fn_extracted, file_url)
    assert_false(annex.drop(fn_extracted)['success'])

    annex.add_url_to_file(fn_extracted, file_url)
    annex.drop(fn_extracted)
    annex.get(fn_extracted)
    annex.drop(fn_extracted)  # so we don't get from this one next

    # Let's create a clone and verify chain of getting file through the tarball
    cloned_annex = AnnexRepo.clone(d, d2,
                                   runner=_get_custom_runner(d2),
                                   direct=direct)
    # we still need to enable manually atm that special remote for archives
    # cloned_annex.enable_remote('annexed-archives')

    assert_false(cloned_annex.file_has_content(fn_archive))
    assert_false(cloned_annex.file_has_content(fn_extracted))
    cloned_annex.get(fn_extracted)
    assert_true(cloned_annex.file_has_content(fn_extracted))
    # as a result it would also fetch tarball
    assert_true(cloned_annex.file_has_content(fn_archive))

    # Check if protocol was collected
    if os.environ.get('DATALAD_TESTS_PROTOCOLREMOTE'):
        assert_is_instance(annex.cmd_call_wrapper.protocol, AnnexExchangeProtocol)
        protocol_file = _path_(annex.path,
                               '.git/bin/git-annex-remote-datalad-archive')
        ok_file_has_content(protocol_file, "VERSION 1", re_=True, match=False)
        ok_file_has_content(protocol_file, "GETAVAILABILITY", re_=True, match=False)
        ok_file_has_content(protocol_file, "#!/bin/bash", re_=True, match=False)
    else:
        assert_false(isinstance(annex.cmd_call_wrapper.protocol, AnnexExchangeProtocol))

    # verify that we can drop if original archive gets dropped but available online:
    #  -- done as part of the test_add_archive_content.py
    # verify that we can't drop a file if archive key was dropped and online archive was removed or changed size! ;)


@with_tree(
    tree={'a.tar.gz': {'d': {fn_inarchive_obscure: '123'}}}
)
@known_failure_direct_mode  #FIXME
def test_annex_get_from_subdir(topdir):
    from datalad.api import add_archive_content
    annex = AnnexRepo(topdir, init=True)
    annex.add('a.tar.gz')
    annex.commit()
    add_archive_content('a.tar.gz', annex=annex, delete=True)
    fpath = opj(topdir, 'a', 'd', fn_inarchive_obscure)

    with chpwd(opj(topdir, 'a', 'd')):
        runner = Runner()
        runner(['git', 'annex', 'drop', '--', fn_inarchive_obscure])  # run git annex drop
        assert_false(annex.file_has_content(fpath))             # and verify if file deleted from directory
        runner(['git', 'annex', 'get', '--', fn_inarchive_obscure])   # run git annex get
        assert_true(annex.file_has_content(fpath))              # and verify if file got into directory


def test_get_git_environ_adjusted():
    gitrunner = GitRunner()
    env = {"GIT_DIR": "../../.git", "GIT_WORK_TREE": "../../", "TEST_VAR": "Exists"}

    # test conversion of relevant env vars from relative_path to correct absolute_path
    adj_env = gitrunner.get_git_environ_adjusted(env)
    assert_equal(adj_env["GIT_DIR"], abspath(env["GIT_DIR"]))
    assert_equal(adj_env["GIT_WORK_TREE"], abspath(env["GIT_WORK_TREE"]))

    # test if other environment variables passed to function returned unaltered
    assert_equal(adj_env["TEST_VAR"], env["TEST_VAR"])

    # test import of sys_env if no environment passed to function
    sys_env = gitrunner.get_git_environ_adjusted()
    assert_equal(sys_env["PWD"], os.environ.get("PWD"))


def test_no_rdflib_loaded():
    # rely on rdflib polluting stdout to see that it is not loaded whenever we load this remote
    # since that adds 300ms delay for no immediate use
    from ...cmd import Runner
    runner = Runner()
    with swallow_outputs() as cmo:
        runner.run([sys.executable, '-c', 'import datalad.customremotes.archives, sys; print([k for k in sys.modules if k.startswith("rdflib")])'],
               log_stdout=False, log_stderr=False)
        # print cmo.out
        assert_not_in("rdflib", cmo.out)
        assert_not_in("rdflib", cmo.err)


from .test_base import BASE_INTERACTION_SCENARIOS, check_interaction_scenario


@with_tree(tree={'archive.tar.gz': {'f1.txt': 'content'}})
def test_interactions(tdir):
    # Just a placeholder since constructor expects a repo
    repo = AnnexRepo(tdir, create=True, init=True)
    repo.add('archive.tar.gz')
    repo.commit('added')
    for scenario in BASE_INTERACTION_SCENARIOS + [
        [
            ('GETCOST', 'COST %d' % ArchiveAnnexCustomRemote.COST),
        ],
        [
            # by default we do not require any fancy init
            # no urls supported by default
            ('CLAIMURL http://example.com', 'CLAIMURL-FAILURE'),
            # we know that is just a single option, url, is expected so full
            # one would be passed
            ('CLAIMURL http://example.com roguearg', 'CLAIMURL-FAILURE'),
        ],
        # basic interaction failing to fetch content from archive
        [
            ('TRANSFER RETRIEVE somekey somefile', 'GETURLS somekey dl+archive:'),
            ('VALUE dl+archive://somekey2#path', None),
            ('VALUE dl+archive://somekey3#path', None),
            ('VALUE',
             re.compile(
                 'TRANSFER-FAILURE RETRIEVE somekey Failed to fetch any '
                 'archive containing somekey. Tried: \[\]')
             )
        ],
        # # incorrect response received from annex -- something isn't right but ... later
        # [
        #     ('TRANSFER RETRIEVE somekey somefile', 'GETURLS somekey dl+archive:'),
        #     # We reply with UNSUPPORTED-REQUEST in these cases
        #     ('GETCOST', 'UNSUPPORTED-REQUEST'),
        # ],
    ]:
        check_interaction_scenario(ArchiveAnnexCustomRemote, tdir, scenario)


from datalad.tests.utils import serve_path_via_http
@with_tree(tree=
    {'1.tar.gz':
         {
             'bu.dat': '52055957098986598349795121365535'*10000,
             'bu3.dat': '8236397048205454767887168342849275422'*10000
          },
    '2.tar.gz':
         {
             'bu2.dat': '17470674346319559612580175475351973007892815102'*10000
          },
    }
)
@serve_path_via_http()
@with_tempfile
def check_observe_tqdm(topdir, topurl, outdir):
    # just a helper to enable/use when want quickly to get some
    # repository with archives and observe tqdm
    from datalad.api import create, download_url, add_archive_content
    ds = create(outdir)
    for f in '1.tar.gz', '2.tar.gz':
        with chpwd(outdir):
            ds.repo.add_url_to_file(f, topurl + f)
            ds.add(f)
            add_archive_content(f, delete=True, drop_after=True)
    files = glob.glob(opj(outdir, '*'))
    ds.drop(files) # will not drop tarballs
    ds.repo.drop([], options=['--all', '--fast'])
    ds.get(files)
    ds.repo.drop([], options=['--all', '--fast'])
    # now loop so we could play with it outside
    print(outdir)
    # import pdb; pdb.set_trace()
    while True:
       sleep(0.1)

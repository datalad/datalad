# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for the universal datalad's annex customremote"""

from ...support.annexrepo import AnnexRepo
from ...consts import DATALAD_SPECIAL_REMOTE
from ...tests.utils import *
from ...support.external_versions import external_versions

from . import _get_custom_runner
from ...support.exceptions import CommandError
from ...downloaders.tests.utils import get_test_providers
from ..datalad import DataladAnnexCustomRemote


@with_tempfile()
@skip_if_no_network
def check_basic_scenario(url, d):
    annex = AnnexRepo(d, runner=_get_custom_runner(d))
    annex.init_remote(
        DATALAD_SPECIAL_REMOTE,
        ['encryption=none', 'type=external', 'externaltype=%s' % DATALAD_SPECIAL_REMOTE,
         'autoenable=true'])

    # TODO skip if no boto or no credentials
    get_test_providers(url) # so to skip if unknown creds

    # Let's try to add some file which we should have access to
    with swallow_outputs() as cmo:
        annex.add_urls([url])
        annex.commit("committing")

    # git-annex got a fix where it stopped replacing - in the middle of the filename
    # Let's cater to the developers who might have some intermediate version and not
    # easy to compare -- we will just check that only one file there is an that it
    # matches what we expect when outside of the development versions range:
    filenames = glob.glob(op.join(d, '3versions[-_]allversioned.txt'))
    assert_equal(len(filenames), 1)
    filename = op.basename(filenames[0])
    if external_versions['cmd:annex'] < '8.20200501':
        assert_in('_', filename)
    # Date after the fix in 8.20200501-53-gcabbc91b1
    elif external_versions['cmd:annex'] >= '8.20200512':
        assert_in('-', filename)
    else:
        pass  # either of those is ok

    whereis1 = annex.whereis(filename, output='full')
    eq_(len(whereis1), 2)  # here and datalad
    annex.drop(filename)

    whereis2 = annex.whereis(filename, output='full')
    eq_(len(whereis2), 1)  # datalad

    # if we provide some bogus address which we can't access, we shouldn't pollute output
    with swallow_outputs() as cmo, swallow_logs() as cml:
        with assert_raises(CommandError) as cme:
            annex.add_urls([url + '_bogus'])
        # assert_equal(cml.out, '')
        err, out = cmo.err, cmo.out
    assert_equal(out, '')
    assert_in('addurl: 1 failed', err)
    # and there should be nothing more


# unfortunately with_tree etc decorators aren't generators friendly thus
# this little adapters to test both on local and s3 urls
@with_tree(tree={'3versions-allversioned.txt': "somefile"})
@serve_path_via_http
def test_basic_scenario_local_url(p, local_url):
    check_basic_scenario("%s3versions-allversioned.txt" % local_url)


def test_basic_scenario_s3():
    check_basic_scenario('s3://datalad-test0-versioned/3versions-allversioned.txt')



from .test_base import BASE_INTERACTION_SCENARIOS, check_interaction_scenario


@with_tree(tree={}) #'archive.tar.gz': {'f1.txt': 'content'}})
def test_interactions(tdir):
    # Just a placeholder since constructor expects a repo
    repo = AnnexRepo(tdir, create=True, init=True)
    for scenario in BASE_INTERACTION_SCENARIOS + [
        [
            ('GETCOST', 'COST %d' % DataladAnnexCustomRemote.COST),
        ],
        [
            # We do support regular URLs
            ('CLAIMURL http://example.com', 'CLAIMURL-SUCCESS'),
            # we know that is just a single option, url, is expected so full
            # one would be passed
            #('CLAIMURL http://example.com roguearg', 'CLAIMURL-FAILURE'),

        ],
            # basic interaction failing to fetch content from archive
        [
            ('TRANSFER RETRIEVE somekey somefile', 'GETURLS somekey http:'),
            ('VALUE', 'GETURLS somekey https:'),
            ('VALUE', 'GETURLS somekey s3:'),
            ('VALUE', re.compile(
             'TRANSFER-FAILURE RETRIEVE somekey Failed to download from any'))
        ],
    ]:
        check_interaction_scenario(DataladAnnexCustomRemote, tdir, scenario)
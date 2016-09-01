# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from ..versions import get_versions
from ...tests.utils import assert_equal, assert_false
from ...tests.utils import assert_raises
from ...support.status import FileStatus
from nose.tools import assert_not_equal
from collections import OrderedDict as od


def test_get_versions_regex():
    # test matching of the version
    fn = 'f_r1.0_buga'
    # no versioneer, so version is left as the full match
    assert_equal(get_versions([fn], '_r\d+[.\d]*_'), od([('_r1.0_', {'fbuga': fn})]))
    # use versioneer to tune it up
    assert_equal(get_versions([fn], '_r\d+[.\d]*_', versioneer=lambda f, v, *args: v.strip('_r')), od([('1.0', {'fbuga': fn})]))
    # use group
    assert_equal(get_versions([fn], '_r(\d+[.\d]*)_'), od([('1.0', {'fbuga': fn})]))
    # and now non memorizing lookup for the trailing _ which then would leave it for the fpath
    assert_equal(get_versions([fn], '_r(\d+[.\d]*)(?=_)'), od([('1.0', {'f_buga': fn})]))
    # multiple groups
    # if no version group -- fail!
    with assert_raises(ValueError):
        assert_equal(get_versions([fn], '(_r(\d+[.\d]*))(?=_)'), od([('1.0', {'f_buga': fn})]))
    assert_equal(get_versions([fn], '(_r(?P<version>\d+[.\d]*))(?=_)'), od([('1.0', {'f_buga': fn})]))
    # add subdirectory
    assert_equal(get_versions(['d1/d2/' + fn], '(_r(?P<version>\d+[.\d]*))(?=_)'), od([('1.0', {'d1/d2/f_buga': 'd1/d2/'+fn})]))


def test_get_versions():
    assert_equal(get_versions(['f1'], '\d+'), od([('1', {'f': 'f1'})]))
    assert_equal(get_versions(['f1', 'f2'], '\d+'), od([('1', {'f': 'f1'}), ('2', {'f': 'f2'})]))
    # with default overlay=True, we should get both versions of two similar files in different subdirs
    # since we operate at the level of the entire path.  note lookbehind assertion in regex to avoid matching d
    assert_equal(get_versions(['d1/f1', 'd2/f2'], '(?<=f)\d+'), od([('1', {'d1/f': 'd1/f1'}), ('2', {'d2/f': 'd2/f2'})]))

    # lets make a complex one with non versioned etc
    assert_equal(get_versions(['un', 'd1/f1', 'd1/f2', 'd2/f2'], '(?<=f)\d+'),
                 od([(None, {'un': 'un'}), ('1', {'d1/f': 'd1/f1'}), ('2', {'d1/f': 'd1/f2', 'd2/f': 'd2/f2'})]))

    # but if there is a conflict with unversioned -- fail!
    with assert_raises(ValueError):
        get_versions(['d1/f', 'd1/f1', 'd1/f2', 'd2/f2'], '(?<=f)\d+')

    # it should all work as fine if we give statuses although they aren't used atm
    # but they all should be returned back within entries
    assert_equal(get_versions([('f1', None)], '\d+'), od([('1', {'f': ('f1', None)})]))
    assert_equal(get_versions(['un', ('d1/f1', None), 'd1/f2', 'd2/f2'], '(?<=f)\d+'),
                 od([(None, {'un': 'un'}), ('1', {'d1/f': ('d1/f1', None)}), ('2', {'d1/f': 'd1/f2', 'd2/f': 'd2/f2'})]))


def test_get_versions_openfmri_dropped_models():
    # discovered while working with ds000017 that models were dropped completely from
    # extraction... it seems we were missing use of always_versioned
    staged = ['.datalad/crawl/statuses/incoming.json', '.gitattributes', 'README.txt', 'changelog.txt',
              'ds017A_R1.1.0_raw.tgz',
              'ds017A_models.tgz', 'ds017A_raw.tgz']
    versions = get_versions(
        staged, regex='_R(?P<version>\d+[\.\d]*)(?=[\._])',
        always_versioned='ds0.*',
        unversioned='default', default='1.0.0')
    target_versions = od([
        (None, {'changelog.txt': 'changelog.txt',
                '.datalad/crawl/statuses/incoming.json': '.datalad/crawl/statuses/incoming.json',
                '.gitattributes': '.gitattributes',
                'README.txt': 'README.txt'}),
        ('1.0.0', {'ds017A_raw.tgz': 'ds017A_raw.tgz',
                   'ds017A_models.tgz': 'ds017A_models.tgz'}),
        ('1.1.0', {'ds017A_raw.tgz': 'ds017A_R1.1.0_raw.tgz'})])
    assert_equal(versions, target_versions)


def test_get_versions_default_version():
    # by default we raise exception if conflict was detected
    assert_raises(ValueError, get_versions, ['f1', 'f'], '\d+')
    # but for default default_version we would need mtime, so raising another one again
    assert_raises(ValueError, get_versions, ['f1', 'f'], '\d+', unversioned='default')
    fstatus = FileStatus(mtime=1456495187)
    assert_equal(get_versions(['f1', ('f', fstatus)], '\d+', unversioned='default'),
                 od([('0.0.20160226', {'f': ('f', fstatus)}), ('1', {'f': 'f1'})]))
    assert_equal(get_versions(['f1', ('f', fstatus)], '\d+', unversioned='default', default='1.0.0'),
                 od([('1', {'f': 'f1'}), ('1.0.0', {'f': ('f', fstatus)})]))
    # and we should be able to assign default one which has no % in its default
    # even without mtime
    assert_equal(get_versions(['f1', 'f'], '\d+', unversioned='default', default='0.0.1'),
                 od([('0.0.1', {'f': 'f'}), ('1', {'f': 'f1'})]))

    # if default is specified but not unversioned -- the same
    assert_equal(get_versions(['f1', 'f'], '\d+', default='0.0.1'),
             od([('0.0.1', {'f': 'f'}), ('1', {'f': 'f1'})]))

    # and what about always versioned and some which do not have to be versioned?
    # test run without forcing
    assert_equal(get_versions(['README', 'f1', 'f', ('ds', fstatus)], '\d+', default='%Y'),
                 od([(None, {'README': 'README', 'ds': ('ds', fstatus)}),
                     ('1', {'f': 'f1'}),
                     ('2016', {'f': 'f'})]))
    assert_equal(get_versions(['README', 'f1', 'f', ('ds', fstatus)], '\d+', default='%Y', always_versioned='^ds.*'),
             od([(None, {'README': 'README'}),
                 ('1', {'f': 'f1'}),
                 ('2016', {'f': 'f', 'ds': ('ds', fstatus)})]))


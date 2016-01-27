# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from ..stats import ActivityStats, _COUNTS

from ...tests.utils import assert_equal
from ...tests.utils import assert_not_equal
from ...tests.utils import assert_raises
from ...tests.utils import assert_in

def test_ActivityStats_basic():
    stats = ActivityStats()
    assert_raises(AttributeError, setattr, stats, "unknown_attribute", 1)

    for c in _COUNTS:
        assert_equal(getattr(stats, c), 0)

    stats.files += 1
    assert_equal(stats.files, 1)
    stats.increment('files')
    assert_equal(stats.files, 2)

    assert_equal(stats.as_dict()['files'], 2)
    # smoke tests
    assert_equal(stats.as_str(), stats.as_str(mode='full'))
    assert_equal(len(stats.as_str(mode='line').split('\n')), 1)

    assert_in('files=2', repr(stats))
    stats.reset()
    for c in _COUNTS:
        assert_equal(getattr(stats, c), 0)

    # Check a copy of stats
    stats_total = stats.get_total()
    assert_equal(stats_total.files, 2)
    stats.files += 1
    assert_equal(stats.files, 1)
    assert_equal(stats_total.files, 2)  # shouldn't change -- a copy!

    # Let's add some merges
    stats.merges.append(('upstream', 'master'))
    stats_total = stats.get_total()
    assert_equal(stats_total.merges, stats.merges)

    assert_equal(stats.as_str(), """Files processed: 1
Branches merged: upstream->master""")
    assert_equal(stats.as_str(mode='line'), "Files processed: 1,  Branches merged: upstream->master")

    stats.urls += 2
    stats.downloaded += 1
    stats.downloaded_size += 123456789  # will invoke formatter
    assert_in("size: 123.5 MB", stats.as_str())

def test_ActivityStats_comparisons():
    stats1 = ActivityStats()
    stats2 = ActivityStats()
    assert_equal(stats1, stats2)
    stats1.files += 1
    assert_not_equal(stats1, stats2)

    # if we reset -- should get back the same although totals should be different
    stats1.reset()
    assert_equal(stats1.as_str(), stats2.as_str())
    assert_equal(stats1, stats2)
    assert_not_equal(stats1.get_total(), stats2.get_total())
    #stats1.reset(full=True)
    #assert_equal(stats1, stats2)

def test_add():
    stats1 = ActivityStats()
    stats2 = ActivityStats()
    stats1.files += 1
    stats2.files += 1
    stats2.urls += 1
    assert_equal(stats1, ActivityStats(files=1))
    assert_equal(stats2, ActivityStats(files=1, urls=1))

    stats1 += stats2
    assert_equal(stats1, ActivityStats(files=2, urls=1))
    assert_equal(stats1.get_total(), ActivityStats(files=2, urls=1))

    stats3 = stats1 + stats2
    # no changes to stats1 or stats2
    assert_equal(stats1, ActivityStats(files=2, urls=1))
    assert_equal(stats1.get_total(), ActivityStats(files=2, urls=1))
    assert_equal(stats2, ActivityStats(files=1, urls=1))
    assert_equal(stats3.get_total(), ActivityStats(files=3, urls=2))

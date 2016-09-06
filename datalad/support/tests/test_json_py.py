# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging

from datalad.support.json_py import load
from datalad.support.json_py import JSONDecodeError

from datalad.tests.utils import with_tempfile
from datalad.tests.utils import eq_
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_in
from datalad.tests.utils import swallow_logs


@with_tempfile(content=b'{"Authors": ["A1"\xc2\xa0, "A2"]}')
def test_load_screwy_unicode(fname):
    # test that we can tollerate some screwy unicode embeddings within json
    assert_raises(JSONDecodeError, load, fname, fixup=False)
    with swallow_logs(new_level=logging.WARNING) as cml:
        eq_(load(fname), {'Authors': ['A1', 'A2']})
        assert_in('Failed to decode content', cml.out)


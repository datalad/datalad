# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from mock import patch
from ..config import ConfigManager
from .utils import ok_, eq_, assert_raises, assert_greater

def test_config_empty():
    # nothing to load
    config = ConfigManager(load_default=False)
    eq_(config._get_file_candidates(), [])
    # nevertheless we should be able to specify variables via env

    assert_raises(ValueError, config.getboolean, 'tests', 'somenonexistingone')
    with patch.dict('os.environ', {'DATALAD_TESTS_NONETWORK': '1'}):
        config.reload()
        ok_(config.getboolean('tests', 'nonetwork'))
        eq_(config.get_as_dtype('tests', 'nonetwork', int), 1)

def test_config_load():
    config = ConfigManager()
    candidates = config._get_file_candidates()
    assert_greater(len(candidates), 2)  # at least system, user, local
    assert_greater(5, len(candidates))  # but shouldn't be too many

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

def test_config_load():
    config = ConfigManager()
    candidates = config._get_file_candidates()
    assert_greater(len(candidates), 2)  # at least system, user, local
    assert_greater(5, len(candidates))  # but shouldn't be too many

from .utils import optional_args, wraps
from .utils import with_tempfile


@optional_args
def with_configmanager(func, content=None):
    """Helper to run a test loading configuration from the sample config

    TODO: If content is a list, multiple files are created/loaded
    """

    @wraps(func)
    @with_tempfile(content=content)
    def newfunc(*args, **kwargs):
        config_files = args[-1:] if content is not None else None
        cm = ConfigManager(config_files, load_default=False)
        try:
            return func(*args[:-1] + (cm,), **kwargs)
        finally:
            pass  # nothing to do for now

    return newfunc


def _test_basic_variables(config):
    with patch.dict(
            'os.environ',
            {
                'DATALAD_TESTS_NONETWORK': '1',
                # With subsection, we don't care about spaces
                #'DATALAD_TESTS_'
            }):
        config.reload()
        ok_(config.getboolean('tests', 'nonetwork'))
        eq_(config.get_as_dtype('tests', 'nonetwork', int), 1)


@with_configmanager
def test_config_none(config):
    eq_(config._get_file_candidates(), [])
    # nevertheless we should be able to specify variables via env
    assert_raises(ValueError, config.getboolean, 'tests', 'somenonexistingone')
    _test_basic_variables(config)
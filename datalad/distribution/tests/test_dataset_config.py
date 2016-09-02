# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test Dataset configuration

"""

from ..dataset import Dataset

from os.path import join as opj
from nose.tools import ok_, eq_, assert_false, assert_equal, assert_true
from datalad.tests.utils import with_tree
from datalad.api import create

# Let's document any configuration option supported in this
# reference configuration
_config_file_content = """\
[datalad "dataset"]
    id = nothing
"""

_dataset_config_template = {
    'ds': {
    '.datalad': {
        'config': _config_file_content}}}


@with_tree(tree=_dataset_config_template)
def test_configuration_access(path):
    ds = Dataset(opj(path, 'ds'))
    # there is something prior creation
    assert_true(ds.config is not None)
    # creation must change the uuid setting
    assert_equal(ds.config['datalad.dataset.id'], 'nothing')
    # create resets this value and records the actual uuid
    ds.create(force=True)
    assert_equal(ds.config.get_value('datalad.dataset', 'id', default='nothing'), ds.id)

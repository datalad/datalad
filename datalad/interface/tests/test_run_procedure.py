# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad run-procedure

"""

__docformat__ = 'restructuredtext'

import os.path as op

from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import skip_if_on_windows
from datalad.tests.utils import with_tree

from datalad.distribution.dataset import Dataset
from datalad.api import run_procedure
from datalad.api import clean


@skip_if_on_windows
#@ignore_nose_capturing_stdout
@with_tree(tree={
    'code': {'datalad_test_proc.py': """\
import sys
import os.path as op
from datalad.api import add, Dataset

with open(op.join(sys.argv[1], 'fromproc.txt'), 'w') as f:
    f.write('hello\\n')
add(dataset=Dataset(sys.argv[1]), path='fromproc.txt')
"""}})
def test_basics(path):
    ds = Dataset(path).create(force=True)
    # TODO: this procedure would leave a clean dataset, but `run` cannot handle dirty
    # input yet, so manual for now
    # V6FACT: this leaves the file staged, but not committed
    ds.add('code', to_git=True)
    # V6FACT: even this leaves it staged
    ds.add('.')
    # V6FACT: but this finally commits it
    ds.save()
    # TODO remove above two lines
    ds.run_procedure('setup_yoda_dataset')
    ok_clean_git(ds.path)
    # configure dataset to look for procedures in its code folder
    ds.config.add(
        'datalad.locations.dataset-procedures',
        'code',
        where='dataset')
    # configure dataset to run the demo procedure prior to the clean command
    ds.config.add(
        'datalad.clean.proc-pre',
        'datalad_test_proc',
        where='dataset')
    # make clean (until run can handle it)
    # XXX for some reason `save` doesn't do the job in direct mode
    ds.add(op.join('.datalad', 'config'))
    ok_clean_git(ds.path)
    # run command that should trigger the demo procedure
    ds.clean()
    # look for traces
    ok_file_has_content(op.join(ds.path, 'fromproc.txt'), 'hello\n')
    ok_clean_git(ds.path)


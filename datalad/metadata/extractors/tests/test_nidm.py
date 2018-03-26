# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test NIDM extractor"""

from shutil import copy
from os.path import dirname
from os.path import join as opj
from datalad.api import Dataset
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count


@with_tempfile(mkdir=True)
def test_nidm(path):
    ds = Dataset(path).create()
    ds.config.add('datalad.metadata.nativetype', 'nidm', where='dataset')
    # imagine filling the dataset up with something that NIDM info could be
    copy(
        opj(dirname(dirname(dirname(__file__))), 'tests', 'data', 'nifti1.nii.gz'),
        path)
    # extracted from
    ds.add('.')
    # all nice and tidy, nothing untracked
    ok_clean_git(ds.path)
    # engage the extractor(s)
    res = ds.aggregate_metadata()
    # aggregation done without whining
    assert_status('ok', res)
    res = ds.metadata(reporton='datasets')
    # ATM we do not forsee file-based metadata to come back from NIDM
    assert_result_count(res, 1)
    # kill version info
    core = res[0]['metadata']['datalad_core']
    core.pop('version', None)
    core.pop('refcommit')
    # show full structure of the assembled metadata from demo content
    assert_result_count(
        res, 1,
        metadata={
            "@context": {
                "@vocab": "http://docs.datalad.org/schema_v2.0.json"
            },
            "datalad_core": {
                "@id": ds.id
            },
            "nidm": {
                "@context": {
                    "mydurationkey": {
                        "@id": "time:Duration"
                    },
                    "myvocabprefix": {
                        "@id": "http://purl.org/ontology/mydefinition",
                        "description": "I am a vocabulary",
                        "type": "http://purl.org/dc/dcam/VocabularyEncodingScheme"
                    }
                },
                "mydurationkey": 0.6
            }
        })

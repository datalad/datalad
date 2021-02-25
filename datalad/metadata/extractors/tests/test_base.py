# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test all extractors at a basic level"""

from pkg_resources import iter_entry_points
from inspect import isgenerator
from datalad.api import Dataset
from datalad.tests.utils import (
    assert_equal,
    assert_repo_status,
    known_failure_githubci_win,
    SkipTest,
    with_tree,
)


@with_tree(tree={'file.dat': ''})
def check_api(annex, path):
    ds = Dataset(path).create(force=True, annex=annex)
    ds.save()
    assert_repo_status(ds.path)

    processed_extractors, skipped_extractors = [], []
    for extractor_ep in iter_entry_points('datalad.metadata.extractors'):
        # we need to be able to query for metadata, even if there is none
        # from any extractor
        try:
            extractor_cls = extractor_ep.load()
        except Exception as exc:
            exc_ = str(exc)
            skipped_extractors += [exc_]
            continue
        extractor = extractor_cls(
            ds, paths=['file.dat'])
        meta = extractor.get_metadata(
            dataset=True,
            content=True)
        # we also get something for the dataset and something for the content
        # even if any of the two is empty
        assert_equal(len(meta), 2)
        dsmeta, contentmeta = meta
        assert (isinstance(dsmeta, dict))
        assert hasattr(contentmeta, '__len__') or isgenerator(contentmeta)
        # verify that generator does not blow and has an entry for our
        # precious file
        cm = dict(contentmeta)
        # datalad_core does provide some (not really) information about our
        # precious file
        if extractor_ep.name == 'datalad_core':
            assert 'file.dat' in cm
        elif extractor_ep.name == 'annex':
            if annex:
                # verify correct key, which is the same for all files of 0 size
                assert_equal(
                    cm['file.dat']['key'],
                    'MD5E-s0--d41d8cd98f00b204e9800998ecf8427e.dat'
                )
            else:
                # no metadata on that file
                assert not cm
        processed_extractors.append(extractor_ep.name)
    assert "datalad_core" in processed_extractors, \
        "Should have managed to find at least the core extractor extractor"
    if skipped_extractors:
        raise SkipTest(
            "Not fully tested/succeded since some extractors failed"
            " to load:\n%s" % ("\n".join(skipped_extractors)))


@known_failure_githubci_win
def test_api_git():
    # should tollerate both pure git and annex repos
    yield check_api, False


@known_failure_githubci_win
def test_api_annex():
    yield check_api, True

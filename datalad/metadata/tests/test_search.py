# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Some additional tests for search command (some are within test_base)"""

import os
from mock import patch
from datalad.api import Dataset, aggregate_metadata, install
from nose.tools import assert_equal, assert_raises
from datalad.utils import chpwd
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_is_generator
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_testsui
from datalad.support.exceptions import NoDatasetArgumentFound

from os.path import join as opj

from datalad.api import search
from datalad.metadata import search as search_mod


@with_testsui(interactive=False)
@with_tempfile(mkdir=True)
def test_search_outside1_noninteractive_ui(tdir):
    # we should raise an informative exception
    with chpwd(tdir):
        with assert_raises(NoDatasetArgumentFound) as cme:
            list(search("bu"))
        assert_in('UI is not interactive', str(cme.exception))


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_search_outside1(tdir, newhome):
    with chpwd(tdir):
        # should fail since directory exists, but not a dataset
        # should not even waste our response ;)
        always_render = os.environ.get('DATALAD_API_ALWAYS_RENDER')
        with patch.object(search_mod, 'LOCAL_CENTRAL_PATH', newhome):
            if always_render:
                # we do try to render results which actually causes exception
                # to come right away
                assert_raises(NoDatasetArgumentFound, search, "bu")
            else:
                gen = search("bu")
                assert_is_generator(gen)
                assert_raises(NoDatasetArgumentFound, next, gen)

        # and if we point to some non-existing dataset -- the same in both cases
        # but might come before even next if always_render
        with assert_raises(ValueError):
            next(search("bu", dataset=newhome))


@with_testsui(responses='yes')
@with_tempfile(mkdir=True)
@with_tempfile()
def test_search_outside1_install_central_ds(tdir, central_dspath):
    with chpwd(tdir):
        # let's mock out even actual install/search calls
        with \
            patch.object(search_mod, 'LOCAL_CENTRAL_PATH', central_dspath), \
            patch('datalad.api.install',
                  return_value=Dataset(central_dspath)) as mock_install, \
            patch('datalad.distribution.dataset.Dataset.search',
                  new_callable=_mock_search):
            _check_mocked_install(central_dspath, mock_install)

            # now on subsequent run, we want to mock as if dataset already exists
            # at central location and then do search again
            from datalad.ui import ui
            ui.add_responses('yes')
            mock_install.reset_mock()
            with patch(
                    'datalad.distribution.dataset.Dataset.is_installed',
                    True):
                _check_mocked_install(central_dspath, mock_install)

            # and what if we say "no" to install?
            ui.add_responses('no')
            mock_install.reset_mock()
            with assert_raises(NoDatasetArgumentFound):
                list(search(".", regex=True))

            # and if path exists and is a valid dataset and we say "no"
            Dataset(central_dspath).create()
            ui.add_responses('no')
            mock_install.reset_mock()
            with assert_raises(NoDatasetArgumentFound):
                list(search(".", regex=True))

_mocked_search_results = [
    ('ds1', {'f': 'v'}),
    ('d2/ds2', {'f1': 'v1'})
]


class _mock_search(object):
    def __call__(*args, **kwargs):
        for loc, report in _mocked_search_results:
            yield loc, report


def _check_mocked_install(central_dspath, mock_install):
    gen = search(".", regex=True)
    assert_is_generator(gen)
    assert_equal(
        list(gen), [(opj(central_dspath, loc), report)
                    for loc, report in _mocked_search_results])
    mock_install.assert_called_once_with(central_dspath, source='///')


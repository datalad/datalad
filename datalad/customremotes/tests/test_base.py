# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for the base of our custom remotes"""

from datalad.tests.utils import known_failure_direct_mode

from os.path import isabs

from datalad.tests.utils import with_tree
from datalad.support.annexrepo import AnnexRepo

from ..base import AnnexCustomRemote, DEFAULT_AVAILABILITY, DEFAULT_COST
from datalad.tests.utils import eq_

@with_tree(tree={'file.dat': ''})
@known_failure_direct_mode  #FIXME
def test_get_contentlocation(tdir):
    repo = AnnexRepo(tdir, create=True, init=True)
    repo.add('file.dat')
    repo.commit('added file.dat')

    key = repo.get_file_key('file.dat')
    cr = AnnexCustomRemote(tdir)
    key_path = cr.get_contentlocation(key, absolute=False)
    assert not isabs(key_path)
    key_path_abs = cr.get_contentlocation(key, absolute=True)
    assert isabs(key_path_abs)
    assert cr._contentlocations == {key: key_path}
    repo.drop('file.dat', options=['--force'])
    assert not cr.get_contentlocation(key, absolute=True)


class FIFO(object):
    """A helper to mimic interactions with git-annex parent process

    We just need a FIFO for input into remote, and one FIFO for output"""
    def __init__(self, content=None, default=None):
        """

        Parameters
        ----------
        content
        default
          If defined, will be the one returned if empty.
          If not defined -- would raise an Exception
        """
        self.content = content or []
        self.default = default

    def _pop(self):
        # return empty line, usually to signal
        if self.content:
            v = self.content.pop(0)
            # allow for debug
            if v.startswith('DEBUG '):
                # next one
                return self._pop()
            return v
        else:
            if self.default is not None:
                return self.default
            else:
                raise IndexError("we are empty")

    def write(self, l):
        self.content.append(l)

    def read(self):
        return self._pop()

    def readline(self):
        return self._pop().rstrip('\n')

    def flush(self):
        pass  # working hard


def check_interaction_scenario(remote_class, tdir, scenario):
    # First one is always version and
    # Final empty command to signal the end of the transactions
    scenario = [(None, 'VERSION 1')] + scenario +  [('', None)]
    fin, fout = FIFO(), FIFO(default='')
    # Feed all "in" lines we expect git-annex to provide to us
    for in_, out_ in scenario:
        if in_ is not None:
            fin.write(in_ + '\n')
    cr = remote_class(path=tdir, fin=fin, fout=fout)

    cr.main()

    for in_, out_ in scenario:
        if out_ is not None:
            out_read = fout.readline()
            if isinstance(out_, type(ERROR_ARGS)):
                assert out_.match(out_read), (out_, out_read)
            else:
                eq_(out_, out_read)
    out_read = fout.readline()
    eq_(out_read, '')  # nothing left to say


import re
ERROR_ARGS = re.compile('ERROR .*(missing|takes) .*\d+ .*argument')
BASE_INTERACTION_SCENARIOS = [
    [],  # default of doing nothing
    [  # support of EXPORT which by default is not supported
        ('EXPORTSUPPORTED', 'EXPORTSUPPORTED-FAILURE'),
    ],
    [  # some unknown option
        ('FANCYNEWOPTION', 'UNSUPPORTED-REQUEST'),
    ],
    [
        # get the COST etc for , and make sure we do not
        # fail right on unsupported
        ('FANCYNEWOPTION', 'UNSUPPORTED-REQUEST'),
        ('GETCOST', re.compile('^COST [0-9]+$')),
        ('GETCOST roguearg', ERROR_ARGS),
        ('INITREMOTE', 'INITREMOTE-SUCCESS'),
        # but if not enough params -- ERROR_ARGS
        ('CLAIMURL', ERROR_ARGS),
        # so far none supports STORE
        ('TRANSFER STORE somekey somefile', 'UNSUPPORTED-REQUEST'),
    ]
]


@with_tree(tree={'file.dat': ''})
def test_interactions(tdir):
    # Just a placeholder since constructor expects a repo
    repo = AnnexRepo(tdir, create=True, init=True)
    repo.add('file.dat')
    repo.commit('added file.dat')
    for scenario in BASE_INTERACTION_SCENARIOS + [
        [
            ('GETAVAILABILITY', 'AVAILABILITY %s' % DEFAULT_AVAILABILITY),
            ('GETCOST', 'COST %d' % DEFAULT_COST),
            ('TRANSFER RETRIEVE somekey somefile',
             re.compile('TRANSFER-FAILURE RETRIEVE somekey NotImplementedError().*')),
        ],
        [
            # by default we do not require any fancy init
            # no urls supported by default
            ('CLAIMURL http://example.com', 'CLAIMURL-FAILURE'),
            # we know that is just a single option, url, is expected so full
            # one would be passed
            ('CLAIMURL http://example.com roguearg', 'CLAIMURL-FAILURE'),
        ]
    ]:
        check_interaction_scenario(AnnexCustomRemote, tdir, scenario)


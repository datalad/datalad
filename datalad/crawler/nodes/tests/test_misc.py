# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os
from stat import *
from os import chmod
from os.path import join as opj
from datalad.tests.utils import with_tempfile, eq_, ok_, SkipTest
from six import next
from collections import OrderedDict

from ..misc import get_disposition_filename
from ..misc import fix_permissions
from ..misc import get_url_filename
from ..misc import range_node
from ..misc import interrupt_if
from ..misc import skip_if
from ..misc import continue_if
from ..misc import func_to_node
from ..misc import sub
from ..misc import find_files
from ..misc import switch
from ..misc import assign
from ..misc import _act_if
from ..misc import rename
from ..misc import debug
from ..misc import Sink
from ...pipeline import FinishPipeline
from ....tests.utils import with_tree
from ....utils import updated
from ...tests.test_pipeline import _out
from datalad.tests.utils import skip_if_no_network
from datalad.tests.utils import use_cassette
from datalad.tests.utils import ok_generator
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_re_in
from datalad.tests.utils import assert_equal
from datalad.tests.utils import assert_false
from datalad.tests.utils import swallow_logs

import logging

from mock import patch
from nose.tools import eq_, assert_raises
from nose import SkipTest


# TODO: redo on a local example
# TODO: seems vcr fetches entire response not just the header which makes this test url
#       in particular not appropriate
#@skip_if_no_network
#@use_cassette('brain-map.org-1', return_body='')
def test_get_disposition_filename():
    input = {'url': 'http://human.brain-map.org/api/v2/well_known_file_download/157722290'}
    with patch('datalad.crawler.nodes.misc.get_url_disposition_filename',
               return_value="T1.nii.gz"):
        output = list(get_disposition_filename(input))
    eq_(len(output), 1)
    eq_(output[0]['filename'], 'T1.nii.gz')


@with_tempfile(mkdir=True)
def test_fix_permissions(outdir):
    filepath = opj(outdir, 'myfile.txt')
    filepath2 = opj(outdir, 'badfile.py')
    filepath3 = opj(outdir, 'nopath.txt')
    with open(filepath, 'w'), open(filepath2, 'w'), open(filepath3, 'w'):
        pass

    gen = fix_permissions('\.(txt|csv)', True, 'filename')

    # make file executable for those that can read it
    filename = opj(outdir, 'myfile.txt')
    chmod(filename, 0o643)
    data = {'url': 'http://mapping.org/docs/?num=45', 'filename': filename}
    eq_(list(gen(data)), [{'url': 'http://mapping.org/docs/?num=45', 'filename': filename}])
    eq_(oct(os.stat(filename)[ST_MODE])[-3:], '753')

    # file that does not match regex
    badfile = opj(outdir, 'badfile.py')
    chmod(badfile, 0o666)
    baddata = {'url': 'http://mapping.org/docs/?num=45', 'filename': badfile}
    eq_(list(gen(baddata)), [{'url': 'http://mapping.org/docs/?num=45', 'filename': badfile}])
    eq_(oct(os.stat(badfile)[ST_MODE])[-3:], '666')

    # file that is actually a dir
    dirdata = {'url': 'http://mapping.org/docs/?num=45', 'filename': outdir}
    eq_(list(gen(dirdata)), [{'url': 'http://mapping.org/docs/?num=45', 'filename': outdir}])

    # path given in args
    nopath = opj(outdir, 'nopath.txt')
    chmod(nopath, 0o643)
    datafile = {'url': 'http://mapping.org/docs/?num=45', 'filename': 'nopath.txt'}
    gen = fix_permissions('\.txt', True, 'filename', outdir)
    eq_(list(gen(datafile)), [{'url': 'http://mapping.org/docs/?num=45', 'filename': 'nopath.txt'}])
    eq_(oct(os.stat(filename)[ST_MODE])[-3:], '753')

    # take permissions away from everyone
    gen = fix_permissions('.txt', False, 'filename')
    filename = opj(outdir, 'myfile.txt')
    chmod(filename, 0o743)
    data = {'url': 'http://mapping.org/docs/?num=45', 'filename': filename}
    eq_(list(gen(data)), [{'url': 'http://mapping.org/docs/?num=45', 'filename': filename}])
    eq_(oct(os.stat(filename)[ST_MODE])[-3:], '642')


def test_get_url_filename():
    input = {'url': 'http://human.brain-map.org/api/v2/well_known_file_download/157722290'}
    output = list(get_url_filename(input))
    eq_(len(output[0]), 2)
    eq_(len(output), 1)
    eq_(output, [{'url': 'http://human.brain-map.org/api/v2/well_known_file_download/157722290', 'filename': '157722290'}])


def test_sink():
    data = {'x': 'y', 'g': 'h', 'a': 'b'}

    keys = ['x', 'a']
    nomatch = ['z']

    # no arguments
    genempty = Sink()
    eq_(list(genempty(data)), [{'a': 'b', 'x': 'y', 'g': 'h'}])

    # check the internal state
    eq_(list(genempty.data), [{'a': 'b', 'x': 'y', 'g': 'h'}])

    # if key for sunk data is specified
    gen = Sink(output='result')
    eq_(list(gen(data)), [{'a': 'b', 'x': 'y', 'result': [{'a': 'b', 'x': 'y', 'g': 'h'}], 'g': 'h'}])
    eq_(list(gen.data), [{'a': 'b', 'x': 'y', 'g': 'h'}])

    # if list of keys is specified
    genkeys = Sink(keys, 'result')
    eq_(list(genkeys(data)), [{'a': 'b', 'x': 'y', 'result': [{'a': 'b', 'x': 'y'}], 'g': 'h'}])
    eq_(list(genkeys.data), [{'a': 'b', 'x': 'y'}])

    # if list of keys has no match
    gentwo = Sink(nomatch, 'result')
    eq_(list(gentwo(data)), [{'a': 'b', 'result': [{}], 'x': 'y', 'g': 'h'}])
    eq_(list(gentwo.data), [{}])

    # check that data's key/value pair matches will be sunk again
    eq_(list(gentwo(data)), [{'a': 'b', 'x': 'y', 'result': [{}, {}], 'g': 'h'}])
    eq_(list(gentwo.data), [{}, {}])


def test_get_values():
    data = {'x': 'y', 'g': 'h', 'a': 'b'}
    keys = ['x', 'a']

    gen = Sink()
    list(gen(data))
    eq_(gen.get_values(keys), [['y', 'b']])


def test_assign():
    data = {'x': 'y'}

    gen = assign({'key': 'value', 'aa': 'bb %(x)s'}, interpolate=True)
    eq_(list(gen(data)), [{'key': 'value', 'aa': 'bb y', 'x': 'y'}])

    genf = assign({'key': 'value %(x)s'}, interpolate=False)
    eq_(list(genf(data)), [{'key': 'value %(x)s', 'x': 'y'}])

    datadup = {'x': 'z'}

    gen = assign({'x': 'value', 'g': 'y %(x)s'}, interpolate=True)
    eq_(list(gen(datadup)), [{'x': 'value', 'g': 'y z'}])


def test__act_if():
    values = {'x': 'y', 'a': 'b'}
    data = {'x': 'y'}
    datamatch = {'x': 'y', 'a': 'b'}

    # matched = true
    gen = _act_if(values)
    eq_(list(gen(datamatch)), [datamatch])

    # matched = false
    genfal = _act_if(values, re=True, negate=False)
    eq_(list(genfal(data)), [{'x': 'y'}])

    # matched = true
    gent = _act_if(values, re=True, negate=True)
    eq_(list(gent(datamatch)), [{'a': 'b', 'x': 'y'}])


def test_rename():
    data = {'x': 'y'}
    datamulti = {'x': 'y', 'aa': 'bb'}

    gen = rename({'x': 'newkey', 'aa': 'bb'})
    genmulti = rename({'x': 'newkey', 'aa': 'newerkey'})

    eq_(list(gen(data)), [{'newkey': 'y'}])
    eq_(list(genmulti(datamulti)), [{'newkey': 'y', 'newerkey': 'bb'}])


def test_range_node():
    eq_(list(range_node(1)()), [{'output': 0}])
    eq_(list(range_node(2)()), [{'output': 0}, {'output': 1}])


def test_interrupt_if():
    n = interrupt_if({'v1': 'done'})
    assert_raises(FinishPipeline, next, n(dict(v1='done')))
    assert_raises(FinishPipeline, next, n(dict(v1='done', someother=123)))
    tdict = dict(v1='not yet', someother=123)
    # and that we would interrupt while matching multiple values
    eq_(list(n(tdict)), [tdict])
    assert_raises(FinishPipeline, next, interrupt_if(tdict)(tdict))

    eq_(list(interrupt_if({'v1': 'ye.$'})(tdict)), [tdict])
    assert_raises(FinishPipeline, next, interrupt_if({'v1': 'ye.$'}, re=True)(tdict))


def test_skip_if():
    n = skip_if({'v1': 'done'})
    eq_(list(n(dict(v1='done'))), [])
    eq_(list(n(dict(v1='not done'))), [{'v1': 'not done'}])
    eq_(list(n(dict(v1='done', someother=123))), [])
    tdict = dict(v1='not yet', someother=123)
    # and that we would interrupt while matching multiple values
    eq_(list(n(tdict)), [tdict])

    eq_(list(skip_if(tdict)(tdict)), [])

    eq_(list(skip_if({'v1': 'ye.$'})(tdict)), [tdict])
    eq_(list(skip_if({'v1': 'ye.$'}, re=True)(tdict)), [])


def test_continue_if():
    d = {'v1': 'done'}
    n = continue_if(d)
    #eq_(list(n(d)), [d])
    eq_(list(n(dict(v1='not done'))), [])
    eq_(list(n(dict(v1='done', someother=123))), [dict(v1='done', someother=123)])

    tdict = dict(v1='not yet', someother=123)
    # and that we would interrupt while matching multiple values
    eq_(list(n(tdict)), [])
    eq_(list(continue_if(tdict)(tdict)), [tdict])

    # regexp
    eq_(list(continue_if({'v1': '^(?P<negate>not +)yet$'}, re=True)(tdict)),
        [updated(tdict, {'negate': 'not '})])


def test_skip_if_negate():
    n = skip_if({'v1': 'done'}, negate=True)
    eq_(list(n(dict(v1='done'))), [dict(v1='done')])
    eq_(list(n(dict(v1='not done'))), [])
    eq_(list(n(dict(v1='done', someother=123))), [dict(v1='done', someother=123)])
    tdict = dict(v1='done', someother=123)
    # and that we would interrupt while matching multiple values
    eq_(list(n(tdict)), [tdict])

    eq_(list(skip_if(tdict, negate=True)(tdict)), [tdict])

    eq_(list(skip_if({'v1': 'don.$'}, negate=True)(tdict)), [])
    eq_(list(skip_if({'v1': 'don.$'}, re=True, negate=True)(tdict)), [tdict])


def test_func_to_node():
    int_node = func_to_node(int)  # node which requires nothing and nothing of output is used
    assert int_node.__doc__
    in_dict = {'in': 1}
    ok_generator(int_node(in_dict))

    # xrange is not considered to be a generator
    def xrange_(n, offset=0):
        for x in range(offset, offset + n):
            yield x

    xrange_node = func_to_node(xrange_, data_args='in', outputs='out')
    assert_in('assigned to out', xrange_node.__doc__)
    assert_false('Additional keyword arguments' in xrange_node.__doc__)
    range_node_gen = xrange_node(in_dict)
    ok_generator(range_node_gen)
    assert_equal(list(range_node_gen), [{'in': 1, 'out': 0}])

    # with additional kwargs
    xrange_node = func_to_node(xrange_, data_args='in', outputs='out', kwargs={'offset': 10})
    assert_in('assigned to out', xrange_node.__doc__)
    assert_in('Additional keyword arguments', xrange_node.__doc__)
    range_node_gen = xrange_node(in_dict)
    ok_generator(range_node_gen)
    assert_equal(list(range_node_gen), [{'in': 1, 'out': 10}])

    # testing func_node
    data = {'offset': 5, 'in': 1}

    xrange_node = func_to_node(xrange_, data_args='in', data_kwargs=['offset'], outputs='out')
    assert_in('assigned to out', xrange_node.__doc__)
    assert_false('Additional keyword arguments' in xrange_node.__doc__)
    gen = xrange_node(data)
    ok_generator(gen)
    assert_equal(list(gen), [{'offset': 5, 'out': 5, 'in': 1}])

    # with multiple outputs
    def split_(s, num):
        yield s.split('/', num)

    data = {'num': 3, 'in': 'datalad/crawler/nodes'}
    split_node = func_to_node(split_, data_args='in', data_kwargs=['num'], outputs=['a', 'b', 'c'])
    assert_in('assigned to a, b, c', split_node.__doc__)
    assert_false('Additional keyword arguments' in split_node.__doc__)
    split_node_gen = split_node(data)
    assert_equal(list(split_node_gen), [{'a': 'datalad', 'c': 'nodes', 'b': 'crawler', 'num': 3, 'in': 'datalad/crawler/nodes'}])


def test_sub():
    s = sub({
        'url': {
            '(http)s?(://.*openfmri\.s3\.amazonaws.com/|://s3\.amazonaws\.com/openfmri/)': r'\1\2'
        }
    })
    ex1 = {'url': 'http://example.com'}
    assert_equal(list(s(ex1)), [ex1])

    assert_equal(list(s({'url': "https://openfmri.s3.amazonaws.com/tarballs/ds001_raw.tgz?param=1"})),
                 [{'url': "http://openfmri.s3.amazonaws.com/tarballs/ds001_raw.tgz?param=1"}])

    assert_equal(
        list(s({
            'url': "https://s3.amazonaws.com/openfmri/tarballs/ds031_retinotopy.tgz?versionId=HcKd4prWsHup6nEwuIq2Ejdv49zwX5U"})),
        [{
            'url': "http://s3.amazonaws.com/openfmri/tarballs/ds031_retinotopy.tgz?versionId=HcKd4prWsHup6nEwuIq2Ejdv49zwX5U"}]
    )


@with_tree(tree={'1': '1', '1.txt': '2'})
def test_find_files(d):
    assert_equal(sorted(list(sorted(x.items())) for x in find_files('.*', topdir=d)({})),
                 [[('filename', '1'), ('path', d)], [('filename', '1.txt'), ('path', d)]])
    assert_equal(list(find_files('.*\.txt', topdir=d)({})), [{'path': d, 'filename': '1.txt'}])
    assert_equal(list(find_files('notmatchable', topdir=d)({})), [])
    assert_raises(RuntimeError, list, find_files('notmatchable', topdir=d, fail_if_none=True)({}))

    # and fail_if_none should operate globally i.e. this should be fine
    ff = find_files('.*\.txt', topdir=d, fail_if_none=True)
    assert_equal(list(ff({})), [{'path': d, 'filename': '1.txt'}])
    os.unlink(opj(d, '1.txt'))
    assert_equal(list(ff({})), [])


def test_switch():
    ran = []

    def n2(data):
        for i in range(2):
            ran.append(len(ran))
            yield updated(data, {'f2': 'x_%d' % i})

    switch_node = switch(
        'f1',
        {
            1: sub({'f2': {'_': '1'}}),
            # should be able to consume nodes and pipelines
            2: [n2],
        }
    )
    out = list(switch_node({'f1': 1, 'f2': 'x_'}))
    assert_equal(out, [{'f1': 1, 'f2': 'x1'}])
    assert_equal(ran, [])
    # but in the 2nd case, the thing is a sub-pipeline so it behaves as such without spitting
    # out its output
    out = list(switch_node({'f1': 2, 'f2': 'x_'}))
    assert_equal(out, _out([{'f1': 2, 'f2': 'x_'}]))
    assert_equal(ran, [0, 1])  # but does execute just fine

    # if there is a value mapping doesn't exist for, by default would fail
    data_missing = {'f1': 3, 'f2': 'x_'}
    with assert_raises(KeyError) as cme:
        list(switch_node(data_missing))
    assert_in('Found no matches for f1 == 3 among', str(cme.exception))

    assert_raises(KeyError, list, switch_node(data_missing))
    switch_node.missing = 'skip'
    assert_equal(list(switch_node(data_missing)), [data_missing])
    switch_node.missing = 'stop'
    assert_equal(list(switch_node(data_missing)), [])

    # and if there is a default -- we should be all good
    switch_node.default = sub({'f2': {'_': '_default'}})
    assert_equal(list(switch_node(data_missing)), [{'f1': 3, 'f2': 'x_default'}])

    # and if we make it output all outputs, we would get them!
    switch_node.mapping[2].insert(0, {'output': 'outputs'})
    out = list(switch_node({'f1': 2, 'f2': 'x_'}))
    assert_equal(out, _out([{'f1': 2, 'f2': 'x_0'}, {'f1': 2, 'f2': 'x_1'}]))


def test_switch_re():
    ran = []

    def n2(data):
        for i in range(2):
            ran.append(len(ran))
            yield updated(data, {'f2': 'x_%d' % i})

    switch_node = switch(
        'f1',
        OrderedDict([
            ('m[13]', sub({'f2': {'_': '1'}})),
            # should be able to consume nodes and pipelines
            ('m[23]', [n2]),
            ('emp.*', None), # just return input
        ]),
        re=True
    )
    out = list(switch_node({'f1': 'm123', 'f2': 'x_'}))
    assert_equal(out, [{'f1': 'm123', 'f2': 'x1'}])
    assert_equal(ran, [])

    # if there is a value mapping doesn't exist for, by default would fail
    data_missing = {'f1': 'xxxxx', 'f2': 'x_'}
    with assert_raises(KeyError) as cme:
        list(switch_node(data_missing))
    assert_re_in('Found no matches for f1 == .xxxxx. matching one of',
                 cme.exception.args)

    # but in the 2nd case, the thing is a sub-pipeline so it behaves as such without spitting
    # out its output
    out = list(switch_node({'f1': 'm2', 'f2': 'x_'}))
    assert_equal(out, _out([{'f1': 'm2', 'f2': 'x_'}]))
    assert_equal(ran, [0, 1])  # but does execute just fine

    # and if matches both -- we need to get all outputs
    for i in range(len(ran)):
        ran.remove(i)
    out = list(switch_node({'f1': 'm3', 'f2': 'x_'}))
    assert_equal(out, [{'f1': 'm3', 'f2': 'x1'}] +
                       _out([{'f1': 'm3', 'f2': 'x_'}]))
    assert_equal(ran, [0, 1])  # and does execute just as fine

    # empty match
    out = list(switch_node({'f1': 'empty', 'f2': 'x_'}))
    assert_equal(out, [{'f1': 'empty', 'f2': 'x_'}])


def _test_debug(msg, args=()):
    if 'empty' in args:
        def node(d):
            # just so Python marks it as a generator
            if False:
                yield d  # pragma: no cover
            else:
                return
    else:
        def node(d):
            yield updated(d, {'debugged': True})

    d1 = debug(node, *args)
    data = {'data': 1}
    with patch('pdb.set_trace') as set_trace:
        with swallow_logs(new_level=logging.INFO) as cml:
            list(d1(data))
            set_trace.assert_called_once_with()
            cml.assert_logged(msg, level='INFO')


def test_debug():
    yield _test_debug, "About to run"
    yield _test_debug, "Ran node .* which yielded 1 times", ('after',)
    yield _test_debug, "Ran node .* which yielded 0 times", ('empty',)
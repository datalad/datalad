# ex: set sts=4 ts=4 sw=4 noet:
# -*- coding: utf-8 -*-
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""

"""

from os.path import join as opj

from datalad.tests.utils import (
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_raises,
    assert_result_count,
    swallow_outputs,
    with_tempfile,
    with_tree,
)

from datalad.distribution.dataset import Dataset


_config_file_content = """\
[something "user"]
name = Jane Doe
email = jd@example.com
novalue
empty =
myint = 3

[onemore "complicated の beast with.dot"]
findme = 5.0
"""

_dataset_config_template = {
    'ds': {
        '.datalad': {
            'config': _config_file_content}}}


@with_tree(tree=_dataset_config_template)
@with_tempfile(mkdir=True)
def test_something(path, new_home):
    ds = Dataset(opj(path, 'ds')).create(force=True)
    ds.save()

    # catches unsupported argument combinations
    assert_raises(ValueError, ds.config, 'dump', spec='some')
    assert_raises(ValueError, ds.config, 'dump', scope='dataset')
    assert_raises(ValueError, ds.config, 'set', spec=('onlyname',))
    assert_raises(ValueError, ds.config, 'set', spec='nosection=value')
    # we also get that from the internal helper
    from datalad.local.configuration import configuration as cfghelper
    assert_in_results(
        cfghelper('set', 'global', [('nosection', 'value')], {}),
        status='error',
    )
    assert_raises(ValueError, ds.config, 'invalid')
    res = ds.config(result_renderer='disabled')

    # TEMP: TODO - fix -- probably lost some binding to dataset with removal of @datasetmethod
    #  which I had to do since we already bind "muled" ConfigManager as .config
    # assert_in_results(
    #     res,
    #     name='something.user.name',
    #     value='Jane Doe')
    # # UTF handling
    # assert_in_results(
    #     res,
    #     name=u'onemore.complicated の beast with.dot.findme',
    #     value='5.0')

    res = ds.config(
        'set',
        spec='some.more=test',
        result_renderer='disabled',
    )
    assert_in_results(
        res,
        name='some.more',
        value='test')
    # Python tuple specs
    # swallow outputs to be able to execise the result renderer
    with swallow_outputs():
        res = ds.config(
            'set',
            spec=[
                ('some.more.still', 'test2'),
                # value is non-str -- will be converted
                ('lonely.val', 4)],
        )
    assert_in_results(
        res,
        name='some.more.still',
        value='test2')
    assert_in_results(
        res,
        name='lonely.val',
        value='4')

    assert_in_results(
        ds.config('get', spec='lonely.val'),
        status='ok',
        name='lonely.val',
        value='4',
    )

    # remove something that does not exist in the specified scope
    assert_in_results(
        ds.config('unset', scope='dataset', spec='lonely.val',
                         result_renderer='disabled', on_failure='ignore'),
        status='error')
    # remove something that does not exist in the specified scope
    assert_in_results(
        ds.config('unset', spec='lonely.val',
                         result_renderer='disabled'),
        status='ok')
    assert_not_in('lonely.val', ds.config)
    # errors if done again
    assert_in_results(
        ds.config('unset', spec='lonely.val',
                         result_renderer='disabled', on_failure='ignore'),
        status='error')

    # add a subdataset to test recursive operation
    subds = ds.create('subds')

    with swallow_outputs():
        res = ds.config('set', spec='rec.test=done', recursive=True)
    # TODO: fix! lost binding to dataset?
    # assert_result_count(
    #     res,
    #     2,
    #     name='rec.test',
    #     value='done',
    # )
    #
    # # exercise the result renderer
    # with swallow_outputs() as cml:
    #     ds.config(recursive=True)
    #     # we get something on the subds with the desired markup
    #     assert_in('<ds>/subds:rec.test=done', cml.out)

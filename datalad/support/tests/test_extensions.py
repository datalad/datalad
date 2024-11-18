from datalad.tests.utils_pytest import (
    assert_in,
    assert_raises,
    eq_,
    nok_,
    ok_,
)

from ..extensions import (
    has_config,
    register_config,
)


def test_register_config():
    nok_(has_config('datalad.testdummies.invalid'))
    assert_raises(
        ValueError,
        register_config,
        'datalad.testdummies.invalid',
        title=None,
        dialog='yesno')
    nok_(has_config('datalad.testdummies.invalid'))

    cfgkey = 'datalad.testdummies.try1'
    nok_(has_config(cfgkey))
    register_config(
        cfgkey,
        'This is what happens, when you do not listen to mama!',
        default_fn=lambda: 5,
        description='Try on-access default "computation"',
        type=int,
        dialog='question',
        scope='global',
    )

    from datalad.interface.common_cfg import definitions
    assert_in(cfgkey, definitions)
    # same thing, other part of the API
    assert_in(cfgkey, definitions.keys())
    # and yet another
    assert_in(cfgkey, [k for k, v in definitions.items()])
    # one more still
    assert_in(cfgkey, [k for k in definitions])
    # more smoke testing, we must have at least this one
    ok_(len(definitions))

    df = definitions[cfgkey]
    # on access default computation
    eq_(df['default'], 5)

    # we could set any novel property
    df['novel'] = 'unexpected'
    eq_(df.get('novel'), 'unexpected')
    eq_(df.get('toonovel'), None)
    # smoke test str/repr
    assert_in('mama', str(df))
    assert_in('mama', repr(df))

    # internal data structure for UI was assembled
    assert_in('ui', df)
    # more smoke
    assert_in('ui', df.keys())
    assert_in('ui', [k for k in df])
    nkeys = len(df)
    df.update(funky='seven')
    eq_(len(df), nkeys + 1)

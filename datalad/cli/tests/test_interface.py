from datalad.interface.tests.test_docs import (
    demo_argdoc,
    demo_doc,
    demo_paramdoc,
)
from datalad.tests.utils_pytest import (
    assert_false,
    assert_in,
    assert_not_in,
    eq_,
)

from ..interface import (
    alter_interface_docs_for_cmdline,
    get_cmdline_command_name,
)


def test_alter_interface_docs_for_cmdline():
    alt = alter_interface_docs_for_cmdline(demo_doc)
    alt_l = alt.split('\n')
    # dedented
    assert_false(alt_l[0].startswith(' '))
    assert_false(alt_l[-1].startswith(' '))
    assert_not_in('PY', alt)
    assert_not_in('CMD', alt)
    assert_not_in('REFLOW', alt)
    assert_in('a b', alt)
    assert_in('not\n   reflowed', alt)
    assert_in("Something for the cmdline only Multiline!", alt)
    # args
    altarg = alter_interface_docs_for_cmdline(demo_argdoc)
    # RST role markup
    eq_(alter_interface_docs_for_cmdline(':murks:`me and my buddies`'),
        'me and my buddies')
    # spread across lines
    eq_(alter_interface_docs_for_cmdline(':term:`Barbara\nStreisand`'),
        'Barbara\nStreisand')
    # multiple on one line
    eq_(alter_interface_docs_for_cmdline(
        ':term:`one` bla bla :term:`two` bla'),
        'one bla bla two bla')

    altpd = alter_interface_docs_for_cmdline(demo_paramdoc)
    assert_not_in('python', altpd)
    assert_in('in between', altpd)
    assert_in('appended', altpd)
    assert_in('cmdline', altpd)


def test_name_generation():
    eq_(
        get_cmdline_command_name(("some.module_something", "SomeClass")),
        "module-something")
    eq_(
        get_cmdline_command_name((
            "some.module_something",
            "SomeClass",
            "override")),
        "override")
    eq_(
        get_cmdline_command_name((
            "some.module_something",
            "SomeClass",
            "override",
            "api_ignore")),
        "override")

# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for interface doc wranglers.

"""

__docformat__ = 'restructuredtext'

from datalad.interface.base import dedent_docstring
from datalad.interface.base import alter_interface_docs_for_api
from datalad.interface.base import alter_interface_docs_for_cmdline
from datalad.tests.utils import assert_true, assert_false, assert_in, \
    assert_not_in, eq_


demo_doc = """\
    Bla bla summary

    Generic intro blurb. Ping pong ping pong ping pong ping pong.  Ping pong ping
    pong ping pong ping pong. Ping pong ping pong ping pong ping pong. Ping pong
    ping pong ping pong ping pong. Ping pong ping pong ping pong ping pong. Ping
    pong ping pong ping pong ping pong.

    || CMDLINE >>
    || REFLOW >>
    Something for the cmdline only
    Multiline!
    << REFLOW ||
    << CMDLINE ||

    || PYTHON >>

    || REFLOW >>
    Some Python-only bits
    Multiline!
    << REFLOW ||

    << PYTHON ||

    And an example for in-line markup: [PY: just for Python PY] and
    the other one [CMD: just for the command line CMD]. End of demo.

    Generic appendix. Ding dong ding dong ding dong.  Ding dong ding dong ding
    dong.  Ding dong ding dong ding dong.  Ding dong ding dong ding dong.  Ding
    dong ding dong ding dong.

"""

demo_paramdoc = """\

    Parameters
    ----------
    dataset : Dataset or None, optional
      something [PY: python only PY] inbetween [CMD: cmdline only CMD] appended [PY: more python PY]
      dataset is given, an attempt is made to identify the dataset based
      Dataset (e.g. a path), or value must be `None`. [Default: None]
"""

demo_argdoc = """\
    specify the dataset to perform the install operation
    on. If no dataset is given, an attempt is made to
    identify the dataset based on the current working
    directory and/or the `path` given. Constraints: Value
    must be a Dataset or a valid identifier of a Dataset
    (e.g. a path), or value must be `None`. [Default:
    None]
"""


def test_dedent():
    assert_false(dedent_docstring("one liner").endswith("\n"))


def test_alter_interface_docs_for_api():
    alt = alter_interface_docs_for_api(demo_doc)
    alt_l = alt.split('\n')
    # dedented
    assert_false(alt_l[0].startswith(' '))
    assert_false(alt_l[-1].startswith(' '))
    assert_not_in('CMD', alt)
    assert_not_in('PY', alt)
    assert_not_in('REFLOW', alt)
    assert_in("Some Python-only bits Multiline!", alt)

    altpd = alter_interface_docs_for_api(demo_paramdoc)
    assert_in('python', altpd)
    assert_in('inbetween', altpd)
    assert_in('appended', altpd)
    assert_not_in('cmdline', altpd)


def test_alter_interface_docs_for_cmdline():
    alt = alter_interface_docs_for_cmdline(demo_doc)
    alt_l = alt.split('\n')
    # dedented
    assert_false(alt_l[0].startswith(' '))
    assert_false(alt_l[-1].startswith(' '))
    assert_not_in('PY', alt)
    assert_not_in('CMD', alt)
    assert_not_in('REFLOW', alt)
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
    assert_in('inbetween', altpd)
    assert_in('appended', altpd)
    assert_in('cmdline', altpd)

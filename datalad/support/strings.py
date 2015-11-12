# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##g
"""Variety of helpers to deal with strings"""

__docformat__ = 'restructuredtext'

from six import binary_type, text_type
import re

def apply_replacement_rules(rules, s):
    """Apply replacement rules specified as a single string

    Examples
    --------

    >>> apply_replacement_rules(r'/my_(.*)\.dat/your_\\1.dat.gz', 'd/my_pony.dat')
    'd/your_pony.dat.gz'

    Parameters
    ----------
    rules : str, list of str
      Rules of the format '/pat1/replacement', where / is an arbitrary
      character to decide replacement.

    Returns
    -------
    str
    """

    if isinstance(rules, (binary_type, text_type)):
        rules = [rules]

    for rule in rules:
        if len(rule) <= 2:
            raise ValueError("")
        rule_split = rule[1:].split(rule[0])
        if len(rule_split) != 2:
            raise ValueError(
                "Rename string must be of format '/pat1/replacement', "
                "where / is an arbitrary character to decide replacement. "
                "Got %s when trying to separate %s" % (rule_split, rule)
            )
        regexp, replacement = rule_split
        s = re.sub(regexp, replacement, s)

    return s

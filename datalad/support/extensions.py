# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Support functionality for extension development"""

import logging

from datalad.interface.common_cfg import (
    _ConfigDefinition,
    _NotGiven,
)
from datalad.interface.common_cfg import definitions as _definitions

__all__ = ['register_config', 'has_config']

lgr = logging.getLogger('datalad.support.extensions')


def register_config(
        name,
        title,
        *,
        default=_NotGiven,
        default_fn=_NotGiven,
        description=None,
        # yes, we shadow type, this is OK
        type=_NotGiven,
        # for manual entry
        dialog=None,
        scope=_NotGiven,
    ):
    """Register a configuration item

    This function can be used by DataLad extensions and other client
    code to register configurations items and their documentation with
    DataLad's configuration management. Specifically, these definitions
    will be interpreted by and acted on by the `configuration` command,
    and `ConfigManager.obtain()`.

    At minimum, each item must be given a name, and a title. Optionally, any
    configuration item can be given a default (or a callable to compute a
    default lazily on access), a type-defining/validating callable (i.e.
    `Constraint`), a (longer) description, a dialog type to enable manual
    entry, and a configuration scope to store entered values in.

    Parameters
    ----------
    name: str
      Configuration item name, in most cases starting with the prefix
      'datalad.' followed by at least a section name, and a variable
      name, e.g. 'datalad.section.variable', following Git's syntax for
      configuration items.
    title: str
      The briefest summary of the configuration item's purpose, typically
      written in the style of a headline for a dialog UI, or that of an
      explanatory inline comment just prior the item definitions.
    default: optional
      A default value that is already known at the time of registering the
      configuration items. Can be of any type.
    default_fn: callable, optional
      A callable to compute a default value lazily on access. The can be
      used, if the actual value is not yet known at the time of registering
      the configuration item, or if the default is expensive to compute
      and its evaluation needs to be deferred to prevent slow startup
      (configuration items are typically defined as one of the first things
      on import).
    description: str, optional
      A longer description to accompany the title, possibly with instructions
      on how a sensible value can be determined, or with details on the
      impact of a configuration switch.
    type: callable, optional
      A callable to perform arbitrary type conversion and validation of value
      (or default values). If validation/conversion fails, the callable
      must raise an arbitrary exception. The `str(callable)` is used as
      a type description.
    dialog: {'yesno', 'question'}
      A type of UI dialog to use when manual value entry is attempted
      (only in interactive sessions, and only when no default is defined.
      `title` and `description` will be displayed in this dialog.
    scope: {'override', 'global', 'local', 'branch'}, optional
      If particular code requests the storage of (manually entered) values,
      but defines no configuration scope, this default scope will be used.

    Raises
    ------
    ValueError
      For missing required, or invalid configuration properties.
    """
    kwargs = dict(
        default=default,
        default_fn=default_fn,
        scope=scope,
        type=type
    )
    kwargs = {k: v for k, v in kwargs.items() if v is not _NotGiven}
    if dialog is not None and not title:
        raise ValueError("Configuration dialog must have a title")
    doc_props = dict(title=title)
    if description:
        doc_props['text'] = description
    # dialog is OK to be None, this is not just about UI, even if
    # the key of the internal data structure seems to suggest that.
    # it is also the source for annotating config listings
    kwargs['ui'] = (dialog, doc_props)
    _definitions[name] = _ConfigDefinition(**kwargs)


def has_config(name):
    """Returns whether a configuration item is registered under the given name

    Parameters
    ----------

    name: str
      Configuration item name

    Returns
    -------
    bool
    """
    return name in _definitions

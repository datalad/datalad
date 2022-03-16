# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See LICENSE file distributed along with the datalad_osf package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Credential management and query"""

__docformat__ = 'restructuredtext'

import json
import logging
import re

from datalad import (
    cfg as dlcfg,
)
from datalad.credman import (
    CredentialManager,
    verify_property_names,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.support.exceptions import CapturedException
from datalad.support.param import Parameter
from datalad.distribution.dataset import (
    datasetmethod,
    EnsureDataset,
    require_dataset,
)
from datalad.interface.results import (
    get_status_dict,
)
from datalad.interface.utils import (
    eval_results,
    generic_result_renderer,
)
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)

lgr = logging.getLogger('datalad.local.credentials')

credential_actions = ('query', 'get', 'set', 'remove')


@build_doc
class Credentials(Interface):
    """Credential management and query

    This command enables inspection and manipulation of credentials used
    throughout DataLad.

    The command provides four basic actions:

    QUERY

    When executed without any property specification, all known credentials
    with all their properties will be yielded. Please note that this may not
    include credentials that only comprise of a secret and no other properties,
    or legacy credentials for which no trace in the configuration can be found.
    Therefore, the query results are not guaranteed to contain all credentials
    ever configured by DataLad.

    When additional property/value pairs are specified, only credentials that
    have matching values for all given properties will be reported. This can be
    used, for example, to discover all suitable credentials for a specific
    "realm", if credentials were annotated with such information.

    GET

    This is a read-only action that will never alter credential properties or
    secrets. Given properties will amend/overwrite those already on record.
    When properties with no value are given, and also no value for the
    respective properties is on record yet, their value will be requested
    interactively, if a ``prompt||--prompt`` text was provided too. This can be
    used to ensure a complete credential record, comprising any number of
    properties.

    SET

    This is the companion to 'get', and can be used to store properties and
    secret of a credential. Importantly, and in contrast to a 'get' operation,
    given properties with no values indicate a removal request. Any matching
    properties on record will be removed. If a credential is to be stored for
    which no secret is on record yet, an interactive session will prompt a user
    for a manual secret entry.

    Only changed properties will be contained in the result record.

    REMOVE

    This action will remove any secret and properties associated with a
    credential identified by its name.


    Details on credentials

    A credential comprises any number of properties, plus exactly one secret.
    There are no constraints on the format or property values or the secret,
    as long as they are encoded as a string.

    Credential properties are normally stored as configuration settings in a
    user's configuration ('global' scope) using the naming scheme:

      `datalad.credential.<name>.<property>`

    Therefore both credential name and credential property name must be
    syntax-compliant with Git configuration items. For property names this
    means only alphanumeric characters and dashes. For credential names
    virtually no naming restrictions exist (only null-byte and newline are
    forbidden). However, when naming credentials it is recommended to use
    simple names in order to enable convenient one-off credential overrides
    by specifying DataLad configuration items via their environment variable
    counterparts (see the documentation of the ``configuration`` command
    for details. In short, avoid underscores and special characters other than
    '.' and '-'.

    While there are no constraints on the number and nature of credential
    properties, a few particular properties are recognized on used for
    particular purposes:

    - 'secret': always refers to the single secret of a credential
    - 'type': identifies the type of a credential. With each standard type,
      a list of mandatory properties is associated (see below)
    - 'last-used': is an ISO 8601 format time stamp that indicated the
      last (successful) usage of a credential

    Standard credential types and properties

    The following standard credential types are recognized, and their
    mandatory field with their standard names will be automatically
    included in a 'get' report.

    - 'user_password': with properties 'user', and the password as secret
    - 'token': only comprising the token as secret
    - 'aws-s3': with properties 'key-id', 'session', 'expiration', and the
      secret_id as the credential secret

    Legacy support

    DataLad credentials not configured via this command may not be fully
    discoverable (i.e., including all their properties). Discovery of
    such legacy credentials can be assisted by specifying a dedicated
    'type' property    """
    result_renderer = 'tailored'

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify a dataset whose configuration to inspect
            rather than the global (user) settings""",
            constraints=EnsureDataset() | EnsureNone()),
        action=Parameter(
            args=("action",),
            nargs='?',
            doc="""which action to perform""",
            constraints=EnsureChoice(*credential_actions)),
        name=Parameter(
            # exclude from CLI
            args=tuple(),
            doc="""name of a credential to set, get, or remove.""",
            constraints=EnsureStr() | EnsureNone()),
        spec=Parameter(
            args=("spec",),
            doc="""specification of[CMD:  a credential name and CMD]
            credential properties. Properties are[CMD:  either CMD] given as
            name/value pairs[CMD:  or as a property name prefixed
            by a colon CMD].
            Properties with [CMD: no CMD][PY: a `None` PY] value
            indicate a property to be deleted (action 'set'), or a
            property to be entered interactively, when no value is set
            yet, and a prompt text is given (action 'get').
            All property names are case-insensitive, must start with
            a letter or a digit, and may only contain '-' apart from
            these characters.
            [PY: Property specifications should be given a as dictionary.
            However, a CLI-like list of string arguments is also
            supported PY]""",
            nargs='*',
            metavar='[name] [:]property[=value]'),
        prompt=Parameter(
            args=("--prompt",),
            doc="""message to display when entry of missing credential
            properties is required for action 'get'. This can be used
            to present information on the nature of a credential and
            for instructions on how to obtain a credential""",
            constraints=EnsureStr() | EnsureNone()),
    )

    @staticmethod
    @datasetmethod(name='credentials')
    @eval_results
    def __call__(action='query', spec=None, *, name=None, prompt=None,
                 dataset=None):
        if action not in credential_actions:
            raise ValueError(f"Unknown action {action!r}")

        if action in ('get', 'set', 'remove') and not name and spec \
                and isinstance(spec, list):
            # spec came in like from the CLI (but doesn't have to be from
            # there) and we have no name set
            if spec[0][0] != ':' and '=' not in spec[0]:
                name = spec[0]
                spec = spec[1:]

        # `spec` could be many things, make uniform dict
        specs = normalize_specs(spec)

        if action in ('set', 'remove') and not name:
            raise ValueError(
                f"Credential name must be provided for action {action!r}")
        if action == 'get' and not name and not spec:
            raise ValueError(
                "Cannot get credential properties when no name and no "
                "property specification is provided")

        # which config manager to use: global or from dataset
        cfg = require_dataset(
            dataset,
            # we do not actually need it
            check_installed=False,
            purpose='manage credentials').config if dataset else dlcfg

        credman = CredentialManager(cfg)

        if action == 'set':
            try:
                updated = credman.set(name, **specs)
            except Exception as e:
                yield get_status_dict(
                    action='credentials',
                    status='error',
                    name=name,
                    message='could not set credential properties',
                    exception=CapturedException(e),
                )
                return
            yield get_status_dict(
                action='credentials',
                status='ok',
                name=name,
                **_prefix_result_keys(updated),
            )
        elif action == 'get':
            cred = credman.get(name=name, _prompt=prompt, **specs)
            if not cred:
                yield get_status_dict(
                    action='credentials',
                    status='error',
                    name=name,
                    message='credential not found',
                )
            else:
                yield get_status_dict(
                    action='credentials',
                    status='ok',
                    name=name,
                    **_prefix_result_keys(cred),
                )
        elif action == 'remove':
            try:
                removed = credman.remove(name, type_hint=specs.get('type'))
            except Exception as e:
                yield get_status_dict(
                    action='credentials',
                    status='error',
                    name=name,
                    message='could not remove credential properties',
                    exception=CapturedException(e),
                )
                return
            yield get_status_dict(
                action='credentials',
                status='ok' if removed else 'notneeded',
                name=name,
            )
        elif action == 'query':
            for name, cred in credman.query_(**specs):
                yield get_status_dict(
                    action='credentials',
                    status='ok',
                    name=name,
                    type='credential',
                    **_prefix_result_keys(cred),
                )
        else:
            raise RuntimeError('Impossible state reached')  # pragma: no cover

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        # we only handle our own stuff in a custom fashion, the rest is generic
        if res['action'] != 'credentials':
            generic_result_renderer(res)
            return
        # must make a copy, because we modify the record in-place
        # https://github.com/datalad/datalad/issues/6560
        res = res.copy()
        # the idea here is to twist the result records such that the generic
        # renderer can be used
        if 'name' in res:
            res['action'] = res['name']
        res['status'] = res.get('cred_type', 'secret')
        if 'message' not in res:
            # give the names of all properties
            # but avoid duplicating the type, hide the prefix,
            # add removal marker for vanished properties
            res['message'] = ','.join(
                p[5:] if res[p] else f':{p[5:]}' for p in res
                if p.startswith('cred_') and p not in (
                    'cred_secret', 'cred_type'))
        generic_result_renderer(res)


def normalize_specs(specs):
    """Normalize all supported `spec` argument values for `credentials`

    Parameter
    ---------
    specs: JSON-formatted str or list

    Returns
    -------
    dict
        Keys are the names of any property (with removal markers stripped),
        and values are `None` whenever property removal is desired, and
        not `None` for any value to be stored.

    Raises
    ------
    ValueError
      For missing values, missing removal markers, and invalid JSON input
    """
    if not specs:
        return {}
    elif isinstance(specs, str):
        try:
            specs = json.loads(specs)
        except json.JSONDecodeError as e:
            raise ValueError('Invalid JSON input') from e
    if isinstance(specs, list):
        # convert property assignment list
        specs = [
            (str(s[0]), str(s[1]))
            if isinstance(s, tuple) else
            (str(s),)
            if '=' not in s else
            (tuple(s.split('=', 1)))
            for s in specs
        ]
    if isinstance(specs, list):
        missing = [
            i for i in specs
            if (len(i) == 1 and i[0][0] != ":") or (
                len(i) > 1 and (i[0][0] == ':' and i[1] is not None))
        ]
    else:
        missing = [
            k for k, v in specs.items()
            if k[0] == ":" and v is not None
        ]
    if missing:
        raise ValueError(
            f'Value or unset flag ":" missing for property {missing!r}')
    if isinstance(specs, list):
        # expand absent values in tuples to ease conversion to dict below
        specs = [(i[0], i[1] if len(i) > 1 else None) for i in specs]
    # apply "unset marker"
    specs = {
        # this stuff goes to git-config, is therefore case-insensitive
        # and we should normalize right away
        (k[1:] if k[0] == ':' else k).lower():
        None if k[0] == ':' else v
        for k, v in (specs.items() if isinstance(specs, dict) else specs)
    }
    verify_property_names(specs)
    return specs


def _prefix_result_keys(props):
    return {
        f'cred_{k}' if not k.startswith('_') else k[1:]: v
        for k, v in props.items()
    }

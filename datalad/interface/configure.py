# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

__docformat__ = 'restructuredtext'

from collections import OrderedDict

from datalad.ui import ui
from .base import Interface
from ..support.param import Parameter
from datalad.dochelpers import exc_str
from datalad.utils import getpwd

from datalad.support.constraints import EnsureNone
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict

from logging import getLogger
lgr = getLogger('datalad.interface.configure')

from datalad import cfg as dlcfg


# using the style from datalad.interface.common_cfg
init_definitions = OrderedDict([
    ('user.name', {
        'ui': ('question', {
               'title': 'Your name',
               'text': 'Name to be associated with changes recorded by Git'}),
        'destination': 'global',
    }),
    ('user.email', {
        'ui': ('question', {
               'title': 'Your email address',
               'text': 'Email address to be associated with changes recorded by Git'}),
        'destination': 'global',
    }),
])


@build_doc
class Configure(Interface):
    """Configure DataLad interactively

    This command allows to configure DataLad, or an individual dataset
    interactively, by answering select questions. The answers will
    be stored in the appropriate Git or DataLad configuration files,
    and can be edited subsequently for further customization.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""if set, configuration items for datasets will be
            presented too, and stored in the specified dataset.""",
            constraints=EnsureDataset() | EnsureNone()),
    )

    @staticmethod
    @datasetmethod(name='configure')
    @eval_results
    def __call__(dataset=None):
        cfg = dlcfg
        if dataset:
            dataset = require_dataset(
                dataset,
                check_installed=True,
                purpose='configuration')
            # be able to configure a dataset
            cfg = dataset.config
        # TODO compose the candidate cfg items from other
        # sources to -- maybe some for initializing a dataset
        # when --dataset is given
        for var, props in init_definitions.items():
            default = props.get('default', None)
            val = cfg.get(var, None)
            dialog_type = props.get('ui', [None])[0]
            dialog_props = props.get('ui', [None, {}])[1]
            valtype = props.get('type', None)
            where = props.get('destination', 'local')

            if where == 'dataset' and dataset is None:
                lgr.debug(
                    'Skip configuration of dataset config variable %s, no dataset available', var)
                continue
            if not dialog_type:
                # errr, cannot ask
                continue
            status = None
            while status not in ('ok', 'notneeded'):
                res = get_status_dict(
                    ds=dataset if where == 'dataset' else None,
                    action='configure',
                    logger=lgr)
                if where != 'dataset':
                    # must have a path in the result
                    res['path'] = getpwd()
                entry = getattr(ui, dialog_type)(
                    default=val if val else default,
                    **dialog_props if dialog_props else {})
                # type check, skip on any set of weird input (escape chars)
                # as a sign of user struggle
                if valtype and '\x1b' not in entry:
                    try:
                        valtype(entry)
                    except Exception as e:
                        ui.message("Value incompatible with target type ({})".format(
                            exc_str(e)))
                        status = 'error'
                        continue
                action = '?'
                while action == '?':
                    action = ui.question(
                        "{} {}={} in the {} configuration?".format(
                            'Set' if val is None else 'Update',
                            var,
                            repr(entry),
                            where),
                        title=None,
                        choices=['y', 'n', 'r', 'x', '?'],
                        # default to re-enter whenever there is a sign of
                        # struggle
                        default='r'
                        if '\x1b' in entry else 'y'
                        if entry != val else 'n',
                        hidden=False)
                    if action == '?':
                        ui.message('Response alternatives: (y)es, (n)o, (r)e-enter, e(x)it')
                if action == 'y':
                    if entry != val:
                        cfg.set(
                            var,
                            entry,
                            where=where,
                            # repeated access is not part of the usage
                            # pattern here, hence no need
                            reload=False,
                            # this command does not support multi-value
                            # options (yet), let it fail
                            force=False)
                        status = 'ok'
                    else:
                        status = 'notneeded'
                    res['status'] = status
                    yield res
                    continue
                elif action == 'n':
                    status = 'ok'
                    continue
                elif action == 'x':
                    return

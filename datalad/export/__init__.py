# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""

"""

__docformat__ = 'restructuredtext'

import logging
from glob import glob
from os.path import join as opj, basename, dirname
from importlib import import_module

from datalad.support.param import Parameter
from datalad.support.constraints import EnsureNone
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset

from datalad.interface.base import Interface

lgr = logging.getLogger('datalad.export')


def _get_exporter_names():
    basepath = dirname(__file__)
    return [basename(e)[:-3]
            for e in glob(opj(basepath, '*.py'))
            if not e.endswith('__init__.py')]


class Export(Interface):
    """Export a dataset to another representation
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to export. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        astype=Parameter(
            args=("astype",),
            choices=_get_exporter_names(),
            doc="""label of the type or format the dataset shall be exported
            to."""),
        getcmdhelp=Parameter(
            args=('--help-type',),
            dest='getcmdhelp',
            action='store_true',
            doc="""show help for a specific export type/format"""),
    )

    @staticmethod
    @datasetmethod(name='export')
    def __call__(astype, dataset, getcmdhelp=False, **kwargs):
        # get a handle on the relevant plugin module
        import datalad.export as export_mod
        exmod = import_module('.%s' % (astype,), package=export_mod.__package__)
        if getcmdhelp:
            # no result, but return the module to make the renderer do the rest
            return (exmod, None)

        ds = require_dataset(dataset, check_installed=True, purpose='exporting')
        # call the plugin, either with the argv array from the cmdline call
        # or directly with the kwargs
        if 'datalad_unparsed_args' in kwargs:
            result = exmod._datalad_export_plugin_call(
                ds, argv=kwargs['datalad_unparsed_args'])
        else:
            result = exmod._datalad_export_plugin_call(ds, **kwargs)
        return (exmod, result)

    @staticmethod
    def result_renderer_cmdline(res, args):
        exmod, result = res
        if args.getcmdhelp:
            # the function that prints the help was returned as result
            exmod._datalad_print_cmdline_help()
            return
        # TODO call exporter function (if any)

# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for managing metadata
"""

__docformat__ = 'restructuredtext'


import re
from six import string_types
from datalad.interface.base import Interface
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    require_dataset
from ..support.param import Parameter
from ..support.constraints import EnsureNone
from ..log import lgr
from . import get_metadata, flatten_metadata_graph


class SearchDatasets(Interface):
    """
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to perform the query operation on. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        match=Parameter(
            args=("match",),
            metavar='REGEX',
            doc="expression to match against all meta data values"),
        #match=Parameter(
        #    args=('-m', '--match',),
        #    metavar='REGEX',
        #    action='append',
        #    nargs=2,
        #    doc="""Pair of two regular expressions to match a property and its
        #    value.[CMD:  This option can be given multiple times CMD]"""),
        report=Parameter(
            args=('-r', '--report'),
            metavar='PROPERTY',
            action='append',
            # could also be regex
            doc="""name of the property to report for any match.[CMD:  This
            option can be given multiple times. CMD] If none are given, all
            properties are reported."""),
        # TODO --json  to output as json
    )

    @staticmethod
    @datasetmethod(name='search_datasets')
    def __call__(match, dataset, report=None):

        ds = require_dataset(dataset, check_installed=True, purpose='dataset search')

        meta = get_metadata(ds, guess_type=False, ignore_subdatasets=False,
                            ignore_cache=False)
        # merge all info on datasets into a single dict per dataset
        lgr.info('Next one is slow, but can be made faster by your contribution!')
        # TODO load offline schema if necessary, cache document load requests
        meta = flatten_metadata_graph(meta)
        lgr.info('Fast again...')
        # TODO cache this somewhere and reload the cache instead of repeating
        # the graph optimization to gain some speed

        # extract graph, if any
        meta = meta.get('@graph', meta)

        # build simple queriable representation
        if not isinstance(meta, list):
            meta = [meta]

        if report and not isinstance(report, list):
            report = [report]

        expr = re.compile(match)

        # for every meta data set
        for mds in meta:
            hit = False
            if not mds.get('type', None) == 'Dataset':
                # we are presently only dealing with datasets
                continue
            # TODO consider the possibility of nested and context/graph dicts
            # but so far we were trying to build simple lists of dicts, as much
            # as possible
            if not isinstance(mds, dict):
                raise NotImplementedError("nested meta data is not yet supported")
            # manual loop for now
            for k, v in mds.iteritems():
                if isinstance(v, dict) or isinstance(v, list):
                    v = unicode(v)
                hit = hit or expr.match(v)
            if hit:
                report_dict = {k: mds[k] for k in report if k in mds} if report else mds
                if len(report_dict):
                    yield report_dict
                else:
                    lgr.warning('meta data match, but no to-be-reported properties found. '
                                'Present properties: %s' % (", ".join(sorted(mds))))

    @staticmethod
    def result_renderer_cmdline(res, cmdlineargs):
        from datalad.ui import ui
        if res is None:
            res = []
        anything = False
        if cmdlineargs.report is None or len(cmdlineargs.report) > 1:
            # multiline if multiple were requested and we need to disambiguate
            ichr = jchr = '\n'
            fmt = ' {k}: {v}'
        else:
            jchr = ', '
            ichr = ' '
            fmt = '{v}'
        for r in res:
            # XXX Yarik thinks that Match should be replaced with actual path to the dataset
            ui.message('Match:{}{}'.format(
                ichr,
                jchr.join([fmt.format(k=k, v=safe_str(r[k])) for k in sorted(r)])))
            anything = True
        if not anything:
            ui.message("Nothing to report")

def safe_str(s):
    try:
        return str(s)
    except UnicodeEncodeError:
        lgr.warning("Failed to encode value correctly. Ignoring errors in encoding")
        # TODO: get current encoding
        return s.encode('utf-8', 'ignore') if isinstance(s, string_types) else "ERROR"
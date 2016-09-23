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

import os
import re
import sys

from operator import itemgetter
from os.path import join as opj, exists
from six import string_types
from six import text_type
from six import iteritems
from six import reraise
from datalad.interface.base import Interface
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    require_dataset
from ..support.param import Parameter
from ..support.constraints import EnsureNone
from ..support.constraints import EnsureChoice
from ..log import lgr
from . import get_metadata, flatten_metadata_graph, pickle

from datalad.consts import LOCAL_CENTRAL_PATH
from datalad import cfg as dlcfg
from datalad.utils import assure_list
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.ui import ui


class Search(Interface):
    """Search within available in datasets' meta data

    Yields
    ------
    location : str
        (relative) path to the dataset
    report : dict
        fields which were requested by `report` option

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
            metavar='STRING',
            nargs="+",
            doc="a string (or a regular expression if "
                "[PY: `regex=True` PY][CMD: --regex CMD]) to search for "
                "in all meta data values. If multiple provided, all must have "
                "a match among some fields of a dataset"),
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
            option can be given multiple times. CMD] If '*' is given, all
            properties are reported."""),
        report_matched=Parameter(
            args=('-R', '--report-matched',),
            action="store_true",
            doc="""flag to report those fields which have matches. If `report`
             option values are provided, union of matched and those in `report`
             will be output"""),
        # Theoretically they should be CMDLINE specific I guess?
        format=Parameter(
            args=('-f', '--format'),
            constraints=EnsureChoice('custom', 'json', 'yaml'),
            doc="""format for output."""
        ),
        regex=Parameter(
            args=("--regex",),
            action="store_true",
            doc="flag for STRING to be used as a (Python) regular expression "
                "which should match the value"),
    )

    @staticmethod
    @datasetmethod(name='search')
    def __call__(match, dataset=None, report=None, report_matched=False, format='custom', regex=False):

        lgr.debug("Initiating search for match=%r and dataset %r",
                  match, dataset)
        try:
            ds = require_dataset(dataset, check_installed=True, purpose='dataset search')
        except NoDatasetArgumentFound:
            exc_info = sys.exc_info()
            if dataset is None:
                if not ui.is_interactive:
                    raise NoDatasetArgumentFound(
                        "No DataLad dataset found at current location and "
                        "current UI is not interactive to assist in installing "
                        "one.  Please run `search` command interactively or "
                        "under an existing DataLad dataset"
                    )
                # none was provided so we could ask user either he possibly wants
                # to install our beautiful mega-duper-super-dataset?
                # TODO: following logic could possibly benefit other actions.
                if os.path.exists(LOCAL_CENTRAL_PATH):
                    central_ds = Dataset(LOCAL_CENTRAL_PATH)
                    if central_ds.is_installed():
                        if ui.yesno(
                            title="No DataLad dataset found at current location",
                            text="Would you like to search within DataLad "
                                 "meta-dataset under % r and search within it?"
                                  % LOCAL_CENTRAL_PATH):
                            pass
                    else:
                        raise NoDatasetArgumentFound(
                            "No DataLad dataset found at current location and "
                            "%r already exists but does not contain an "
                            "installed dataset." % LOCAL_CENTRAL_PATH)
                elif ui.yesno(
                       title="No DataLad dataset found at current location",
                       text="Would you like to install stock DataLad "
                            "meta-dataset under %r?"
                            % LOCAL_CENTRAL_PATH
                       ):
                    from datalad.api import install
                    central_ds = install(LOCAL_CENTRAL_PATH, source='///')
                else:
                    reraise(*exc_info)

                lgr.info(
                    "Performing search using central dataset %r",
                    central_ds.path
                )
                for loc, r in central_ds.search(
                        match,
                        report=report, report_matched=report_matched,
                        format=format, regex=regex):
                    full_loc = opj(central_ds.path, loc)
                    yield full_loc, r
                return
            else:
                raise

        cache_dir = opj(dlcfg.dirs.user_cache_dir, 'metadata')
        mcache_fname = opj(cache_dir, ds.id)

        meta = None
        if os.path.exists(mcache_fname):
            lgr.debug("use cached metadata of '{}' from {}".format(ds, mcache_fname))
            meta, checksum = pickle.load(open(mcache_fname))
            # TODO add more sophisticated tests to decide when the cache is no longer valid
            if checksum != ds.repo.get_hexsha():
                # errrr, try again below
                meta = None

        # don't put in 'else', as yet to be written tests above might fail and require
        # regenerating meta data
        if meta is None:
            lgr.info("Loading and caching local meta-data... might take a few seconds")
            if not exists(cache_dir):
                os.makedirs(cache_dir)

            meta = get_metadata(ds, guess_type=False, ignore_subdatasets=False,
                                ignore_cache=False)
            # merge all info on datasets into a single dict per dataset
            meta = flatten_metadata_graph(meta)
            # extract graph, if any
            meta = meta.get('@graph', meta)
            # build simple queriable representation
            if not isinstance(meta, list):
                meta = [meta]

            # sort entries by location (if present)
            sort_keys = ('location', 'description', 'id')
            meta = sorted(meta, key=lambda m: tuple(m.get(x) for x in sort_keys))

            # use pickle to store the optimized graph in the cache
            pickle.dump(
                # graph plus checksum from what it was built
                (meta, ds.repo.get_hexsha()),
                open(mcache_fname, 'w'))
            lgr.debug("cached meta data graph of '{}' in {}".format(ds, mcache_fname))

        if report in ('', ['']):
            report = []
        elif report and not isinstance(report, list):
            report = [report]

        match = assure_list(match)

        def get_in_matcher(m):
            """Function generator to provide closure for a specific value of m"""
            mlower = m.lower()
            def matcher(s):
                return mlower in s.lower()
            return matcher

        matchers = [
            re.compile(match_).search
                if regex
                else get_in_matcher(match_)
            for match_ in match
        ]

        # for every meta data set
        for mds in meta:
            hit = False
            hits = [False] * len(matchers)
            matched_fields = set()
            if not mds.get('type', None) == 'Dataset':
                # we are presently only dealing with datasets
                continue
            # TODO consider the possibility of nested and context/graph dicts
            # but so far we were trying to build simple lists of dicts, as much
            # as possible
            if not isinstance(mds, dict):
                raise NotImplementedError("nested meta data is not yet supported")

            # manual loop for now
            for k, v in iteritems(mds):
                if isinstance(v, dict) or isinstance(v, list):
                    v = unicode(v)
                for imatcher, matcher in enumerate(matchers):
                    if matcher(v):
                        hits[imatcher] = True
                        matched_fields.add(k)
                if all(hits):
                    hit = True
                    # no need to do it longer than necessary
                    if not report_matched:
                        break

            if hit:
                location = mds.get('location', '.')
                report_ = matched_fields.union(report if report else {}) \
                    if report_matched else report
                if report_ == ['*']:
                    report_dict = mds
                elif report_:
                    report_dict = {k: mds[k] for k in report_ if k in mds}
                    if report_ and not report_dict:
                        lgr.debug(
                            'meta data match for %s, but no to-be-reported '
                            'properties (%s) found. Present properties: %s',
                            location, ", ".join(report_), ", ".join(sorted(mds))
                        )
                else:
                    report_dict = {}  # it was empty but not None -- asked to
                    # not report any specific field
                yield location, report_dict


    @staticmethod
    def result_renderer_cmdline(res, cmdlineargs):
        from datalad.ui import ui
        if res is None:
            res = []

        format = cmdlineargs.format or 'custom'
        if format =='custom':

            if cmdlineargs.report in ('*', ['*']) \
                    or cmdlineargs.report_matched \
                    or (cmdlineargs.report is not None
                        and len(cmdlineargs.report) > 1):
                # multiline if multiple were requested and we need to disambiguate
                ichr = jchr = '\n'
                fmt = ' {k}: {v}'
            else:
                jchr = ', '
                ichr = ' '
                fmt = '{v}'

            anything = False
            for location, r in res:
                # XXX Yarik thinks that Match should be replaced with actual path to the dataset
                ui.message('{}{}{}{}'.format(
                    location,
                    ':' if r else '',
                    ichr,
                    jchr.join([fmt.format(k=k, v=pretty_str(r[k])) for k in sorted(r)])))
                anything = True
            if not anything:
                ui.message("Nothing to report")
        elif format == 'json':
            import json
            ui.message(json.dumps(list(map(itemgetter(1), res)), indent=2))
        elif format == 'yaml':
            import yaml
            lgr.warning("yaml output support is not yet polished")
            ui.message(yaml.safe_dump(list(map(itemgetter(1), res)), allow_unicode=True, encoding='utf-8'))


def pretty_str(s):
    """Helper to provide sensible rendering for lists, dicts, and unicode"""
    if isinstance(s, list):
        return ", ".join(map(pretty_str, s))
    elif isinstance(s, dict):
        return pretty_str(["%s=%s" % (pretty_str(k), pretty_str(v))
                           for k, v in s.items()])
    elif isinstance(s, text_type):
        try:
            return s.encode('utf-8')
        except UnicodeEncodeError:
            lgr.warning("Failed to encode value correctly. Ignoring errors in encoding")
            # TODO: get current encoding
            return s.encode('utf-8', 'ignore') if isinstance(s, string_types) else "ERROR"
    else:
        return str(s)

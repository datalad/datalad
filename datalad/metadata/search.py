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
from six import PY3
from datalad.interface.base import Interface
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    require_dataset
from datalad.distribution.utils import get_git_dir
from ..support.param import Parameter
from ..support.constraints import EnsureNone
from ..support.constraints import EnsureChoice
from ..log import lgr
from . import get_metadata, flatten_metadata_graph, pickle

from datalad.consts import LOCAL_CENTRAL_PATH
from datalad.utils import assure_list
from datalad.utils import get_path_prefix
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.support import ansi_colors
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
        search=Parameter(
            args=('-s', '--search'),
            metavar='PROPERTY',
            action='append',
            # could also be regex
            doc="""name of the property to search for any match.[CMD:  This
            option can be given multiple times. CMD] By default, all properties
            are searched."""),
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
    def __call__(match,
                 dataset=None,
                 search=None,
                 report=None,
                 report_matched=False,
                 format='custom',
                 regex=False):

        lgr.debug("Initiating search for match=%r and dataset %r",
                  match, dataset)
        try:
            ds = require_dataset(dataset, check_installed=True, purpose='dataset search')
            if ds.id is None:
                raise NoDatasetArgumentFound(
                    "This does not seem to be a dataset (no DataLad dataset ID "
                    "found). 'datalad create --force %s' can initialize "
                    "this repository as a DataLad dataset" % ds.path)
        except NoDatasetArgumentFound:
            exc_info = sys.exc_info()
            if dataset is None:
                if not ui.is_interactive:
                    raise NoDatasetArgumentFound(
                        "No DataLad dataset found. Specify a dataset to be "
                        "searched, or run interactively to get assistance "
                        "installing a queriable superdataset."
                    )
                # none was provided so we could ask user either he possibly wants
                # to install our beautiful mega-duper-super-dataset?
                # TODO: following logic could possibly benefit other actions.
                if os.path.exists(LOCAL_CENTRAL_PATH):
                    central_ds = Dataset(LOCAL_CENTRAL_PATH)
                    if central_ds.is_installed():
                        if ui.yesno(
                            title="No DataLad dataset found at current location",
                            text="Would you like to search the DataLad "
                                 "superdataset at %r?"
                                  % LOCAL_CENTRAL_PATH):
                            pass
                        else:
                            reraise(*exc_info)
                    else:
                        raise NoDatasetArgumentFound(
                            "No DataLad dataset found at current location. "
                            "The DataLad superdataset location %r exists, "
                            "but does not contain an dataset."
                            % LOCAL_CENTRAL_PATH)
                elif ui.yesno(
                        title="No DataLad dataset found at current location",
                        text="Would you like to install the DataLad "
                             "superdataset at %r?"
                             % LOCAL_CENTRAL_PATH):
                    from datalad.api import install
                    central_ds = install(LOCAL_CENTRAL_PATH, source='///')
                    ui.message(
                        "From now on you can refer to this dataset using the "
                        "label '///'"
                    )
                else:
                    reraise(*exc_info)

                lgr.info(
                    "Performing search using DataLad superdataset %r",
                    central_ds.path
                )
                for res in central_ds.search(
                        match,
                        search=search, report=report,
                        report_matched=report_matched,
                        format=format, regex=regex):
                    yield res
                return
            else:
                raise

        cache_dir = opj(opj(ds.path, get_git_dir(ds.path)), 'datalad', 'cache')
        mcache_fname = opj(cache_dir, 'metadata.p%d' % pickle.HIGHEST_PROTOCOL)

        meta = None
        if os.path.exists(mcache_fname):
            lgr.debug("use cached metadata of '{}' from {}".format(ds, mcache_fname))
            meta, checksum = pickle.load(open(mcache_fname, 'rb'))
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
            # note with str() instead of '%' getting encoding issues...
            meta = sorted(meta, key=lambda m: tuple("%s" % (m.get(x, ""),) for x in sort_keys))

            # use pickle to store the optimized graph in the cache
            pickle.dump(
                # graph plus checksum from what it was built
                (meta, ds.repo.get_hexsha()),
                open(mcache_fname, 'wb'))
            lgr.debug("cached meta data graph of '{}' in {}".format(ds, mcache_fname))

        if report in ('', ['']):
            report = []
        elif report and not isinstance(report, list):
            report = [report]

        match = assure_list(match)
        search = assure_list(search)
        # convert all to lower case for case insensitive matching
        search = {x.lower() for x in search}

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

        # location should be reported relative to current location
        # We will assume that noone chpwd while we are yielding
        ds_path_prefix = get_path_prefix(ds.path)

        # So we could provide a useful message whenever there were not a single
        # dataset with specified `--search` properties
        observed_properties = set()

        # for every meta data set
        for mds in meta:
            hit = False
            hits = [False] * len(matchers)
            matched_fields = set()
            if not mds.get('type', mds.get('schema:type', None)) == 'Dataset':
                # we are presently only dealing with datasets
                continue
            # TODO consider the possibility of nested and context/graph dicts
            # but so far we were trying to build simple lists of dicts, as much
            # as possible
            if not isinstance(mds, dict):
                raise NotImplementedError("nested meta data is not yet supported")

            # manual loop for now
            for k, v in iteritems(mds):
                if search:
                    k_lower = k.lower()
                    if k_lower not in search:
                        if observed_properties is not None:
                            # record for providing a hint later
                            observed_properties.add(k_lower)
                        continue
                    # so we have a hit, no need to track
                    observed_properties = None
                if isinstance(v, dict) or isinstance(v, list):
                    v = text_type(v)
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
                if isinstance(location, (list, tuple)):
                    # could be that the same dataset installed into multiple
                    # locations. For now report them separately
                    for l in location:
                        yield opj(ds_path_prefix, l), report_dict
                else:
                    yield opj(ds_path_prefix, location), report_dict

        if search and observed_properties is not None:
            import difflib
            suggestions = {
                s: difflib.get_close_matches(s, observed_properties)
                for s in search
            }
            suggestions_str = "\n ".join(
                "%s for %s" % (", ".join(choices), s)
                for s, choices in iteritems(suggestions) if choices
            )
            lgr.warning(
                "Found no properties which matched one of the one you "
                "specified (%s).  May be you meant one among: %s.\n"
                "Suggestions:\n"
                " %s",
                ", ".join(search),
                ", ".join(observed_properties),
                suggestions_str if suggestions_str.strip() else "none"
            )

    @staticmethod
    def result_renderer_cmdline(res, cmdlineargs):
        from datalad.ui import ui
        if res is None:
            res = []

        format = cmdlineargs.format or 'custom'
        if format == 'custom':

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
                    ansi_colors.color_word(location, ansi_colors.DATASET),
                    ':' if r else '',
                    ichr,
                    jchr.join(
                        [
                            fmt.format(
                                k=ansi_colors.color_word(k, ansi_colors.FIELD),
                                v=pretty_bytes(r[k]))
                            for k in sorted(r)
                        ])))
                anything = True
            if not anything:
                ui.message("Nothing to report")
        elif format == 'json':
            import json
            ui.message(json.dumps(list(map(itemgetter(1), res)), indent=2))
        elif format == 'yaml':
            import yaml
            lgr.warning("yaml output support is not yet polished")
            ui.message(yaml.safe_dump(list(map(itemgetter(1), res)),
                                      allow_unicode=True))


_lines_regex = re.compile('[\n\r]')


def pretty_bytes(s):
    """Helper to provide sensible rendering for lists, dicts, and unicode

    encoded into byte-stream (why really???)
    """
    if isinstance(s, list):
        return ", ".join(map(pretty_bytes, s))
    elif isinstance(s, dict):
        return pretty_bytes(["%s=%s" % (pretty_bytes(k), pretty_bytes(v))
                             for k, v in s.items()])
    elif isinstance(s, text_type):
        s_ = (os.linesep + "  ").join(_lines_regex.split(s))
        try:
            if PY3:
                return s_
            return s_.encode('utf-8')
        except UnicodeEncodeError:
            lgr.warning("Failed to encode value correctly. Ignoring errors in encoding")
            # TODO: get current encoding
            return s_.encode('utf-8', 'ignore') if isinstance(s_, string_types) else "ERROR"
    else:
        return str(s).encode()

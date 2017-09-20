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
from os.path import join as opj, exists
from os.path import relpath
from os.path import normpath
import sys
from six import reraise
from six import string_types
from six import PY3

from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.interface.common_opts import reporton_opt
from datalad.interface.utils import eval_results
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    require_dataset
from datalad.distribution.utils import get_git_dir
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureInt
from datalad.log import lgr
from datalad.metadata.definitions import common_defs
from datalad.metadata.metadata import _query_aggregated_metadata

from datalad.consts import LOCAL_CENTRAL_PATH
from datalad.utils import assure_list
from datalad.utils import assure_unicode
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.ui import ui
from datalad.dochelpers import single_or_plural

unicode_srctypes = string_types
if PY3:
    unicode_srctypes = unicode_srctypes + (bytes,)

# this ammends the metadata key definitions (common_defs)
# default will be TEXT, hence we only need to specific the differences
# using string identifiers to not have to import whoosh at global scope
whoosh_field_types = {
    "id": "ID",
    "modified": "DATETIME",
}


def _add_document(idx, **kwargs):
    idx.add_document(
        **{assure_unicode(k):
           assure_unicode(v) if isinstance(v, unicode_srctypes) else v
           for k, v in kwargs.items()})


def _meta2index_dict(meta, schema):
    return {
        k: ', '.join(assure_unicode(i) for i in v)
        if isinstance(v, list) else assure_unicode(v)
        for k, v in (meta or {}).items()
        if k in schema.names()
    }


def _get_search_index(index_dir, ds, schema, force_reindex):
    from whoosh import index as widx

    if not force_reindex and exists(index_dir):
        try:
            # TODO check that the index schema is the same
            # as the one we would have used for reindexing
            # TODO support incremental re-indexing, whoosh can do it
            return widx.open_dir(index_dir)
        except widx.LockError as e:
            raise e
        except widx.IndexError as e:
            # Generic index error.
            # we try to regenerate
            # TODO log this
            pass
        except widx.IndexVersionError as e:  # (msg, version, release=None)
            # Raised when you try to open an index using a format that the
            # current version of Whoosh cannot read. That is, when the index
            # you're trying to open is either not backward or forward
            # compatible with this version of Whoosh.
            # we try to regenerate
            # TODO log this
            pass
        except widx.OutOfDateError as e:
            # Raised when you try to commit changes to an index which is not
            # the latest generation.
            # this should not happen here, but if it does ... KABOOM
            raise e
        except widx.EmptyIndexError as e:
            # Raised when you try to work with an index that has no indexed
            # terms.
            # we can just continue with generating an index
            pass

    if not exists(index_dir):
        os.makedirs(index_dir)

    idx_obj = widx.create_in(index_dir, schema)
    idx = idx_obj.writer()

    # load metadata of the base dataset and what it knows about all its subdatasets
    # (recursively)
    for res in _query_aggregated_metadata(
            # TODO expose parameter
            reporton='all',
            ds=ds,
            aps=[dict(path=ds.path, type='dataset')],
            # TODO expose? but this would likely only affect metadata in the
            # base dataset
            merge_mode='init',
            # MIH: I cannot see a case when we would not want recursion (within
            # the metadata)
            recursive=True):
            # **kwargs):
        _add_document(
            idx,
            id=ds.id if res['type'] == 'dataset' else None,
            path=relpath(res['path'], start=ds.path),
            type=res['type'],
            # TODO emulate old approach of building one giant text blob per entry
            # and anything else we know about, and is known to the schema
            **_meta2index_dict(res.get('metadata', None), schema))
    idx.commit()
    return idx_obj


def _search_from_virgin_install(dataset, query):
    #
    # this is to be nice to newbies
    #
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
        for res in central_ds.search(query):
            yield res
        return
    else:
        raise


@build_doc
class Search(Interface):
    """Search within available in datasets' meta data
    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to perform the query operation on. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        query=Parameter(
            args=("query",),
            metavar='QUERY',
            nargs="+",
            doc="tell me"),
        force_reindex=Parameter(
            args=("--reindex",),
            dest='force_reindex',
            action='store_true',
            doc="tell me"),
        max_nresults=Parameter(
            args=("--max-nresults",),
            doc="""maxmimum number of search results to report. Setting this
            to 0 will report any search matches, and make searching substantially
            slower on large metadata sets.""",
            constraints=EnsureInt()),
        reporton=reporton_opt,
        requery_metadata=Parameter(
            args=('--requery-metadata',),
            action='store_true',
            doc="""Flag whether to re-query up-to-date metadata for any path
            matching a search query that is presently available on disk.
            If not set, previously aggregated metadata will be reported instead.
            The latter might be substantially faster."""),
    )

    @staticmethod
    @datasetmethod(name='search')
    @eval_results
    def __call__(query,
                 dataset=None,
                 force_reindex=False,
                 max_nresults=20,
                 reporton='all',
                 requery_metadata=False):
        from whoosh import fields as wf
        from whoosh import qparser as qparse

        try:
            ds = require_dataset(dataset, check_installed=True, purpose='dataset search')
            if ds.id is None:
                raise NoDatasetArgumentFound(
                    "This does not seem to be a dataset (no DataLad dataset ID "
                    "found). 'datalad create --force %s' can initialize "
                    "this repository as a DataLad dataset" % ds.path)
        except NoDatasetArgumentFound:
            for r in _search_from_virgin_install(dataset, query):
                yield r
            return

        # where does the bunny have the eggs?
        index_dir = opj(ds.path, get_git_dir(ds.path), 'datalad', 'search_index')

        # auto-builds search schema from common metadata keys
        # the idea is to only store what we need to pull up the full metadata
        # for a search hit
        datalad_schema = wf.Schema(
            id=wf.ID(stored=True),
            path=wf.ID(stored=True),
            type=wf.ID(stored=True),
            **{k: getattr(wf, whoosh_field_types.get(k, 'TEXT'))
               # TODO not just common_defs, but the entire vocabulary defined
               # by any parser
               for k in common_defs
               if not k.startswith('@') and not k == 'type'})

        idx_obj = _get_search_index(
            index_dir, ds, datalad_schema, force_reindex)

        with idx_obj.searcher() as searcher:
            # parse the query string, default whoosh parser ATM, could be
            # tailored with plugins
            parser = qparse.MultifieldParser(
                # TODO same here, not just common defs
                [k for k in common_defs if not k.startswith('@')] +
                ['id', 'path', 'type'],
                datalad_schema)
            # XXX: plugin is broken in Debian's whoosh 2.7.0-2, but already fixed
            # upstream
            parser.add_plugin(qparse.FuzzyTermPlugin())
            parser.add_plugin(qparse.GtLtPlugin())
            # for convenience we accept any number of args-words from the
            # shell and put them together to a single string here
            querystr = ' '.join(assure_list(query))
            # this gives a formal whoosh query
            wquery = parser.parse(querystr)
            # perform the actual search
            hits = searcher.search(
                wquery,
                terms=True,
                limit=max_nresults if max_nresults > 0 else None)
            # cheap way to get an approximate number of hits, without an expensive
            # scoring of all items
            nhits = hits.estimated_length()
            # report query stats
            lgr.info('{} {} matching {} in {} sec.{}'.format(
                'Estimated' if nhits else 'Found',
                nhits,
                single_or_plural('record', 'records', nhits),
                hits.runtime,
                ' Reporting metadata for the {} top {}.'.format(
                    min(max_nresults, nhits),
                    single_or_plural(
                        'match', 'matches',
                        min(max_nresults, nhits)))
                if max_nresults else ''))
            # XXX now there are to principle ways to continue.
            # 1. we ignore everything, just takes the path of any hits
            #    and pass it to `metadata`, which will then do whatever is
            #    necessary and state of the art to report metadata
            #    This is great, because it minimizes the code, but it is likely
            #    a little slower, because annex might be called again to report
            #    file metadata, and we also loose some specificity (e.g. the
            #    `metadata` won't know whether we query a specific path to
            #    get all metadata for anything underneath it, or to just get
            #    dataset metadata
            # 2. we pull only from aggregated metadata. No calls, fast, but
            #    increased chances of yielding outdated results, and duplication
            #    in code base.
            # TODO implement alternative to just query aggregated metadata
            if not hits:
                return
            qpaths = [dict(
                # normpath to avoid trailing dot
                path=normpath(opj(ds.path, h['path'])),
                # we must not pre-annotate the paths with the recorded type
                # depending on how the metadata query below is performed
                # this will throw off the detection of absent subdatasets
                #type=h['type'],
                query_matched={assure_unicode(k): assure_unicode(v)
                               if isinstance(v, unicode_srctypes) else v
                               for k, v in h.matched_terms()})
                      for h in hits]
            if requery_metadata:
                gen = ds.metadata(
                    # turn hits into annotated paths
                    path=qpaths,
                    # TODO expose as arg?
                    merge_native='init',
                    reporton=reporton,
                    recursive=False,
                    return_type='generator',
                    on_failure='ignore',
                    result_renderer=None)
            else:
                gen = _query_aggregated_metadata(
                    reporton=reporton,
                    ds=ds,
                    aps=qpaths,
                    # TODO expose as arg?
                    merge_mode='init',
                    recursive=False)
            for r in gen:
                # assemble result
                r.update(dict(
                    action='search',
                    status='ok',
                    logger=lgr,
                    refds=ds.path))
                yield r

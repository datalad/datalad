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
from os.path import dirname
from os.path import relpath
import sys
from six import reraise

from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.interface.utils import eval_results
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import datasetmethod, EnsureDataset, \
    require_dataset
from datalad.distribution.utils import get_git_dir
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureNone
from datalad.support.constraints import EnsureInt
from datalad.log import lgr
from datalad.metadata.definitions import common_key_defs
from datalad.metadata.metadata import agginfo_relpath

from datalad.consts import LOCAL_CENTRAL_PATH
from datalad.utils import assure_list
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.support.json_py import load as jsonload
from datalad.ui import ui


# this ammends the metadata key definitions (common_key_defs)
# default will be TEXT, hence we only need to specific the differences
# using string identifiers to not have to import whoosh at global scope
whoosh_field_types = {
    "id": "ID",
    "modified": "DATETIME",
    "tag": "KEYWORD",
}


def _get_search_index(index_dir, ds, schema, force_reindex,
                      agginfo_fpath, agg_base_path):
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
    # load aggregate metadata
    for ds_relpath, ds_info in jsonload(agginfo_fpath).items():
        for item in ds_info:
            # load the stored data, if there is any
            if item.get('location', None):
                agg_obj_path = opj(agg_base_path, item['location'])
                md = jsonload(agg_obj_path)
            else:
                agg_obj_path = None
                md = {}
            agg_obj = relpath(agg_obj_path, start=agg_base_path) \
                if agg_obj_path else None
            if item['type'] == 'dataset':
                idx.add_document(
                    datalad__agg_obj=agg_obj,
                    id=item['id'],
                    path=ds_relpath,
                    type=item['type'],
                    # and anything else we know about, and is known to the schema
                    **{k: v for k, v in md.items()
                       if k in schema.names()})
            elif item['type'] == 'files':
                for f in md:
                    idx.add_document(
                        datalad__agg_obj=agg_obj,
                        path=f,
                        type='file',
                        # and anything else we know about, and is known to the schema
                        **{k: v for k, v in md[f].items()
                           if k in schema.names()})
    idx.commit()
    return idx_obj


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
    )

    @staticmethod
    @datasetmethod(name='search')
    @eval_results
    def __call__(query,
                 dataset=None,
                 force_reindex=False,
                 max_nresults=20):
        from whoosh import fields as wf
        from whoosh.qparser import QueryParser

        try:
            ds = require_dataset(dataset, check_installed=True, purpose='dataset search')
            if ds.id is None:
                raise NoDatasetArgumentFound(
                    "This does not seem to be a dataset (no DataLad dataset ID "
                    "found). 'datalad create --force %s' can initialize "
                    "this repository as a DataLad dataset" % ds.path)
        except NoDatasetArgumentFound:
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

        # where does the bunny have the eggs?
        agginfo_fpath = opj(ds.path, agginfo_relpath)
        agg_base_path = dirname(agginfo_fpath)

        index_dir = opj(ds.path, get_git_dir(ds.path), 'datalad', 'search_index')

        # auto-builds search schema from common metadata keys
        # the idea is to only store what we need to pull up the full metadata
        # for a search hit
        datalad_schema = wf.Schema(
            datalad__agg_obj=wf.STORED,
            id=wf.ID(stored=True),
            path=wf.ID(stored=True),
            type=wf.ID(stored=True),
            **{k: getattr(wf, whoosh_field_types.get(k, 'TEXT'))
               for k in common_key_defs
               if not k.startswith('@') and not k == 'type'})

        idx_obj = _get_search_index(
            index_dir, ds, datalad_schema, force_reindex,
            agginfo_fpath, agg_base_path)

        with idx_obj.searcher() as searcher:
            # parse the query string, default whoosh parser ATM, could be
            # tailored with plugins
            parser = QueryParser("description", datalad_schema)
            # for convenience we accept any number of args-words from the
            # shell and put them together to a single string here
            querystr = ' '.join(assure_list(query))
            # this gives a formal whoosh query
            wquery = parser.parse(querystr)
            # perform the actual search
            # TODO I believe the hits objects also has performance stats
            # -- we could show them ...
            hits = searcher.search(
                wquery,
                # TODO terms that actually matched could be reported
                #terms=True,
                limit=max_nresults if max_nresults > 0 else None)
            # XXX now there are to principle ways to continue.
            # 1. we ignore everything, just takes the path of any hits
            #    and pass it to `metadata`, which will then do whatever is
            #    necessary and state of the art to report metadata
            #    This is great, because it minimizes the code, but it is likely
            #    a little slower, because annex might be called again to report
            #    file metadata, and we also loose some specificity (e.g. the
            #    `metadata` won't know whether we query a specific path to
            #    get all metadata for anything underneath it, or to just get
            #    dataset metadata, code bits:
            #    for res in Metadata.__call__(
            #            dataset=ds.path,
            #            path=[r['path'] for r in hits if r.get('type', None) == 'dataset'],
            #            # limit queries (not just results) to datasets
            #            reporton='datasets',
            #            recursive=False,
            #            return_type='generator',
            #            on_failure='ignore',
            #            result_renderer=None):
            #        res['action'] = 'search'
            #        yield res
            # 2. we pull only form aggregated metadata. No calls, fast, but
            #    increased chances of yielding outdated results, and duplication
            #    in code base.
            # MIH: going with two, as only this approach offers an easy and fast
            #      way to maintain the order of hits during processing -- and
            #      only this allows for using whoosh features such as boosting
            #      results and all the other fancy stuff
            aggobj_cache = {}
            for r in hits:
                rtype = r.get('type', None)
                rpath = r['path']
                aggobj_path = r.get('datalad__agg_obj', None)
                if aggobj_path:
                    aggobj_path = opj(agg_base_path, aggobj_path)
                    # cache the JSON content, we might hit another file in here
                    md = aggobj_cache.get(aggobj_path, jsonload(aggobj_path))
                    aggobj_cache[aggobj_path] = md
                    if rtype == 'file':
                        md = md[r['path']]
                # TODO report matched terms in the result
                #matched = r.matched_terms()
                # assemble result
                res = dict(
                    action='search',
                    status='ok',
                    path=opj(ds.path, rpath),
                    type=rtype,
                    metadata=md,
                    #matched=matched,
                    logger=lgr,
                    refds=ds.path)
                yield res

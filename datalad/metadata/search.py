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
from datalad.metadata.definitions import vocabulary_id
from datalad.metadata.metadata import _query_aggregated_metadata
from datalad.metadata.metadata import MetadataDict

from datalad.consts import LOCAL_CENTRAL_PATH
from datalad.utils import assure_list
from datalad.utils import assure_unicode
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.ui import ui
from datalad.dochelpers import single_or_plural

unicode_srctypes = string_types
if PY3:
    unicode_srctypes = unicode_srctypes + (bytes,)


def _add_document(idx, **kwargs):
    idx.add_document(
        **{assure_unicode(k):
           assure_unicode(v) if isinstance(v, unicode_srctypes) else v
           for k, v in kwargs.items()})


def _meta2index_dict(meta, definitions, ds_defs):
    """Takes care of dtype conversion into unicode, potential key mappings
    and concatenation of sequence-type fields into CSV strings
    """
    # TODO maybe leave the unicode conversion out here and only do in
    # _add_document()
    # TODO also take care of the conversion from numerical values to a string type elsewhere
    return {
        # apply any dataset-specific key mapping
        ds_defs.get(k, k):
        # turn lists into CSV strings
        ', '.join(str(i) if isinstance(i, (int, float)) else assure_unicode(i) for i in v) if isinstance(v, (list, tuple)) else
        # dicts into SSV strings
        '; '.join(str(i) if isinstance(i, (int, float)) else assure_unicode(v[i]) for i in v) if isinstance(v, dict) else
        # and the rest into unicode
        str(v) if isinstance(v, (int, float)) else assure_unicode(v)
        for k, v in (meta or {}).items()
        # ignore anything that is not defined
        if k in definitions
    }


def _get_search_schema(ds):
    from whoosh import fields as wf

    # this will harvest all discovered term definitions
    definitions = {
        '@id': 'unique identifier of an entity',
        'path': 'path name of an entity relative to the searched base dataset',
        'parentds': 'path of the datasets that contains an entity',
        # 'type' will not come from a metadata field, hence will not be detected
        'type': common_defs['type'],
    }

    schema_fields = {
        n: wf.ID(stored=True, unique=n == '@id')
        for n in definitions}
    # this will contain any dataset-specific term mappings, in case we find
    # non-unique keys that are differently defined
    per_ds_defs = {}
    ds_defs = {}

    lgr.info('Scanning for metadata keys')
    # quick 1st pass over all dataset to gather the needed schema fields
    for res in _query_aggregated_metadata(
            reporton='datasets',
            ds=ds,
            aps=[dict(path=ds.path, type='dataset')],
            merge_mode='init',
            recursive=True):
        ds_defs = {}
        meta = res.get('metadata', {})
        for k, v in meta.get('@context', {}).items():
            if k not in definitions or definitions[k] == v:
                # this is new, but unique, or uniformly defined
                definitions[k] = v
            else:
                # non-unique key (across all seen datasets)
                # make unique
                # TODO we have to deal with @vocab fields in here, those
                # might be different when some aggregated metadata was
                # generated with an old version of datalad
                # in this case we should actually load the old vocabulary
                set.add(', '.join(i for i in v) if isinstance(v, (tuple, list)) else v)
                # and perform the mapping to the current one in here
                count = 0
                uk = k
                while uk in definitions:
                    count += 1
                    uk = '{}_{}'.format(k, count)
                ds_defs[k] = uk
                k = uk
            definitions[k] = v
            # we register a field for any definition in the context.
            # while this has the potential to needlessly blow up the
            # index size, the only alternative would be to iterate over
            # all content metadata in this first pass too, in order to
            # do a full scan.
            if k == '@vocab' or isinstance(v, dict) and v.get('type', None) == vocabulary_id:
                continue
            schema_fields[k] = wf.TEXT(stored=True)
        if ds_defs:
            # store ds-specific mapping for the second pass that actually
            # generates the search index
            per_ds_defs[res['path']] = ds_defs

        # anything that is a direct metadata key or is reported as being a content metadata
        # key is a valid candidate for inclusion into the schema
        cand_keys = list(meta)
        cand_keys.extend(meta.get('unique_content_properties', []))
        for k in cand_keys:
            # check if we have any kind of definitions for this key
            if k not in definitions:
                # not in the dataset definitions
                termdef = common_defs.get(k, None)
                if termdef is None:
                    # not in the common vocabulary
                    if ':' not in k and k.split(':')[0] not in definitions:
                        # this key also doesn't have a prefix that is defined in the
                        # vocabulary, we are lost -> ignore this key as it cannot
                        # possibly be resolved
                        continue
                    # we cannt resolve this for cheaps, just keep a record
                    definitions[k] = k
                else:
                    definitions[k] = termdef
                # TODO treat keywords/tags separately
                schema_fields[k] = wf.TEXT(stored=True)

    schema = wf.Schema(**schema_fields)
    return schema, definitions, per_ds_defs


def _get_search_index(index_dir, ds, force_reindex):
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

    schema, definitions, per_ds_defs = _get_search_schema(ds)

    idx_obj = widx.create_in(index_dir, schema)
    idx = idx_obj.writer()

    lgr.info('Building search index')
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
        rpath = relpath(res['path'], start=ds.path)
        # this assumes that files are reported after each dataset report,
        # and after a subsequent dataset report no files for the previous
        # dataset will be reported again
        rtype = res['type']
        meta = res.get('metadata', {})
        meta = MetadataDict(meta)
        if rtype == 'dataset':
            # get any custom dataset mappings
            ds_defs = per_ds_defs.get(res['path'], {})
            lgr.info('Adding information about Dataset %s', rpath)
            # now we merge all reported unique content properties (flattened representation
            # of content metadata) with the main metadata set, using the 'add' strategy
            # this way any existing metadata value of a dataset itself will be amended by
            # those coming from the content. E.g. a single dataset 'license' might be turned
            # into a sequence of unique license identifiers across all dataset components
            meta.merge_add(meta.get('unique_content_properties', {}))
            meta.pop('unique_content_properties', None)
        doc_props = dict(
            path=rpath,
            type=rtype,
            **_meta2index_dict(meta, definitions, ds_defs))
        if 'parentds' in res:
            doc_props['parentds'] = relpath(res['parentds'], start=ds.path)
        _add_document(idx, **doc_props)

    idx.commit()
    lgr.info('Search index contains %i documents', idx.doc_count())
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
            nargs="*",
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
        show_keys=Parameter(
            args=('--show-keys',),
            action='store_true',
            doc="""if given, a list of known search keys is shown (one per line).
            No other action is performed, even if other arguments are given."""),
    )

    @staticmethod
    @datasetmethod(name='search')
    @eval_results
    def __call__(query=None,
                 dataset=None,
                 force_reindex=False,
                 max_nresults=20,
                 show_keys=False):
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

        idx_obj = _get_search_index(
            index_dir, ds, force_reindex)

        if show_keys:
            for k in idx_obj.schema.names():
                print(k)
            return

        if not query:
            return

        with idx_obj.searcher() as searcher:
            # parse the query string, default whoosh parser ATM, could be
            # tailored with plugins
            parser = qparse.MultifieldParser(
                idx_obj.schema.names(),
                idx_obj.schema)
            # XXX: plugin is broken in Debian's whoosh 2.7.0-2, but already fixed
            # upstream
            parser.add_plugin(qparse.FuzzyTermPlugin())
            parser.add_plugin(qparse.GtLtPlugin())
            # replace field defintion to allow for colons to be part of a field's name:
            parser.replace_plugin(qparse.FieldsPlugin(expr=r"(?P<text>[:\w]+|[*]):"))
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
            # disabled: unreliable estimate, often confusing
            #nhits = hits.estimated_min_length()
            # report query stats
            lgr.info('Query completed in {} sec.{}'.format(
                hits.runtime,
                ' Reporting {}.'.format(
                    'max. {} top {}'.format(
                        max_nresults,
                        single_or_plural('match', 'matches', max_nresults))
                    if max_nresults > 0 else 'all matches')
                if not hits.is_empty() else ''))

            if not hits:
                return

            for hit in hits:
                res = dict(
                    action='search',
                    status='ok',
                    logger=lgr,
                    refds=ds.path,
                    # normpath to avoid trailing dot
                    path=normpath(opj(ds.path, hit['path'])),
                    query_matched={assure_unicode(k): assure_unicode(v)
                                   if isinstance(v, unicode_srctypes) else v
                                   for k, v in hit.matched_terms()},
                    metadata={k: v for k, v in hit.fields().items()
                              if k not in ('path', 'parentds')})
                if 'parentds' in hit:
                    res['parentds'] = normpath(opj(ds.path, hit['parentds']))
                yield res

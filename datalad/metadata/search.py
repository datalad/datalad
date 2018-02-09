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

import logging
lgr = logging.getLogger('datalad.metadata.search')

import re
import os
from os.path import join as opj, exists
from os.path import relpath
from os.path import normpath
import sys
from six import reraise
from six import string_types
from six import PY3

from datalad import cfg
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
from datalad.metadata.metadata import query_aggregated_metadata

from datalad.consts import LOCAL_CENTRAL_PATH
from datalad.consts import SEARCH_INDEX_DOTGITDIR
from datalad.utils import assure_list
from datalad.utils import assure_unicode
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.ui import ui
from datalad.dochelpers import single_or_plural
from datalad.dochelpers import exc_str

if PY3:
    unicode_srctypes = string_types + (bytes,)
    str_contructor = str
else:
    unicode_srctypes = string_types
    str_contructor = unicode

# regex for a cheap test if something looks like a URL
r_url = re.compile(r"^https?://")


def _any2unicode(val):
    if val is None:
        return u''
    return str_contructor(val) \
        if isinstance(val, (int, float, tuple, list, dict)) \
        else assure_unicode(val)


def _listdict2dictlist(lst):
    # unique values that we got, always a list
    if all(not isinstance(uval, dict) for uval in lst):
        # no nested structures, take as is
        return lst

    # we need to turn them inside out, instead of a list of
    # dicts, we want a dict where keys are lists, because we
    # cannot handle hierarchies in a tabular search index
    # if you came here to find that out, go ahead and use a graph
    # DB/search
    udict = {}
    for uv in lst:
        if not isinstance(uv, dict):
            # we cannot mix and match, discard any scalar values
            # in favor of the structured metadata
            continue
        for k, v in uv.items():
            if isinstance(v, (tuple, list, dict)):
                # this is where we draw the line, two levels of
                # nesting. whoosh can only handle string values
                # injecting a stringified blob of something doesn't
                # really enable anything useful -> graph search
                continue
            if v == "":
                # no cruft
                continue
            uvals = udict.get(k, set())
            uvals.add(v)
            udict[k] = uvals
    return {
        # set not good for JSON, have plain list
        k: list(v) if len(v) > 1 else list(v)[0]
        for k, v in udict.items()
        # do not accumulate cruft
        if len(v)}


#
# START: autofield mode functions
#
def _meta2autofield_dict(meta, val2str=True, schema=None):
    """Takes care of dtype conversion into unicode, potential key mappings
    and concatenation of sequence-type fields into CSV strings
    """
    # loop over all metadata sources and the report of their unique values
    for src in meta.get("datalad_unique_content_properties", {}):
        umeta = meta["datalad_unique_content_properties"][src]
        srcmeta = meta.get(src, {})
        for uk in umeta:
            if uk in srcmeta:
                # we have a real entry for this key in the dataset metadata
                # ignore any generated unique value list in favor of the
                # tailored data
                continue
            srcmeta[uk] = _listdict2dictlist(umeta[uk])

    def _deep_kv(basekey, dct):
        """Return key/value pairs of any depth following a rule for key
        composition

        dct must be a dict
        """
        for k, v in dct.items():
            if k.startswith('@') or k == 'datalad_unique_content_properties':
                # ignore all JSON-LD specials
                continue
            # TODO `k` might need remapping, if another key was already found
            # with the same definition
            key = '{}{}'.format(
                basekey,
                # replace now special chars, and avoid spaces
                # TODO maybe even kill parentheses
                k.replace(' ', '_').replace('-', '_').replace('.', '_').replace(':', '-')
            )
            if isinstance(v, list):
                v = _listdict2dictlist(v)

            if isinstance(v, dict):
                # dive
                for i in _deep_kv('{}.'.format(key), v):
                    yield i
            else:
                yield key, v

    return {
        k:
        # turn lists into space-separated value strings
        (u' '.join(_any2unicode(i) for i in v) if isinstance(v, (list, tuple)) else
         # and the rest into unicode
         _any2unicode(v)) if val2str else v
        for k, v in _deep_kv('', meta or {})
        # auto-exclude any key that is not a defined field in the schema (if there is
        # a schema
        if schema is None or k in schema
    }


def _get_schema_autofield(ds):
    from whoosh import fields as wf
    from whoosh.analysis import StandardAnalyzer

    # haven for terms that have been found to be undefined
    # (for faster decision-making upon next encounter)
    # this will harvest all discovered term definitions
    definitions = {
        '@id': 'unique identifier of an entity',
        # TODO make proper JSON-LD definition
        'path': 'path name of an entity relative to the searched base dataset',
        # TODO make proper JSON-LD definition
        'parentds': 'path of the datasets that contains an entity',
        # 'type' will not come from a metadata field, hence will not be detected
        'type': 'type of a record',
    }

    schema_fields = {
        n.lstrip('@'): wf.ID(stored=True, unique=n == '@id')
        for n in definitions}

    lgr.info('Scanning for metadata keys')
    # quick 1st pass over all dataset to gather the needed schema fields
    for res in query_aggregated_metadata(
            reporton='datasets',
            ds=ds,
            aps=[dict(path=ds.path, type='dataset')],
            recursive=True):
        meta = res.get('metadata', {})
        # no stringification of values for speed, we do not need/use the
        # actual values at this point, only the keys
        idxd = _meta2autofield_dict(meta, val2str=False)

        for k in idxd:
            schema_fields[k] = wf.TEXT(stored=True,
                                       analyzer=StandardAnalyzer(minsize=1))

    schema = wf.Schema(**schema_fields)
    return schema


def _get_parser_autofield(idx_obj):
    from whoosh import qparser as qparse

    parser = qparse.MultifieldParser(
        idx_obj.schema.names(),
        idx_obj.schema)
    # XXX: plugin is broken in Debian's whoosh 2.7.0-2, but already fixed
    # upstream
    parser.add_plugin(qparse.FuzzyTermPlugin())
    parser.add_plugin(qparse.GtLtPlugin())
    parser.add_plugin(qparse.SingleQuotePlugin())
    # replace field defintion to allow for colons to be part of a field's name:
    parser.replace_plugin(qparse.FieldsPlugin(expr=r"(?P<text>[()<>.\w]+|[*]):"))
    return parser


#
# START: homoblob mode functions
#
def _meta2homoblob_dict(meta, val2str=True, schema=None):
    # coerce the entire flattened metadata dict into a comma-separated string
    # that also includes the keys
    return dict(meta=u', '.join(
        '{}: {}'.format(k, v)
        for k, v in _meta2autofield_dict(
            meta,
            val2str=True,
            schema=None).items()))


def _get_schema_homoblob(ds):
    from whoosh import fields as wf
    from whoosh.analysis import StandardAnalyzer

    # TODO support some customizable mapping to homogenize some metadata fields
    # onto a given set of index keys
    schema = wf.Schema(
        id=wf.ID,
        path=wf.ID(stored=True),
        type=wf.ID(stored=True),
        parentds=wf.ID(stored=True),
        meta=wf.TEXT(
            stored=False,
            analyzer=StandardAnalyzer(minsize=2))
    )
    return schema


def _get_parser_homoblob(idx_obj):
    from whoosh import qparser as qparse

    return qparse.QueryParser(
        "meta",
        schema=idx_obj.schema
    )


def _get_search_index(index_dir, label, ds, force_reindex, get_schema, meta2doc):
    """Generic entrypoint to index generation

    The actual work that determines the structure and content of the index
    is done by functions that are passed in as arguments

    `get_schema` - must return whoosh schema
    `meta2doc` - must return dict for index document from result input
    `label` - string label to distinguish an index type from others (must be a valid
              directory name
    """
    from whoosh import index as widx
    from .metadata import agginfo_relpath
    # what is the lastest state of aggregated metadata
    metadata_state = ds.repo.get_last_commit_hash(agginfo_relpath)
    # use location common to all index types, they would all invalidate
    # simultaneously
    stamp_fname = opj(index_dir, 'datalad_metadata_state')
    index_dir = opj(index_dir, label)

    if (not force_reindex) and \
            exists(index_dir) and \
            exists(stamp_fname) and \
            open(stamp_fname).read() == metadata_state:
        try:
            # TODO check that the index schema is the same
            # as the one we would have used for reindexing
            # TODO support incremental re-indexing, whoosh can do it
            idx = widx.open_dir(index_dir)
            lgr.debug(
                'Search index contains %i documents',
                idx.doc_count())
            return idx
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
            lgr.warning(exc_str(e))
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

    lgr.info('{} search index'.format(
        'Rebuilding' if exists(index_dir) else 'Building'))

    if not exists(index_dir):
        os.makedirs(index_dir)

    schema = get_schema(ds)

    idx_obj = widx.create_in(index_dir, schema)
    idx = idx_obj.writer(
        # cache size per process
        limitmb=cfg.obtain('datalad.search.indexercachesize'),
        # disable parallel indexing for now till #1927 is resolved
        ## number of processes for indexing
        #procs=multiprocessing.cpu_count(),
        ## write separate index segments in each process for speed
        ## asks for writer.commit(optimize=True)
        #multisegment=True,
    )

    # load metadata of the base dataset and what it knows about all its subdatasets
    # (recursively)
    old_idx_size = 0
    old_ds_rpath = ''
    idx_size = 0
    for res in query_aggregated_metadata(
            reporton=ds.config.obtain('datalad.metadata.searchindex-documenttype'),
            ds=ds,
            aps=[dict(path=ds.path, type='dataset')],
            # MIH: I cannot see a case when we would not want recursion (within
            # the metadata)
            recursive=True):
        # this assumes that files are reported after each dataset report,
        # and after a subsequent dataset report no files for the previous
        # dataset will be reported again
        meta = res.get('metadata', {})
        doc = meta2doc(
            meta,
            # this time stringification of values so whoosh can handle them
            val2str=True,
            schema=schema)
        admin = {
            'type': res['type'],
            'path': relpath(res['path'], start=ds.path),
        }
        if 'parentds' in res:
            admin['parentds'] = relpath(res['parentds'], start=ds.path)
        if admin['type'] == 'dataset':
            if old_ds_rpath:
                lgr.info(
                    'Added %s on dataset %s',
                    single_or_plural(
                        'document',
                        'documents',
                        idx_size - old_idx_size,
                        include_count=True),
                    old_ds_rpath)
            old_idx_size = idx_size
            old_ds_rpath = admin['path']

        doc.update({k: assure_unicode(v) for k, v in admin.items()})
        # inject into index
        idx.add_document(**doc)
        idx_size += 1

    if old_ds_rpath:
        lgr.info(
            'Added %s on dataset %s',
            single_or_plural(
                'document',
                'documents',
                idx_size - old_idx_size,
                include_count=True),
            old_ds_rpath)

    lgr.debug("Committing index")
    idx.commit(optimize=True)

    # "timestamp" the search index to allow for automatic invalidation
    with open(stamp_fname, 'w') as f:
        f.write(metadata_state)

    lgr.info('Search index contains %i documents', idx_size)
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
    """Search a dataset's metadata.

    Search capabilities depend on the amount and nature of metadata available
    in a dataset. This can include metadata about a dataset as a whole, or
    metadata on dataset content (e.g. one or more files). One dataset can also
    contain metadata from multiple subdatasets (see the 'aggregate-metadata'
    command), in which case a search can discover any dataset or any file in
    of these datasets.

    A search index is automatically built from the available metadata of any
    dataset or file, and a schema for this index is generated dynamically, too.
    Consequently, the search index will be tailored to data provided in a
    particular collection of datasets.

    Metadata fields (and possibly also values) are typically defined terms from
    a controlled vocabulary. Field names are accessible via the --show-keys
    flag.

    DataLad's search is built on the Python package 'Whoosh', which provides
    a powerful query language. Links to a description of the language and
    particular feature can be found below.

    Here are a few examples. Basic search::

      % datalad search searchterm

    Search for a file::

      % datalad search searchterm type:file


    *Performance considerations*

    For dataset collections with many files (100k+) generating a comprehensive
    search index comprised of documents for datasets and individual files can
    take a considerable amount of time. If this becomes an issue, search index
    generation can be limited to a particular type of document (see the
    'metadata --reporton' option for possible values). The configuration
    setting 'datalad.metadata.searchindex-documenttype' will be queried on
    search index generation. It is recommended to place an appropriate
    configuration into a dataset's configuration file (.datalad/config)::

      [datalad "metadata"]
        searchindex-documenttype = datasets

    .. seealso::
      - Description of the Whoosh query language:
        http://whoosh.readthedocs.io/en/latest/querylang.html)
      - Description of a number of query language customizations that are
        enabled in DataLad, such as, querying multiple fields by default and
        fuzzy term matching:
        http://whoosh.readthedocs.io/en/latest/parsing.html#common-customizations
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
            doc="""search query using the Whoosh query language (see link to
            detailed description above). For simple queries, any number of search
            terms can be given as a list[CMD: (space-separated) CMD], and the
            query will return all hits that match all terms (AND) in any combination
            of fields (OR)."""),
        force_reindex=Parameter(
            args=("--reindex",),
            dest='force_reindex',
            action='store_true',
            doc="""force rebuilding the search index, even if no change in the
            dataset's state has been detected. This is mostly useful for
            developing new metadata support extensions."""),
        max_nresults=Parameter(
            args=("--max-nresults",),
            doc="""maxmimum number of search results to report. Setting this
            to 0 will report all search matches, and make searching substantially
            slower on large metadata sets.""",
            constraints=EnsureInt()),
        mode=Parameter(
            args=("--mode",),
            choices=('default', 'autofield',),
            nargs=1,
            doc="""Mode of search index structure and content. 'autofield': metadata
            fields are discovered automatically, datasets and files can be discovered.
            """),
        show_keys=Parameter(
            args=('--show-keys',),
            action='store_true',
            doc="""if given, a list of known search keys is shown (one per line).
            No other action is performed (except for reindexing), even if other
            arguments are given. Each key is accompanied by a term definition in
            parenthesis. In most cases a definition is given in the form
            of a URL. If an ontology definition for a term is known, this URL
            can resolve to a webpage that provides a comprehensive definition
            of the term. However, for speed reasons term resolution is solely done
            on information contained in a local dataset's metadata, and definition
            URLs might be outdated or point to no longer existing resources."""),
        show_query=Parameter(
            args=('--show-query',),
            action='store_true',
            doc="""if given, the formal query that was generated from the given
            query string is shown, but not actually executed. This is mostly useful
            for debugging purposes."""),
    )

    @staticmethod
    @datasetmethod(name='search')
    @eval_results
    def __call__(query=None,
                 dataset=None,
                 force_reindex=False,
                 max_nresults=20,
                 mode='default',
                 show_keys=False,
                 show_query=False):
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
        index_dir = opj(ds.path, get_git_dir(ds.path), SEARCH_INDEX_DOTGITDIR)

        if mode == 'default':
            get_schema_fx = _get_schema_homoblob
            meta2doc_fx = _meta2homoblob_dict
            get_parser = _get_parser_homoblob
        elif mode == 'autofield':
            get_schema_fx = _get_schema_autofield
            meta2doc_fx = _meta2autofield_dict
            get_parser = _get_parser_autofield

        idx_obj = _get_search_index(
            index_dir,
            mode,
            ds,
            force_reindex,
            get_schema_fx,
            meta2doc_fx)

        if show_keys:
            for k in idx_obj.schema.names():
                print('{}'.format(k))
            return

        if not query:
            return

        with idx_obj.searcher() as searcher:
            # parse the query string
            parser = get_parser(idx_obj)
            # for convenience we accept any number of args-words from the
            # shell and put them together to a single string here
            querystr = ' '.join(assure_list(query))
            # this gives a formal whoosh query
            wquery = parser.parse(querystr)

            if show_query:
                print(wquery)
                return
            # perform the actual search
            hits = searcher.search(
                wquery,
                terms=True,
                limit=max_nresults if max_nresults > 0 else None)
            # report query stats
            topstr = '{} top {}'.format(
                max_nresults,
                single_or_plural('match', 'matches', max_nresults)
            )
            lgr.info('Query completed in {} sec.{}'.format(
                hits.runtime,
                ' Reporting {}.'.format(
                    ('up to ' + topstr)
                    if max_nresults > 0
                    else 'all matches'
                )
                if not hits.is_empty()
                else ' No matches.'
            ))

            if not hits:
                return

            nhits = 0
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
                if res['metadata'].get('type', None) in ('file', 'dataset'):
                    res['type'] = res['metadata']['type']
                yield res
                nhits += 1

            if max_nresults and nhits == max_nresults:
                lgr.info(
                    "Reached the limit of {}, there could be more which "
                    "were not reported.".format(topstr)
                )

# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
import os
import re
import sys
from functools import partial

from datalad import cfg
from datalad.distribution.dataset import Dataset
from datalad.metadata.search import lgr
from datalad.support.exceptions import NoDatasetFound
from datalad.ui import ui
from datalad.utils import as_unicode

# TODO: consider using plain as_unicode, without restricting
# the types?

_any2unicode = partial(as_unicode, cast_types=(int, float, tuple, list, dict))


def _listdict2dictlist(lst, strict=True):
    """Helper to deal with DataLad's unique value reports

    Parameters
    ----------
    lst : list
      List of dicts
    strict : bool
      In strict mode any dictionary items that doesn't have a simple value
      (but another container) is discarded. In non-strict mode, arbitrary
      levels of nesting are preserved, and no unique-ification of values
      is performed. The latter can be used when it is mostly (or merely)
      interesting to get a list of metadata keys.
    """
    # unique values that we got, always a list
    if all(not isinstance(uval, dict) for uval in lst):
        # no nested structures, take as is
        return lst

    type_excluder = (tuple, list)
    if strict:
        type_excluder += (dict,)
    # we need to turn them inside out, instead of a list of
    # dicts, we want a dict where values are lists, because we
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
            if isinstance(v, type_excluder):
                # this is where we draw the line, two levels of
                # nesting. whoosh can only handle string values
                # injecting a stringified blob of something doesn't
                # really enable anything useful -> graph search
                continue
            if v == "":
                # no cruft
                continue
            if strict:
                # no duplicate values, only hashable stuff
                uvals = udict.get(k, set())
                uvals.add(v)
            else:
                # whatever it is, we'll take it
                uvals = udict.get(k, [])
                uvals.append(v)
            udict[k] = uvals
    return {
        # set not good for JSON, have plain list
        k: list(v) if len(v) > 1 else list(v)[0]
        for k, v in udict.items()
        # do not accumulate cruft
        if len(v)}


def _meta2autofield_dict(meta, val2str=True, schema=None, consider_ucn=True):
    """Takes care of dtype conversion into unicode, potential key mappings
    and concatenation of sequence-type fields into CSV strings

    - if `consider_ucn` (default) it would copy keys from
      datalad_unique_content_properties into `meta` for that extractor
    - ... TODO ...
    """
    if consider_ucn:
        # loop over all metadata sources and the report of their unique values
        ucnprops = meta.get("datalad_unique_content_properties", {})
        for src, umeta in ucnprops.items():
            srcmeta = meta.get(src, {})
            for uk in umeta:
                if uk in srcmeta:
                    # we have a real entry for this key in the dataset metadata
                    # ignore any generated unique value list in favor of the
                    # tailored data
                    continue
                srcmeta[uk] = _listdict2dictlist(umeta[uk], strict=False) if umeta[uk] is not None else None
            if src not in meta and srcmeta:
                meta[src] = srcmeta  # assign the new one back

    srcmeta = None   # for paranoids to avoid some kind of manipulation of the last

    def _deep_kv(basekey, dct):
        """Return key/value pairs of any depth following a rule for key
        composition

        dct must be a dict
        """
        for k, v in dct.items():
            if (k != '@id' and k.startswith('@')) or k == 'datalad_unique_content_properties':
                # ignore all JSON-LD specials, but @id
                continue
            # TODO `k` might need remapping, if another key was already found
            # with the same definition
            key = u'{}{}'.format(
                basekey,
                # replace now special chars, and avoid spaces
                # `os.sep` needs to go, because whoosh uses the field name for
                # temp files during index staging, and trips over absent "directories"
                # TODO maybe even kill parentheses
                # TODO actually, it might be better to have an explicit whitelist
                k.lstrip('@').replace(os.sep, '_').replace(' ', '_').replace('-', '_').replace('.', '_').replace(':', '-')
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


def _search_from_virgin_install(dataset, query):
    #
    # this is to be nice to newbies
    #
    exc_info = sys.exc_info()
    if dataset is None:
        if not ui.is_interactive:
            raise NoDatasetFound(
                "No DataLad dataset found. Specify a dataset to be "
                "searched, or run interactively to get assistance "
                "installing a queriable superdataset."
            )
        # none was provided so we could ask user whether he possibly wants
        # to install our beautiful mega-duper-super-dataset?
        # TODO: following logic could possibly benefit other actions.
        DEFAULT_DATASET_PATH = cfg.obtain('datalad.locations.default-dataset')
        if os.path.exists(DEFAULT_DATASET_PATH):
            default_ds = Dataset(DEFAULT_DATASET_PATH)
            if default_ds.is_installed():
                if ui.yesno(
                    title="No DataLad dataset found at current location",
                    text="Would you like to search the DataLad "
                         "superdataset at %r?"
                          % DEFAULT_DATASET_PATH):
                    pass
                else:
                    raise exc_info[1]
            else:
                raise NoDatasetFound(
                    "No DataLad dataset found at current location. "
                    "The DataLad superdataset location %r exists, "
                    "but does not contain an dataset."
                    % DEFAULT_DATASET_PATH)
        elif ui.yesno(
                title="No DataLad dataset found at current location",
                text="Would you like to install the DataLad "
                     "superdataset at %r?"
                     % DEFAULT_DATASET_PATH):
            from datalad.api import install
            default_ds = install(DEFAULT_DATASET_PATH, source='///')
            ui.message(
                "From now on you can refer to this dataset using the "
                "label '///'"
            )
        else:
            raise exc_info[1]

        lgr.info(
            "Performing search using DataLad superdataset %r",
            default_ds.path
        )
        for res in default_ds.search(query):
            yield res
        return
    else:
        raise  # this function is called within exception handling block


class _Search(object):
    _default_documenttype = None  # Abstract: To be specified in subclasses

    def __init__(self, ds, **kwargs):
        self.ds = ds
        self.documenttype = self.ds.config.obtain(
            'datalad.search.index-{}-documenttype'.format(self._mode_label),
            default=self._default_documenttype)

    def __call__(self, query, max_nresults=None):
        raise NotImplementedError

    @classmethod
    def _key_matches(cls, k, regexes):
        """Return which regex the key matches
        """
        for regex in regexes:
            if re.search(regex, k):
                return regex

    def show_keys(self, *args, **kwargs):
        raise NotImplementedError(args)

    def get_query(self, query):
        """Prepare query structure specific for a search backend.

        It can also memorize within instance some parameters of the last query
        which could be used to assist output formatting/structuring later on
        """
        raise NotImplementedError

    def get_nohits_msg(self):
        """Given what it knows, provide recommendation in the case of no hits"""
        return "No search hits, wrong query? " \
               "See 'datalad search --show-keys name' for known keys " \
               "and 'datalad search --help' on how to prepare your query."


class _LoopySearch(_Search):
    """A search engine implementing providing the base implementation for search
    via looping through datasets and their metadata

    TODO:
    - add support for early exits from a loop
    - parallelize at dataset level
    - expand with its features and options common to all loopy engines
    """
    _default_documenttype = 'datasets'

    # def __init__(self, ds, **kwargs):
    #     super(_PyEvalSearch, self).__init__(ds, **kwargs)
    #     #self._queried_keys = None  # to be memoized by get_query

    @classmethod  # insofar
    def _prep_meta(cls, meta):
        """Convert metadata to a "doc" usable by backend.

        E.g. it could flatten hierarhical metadata structure.
        By default - just return a copy of meta so it could be augmented
        """
        return meta.copy()

    @classmethod
    def _prep_key(cls, key):
        """Possibly sanitize keys. By default - nothing is done"""
        return key

    def _get_matcher(self, query, executed_query):
        """
        Parameters
        ----------
        """
        raise NotImplementedError(
            "Every engine should provide its own matcher based on its instance parameters and "
            "given a query"
        )

    def _prep_search_doc(self, meta, res):
        """Prepare a document used in search.

        It would rely on additional _prep methods such as `_prep_meta` and `_prep_key`
        which might be specific to the engine"""
        # possibly flatten or do other manipulations engine specific
        doc = self._prep_meta(meta)
        # inject a few basic properties into the dict
        # analog to what the other modes do in their index
        doc.update({
            # RF: @ replacement specific to pyeval since variable cannot start with @!
            self._prep_key(k): res[k]
            for k in ('@id', 'type', 'path', 'parentds')
            if k in res
        })
        return doc

    # TODO2: that loop would be two nested dataset/files so we could
    #  quickly exit whenever enough per dataset (e.g. 1) found
    def __call__(self, query, max_nresults=None, full_record=True):
        from itertools import chain
        from time import time

        from datalad.utils import ensure_list
        from datalad.metadata.metadata import query_aggregated_metadata

        query = ensure_list(query)
        if max_nresults is None:
            # no limit by default
            max_nresults = 0
        # TODO: how to provide engine-specific customizaions into the query?
        executed_query = self.get_query(query)


        # TODO: abstract away matcher!
        def matcher(doc):
            try:
                return eval(executed_query, {}, doc)
            except (KeyError, NameError) as exc:
                # lgr.debug("Something was missing in the record -- should be generally ok")
                # TODO: record if ANY matching resulted in not hitting this.
                #  If not -- we must have misspecified something, and should
                #  alert user similarly to get_nohits_msg of egrep.
                #  So -- we need smth like _queried_keys here as well
                pass
            except Exception as exc:
                # TODO: we could analyze each part of executed_query independently
                # (if len(query) > 1) to provide a more specific pointer to what part
                # has caused a failure
                lgr.info("Failed to match %s: %s", query, exc_str())

        nhits = 0
        # TODO: That is the most likely target for parallelization
        # TODO: interface recursion limit? insofar I had no use cases for that
        for ds in chain([self.ds], self.ds.subdatasets(recursive=True, return_type='generator')]:
            for res in query_aggregated_metadata(
                    reporton=self.documenttype,
                    ds=ds,
                    aps=[dict(path=ds.path, type='dataset')],
                    recursive=False):
                # this assumes that files are reported after each dataset report,
                # and after a subsequent dataset report no files for the previous
                # dataset will be reported again
                meta = res.get('metadata', {})
                # Metadata record might need to be enhanced with additional keys from res
                # We will call that structure a 'doc' in good memory of whoosh
                doc = self._prep_search_doc(meta, res)

                lgr.log(7, "Querying %s among %d items", query, len(doc))
                t0 = time()
                is_a_match = matcher(doc)
                dt = time() - t0
                lgr.log(7, "Finished querying in %f sec", dt)

                # The rest below seemed to be specific to the grep one, although
                # TODO: check exactly what was intended
                # # retain what actually matched
                # matched = {k[1]: match.group() for k, match in matches.items() if match}
                # # implement AND behavior across query expressions, but OR behavior
                # # across queries matching multiple fields for a single query expression
                # # for multiple queries, this makes it consistent with a query that
                # # has no field specification
                # if matched and len(query) == len(set(k[0] for k in matches if matches[k])):
                if is_a_match:
                    hit = dict(
                        res,
                        action='search',
                        # query_matched=matched,
                    )
                    yield hit
                    nhits += 1
                    if max_nresults and nhits == max_nresults:
                        # report query stats
                        topstr = '{} top {}'.format(
                            max_nresults,
                            single_or_plural('match', 'matches', max_nresults)
                        )
                        lgr.info(
                            "Reached the limit of {}, there could be more which "
                            "were not reported.".format(topstr)
                        )
                        break
# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import re
from time import time

from datalad.dochelpers import single_or_plural
from datalad.metadata.metadata import query_aggregated_metadata
from datalad.metadata.search import lgr
from datalad.metadata.search_base import _Search, _meta2autofield_dict
from datalad.utils import assure_unicode, shortened_repr, assure_list, \
    get_suggestions_msg


class _EGrepCSSearch(_Search):
    _mode_label = 'egrepcs'

    def __init__(self, ds, **kwargs):
        super(_EGrepCSSearch, self).__init__(ds, **kwargs)
        self._queried_keys = None  # to be memoized by get_query

    @classmethod
    def _prep_meta(cls, meta):
        return _meta2autofield_dict(meta, val2str=True, consider_ucn=False)

    # If there were custom "per-search engine" options, we could expose
    # --consider_ucn - search through unique content properties of the dataset
    #    which might be more computationally demanding
    def __call__(self, query, max_nresults=None, full_record=True):
        if max_nresults is None:
            # no limit by default
            max_nresults = 0
        executed_query = self.get_query(query)

        nhits = 0
        for res in query_aggregated_metadata(
                reporton=self.documenttype,
                ds=self.ds,
                aps=[dict(path=self.ds.path, type='dataset')],
                # MIH: I cannot see a case when we would not want recursion (within
                # the metadata)
                recursive=True):
            # this assumes that files are reported after each dataset report,
            # and after a subsequent dataset report no files for the previous
            # dataset will be reported again
            meta = res.get('metadata', {})
            # produce a flattened metadata dict to search through
            doc = _meta2autofield_dict(meta, val2str=True, consider_ucn=False)
            # inject a few basic properties into the dict
            # analog to what the other modes do in their index
            doc.update({
                k: res[k] for k in ('@id', 'type', 'path', 'parentds')
                if k in res})
            # use search instead of match to not just get hits at the start of the string
            # this will be slower, but avoids having to use actual regex syntax at the user
            # side even for simple queries
            # DOTALL is needed to handle multiline description fields and such, and still
            # be able to match content coming for a later field
            lgr.log(7, "Querying %s among %d items", executed_query, len(doc))
            t0 = time()
            matches = {(q['query'] if isinstance(q, dict) else q, k):
                       q['query'].search(v) if isinstance(q, dict) else q.search(v)
                       for k, v in doc.items()
                       for q in executed_query
                       if not isinstance(q, dict) or q['field'].match(k)}
            dt = time() - t0
            lgr.log(7, "Finished querying in %f sec", dt)
            # retain what actually matched
            matched = {k[1]: match.group() for k, match in matches.items() if match}
            # implement AND behavior across query expressions, but OR behavior
            # across queries matching multiple fields for a single query expression
            # for multiple queries, this makes it consistent with a query that
            # has no field specification
            if matched and len(executed_query) == len(set(k[0] for k in matches if matches[k])):
                hit = dict(
                    res,
                    action='search',
                    query_matched=matched,
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

    def show_keys(self, mode=None, regexes=None):
        """

        Parameters
        ----------
        mode: {"name", "short", "full"}
        regexes: list of regex
          Which keys to bother working on
        """
        maxl = 100  # approx maximal line length for unique values in mode=short
        # use a dict already, later we need to map to a definition
        # meanwhile map to the values

        keys = self._get_keys(mode)

        for k in sorted(keys):
            if regexes and not self._key_matches(k, regexes):
                continue
            if mode == 'name':
                print(k)
                continue

            # do a bit more
            stat = keys[k]
            all_uvals = uvals = sorted(stat.uvals)

            stat.uvals_str = assure_unicode(
                "{} unique values: ".format(len(all_uvals))
            )

            if mode == 'short':
                # show only up until we fill maxl
                uvals_str = ''
                uvals = []
                for v in all_uvals:
                    appendix = ('; ' if uvals else '') + v
                    if len(uvals_str) + len(appendix) > maxl - len(stat.uvals_str):
                        break
                    uvals.append(v)
                    uvals_str += appendix
            elif mode == 'full':
                pass
            else:
                raise ValueError(
                    "Unknown value for stats. Know full and short")

            stat.uvals_str += '; '.join(uvals)

            if len(all_uvals) > len(uvals):
                stat.uvals_str += \
                    '; +%s' % single_or_plural("value", "values", len(all_uvals) - len(uvals), True)

            print(
                u'{k}\n in  {stat.ndatasets} datasets\n has {stat.uvals_str}'.format(
                k=k, stat=stat
            ))
        # After #2156 datasets may not necessarily carry all
        # keys in the "unique" summary
        lgr.warning('In this search mode, the reported list of metadata keys may be incomplete')


    def _get_keys(self, mode=None):
        """Return keys and their statistics if mode != 'name'."""
        class key_stat:
            def __init__(self):
                self.ndatasets = 0  # how many datasets have this field
                self.uvals = set()

        from collections import defaultdict
        keys = defaultdict(key_stat)
        for res in query_aggregated_metadata(
                # XXX TODO After #2156 datasets may not necessarily carry all
                # keys in the "unique" summary
                reporton='datasets',
                ds=self.ds,
                aps=[dict(path=self.ds.path, type='dataset')],
                recursive=True):
            meta = res.get('metadata', {})
            # inject a few basic properties into the dict
            # analog to what the other modes do in their index
            meta.update({
                k: res.get(k, None) for k in ('@id', 'type', 'path', 'parentds')
                # parentds is tricky all files will have it, but the dataset
                # queried above might not (single dataset), let's force it in
                if k == 'parentds' or k in res})

            # no stringification of values for speed
            idxd = _meta2autofield_dict(meta, val2str=False)

            for k, kvals in idxd.items():
                # TODO deal with conflicting definitions when available
                keys[k].ndatasets += 1
                if mode == 'name':
                    continue
                keys[k].uvals |= self.get_repr_uvalues(kvals)
        return keys

    def get_repr_uvalues(self, kvals):
        kvals_set = set()
        if not kvals:
            return kvals_set
        kvals_iter = (
            kvals
            if hasattr(kvals, '__iter__') and not isinstance(kvals, (str, bytes))
            else [kvals]
        )
        return set(shortened_repr(x, 50) for x in kvals_iter)

    def get_query(self, query):
        query = assure_list(query)
        simple_fieldspec = re.compile(r"(?P<field>\S*?):(?P<query>.*)")
        quoted_fieldspec = re.compile(r"'(?P<field>[^']+?)':(?P<query>.*)")
        query_rec_matches = [
            simple_fieldspec.match(q) or
            quoted_fieldspec.match(q) or
            q
            for q in query]
        query_group_dicts_only = [
            q.groupdict() for q in query_rec_matches if hasattr(q, 'groupdict')
        ]
        self._queried_keys = [
            qgd['field']
            for qgd in query_group_dicts_only
            if ('field' in qgd and qgd['field'])
        ]
        if len(query_group_dicts_only) != len(query_rec_matches):
            # we had a query element without field specification add
            # None as an indicator of that
            self._queried_keys.append(None)
        # expand matches, compile expressions
        query = [
            {k: self._compile_query(v) for k, v in q.groupdict().items()}
            if hasattr(q, 'groupdict') else self._compile_query(q)
            for q in query_rec_matches
        ]

        # turn "empty" field specs into simple queries
        # this is used to forcibly disable field-based search
        # e.g. when searching for a value
        query = [q['query']
                 if isinstance(q, dict) and q['field'].pattern == '' else q
                 for q in query]
        return query

    def _xfm_query(self, q):
        # implement potential transformations of regex before they get compiled
        return q

    def _compile_query(self, q):
        """xfm and compile the query, with informative exception if query is incorrect
        """
        q_xfmed = self._xfm_query(q)
        try:
            return re.compile(q_xfmed)
        except re.error as exc:
            omsg = " (original: '%s')" % q if q != q_xfmed else ''
            raise ValueError(
                "regular expression '%s'%s is incorrect: %s"
                % (q_xfmed, omsg, exc)
            )

    def get_nohits_msg(self):
        """Given the query and performed search, provide recommendation

        Quite often a key in the query is mistyped or I simply query for something
        which is not actually known.  It requires --show-keys  run first, doing
        visual search etc to mitigate.  Here we can analyze either all queried
        keys are actually known, and if not known -- what would be the ones available.

        Returns
        -------
        str
          A sentence or a paragraph to be logged/output
        """
        #
        queried_keys = self._queried_keys[:]
        if queried_keys and None in queried_keys:
            queried_keys.pop(queried_keys.index(None))
        if not queried_keys:
            return  # No keys were queried, we are of no use here
        known_keys = self._get_keys(mode='name')
        unknown_keys = sorted(list(set(queried_keys).difference(known_keys)))
        if not unknown_keys:
            return  # again we are of no help here
        msg = super(_EGrepCSSearch, self).get_nohits_msg()
        msg += " Following keys were not found in available metadata: %s. " \
              % ", ".join(unknown_keys)
        suggestions_msg = get_suggestions_msg(unknown_keys, known_keys)
        if suggestions_msg:
            msg += ' ' + suggestions_msg
        return msg


class _EGrepSearch(_EGrepCSSearch):
    _mode_label = 'egrep'
    _default_documenttype = 'datasets'

    def _xfm_query(self, q):
        if q == q.lower():
            # we have no upper case symbol in the query, go case-insensitive
            return '(?i){}'.format(q)
        else:
            return q
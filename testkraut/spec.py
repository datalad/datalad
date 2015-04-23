# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the testkraut package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

__docformat__ = 'restructuredtext'

import json
import difflib
from uuid import uuid1 as uuid

__allowed_spec_keys__ = [
        'assertions',
        'authors',
        'dependencies',
        'description',
        'environment',
        'id',
        'inputs',
        'metrics',
        'outputs',
        'processes',
        'tests',
        'version',
    ]

def _raise(exception, why, input=None):
    if not input is None:
        input = ' (got: %s)' % repr(input)
    else:
        input = ''
    raise exception("SPEC: %s%s" % (why, input))

def _verify_tags(struct, tags, name):
    for tag in tags:
        if isinstance(tag, set):
            if not tag.intersection(struct):
                _raise(ValueError,
                       "at least one of the keys %s must be in %s" % (tag, name))
        else:
            if not tag in struct:
                _raise(ValueError,
                       "mandatory key '%s' is not in %s" % (tag, name))

def _verify_spec_tags(specs, tags, name):
    for i, os_id in enumerate(specs):
        os = specs[os_id]
        _verify_tags(os, tags, '%s: %s' % (name, os_id))

class SPECJSONEncoder(json.JSONEncoder):
    def default(self, o):
        try:
            import numpy as np
            if isinstance(o, np.ndarray):
                if len(o.shape):
                    return list(o)
                else:
                    # 0d-arrays
                    return o.item()
        except ImportError:
            # let is fail elsewhere if numpy is not available
            pass
        return super(SPECJSONEncoder, self).default(o)

class SPEC(dict):
    def __init__(self, src=None):
        dict.__init__(self)
        if isinstance(src, file):
            self.update(json.load(src))
        elif isinstance(src, basestring):
            self.update(json.loads(src))
        elif isinstance(src, dict):
            self.update(src)
        # charge with sane defaults
        if not 'id' in self:
            self['id'] = uuid().hex
        if not 'version' in self:
            self['version'] = 0
        self._check()

    def _check(self):
        # Late import to prevent circular imports
        from .testcase import __spec_matchers__
        _verify_tags(self, ('id', 'version', 'tests'), 'SPEC')
        _verify_spec_tags(self.get('outputs', {}), ('type', set(__spec_matchers__.keys())),
                          'outputs')
        _verify_spec_tags(self.get('inputs', {}), ('type', 'value'),
                          'inputs')

    def __setitem__(self, key, value):
        if not key in __allowed_spec_keys__:
            _raise(ValueError, "refuse to add unsupported key", key)
        if key == 'version':
            if not isinstance(value, int) or value < 0:
                _raise(ValueError,
                    "version needs to be a non-negative integer value "
                    "(got: %s)." % value)
        dict.__setitem__(self, key, value)

    def get(self, *args):
        # check for proper field names
        if len(args) and not args[0] in __allowed_spec_keys__:
            raise ValueError("refuse to access unsupported key", args[0])
        return super(SPEC, self).get(*args)

    def get_hash(self):
        from hashlib import sha1
        str_repr = json.dumps(self, separators=(',',':'), sort_keys=True)
        return sha1(str_repr).hexdigest()

    def save(self, filename, minimize=False):
        from operator import isSequenceType, isMappingType
        spec_file = open(filename, 'w')
        if minimize:
            # don't write empty containers
            towrite = dict([(k, v) for k, v in self.iteritems()
                                if not (isSequenceType(v) or isMappingType(v)) \
                                   or len(v)])
        else:
            towrite = self
        spec_file.write(json.dumps(towrite, indent=2, sort_keys=True,
                                   cls=SPECJSONEncoder))
        spec_file.write('\n')
        spec_file.close()

    def _get_dict_specs(self, category, spec_type):
        if not category in self:
            return {}
        if spec_type is None:
            return self[category]
        else:
            specs = self[category] 
            return dict([(s, specs[s]) for s in specs if specs[s]['type'] == spec_type])

    def get_inputs(self, type_=None):
        return self._get_dict_specs('inputs', spec_type=type_)

    def get_outputs(self, type_=None):
        return self._get_dict_specs('outputs', spec_type=type_)

    def diff(self, spec, **kwargs):
        return diff(self, spec, **kwargs)


def spec_testoutput_ids(spec):
        return spec.get('outputs', {}).keys()

def diff(fr, to, recursive_list=False, min_abs_numdiff=None,
         min_rel_numdiff=None):
    """Build a difference tree from two container objects

    Most commonly such objects will be SPECs or components thereof.

    Parameters
    ----------
    fr: dict or list or tuple or float or int or str or None
      "from" input into the diff algorithm.
    to: dict or list or tuple or float or int or str or None
      "to" input into the diff algorithm.
    recursive_list: bool
    min_abs_numdiff: float or None
      If not None, this is te minimum absolute numerical difference that shall
      be regarded as an actual difference. All smaller values will be considered
      zero.
    min_rel_numdiff: float or None
      Analog to ``min_abs_numdiff``, but differences will evaluated relative to
      the corresponding ``fr`` value. Specifying 0.1 here, would cause any
      numerical difference to be ignored that is not at least 10% of the
      corresponding numerical value in the first SPEC.
    """
    if not type(fr) == type(to):
        # different type
        return {'from': fr, 'to': to, '%%magic%%': 'diff'}
    elif fr is None and to is None:
        return None
    elif isinstance(fr, dict):
        dtree = {}
        # a dict
        fr_keys = set(fr.keys())
        to_keys = set(to.keys())
        # keys in fr but not in to
        for missing in fr_keys - to_keys:
            dtree[missing] = {'from': fr, '%%magic%%': 'diff'}
        # keys in to but not in fr
        for missing in to_keys - fr_keys:
            dtree[missing] = {'to': to, '%%magic%%': 'diff'}
        # compare intersecting keys
        for key in fr_keys.intersection(to_keys):
            value_diff = diff(fr[key], to[key],
                              recursive_list=recursive_list,
                              min_abs_numdiff=min_abs_numdiff,
                              min_rel_numdiff=min_rel_numdiff)
            if not value_diff is None:
                dtree[key] = value_diff
        if len(dtree):
            return dtree
        else:
            return None
    elif isinstance(fr, basestring):
        # any string
        if not fr == to:
            return {'ndiff': difflib.ndiff(('%s\n' % fr).splitlines(True),
                                           ('%s\n' % to).splitlines(True)),
                    '%%magic%%': 'diff'}
        else:
            return None
    elif isinstance(fr, float) or isinstance(fr, int):
        numdiff = to - fr
        if numdiff and \
           (
               (    min_abs_numdiff is None and
                    min_rel_numdiff is None) \
            or (not min_abs_numdiff is None and
                    min_rel_numdiff is None and
                    abs(numdiff) >= min_abs_numdiff) \
            or (    min_abs_numdiff is None and
                not min_rel_numdiff is None and
                    (fr == 0 or abs(float(numdiff)/fr) >= min_rel_numdiff))):
            return {'numdiff': numdiff, '%%magic%%': 'diff'}
        else:
            return None
    elif isinstance(fr, list):
        if isinstance(to, list) and len(fr) == len(to) and len(fr) > 0:
            # two sequences of the same length: maybe two numerical arrays?
            try:
                # if we have numpy, try converting it into an array and attempt 
                # to compute an element-wise difference
                import numpy as np
                arr_fr = np.array(fr)
                arr_to = np.array(to)
                numdiff = arr_to - arr_fr
                absnumdiff = np.abs(numdiff)
                absmaxdiff = float(absnumdiff.max())
                fr_base = arr_fr.ravel()[absnumdiff.argmax()]
                if absmaxdiff > 0 and \
                   (
                       (min_abs_numdiff is None and
                        min_rel_numdiff is None) \
                    or (not min_abs_numdiff is None and
                            min_rel_numdiff is None and
                            absmaxdiff >= min_abs_numdiff) \
                    or (    min_abs_numdiff is None and
                        not min_rel_numdiff is None and
                            (fr_base == 0 or absmaxdiff / fr_base) >= min_rel_numdiff)):
                    return {'numdiff': numdiff, '%%magic%%': 'diff'}
                return None
            except ImportError:
                # silently fail and do a non-array diff
                pass
            except TypeError:
                # probably not an array with numeric values
                pass
        try:
            seqmatch = difflib.SequenceMatcher(None, fr, to).get_opcodes()
        except TypeError:
            raise NotImplementedError(
                "comparing sequences with unhashable values is not supported")
        if not len(seqmatch):
            return None
        elif len(seqmatch) == 1:
            # simple cases
            if seqmatch[0][0] == 'equal':
                # all the same
                return None
            if recursive_list:
                if seqmatch[0][0] == 'replace':
                    # all different
                    return {'from': fr, 'to': to, '%%magic%%': 'diff'}
                else:
                    # either 'from' or 'to' were empty
                    return {'from': fr, 'to': to, '%%magic%%': 'diff'}
        if recursive_list and \
            len([None for s in seqmatch
                 if s[0] == 'equal'
                    or (s[0] == 'replace' 
                          and s[2] == s[4] and s[1] == s[3])]) \
            == len(seqmatch):
            # only some values changed, but hopefully no shifts
            out = []
            for s in seqmatch:
                if s[0] == 'equal':
                    out.extend(fr[s[1]:s[2]])
                elif s[0] == 'replace':
                    for i in xrange(s[1], s[2]):
                        out.append(diff(fr[i], to[i],
                                        recursive_list=recursive_list,
                                        min_abs_numdiff=min_abs_numdiff,
                                        min_rel_numdiff=min_rel_numdiff))
                else:
                    # all other conditions should be caught by top-level IF
                    raise RuntimeError('impossible opcode in sequence match')
            return out
        else:
            # complicated
            return {'seqmatch': seqmatch, '%%magic%%': 'diff'}
    raise RuntimeError('unhandled condition is SPEC diff')



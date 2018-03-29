# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""generate metadata for submission to Scientific Data from a BIDS dataset"""

__docformat__ = 'restructuredtext'


import logging
lgr = logging.getLogger('datalad.plugin.bids2scidata')

from collections import OrderedDict
import os
import re
from os.path import exists
from os.path import relpath
from os.path import abspath
from os.path import join as opj
from os.path import split as psplit

from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.utils import assure_list
from six.moves.urllib.parse import urlsplit
from six.moves.urllib.parse import urlunsplit
from posixpath import split as posixsplit

try:
    import pandas as pd
except ImportError:
    pd = None

# regex for a cheap test if something looks like a URL
r_url = re.compile(r"^https?://")

common_sample_props = {
    "Characteristics[organism]": "homo sapiens",
    "Characteristics[organism part]": "brain",
    "Protocol REF": "Participant recruitment",
}

# standardize columns from participants.tsv
sample_property_name_map = {
    "age": "Characteristics[age at scan]",
    "age(years)": "Characteristics[age at scan]",
    "gender": "Characteristics[sex]",
    "handedness": "Characteristics[handedness]",
    "participant_id": "Sample Name",
    "id": "Sample Name",
    "sex": "Characteristics[sex]",
}

# map datalad ontology prefixes to ontology labels recognized by scidata
ontology_map = {
    'uo': 'UO',
    'pato': 'PATO',
}

# this defines both the mapping and order of assay properties as they
# will be presented in an assay table
# case 0: any term is properly defined in the metadata context
# (datalad_term, isatab_term)
# if datalad term is None, it needs to come from somewhere else -> special case
# if datalad term is '', it comes from the filename
# case 1: the defintion for a term value comes from another metadata field
# (datalad_term, isatab_term, datalad_valuedef
# case 2: we take the value as-is and define a unit for it
# (datalad_term, isatab_term, isatab_unitvalue, isatab_unitdef
recognized_assay_props = (
    (('bids', 'participant_id'), "Sample Name"),
    (None, "Protocol REF"),
    # BIDS repetition time by default, but override with info from
    # file if possible
    (("bids", "RepetitionTime"), "Parameter Value[4d spacing]"),
    (("nifti1", "temporal_spacing(s)"), 'Parameter Value[4d spacing]'),
    (("nifti1", "spatial_resolution(mm)"), "Parameter Value[resolution]"),
    (("bids", "EchoTime"), "Parameter Value[echo time]", "second", 'UO:0000010'),
    (("bids", "FlipAngle"), "Parameter Value[flip angle]", "degree", 'UO:0000185'),
    ('', "Parameter Value[modality]"),
    (("bids", "Manufacturer"), "Parameter Value[instrument manufacturer]"),
    (("bids", "ManufacturerModelName"), 'Parameter Value[instrument name]'),
    (("bids", "HardcopyDeviceSoftwareVersion"), 'Parameter Value[instrument software version]'),
    (("bids", "MagneticFieldStrength"), 'Parameter Value[magnetic field strength]', 'tesla', 'UO:0000228'),
    (("bids", "ReceiveCoilName"), "Parameter Value[coil type]"),
    (("bids", "PulseSequenceType"), "Parameter Value[sequence]"),
    (("bids", "ParallelAcquisitionTechnique"), "Parameter Value[parallel acquisition technique]"),
    ('', "Assay Name"),
    ('', "Raw Data File"),
    (None, "Comment[Data Repository]"),
    (None, "Comment[Data Record Accession]"),
    (None, "Comment[Data Record URI]"),
    (("bids", "TaskName"), "Factor Value[task]", "bids:CogAtlasID"),
)

# functors to send a sequence of stringified sequence elements to
# build the table representation of a value
repr_props = {
    "Parameter Value[resolution]": 'x'.join,
}

# properties of assay tables to track
assay_props = (
    'assay_fname',
    'assay_techtype', 'assay_techtype_term', 'assay_techtype_termsrc',
    'assay_measurementtype', 'assay_measurementtype_term',
    'assay_measurementtype_termsrc',
)

# properties of study protocols to track
protocol_props = (
    'protocol_name',
    'protocol_type',
    'protocol_term',
    'protocol_termsrc',
    'protocol_parameters',
)

protocol_defs = {
    'Participant recruitment': {
        'type': 'selection',
        'term': 'OBI:0001928',
        'termsrc': 'OBI'},
    'Magnetic Resonance Imaging': {
        'type': 'nuclear magnetic resonance',
        'term': 'OBI:0000182',
        'termsrc': 'OBI'},
}


def getprop(obj, path, default):
    """Helper to get a property from a metadata structure that might not be there"""
    for p in path:
        if p not in obj:
            return default
        obj = obj[p]
    return obj


def split_term_source_accession(val):
    if val is None:
        return '', ''
    if not r_url.match(val):
        # no URL
        if ':' in val:
            val_l = val.split(':')
            vocab = ontology_map.get(val_l[0], val_l[0])
            return vocab, '{}:{}'.format(vocab, val[len(val_l[0]) + 1:])
        else:
            # no idea
            lgr.warn("Could not identify term source REF in: '%s'", val)
            return '', val
    else:
        try:
            # this is a URL, assume simple: last path segment is accession id
            url_s = urlsplit(val)
            urlpath, accession = posixsplit(url_s.path)
            term_source = urlunsplit((url_s[0], url_s[1], urlpath, url_s[3], url_s[4]))
            return ontology_map.get(term_source, term_source), accession
        except Exception as e:
            lgr.warn("Could not identify term source REF in: '%s' [%s]", val, exc_str(e))
            return '', val


def _get_study_df(dsmeta):
    # TODO use helper
    participants = getprop(
        dsmeta,
        ["metadata", "datalad_unique_content_properties", "bids", "participant"],
        [])
    sample_info = [
        dict(
            common_sample_props,
            **{sample_property_name_map.get(
                k,
                "Comment[{}]".format(k.lower())): v
               for k, v in p.items()})
        for p in participants]
    columns_addon = set()
    for i in sample_info:
        # we use the participant ID as the source name
        i["Source Name"] = i.get("Sample Name", None)
        columns_addon.update(i.keys())
    # convert to data frame, impose strict order
    column_order = [
        "Source Name",
        "Characteristics[organism]",
        "Characteristics[organism part]",
        "Protocol REF",
        "Sample Name"
    ]
    df = pd.DataFrame(
        sample_info,
        columns=column_order + sorted(c for c in columns_addon if c not in column_order))
    if 'Sample Name' in df:
        df = df.sort_values(['Sample Name'])
    return df


def _describe_file(dsmeta, fmeta):
    meta = getprop(fmeta, ['metadata'], {})
    bidsmeta = getprop(meta, ['bids'], {})
    modality = getprop(bidsmeta, ['type'], None)
    if modality is None:
        raise ValueError('file record has no type info, not sure what this is')
    info = {
        'Sample Name': getprop(bidsmeta, ['participant', 'id'], None),
        # assay name is the entire filename except for the modality suffix
        # so that, e.g. simultaneous recordings match wrt to the assay name
        # across assay tables
        'Assay Name': psplit(fmeta['path'])[-1].split('.')[0][:-(len(modality) + 1)],
        'Raw Data File': relpath(fmeta['path'], start=fmeta['parentds']),
        'Parameter Value[modality]': modality,
    }
    for l in ('rec', 'recording'):
        if l in bidsmeta:
            info['Parameter Value[recording label]'] = bidsmeta[l]
    for l in ('acq', 'acquisition'):
        if l in bidsmeta:
            info['Parameter Value[acquisition label]'] = bidsmeta[l]
    if 'task' in bidsmeta:
        info['Factor Value[task]'] = bidsmeta['task']

    # now pull in the value of all recognized properties
    # perform any necessary conversion to achieve final
    # form for ISATAB table
    for prop in recognized_assay_props:
        src, dst = prop[:2]
        # expand src specfification
        namespace, src = src if src else (None, src)
        if src is None:
            # special case, not handled here
            continue
        if src in meta.get(namespace, {}):
            # pull out the value from datalad metadata directly,
            # unless we have a definition URL in another field,
            # in which case put it into a 2-tuple also
            val = meta[namespace][src]
            if dst in repr_props and isinstance(val, (list, tuple)):
                val = repr_props[dst](str(i) for i in val)
            info[dst] = val
            if len(prop) == 4:
                # we have a unit definition
                info['{}_unit_label'.format(dst)] = prop[2]
            term_source = term_accession = None
            if len(prop) > 2:
                term_source, term_accession = split_term_source_accession(
                    meta.get(prop[2], None) if len(prop) == 3 else prop[3])
            elif prop[0] and prop[1] != 'Sample Name':
                # exclude all info source outside the metadata
                # this plugin has no vocabulary info for this field
                # we need to look into the dataset context to see if we know
                # anything
                # FIXME TODO the next line should look into the local context
                # of the 'bids' metadata source
                termdef = getprop(dsmeta, ['metadata', namespace, '@context', src], {})
                term_source, term_accession = split_term_source_accession(
                    termdef.get('unit' if 'unit' in termdef else '@id', None))
                if 'unit_label' in termdef:
                    info['{}_unit_label'.format(dst)] = termdef['unit_label']
            if term_accession is not None:
                info['{}_term_source'.format(dst)] = term_source
                info['{}_term_accession'.format(dst)] = term_accession

    return info


def _get_colkey(idx, colname):
    return '{0:0>5}_{1}'.format(idx, colname)


def _get_assay_df(
        dsmeta,
        modality, protocol_ref, files, file_descr,
        repository_info=None):
    if not repository_info:
        repository_info = {}
    # main assays
    # we cannot use a dict to collect the data before going to
    # a data frame, because we will have multiple columns with
    # the same name carrying the ontology info for preceeding
    # columns
    # --> prefix with some index, create dataframe and rename
    # the column names in the dataframe with the prefix stripped
    assay_dict = {}
    # get all files described and determine the union of all keys
    finfos = []
    info_keys = set()
    for finfo in files:
        # get file metadata in ISATAB notation
        finfo = file_descr(dsmeta, finfo)
        info_keys = info_keys.union(finfo.keys())
        finfos.append(finfo)
    # receiver for data in all columns of the table
    collector_dict = dict(zip(info_keys, [[] for i in range(len(info_keys))]))
    # expand data with missing values across all files/rows
    for finfo in finfos:
        for spec in info_keys:
            fspec = finfo.get(spec, None)
            collector_dict[spec].append(fspec)
    # build the table order
    idx = 1
    idx_map = {}
    assay_name_key = None
    for prop in recognized_assay_props:
        colname = prop[1]
        if colname in idx_map:
            # we already know about this column, that means it has multiple sources
            # and we have processed one already. no need to do anything in addition
            continue
        if prop[0] is None:
            # special case handling
            if colname == 'Protocol REF':
                assay_dict[_get_colkey(idx, colname)] = protocol_ref
                idx += 1
            elif colname in repository_info:
                assay_dict[_get_colkey(idx, colname)] = repository_info[colname]
                idx += 1
            continue

        elif colname not in collector_dict:
            # we got nothing for this column
            continue
        # skip empty
        if not all([v is None for v in collector_dict[colname]]):
            # be able to look up the actual column key in case
            # prev information needs to be replaced by a value from
            # a better source (as determined by the order)
            colkey = idx_map.get(colname, _get_colkey(idx, colname))
            idx_map[colname] = colkey
            assay_dict[colkey] = collector_dict[colname]
            idx += 1
            if colname == 'Assay Name':
                assay_name_key = colkey
            for aux_info, aux_colname in (
                    ('unit_label', 'Unit'),
                    ('term_source', 'Term Source REF'),
                    ('term_accession', 'Term Accession Number')):
                aux_source = '{}_{}'.format(colname, aux_info)
                if aux_source not in collector_dict:
                    # we got nothing on this from any file
                    continue
                assay_dict[_get_colkey(idx, aux_colname)] = collector_dict[aux_source]
                idx += 1

    if assay_name_key is None:
        # we didn't get a single meaningful file
        return None

    # TODO use assay name as index! for join with deface later on
    df = pd.DataFrame(assay_dict, index=assay_dict[assay_name_key])
    return df


def _store_beautiful_table(df, output_directory, fname):
    if df is None:
        return
    if 'Assay Name' in df:
        df = df.sort_values(['Assay Name'])
    df.to_csv(
        opj(output_directory, fname),
        sep="\t",
        index=False)


def _gather_protocol_parameters_from_df(df, protocols):
    params = set()
    protos = None
    for i, col in enumerate(list(df.columns) + ['Protocol REF']):
        if col == 'Protocol REF':
            if protos is not None:
                # we had some before, store
                for p in protos:
                    pdef = protocols.get(p, set()).union(params)
                    protocols[p] = pdef
                if i > len(df.columns) - 1:
                    break
            # this is a protocol definition column,
            # make entry for each unique value
            protos = df.ix[:, i].unique()
        if col.startswith('Parameter Value['):
            params.add(col[16:-1])


def convert(
        dsmeta,
        filemeta,
        output_directory,
        repository_info=None):
    if pd is None:
        lgr.error(
            "This plugin requires Pandas to be available (error follows)")
        import pandas
        return

    # collect infos about dataset and ISATAB structure for use in investigator
    # template
    info = {}
    if not exists(output_directory):
        lgr.info(
            "creating output directory at '{}'".format(output_directory))
        os.makedirs(output_directory)

    # prep for assay table info
    protocols = OrderedDict()
    for prop in assay_props:
        info[prop] = []

    # pull out essential metadata bits about the dataset itself
    # for study description)
    dsbidsmeta = getprop(dsmeta, ['metadata', 'bids'], {})
    info['name'] = dsbidsmeta.get('shortdescription', dsbidsmeta.get('name', 'TODO'))
    info['author'] = '\t'.join(assure_list(dsbidsmeta.get('author', [])))
    info['keywords'] = '\t'.join(assure_list(dsbidsmeta.get('tag', [])))
    # generate: s_study.txt
    study_df = _get_study_df(dsmeta)
    if study_df.empty:
        # no samples, no assays, no metadataset
        return None

    _gather_protocol_parameters_from_df(study_df, protocols)
    _store_beautiful_table(
        study_df,
        output_directory,
        "s_study.txt")
    info['studytab_filename'] = 's_study.txt'

    deface_df = None
    # all imaging modalities recognized in BIDS
    #TODO maybe fold 'defacemask' into each modality as a derivative
    for modality in ('defacemask',
                     'T1w', 'T2w', 'T1map', 'T2map', 'FLAIR', 'FLASH', 'PD',
                     'PDmap', 'PDT2', 'inplaneT1', 'inplaneT2', 'angio',
                     'sbref', 'bold', 'SWImagandphase'):
        # what files do we have for this type
        modfiles = [f for f in filemeta
                    if getprop(f, ['metadata', 'bids', 'type'], None) == modality]
        if not len(modfiles):
            # not files found, try next
            lgr.info(
                "no files match MRI modality '{}', skipping".format(modality))
            continue

        df = _get_assay_df(
            dsmeta,
            modality,
            "Magnetic Resonance Imaging",
            modfiles,
            _describe_file,
            repository_info)
        if df is None:
            continue
        if modality == 'defacemask':
            # rename columns to strip index
            df.columns = [c[6:] for c in df.columns]
            df.rename(columns={'Raw Data File': 'Derived Data File'}, inplace=True)
            df.drop(
                ['Assay Name', 'Sample Name'] +
                [c for c in df.columns if c.startswith('Factor')],
                axis=1,
                inplace=True)
            deface_df = df
            # re-prefix for merge logic compatibility below
            deface_df.columns = [_get_colkey(i, c) for i, c in enumerate(df.columns)]
            # do not save separate, but include into the others as a derivative
            continue
        elif deface_df is not None:
            # get any factor columns, put last in final table
            factors = []
            # find where they stat
            for i, c in enumerate(df.columns):
                if '_Factor Value[' in c:
                    factors = df.columns[i:]
                    break
            factor_df = df[factors]
            df.drop(factors, axis=1, inplace=True)
            # merge relevant rows from deface df (hstack), by matching assay name
            df = df.join(deface_df, rsuffix='_deface')
            df.columns = [c[:-7] if c.endswith('_deface') else c for c in df.columns]
            # cannot have overlapping columns, we removed the factor before
            df = df.join(factor_df)
        # rename columns to strip index
        df.columns = [c[6:] for c in df.columns]
        # parse df to gather protocol info
        _gather_protocol_parameters_from_df(df, protocols)
        # store
        assay_fname = "a_mri_{}.txt".format(modality.lower())
        _store_beautiful_table(
            df,
            output_directory,
            assay_fname)
        info['assay_fname'].append(assay_fname)
        info['assay_techtype'].append('nuclear magnetic resonance')
        info['assay_techtype_term'].append('OBI:0000182')
        info['assay_techtype_termsrc'].append('OBI')
        info['assay_measurementtype'].append('MRI Scanner')
        info['assay_measurementtype_term'].append('ERO:MRI_Scanner')
        info['assay_measurementtype_termsrc'].append('ERO')

    # non-MRI modalities
    for modlabel, assaylabel, protoref in (
            ('physio', 'physio', "Physiological Measurement"),
            ('stim', 'stimulation', "Stimulation")):
        df = _get_assay_df(
            dsmeta,
            modlabel,
            protoref,
            [f for f in filemeta
             if getprop(f, ['metadata', 'bids', 'type'], None) == modality],
            _describe_file,
            repository_info)
        if df is None:
            continue
        # rename columns to strip index
        df.columns = [c[6:] for c in df.columns]
        assay_fname = "a_{}.txt".format(assaylabel)
        _store_beautiful_table(
            df,
            output_directory,
            assay_fname)
        info['assay_fname'].append(assay_fname)
        # ATM we cannot say anything definitive about these
        info['assay_techtype'].append('TODO')
        info['assay_techtype_term'].append('TODO')
        info['assay_techtype_termsrc'].append('TODO')
        info['assay_measurementtype'].append(assaylabel)
        info['assay_measurementtype_term'].append('TODO')
        info['assay_measurementtype_termsrc'].append('TODO')

    # post-proc assay-props for output
    for prop in assay_props:
        info[prop] = '\t'.join(assure_list(info[prop]))

    info['protocol_name'] = '\t'.join(protocols.keys())
    for k in ('type', 'term', 'termsrc'):
        info['protocol_{}'.format(k)] = '\t'.join(
            protocol_defs.get(p, {}).get(k, 'TODO') for p in protocols)
    info['protocol_parameters'] = '\t'.join(
            '; '.join(sorted(protocols[p])) for p in protocols)
    return info


#
# Make it work seamlessly as a datalad export plugin
#
@build_doc
class BIDS2Scidata(Interface):
    """BIDS to ISA-Tab converter"""
    from datalad.support.param import Parameter
    from datalad.distribution.dataset import datasetmethod
    from datalad.interface.utils import eval_results
    from datalad.distribution.dataset import EnsureDataset
    from datalad.support.constraints import EnsureNone, EnsureStr

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""Dataset to query for metadata of a BIDS-compatible dataset.
            The queried dataset itself does not have to be a BIDS dataset.
            If not dataset is given, an attempt is made to identify the dataset
            based on the current working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=('path',),
            doc="""path to a BIDS-compatible dataset to export metadata on"""),
        repo_name=Parameter(
            args=('--repo-name',),
            doc="""data repository name to be used in assay tables.
            Example: OpenfMRI"""),
        repo_accession=Parameter(
            args=('--repo-accession',),
            doc="""data repository accession number to be used in assay tables.
            Example: ds000113d"""),
        repo_url=Parameter(
            args=('--repo-url',),
            doc="""data repository URL to be used in assay tables.
            Example: https://openfmri.org/dataset/ds000113d"""),
        output=Parameter(
            args=('--output',),
            doc="""directory where ISA-TAB files will be stored""",)
    )

    @staticmethod
    @datasetmethod(name='bids2scidata')
    @eval_results
    def __call__(repo_name, repo_accession, repo_url, path=None, output=None, dataset=None):
        from os.path import dirname
        from os.path import join as opj
        from datetime import datetime
        from io import open
        import logging
        lgr = logging.getLogger('datalad.plugin.bids2scidata')
        import datalad
        from datalad import cfg
        from datalad.plugin.bids2scidata import convert
        from datalad.coreapi import metadata
        from datalad.distribution.dataset import require_dataset

        # we need this resource file, no point in starting without it
        itmpl_path = cfg.obtain(
            'datalad.plugin.bids2scidata.investigator.template',
            default=opj(
                dirname(datalad.__file__),
                'resources', 'isatab', 'scidata_bids_investigator.txt'))

        if path and dataset is None:
            dataset = path
        dataset = require_dataset(
            dataset, purpose='metadata query', check_installed=True)

        errored = False
        dsmeta = None
        filemeta = []
        for m in metadata(
                path,
                dataset=dataset,
                # BIDS hierarchy might go across multiple dataset
                recursive=True,
                reporton='all',
                return_type='generator',
                result_renderer='disabled'):
            type = m.get('type', None)
            if type not in ('dataset', 'file'):
                continue
            if m.get('status', None) != 'ok':
                errored = errored or m.get('status', None) in ('error', 'impossible')
                yield m
                continue
            if type == 'dataset':
                if dsmeta is not None:
                    lgr.warn(
                        'Found metadata for more than one datasets, '
                        'ignoring their dataset-level metadata')
                    continue
                dsmeta = m
            elif type == 'file':
                filemeta.append(m)
        if errored:
            return

        if not dsmeta or not 'refcommit' in dsmeta:
            yield dict(
                status='error',
                message=("could not find aggregated metadata on path '%s'", path),
                path=dataset.path,
                type='dataset',
                action='bids2scidata',
                logger=lgr)
            return

        lgr.info("Metadata for %i files associated with '%s' on record in %s",
                 len(filemeta),
                 path,
                 dataset)

        if not output:
            output = 'scidata_isatab_{}'.format(dsmeta['refcommit'])

        info = convert(
            dsmeta,
            filemeta,
            output_directory=output,
            repository_info={
                'Comment[Data Repository]': repo_name,
                'Comment[Data Record Accession]': repo_accession,
                'Comment[Data Record URI]': repo_url},
        )
        if info is None:
            yield dict(
                status='error',
                message='dataset does not seem to contain relevant metadata',
                path=dataset.path,
                type='dataset',
                action='bids2scidata',
                logger=lgr)
            return

        itmpl = open(itmpl_path, encoding='utf-8').read()
        with open(opj(output, 'i_Investigation.txt'), 'w', encoding='utf-8') as ifile:
            ifile.write(
                itmpl.format(
                    datalad_version=datalad.__version__,
                    date=datetime.now().strftime('%Y/%m/%d'),
                    repo_name=repo_name,
                    repo_accession=repo_accession,
                    repo_url=repo_url,
                    **info
                ))
        yield dict(
            status='ok',
            path=abspath(output),
            # TODO add switch to make tarball/ZIP
            #type='file',
            type='directory',
            action='bids2scidata',
            logger=lgr)


__datalad_plugin__ = BIDS2Scidata

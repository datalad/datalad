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
from glob import glob
import os
import re
from os.path import exists
from os.path import relpath
from os.path import join as opj
from os.path import split as psplit

from datalad.metadata.metadata import query_aggregated_metadata
from datalad.metadata.search import r_url
from urlparse import urlsplit
from urlparse import urlunsplit
from posixpath import split as posixsplit

try:
    import pandas as pd
except ImportError:
    pd = None


# map column titles to ontology specs
# based on this info the appropriate additonal column in the ISATab tables are
# generated
ontology_term_map = {
    # qualitative information
    "Characteristics[organism]": {
        'homo sapiens': ('homo sapiens', 'NCBITAXON', 'NCBITaxon:9606'),
    },
    "Characteristics[organism part]": {
        'brain': ('brain', 'UBERON', 'UBERON:0000955'),
    },
    "Characteristics[sex]": {
        'female': ('female', 'PATO', 'PATO:0000383'),
        'f': ('female', 'PATO', 'PATO:0000383'),
        'male': ('male', 'PATO', 'PATO:0000384'),
        'm': ('male', 'PATO', 'PATO:0000384'),
    },
    "Characteristics[handedness]": {
        'right':  ('right', 'PATO', 'PATO:0002203'),
        'r':  ('right', 'PATO', 'PATO:0002203'),
        'left': ('left', 'PATO', 'PATO:0002202'),
        'l': ('left', 'PATO', 'PATO:0002202'),
        'ambidextrous': ('ambidextrous', 'PATO', 'PATO:0002204'),
        'r;l': ('ambidextrous', 'PATO', 'PATO:0002204'),
        'l;r': ('ambidextrous', 'PATO', 'PATO:0002204'),
    },
    # take as is ...
    'Parameter Value[4d spacing]': None,
    # ...but have dedicated unit column
    'Parameter Unit[4d spacing]': {
        'millimeter': ('millimiter', 'UO', 'UO:0000016'),
        'second': ('second', 'UO', 'UO:0000010'),
        'hertz': ('hertz', 'UO', 'UO:0000106'),
        'hz': ('hertz', 'UO', 'UO:0000106'),
        'ppm': ('parts per million', 'UO', 'UO:0000109'),
        'rad': ('radian', 'UO', 'UO:0000123'),
        'rads': ('radian', 'UO', 'UO:0000123'),
    },
    # quantitative information
    "Characteristics[age at scan]": ('UO', 'UO:0000036', 'year'),
    "Parameter Value[resolution]": ('UO', 'UO:0000016', 'millimeter'),
    "Parameter Value[repetition time]": ('UO', 'UO:0000010', 'second'),
    "Parameter Value[magnetic field strength]": ('UO', 'UO:0000228', 'tesla'),
    "Parameter Value[flip angle]": ('UO', 'UO:0000185', 'degree'),
    "Parameter Value[echo time]": ('UO', 'UO:0000010', 'second'),
    "Parameter Value[sampling frequency]": ('UO', 'UO:0000106', 'hertz'),
    # no associated term, keep but leave untouched
    "Parameter Value[instrument name]": None,
    "Parameter Value[instrument manufacturer]": None,
    "Parameter Value[instrument software version]": None,
    "Parameter Value[coil type]": None,
    "Parameter Value[sequence]": None,
    # TODO next two maybe factor values?
    "Parameter Value[recording label]": None,
    "Parameter Value[acquisition label]": None,
    "Parameter Value[content description]": None,
    # Keep any task factor, and any of the two task term sources
    # of which one will get used (whatever is found first)
    "Factor Value[task]": None,
    'Parameter Value[CogAtlasID]': None,
    'Parameter Value[CogPOID]': None,
    'Protocol REF': None,
    'Sample Name': None,
    'Assay Name': None,
    'Raw Data File': None,
    # modality should get proper terms attached
    'Parameter Value[modality]': None,
    # not sure if there are terms for SENSE and GRAPPA etc. anywhere
    'Parameter Value[parallel acquisition technique]': None,
}

# standardize columns from participants.tsv
sample_property_name_map = {
    "age": "Characteristics[age at scan]",
    "gender": "Characteristics[sex]",
    "handedness": "Characteristics[handedness]",
    "participant_id": "Sample Name",
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
    ('bids:participant_id', "Sample Name"),
    (None, "Protocol REF"),
    # BIDS repetition time by default, but override with info from
    # file if possible
    ("bids:RepetitionTime", "Parameter Value[4d spacing]"),
    ("temporal_spacing(s)", 'Parameter Value[4d spacing]'),
    ("spatial_resolution(mm)", "Parameter Value[resolution]"),
    ("bids:EchoTime", "Parameter Value[echo time]", "second", 'UO:0000010'),
    ("bids:FlipAngle", "Parameter Value[flip angle]", "degree", 'UO:0000185'),
    ('', "Parameter Value[modality]"),
    ("bids:Manufacturer", "Parameter Value[instrument manufacturer]"),
    ("bids:ManufacturerModelName", 'Parameter Value[instrument name]'),
    ("bids:HardcopyDeviceSoftwareVersion", 'Parameter Value[instrument software version]'),
    ("bids:MagneticFieldStrength", 'Parameter Value[magnetic field strength]', 'tesla', 'UO:0000228'),
    ("bids:ReceiveCoilName", "Parameter Value[coil type]"),
    ("bids:PulseSequenceType", "Parameter Value[sequence]"),
    ("bids:ParallelAcquisitionTechnique", "Parameter Value[parallel acquisition technique]"),
    ('', "Assay Name"),
    ('', "Raw Data File"),
    (None, "Comment[Data Repository]"),
    (None, "Comment[Data Record Accession]"),
    (None, "Comment[Data Record URI]"),
    ("bids:TaskName", "Factor Value[task]", "bids:CogAtlasID"),
)

# functors to send a sequence of stringified sequence elements to
# build the table representation of a value
repr_props = {
    "Parameter Value[resolution]": 'x'.join,
}


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


def _get_study_df(ds):
    subject_ids = []
    study_dict = OrderedDict()
    for file in glob(opj(ds.path, "sub-*")):
        if os.path.isdir(file):
            subject_ids.append(psplit(file)[-1][4:])
    subject_ids.sort()
    study_dict["Source Name"] = subject_ids
    study_dict["Characteristics[organism]"] = "homo sapiens"
    study_dict["Characteristics[organism part]"] = "brain"
    study_dict["Protocol REF"] = "Participant recruitment"
    study_dict["Sample Name"] = subject_ids
    df = pd.DataFrame(study_dict)

    participants_file = opj(ds.path, "participants.tsv")
    if not exists(participants_file):
        return df

    participants_df = pd.read_csv(participants_file, sep="\t")
    rename_rule = sample_property_name_map.copy()
    # remove all mapping that do not match the columns at hand
    for r in list(rename_rule.keys()):
        if not r in participants_df.keys():
            del rename_rule[r]
    # turn all unknown properties into comment columns
    for c in participants_df.keys():
        if not c in rename_rule:
            rename_rule[c] = "Comment[{}]".format(c.lower())

    participants_df.rename(columns=rename_rule, inplace=True)
    # simplify sample names by stripping the common prefix
    participants_df["Sample Name"] = \
        [s[4:] for s in list(participants_df["Sample Name"])]
    # merge participant info with study info
    df = pd.merge(
        df,
        participants_df,
        left_on="Sample Name",
        right_on="Sample Name")
    return df


def _describe_file(fpath, db):
    fmeta = db[fpath]
    fname = psplit(fpath)[-1]
    fname_components = fname.split(".")[0].split('_')
    info = {
        'Sample Name': fmeta.get("bids:participant_id", fname_components[0]),
        # assay name is the entire filename except for the modality suffix
        # so that, e.g. simultaneous recordings match wrt to the assay name
        # across assay tables
        'Assay Name': '_'.join(fname_components[:-1]),
        'Raw Data File': fpath,
        'Parameter Value[modality]': fname_components[-1]
    }
    # more optional info that could be pulled from the filename
    comp_dict = dict([c.split('-') for c in fname_components[:-1]])
    for l in ('rec', 'recording'):
        if l in comp_dict:
            info['Parameter Value[recording label]'] = comp_dict[l]
    for l in ('acq', 'acquisition'):
        if l in comp_dict:
            info['Parameter Value[acquisition label]'] = comp_dict[l]
    if 'task' in comp_dict:
        info['Factor Value[task]'] = comp_dict['task']

    # now pull in the value of all recognized properties
    # perform any necessary conversion to achieve final
    # form for ISATAB table
    for prop in recognized_assay_props:
        src, dst = prop[:2]
        if src is None:
            # special case, not handled here
            continue
        if src in fmeta:
            # pull out the value from datalad metadata directly,
            # unless we have a definition URL in another field,
            # in which case put it into a 2-tuple also
            val = fmeta[src]
            if dst in repr_props and isinstance(val, (list, tuple)):
                val = repr_props[dst](str(i) for i in val)
            info[dst] = val
            if len(prop) == 4:
                # we have a unit definition
                info['{}_unit_label'.format(dst)] = prop[2]
            term_source = term_accession = None
            if len(prop) > 2:
                term_source, term_accession = split_term_source_accession(
                    fmeta.get(prop[2], None) if len(prop) == 3 else prop[3])
            elif prop[0] and prop[1] != 'Sample Name':
                # exclude all info source outside the metadata
                # this plugin has no vocabulary info for this field
                # we need to look into the dataset context to see if we know
                # anything
                termdef = db['.'].get('@context', {}).get(src, {})
                term_source, term_accession = split_term_source_accession(
                    termdef.get('unit' if 'unit' in termdef else '@id', None))
                if 'unit_label' in termdef:
                    info['{}_unit_label'.format(dst)] = termdef['unit_label']
            if term_accession is not None:
                info['{}_term_source'.format(dst)] = term_source
                info['{}_term_accession'.format(dst)] = term_accession

    return info


def _get_file_matches(db, pattern):
    expr = re.compile(pattern)
    return [f for f in db if expr.match(f)]


def _get_colkey(idx, colname):
    return '{0:0>5}_{1}'.format(idx, colname)


def _get_assay_df(
        db, modality, protocol_ref, files, file_descr,
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
    for fname in files:
        # get file metadata in ISATAB notation
        finfo = file_descr(fname, db)
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


def extract(
        ds,
        output_directory,
        repository_info=None):
    if pd is None:
        lgr.error(
            "This plugin requires Pandas to be available (error follows)")
        import pandas
        return

    if not exists(output_directory):
        lgr.info(
            "creating output directory at '{}'".format(output_directory))
        os.makedirs(output_directory)

    # pull out everything we know about any file in the dataset, and the dataset
    # itself
    metadb = {
        relpath(r['path'], ds.path): r.get('metadata', {})
        for r in query_aggregated_metadata(
            'all',
            ds,
            [dict(path='.', type='directory')],
            'init')
    }

    # generate: s_study.txt
    _store_beautiful_table(
        _get_study_df(ds),
        output_directory,
        "s_study.txt")

    deface_df = None
    # all imaging modalities recognized in BIDS
    #TODO maybe fold 'defacemask' into each modality as a derivative
    for modality in ('defacemask',
                     'T1w', 'T2w', 'T1map', 'T2map', 'FLAIR', 'FLASH', 'PD',
                     'PDmap', 'PDT2', 'inplaneT1', 'inplaneT2', 'angio',
                     'sbref', 'bold', 'SWImagandphase'):
        # what files do we have for this modality
        modfiles = _get_file_matches(
            metadb,
            '^sub-.*_{}\.nii\.gz$'.format(modality))
        if not len(modfiles):
            # not files found, try next
            lgr.info(
                "no files match MRI modality '{}', skipping".format(modality))
            continue

        df = _get_assay_df(
            metadb,
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
        _store_beautiful_table(
            df,
            output_directory,
            "a_mri_{}.txt".format(modality.lower()))

    # non-MRI modalities
    for modlabel, assaylabel, protoref in (
            ('physio', 'physio', "Physiological Measurement"),
            ('stim', 'stimulation', "Stimulation")):
        df = _get_assay_df(
            metadb,
            modlabel,
            protoref,
            _get_file_matches(metadb, '^sub-.*_{}.tsv.gz$'.format(modlabel)),
            _describe_file,
            repository_info)
        if df is None:
            continue
        # rename columns to strip index
        df.columns = [c[6:] for c in df.columns]
        _store_beautiful_table(
            df,
            output_directory,
            'a_{}.txt'.format(assaylabel))

    # generate: i_investigation.txt
    # TODO
    #investigation_template = _get_investigation_template(
    #    ds, mri_par_names)
    #with open(opj(output_directory, "i_investigation.txt"), "w") as fp:
    #    fp.write(investigation_template)


#
# Make it work seamlessly as a datalad export plugin
#
def dlplugin(
        dataset,
        repo_name,
        repo_accession,
        repo_url,
        output=None):
    """BIDS to ISA-Tab converter

    Parameters
    ----------
    ds : Dataset
      dataset in BIDS-compatible format
    repo_name : str
        data repository name to be used in assay tables.
        Example: OpenfMRI
    repo_accession : str
        data repository accession number to be used in assay tables.
        Example: ds000113d
    repo_url : str
        data repository URL to be used in assay tables.
        Example: https://openfmri.org/dataset/ds000113d
    output : str, optional
      directory where ISA-TAB files will be stored
    """
    import logging
    lgr = logging.getLogger('datalad.plugin.bids2scidata')
    from datalad.plugin.bids2scidata import extract

    if not output:
        output = 'scidata_isatab_{}'.format(dataset.repo.get_hexsha())

    extract(
        dataset,
        output_directory=output,
        repository_info={
            'Comment[Data Repository]': repo_name,
            'Comment[Data Record Accession]': repo_accession,
            'Comment[Data Record URI]': repo_url},
    )
        # TODO
        #i_investigation_template
    yield dict(
        status='ok',
        path=output,
        # TODO add switch to make tarball/ZIP
        #type='file',
        type='directory',
        action='bids2scidata',
        logger=lgr)


default_i_investigation_template = """\
# Investigation File template generated by BIDS2ISATab. This metadata file is CC0
ONTOLOGY SOURCE REFERENCE
Term Source Name	NCBITAXON	UBERON	PATO	UO	NCIT	OBI	ERO
Term Source File	http://data.bioontology.org/ontologies/NCBITAXON	http://data.bioontology.org/ontologies/UBERON	http://data.bioontology.org/ontologies/PATO	http://data.bioontology.org/ontologies/UO	http://data.bioontology.org/ontologies/NCIT	http://data.bioontology.org/ontologies/OBI	http://data.bioontology.org/ontologies/ERO
Term Source Version	2015AA	releases/2014-06-15	unknown	unknown	15.05d	2014-08-18	2013-08-02
Term Source Description	National Center for Biotechnology Information (NCBI) Organismal Classification	Uber Anatomy Ontology	Phenotypic Quality Ontology	Units of Measurement Ontology	National Cancer Institute Thesaurus	Ontology for Biomedical Investigations	Eagle-I Research Resource Ontology
INVESTIGATION
Investigation Identifier
Investigation Title
Investigation Description
Investigation Submission Date
Investigation Public Release Date
INVESTIGATION PUBLICATIONS
Investigation PubMed ID
Investigation Publication DOI
Investigation Publication Author List
Investigation Publication Title
Investigation Publication Status
Investigation Publication Status Term Accession Number
Investigation Publication Status Term Source REF
INVESTIGATION CONTACTS
Investigation Person Last Name
Investigation Person Mid Initials
Investigation Person First Name
Investigation Person Address
Investigation Person Phone
Investigation Person Fax
Investigation Person Email
Investigation Person Affiliation
Investigation Person Roles
Investigation Person Roles Term Accession Number
Investigation Person Roles Term Source REF
STUDY
Study Identifier	[TODO: IDENTIFIER]
Study Title	[TODO: TITLE]
Study Submission Date
Study Public Release Date
Study Description
Study File Name	s_study.txt
Comment[Subject Keywords]
Comment[Manuscript Licence]
Comment[Experimental Metadata Licence]
Comment[Supplementary Information File Name]
Comment[Supplementary Information File Type]
Comment[Supplementary Information File URL]
Comment[Data Repository]
Comment[Data Record Accession]
Comment[Data Record URI]
STUDY DESIGN DESCRIPTORS
Study Design Type
Study Design Type Term Accession Number
Study Design Type Term Source
STUDY PUBLICATIONS
Study PubMed ID
Study Publication DOI
Study Publication Author List
Study Publication Title
Study Publication Status
Study Publication Status Term Accession Number
Study Publication Status Term Source REF
STUDY FACTORS
Study Factor Name
Study Factor Type
Study Factor Type Term Accession Number
Study Factor Type Term Source REF
STUDY ASSAYS
Study Assay Measurement Type	nuclear magnetic resonance assay
Study Assay Measurement Type Term Accession Number	OBI:0000182
Study Assay Measurement Type Term Source REF	OBI
Study Assay Technology Type	MRI Scanner
Study Assay Technology Type Term Accession Number	ERO:MRI_Scanner
Study Assay Technology Type Term Source REF	ERO
Study Assay Technology Platform	
Study Assay File Name	a_assay.txt
STUDY PROTOCOLS
Study Protocol Name	Participant recruitment	Magnetic Resonance Imaging
Study Protocol Type	selection	nuclear magnetic resonance assay
Study Protocol Type Term Accession Number	OBI:0001928	OBI:0000182
Study Protocol Type Term Source REF	OBI	OBI
Study Protocol Description	""	""
Study Protocol URI	""	""
Study Protocol Version	""	""
Study Protocol Parameters Name	""	[TODO: MRI_PAR_NAMES]
Study Protocol Parameters Name Term Accession Number	""	""
Study Protocol Parameters Name Term Source REF	""	""
Study Protocol Components Name	""	""
Study Protocol Components Type	""	""
Study Protocol Components Type Term Accession Number	""	""
Study Protocol Components Type Term Source REF	""	""
STUDY CONTACTS
Study Person Last Name
Study Person First Name
Study Person Mid Initials
Study Person Email
Study Person Phone
Study Person Fax
Study Person Address
Study Person Affiliation
Study Person Roles
Study Person Roles Term Accession Number
Study Person Roles Term Source REF
Comment[Study Person ORCID]
Comment[Funder]
Comment[FundRef ID]
Comment[Funder Term Source REF]
Comment[Grant Identifier]
"""

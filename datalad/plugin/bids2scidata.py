#!/usr/bin/env python
#

# import modules used here -- sys is a very standard one
from __future__ import print_function
import argparse
import logging
from collections import OrderedDict
from glob import glob
import os
from os.path import exists, join as opj, split as psplit
import sys


import nibabel
import json
import pandas as pd


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

# translate from what we find in BIDS or a DICOM dump into the
# names that ScientificData prefers
# matching will be done on lower case string
# add any synonyms or additions as entries toi this dictionary
parameter_name_map = {
    "manufacturermodelname": "instrument name",
    "manufacturer": "instrument manufacturer",
    "hardcopydevicesoftwareversion": "instrument software version",
    "receivecoilname": "coil type",
    "magneticfieldstrength": "magnetic field strength",
    "receivecoilname": "coil type",
    "echotime": "echo time",
    "repetitiontime": "repetition time",
    "flipangle": "flip angle",
    "pulsesequencetype": "sequence",
    "parallelacquisitiontechnique": "parallel acquisition technique",
    "samplingfrequency": "sampling frequency",
    "contentdescription": "content description",
}

# standardize columns from participants.tsv
sample_property_name_map = {
    "age": "Characteristics[age at scan]",
    "gender": "Characteristics[sex]",
    "handedness": "Characteristics[handedness]",
    "participant_id": "Sample Name",
    "sex": "Characteristics[sex]",
}


def get_bids_metadata(bids_root, basepath):
    """Query the BIDS meta data JSON file hierarchy

    Parameters
    ----------
    bids_root : path
      Path to the root of the BIDS dataset
    basepath : path
      Relative path to the file (filename without extension, e.g. no '.nii.gz')
      for which meta data shall be queried.
    """
    sidecar_json = '{}.json'.format(basepath)

    path_components = psplit(sidecar_json)
    filename_components = path_components[-1].split("_")
    session_level_componentList = []
    subject_level_componentList = []
    top_level_componentList = []
    ses = None
    sub = None

    for filename_component in filename_components:
        if filename_component[:3] != "run":
            session_level_componentList.append(filename_component)
            if filename_component[:3] == "ses":
                ses = filename_component
            else:
                subject_level_componentList.append(filename_component)
                if filename_component[:3] == "sub":
                    sub = filename_component
                else:
                    top_level_componentList.append(filename_component)

    # the top-level should have at least two components, e.g. task and modality
    # but could also have more, e.g. task, recording and modality
    # query sidecars for each single-component plus modality
    potential_jsons = []
    for comp in top_level_componentList[:-1]:
        potential_jsons.append(
            opj(bids_root, "_".join([comp, top_level_componentList[-1]])))
    # and one for all components combined
    potential_jsons.append(opj(bids_root, "_".join(top_level_componentList)))

    subject_level_json = opj(bids_root, sub, "_".join(subject_level_componentList))
    potential_jsons.append(subject_level_json)

    if ses:
        session_level_json = opj(bids_root, sub, ses, "_".join(session_level_componentList))
        potential_jsons.append(session_level_json)

    potential_jsons.append(sidecar_json)

    merged_param_dict = {}
    for json_file_path in potential_jsons:
        if exists(json_file_path):
            param_dict = json.load(open(json_file_path, "r"))
            merged_param_dict.update(param_dict)

    return merged_param_dict


def get_chainvalue(chain, src):
    try:
        for key in chain:
            src = src[key]
        return src
    except KeyError:
        return None


def get_keychains(d, dest, prefix):
    if isinstance(d, dict):
        for item in d:
            dest = get_keychains(d[item], dest, prefix + [item])
    else:
        if d and not (d == 'UNDEFINED'):
            # ignore empty stuff
            dest = dest.union((tuple(prefix),))
    return dest


def _get_study_df(bids_directory):
    subject_ids = []
    study_dict = OrderedDict()
    for file in glob(opj(bids_directory, "sub-*")):
        if os.path.isdir(file):
            subject_ids.append(psplit(file)[-1][4:])
    subject_ids.sort()
    study_dict["Source Name"] = subject_ids
    study_dict["Characteristics[organism]"] = "homo sapiens"
    study_dict["Characteristics[organism part]"] = "brain"
    study_dict["Protocol REF"] = "Participant recruitment"
    study_dict["Sample Name"] = subject_ids
    df = pd.DataFrame(study_dict)

    participants_file = opj(bids_directory, "participants.tsv")
    if not exists(participants_file):
        return df

    participants_df = pd.read_csv(participants_file, sep="\t")
    rename_rule = sample_property_name_map.copy()
    # remove all mapping that do not match the columns at hand
    for r in rename_rule.keys():
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


def _describe_file(fpath, bids_directory):
    fname = psplit(fpath)[-1]
    fname_components = fname.split(".")[0].split('_')
    info = {
        'Sample Name': fname_components[0][4:],
        # assay name is the entire filename except for the modality suffix
        # so that, e.g. simultaneous recordings match wrt to the assay name
        # across assay tables
        'Assay Name': '_'.join(fname_components[:-1]),
        'Raw Data File': fpath[len(bids_directory):],
        'Parameter Value[modality]': fname_components[-1]
    }
    comp_dict = dict([c.split('-') for c in fname_components[:-1]])
    for l in ('rec', 'recording'):
        if l in comp_dict:
            info['Parameter Value[recording label]'] = comp_dict[l]
    for l in ('acq', 'acquisition'):
        if l in comp_dict:
            info['Parameter Value[acquisition label]'] = comp_dict[l]
    if 'task' in comp_dict:
        info['Factor Value[task]'] = comp_dict['task']
    info['other_fields'] = get_bids_metadata(
        bids_directory,
        '_'.join(fname_components)
    )
    return info


def _describe_mri_file(fpath, bids_directory):
    info = _describe_file(fpath, bids_directory)

    if not exists(fpath):
        # this could happen in the case of a dead symlink in,
        # e.g., a git-annex repo
        logging.warn(
            "cannot extract meta data from '{}'".format(fpath))
        return info

    header = nibabel.load(fpath).get_header()
    spatial_unit = header.get_xyzt_units()[0]
    # by what factor to multiply by to get to 'mm'
    if spatial_unit == 'unknown':
        logging.warn(
            "unit of spatial resolution for '{}' unkown, assuming 'millimeter'".format(
                fpath))
    spatial_unit_conversion = {
        'unknown': 1,
        'meter': 1000,
        'mm': 1,
        'micron': 0.001}.get(spatial_unit, None)
    if spatial_unit_conversion is None:
        raise RuntimeError("unexpected spatial unit code '{}' from NiBabel".format(
            spatial_unit))

    info['Parameter Value[resolution]'] = "x".join(
        [str(i * spatial_unit_conversion) for i in header.get_zooms()[:3]])
    if len(header.get_zooms()) > 3:
        # got a 4th dimension
        rts_unit = header.get_xyzt_units()[1]
        if rts_unit == 'unknown':
            logging.warn(
                "RTS unit '{}' unkown, assuming 'seconds'".format(
                    fpath))
        # normalize to seconds, if possible
        rts_unit_conversion = {
            'msec': 0.001,
            'micron': 0.000001}.get(rts_unit, 1.0)
        info['Parameter Value[4d spacing]'] = header.get_zooms()[3] * rts_unit_conversion
        if rts_unit in ('hz', 'ppm', 'rads'):
            # not a time unit
            info['Parameter Unit[4d spacing]'] = rts_unit
        else:
            info['Parameter Unit[4d spacing]'] = 'second'
    return info


def _get_file_matches(bids_directory, glob_pattern):
    files = glob(
        opj(bids_directory, "sub-*", "*", "sub-{}".format(glob_pattern)))
    files += glob(
        opj(bids_directory, "sub-*", "ses-*", "*", "sub-*_ses-{}".format(
            glob_pattern)))
    return files


def _get_mri_assay_df(bids_directory, modality):
    # locate MRI files
    files = _get_file_matches(bids_directory, '*_{}.nii.gz'.format(modality))

    df, params = _get_assay_df(
        bids_directory,
        modality,
        "Magnetic Resonance Imaging",
        files,
        _describe_mri_file)
    return df, params


def _get_assay_df(bids_directory, modality, protocol_ref, files, file_descr):
    assay_dict = OrderedDict()
    assay_dict["Protocol REF"] = protocol_ref
    finfos = []
    info_keys = set()
    for fname in files:
        finfo = file_descr(fname, bids_directory)
        info_keys = info_keys.union(finfo.keys())
        finfos.append(finfo)
    collector_dict = dict(zip(info_keys, [[] for i in range(len(info_keys))]))
    for finfo in finfos:
        for spec in info_keys:
            fspec = finfo.get(spec, None)
            collector_dict[spec].append(fspec)
    for k in collector_dict:
        if k == 'other_fields':
            # special case dealt with below
            continue
        # skip empty
        if not all([v is None for v in collector_dict[k]]):
            assay_dict[k] = collector_dict[k]

    # record order of parameters; needs to match order in above loop
    mri_par_names = ["Resolution", "Modality"]

    # determine the union of any additional fields found for any file
    new_fields = set()
    for d in collector_dict.get('other_fields', []):
        new_fields = get_keychains(d, new_fields, [])
    # create a parameter column for each of them
    for field in new_fields:
        # deal with nested structures by concatenating the field names
        field_name = ':'.join(field)
        # normalize parameter names
        field_name = parameter_name_map.get(field_name.lower(), field_name)
        # final column ID
        column_id = "Parameter Value[{}]".format(field_name)
        assay_dict[column_id] = []
        # and fill with content from files
        for d in collector_dict['other_fields']:
            assay_dict[column_id].append(get_chainvalue(field, d))

    if 'Assay Name' in assay_dict:
        df = pd.DataFrame(assay_dict)
        df = df.sort_values(['Assay Name'])
        return df, mri_par_names  # TODO investigate necessity for 2nd return value
    else:
        return pd.DataFrame(), []


def _get_investigation_template(bids_directory, mri_par_names):
    this_path = os.path.realpath(
        __file__[:-1] if __file__.endswith('.pyc') else __file__)
    template_path = opj(
        *(psplit(this_path)[:-1] + ("i_investigation_template.txt", )))
    investigation_template = open(template_path).read()

    title = psplit(bids_directory)[-1]

    if exists(opj(bids_directory, "dataset_description.json")):
        with open(opj(bids_directory, "dataset_description.json"), "r") \
                as description_dict_fp:
            description_dict = json.load(description_dict_fp)
            if "Name" in description_dict:
                title = description_dict["Name"]

    investigation_template = investigation_template.replace(
        "[TODO: TITLE]", title)
    investigation_template = investigation_template.replace(
        "[TODO: MRI_PAR_NAMES]", ";".join(mri_par_names))
    return investigation_template


def _drop_from_df(df, drop):
    if drop is None:
        return df
    elif drop == 'unknown':
        # remove anything that isn't white-listed
        drop = [k for k in df.keys() if not k in ontology_term_map]
    elif isinstance(drop, (tuple, list)):
        # is list of parameter names to drop
        drop = ['Parameter Value[{}]'.format(d) for d in drop]

    # at this point drop is some iterable
    # filter assay table and take out matching parameters
    for k in df.keys():
        if k in drop:
            print('dropping %s from output' % k)
            df.drop(k, axis=1, inplace=True)
    return df


def _item_sorter_key(item):
    # define custom column order for tables
    name = item[0]
    if name in ('Sample Name', 'Source Name'):
        return 0
    elif name.startswith('Characteristics['):
        return 1
    elif name.startswith('Factor Value['):
        return 2
    elif name.startswith('Protocol REF'):
        return 3
    elif name == 'Assay Name':
        return 4
    elif name.startswith('Parameter Value['):
        return 5
    elif name == 'Raw Data File':
        return 6
    elif name.startswith('Comment['):
        return 10
    elif name.startswith('Parameter Unit['):
        # put them at the very end so we discover them last when adding
        # ontology terms
        return 99


def _sort_df(df):
    return pd.DataFrame.from_items(sorted(df.iteritems(), key=_item_sorter_key))


def _extend_column_list(clist, addition, after=None):
    if after is None:
        for a in addition:
            clist.append(a)
    else:
        tindex = None
        for i, c in enumerate(clist):
            if c[0] == after:
                tindex = i
        if tindex is None:
            raise ValueError("cannot find column '{}' in list".format(after))
        for a in addition:
            clist.insert(tindex + 1, a)
            tindex += 1


def _df_with_ontology_info(df):
    items = []
    # check whether we need ontology info for a task factor
    need_task_terms = False
    for col, val in df.iteritems():
        # check if we know something about this column
        term_map = ontology_term_map.get(col, None)
        if term_map is None:
            new_columns = [(col, val)]
        elif isinstance(term_map, tuple):
            # this is quantitative information -> 4-column group
            new_columns = [(col, val),
                           ('Unit', term_map[2]),
                           ('Term Source REF', term_map[0]),
                           ('Term Accession Number', term_map[1])]
        elif isinstance(term_map, dict):
            # this is qualitative information -> 3-column group
            normvals = []
            refs = []
            acss = []
            for v in val:
                normval, ref, acs = term_map.get(
                    v.lower() if hasattr(v, 'lower') else v,
                    (None, None, None))
                normvals.append(normval)
                refs.append(ref)
                acss.append(acs)
                if v and normval is None:
                    logging.warn("unknown value '{}' for '{}' (known: {})".format(
                        v, col, term_map.keys()))
            new_columns = [(col, normvals),
                           ('Term Source REF', refs),
                           ('Term Accession Number', acss)]
        # merged addition with current set of columns
        if col.startswith('Parameter Unit['):
            # we have a unit column plus terms, insert after matching
            # parameter value column
            after = 'Parameter Value[{}]'.format(col[15:-1])
            new_columns[0] = ('Unit', new_columns[0][1])
        elif col == 'Factor Value[task]':
            # flag that we ought to be looking for task info
            need_task_terms = True
        elif col in ('Parameter Value[CogPOID]',
                     'Parameter Value[CogAtlasID]'):
            if not need_task_terms:
                after = None
                new_columns = []
            else:
                after = 'Factor Value[task]'
                # TODO check with Varsha how those could be formated
                terms = [v.strip('/').split('/')[-1] if v is not None else None
                         for v in val]
                source_refs = [v[:-(len(terms[i]))] if terms[i] is not None else None
                               for i, v in enumerate(val)]
                new_columns = [('Term Source REF', source_refs),
                               ('Term Accession Number', terms)]
                # ignore a possible second term set
                need_task_terms = False
        else:
            # straight append
            after = None
        _extend_column_list(items, new_columns, after)

    return pd.DataFrame.from_items(items)


def _store_beautiful_table(df, output_directory, fname, repository_info=None):
    df = _sort_df(df)
    df = _df_with_ontology_info(df)
    if repository_info:
        df['Comment[Data Repository]'] = repository_info[0]
        df['Comment[Data Record Accession]'] = repository_info[1]
        df['Comment[Data Record URI]'] = repository_info[2]
    df.to_csv(
        opj(output_directory, fname),
        sep="\t",
        index=False)


def extract(
        bids_directory,
        output_directory,
        drop_parameter=None,
        repository_info=None):
    if not exists(output_directory):
        logging.info(
            "creating output directory at '{}'".format(output_directory))
        os.makedirs(output_directory)

    # generate: s_study.txt
    _store_beautiful_table(
        _get_study_df(bids_directory),
        output_directory,
        "s_study.txt")

    # all imaging modalities recognized in BIDS
    for modality in ('T1w', 'T2w', 'T1map', 'T2map', 'FLAIR', 'FLASH', 'PD',
                     'PDmap', 'PDT2', 'inplaneT1', 'inplaneT2', 'angio',
                     'sbref', 'bold', 'defacemask', 'SWImagandphase'):
        # generate: a_assay.txt
        mri_assay_df, mri_par_names = _get_mri_assay_df(bids_directory, modality)
        if not len(mri_assay_df):
            # not files found, try next
            logging.info(
                "no files match MRI modality '{}', skipping".format(modality))
            continue
        _drop_from_df(mri_assay_df, drop_parameter)
        _store_beautiful_table(
            mri_assay_df,
            output_directory,
            "a_assay_mri_{}.txt".format(modality.lower()),
            repository_info)

    # physio
    df, params = _get_assay_df(
        bids_directory,
        'physio',
        "Physiological Measurement",
        _get_file_matches(bids_directory, '*_physio.tsv.gz'),
        _describe_file)
    if len(df):
        _store_beautiful_table(
            _drop_from_df(df, drop_parameter),
            output_directory,
            'a_assay_physiology.txt',
            repository_info)

    # stimulus
    df, params = _get_assay_df(
        bids_directory,
        'stim',
        "Stimulation",
        _get_file_matches(bids_directory, '*_stim.tsv.gz'),
        _describe_file)
    if len(df):
        _store_beautiful_table(
            _drop_from_df(df, drop_parameter),
            output_directory,
            'a_assay_stimulation.txt',
            repository_info)

    # generate: i_investigation.txt
    investigation_template = _get_investigation_template(
        bids_directory, mri_par_names)
    with open(opj(output_directory, "i_investigation.txt"), "w") as fp:
        fp.write(investigation_template)


def _get_cmdline_parser():
    class MyParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: %s\n' % message)
            self.print_help()
            sys.exit(2)

    parser = MyParser(
        description="BIDS to ISA-Tab converter.",
        fromfile_prefix_chars='@')
    # TODO Specify your real parameters here.
    parser.add_argument(
        "bids_directory",
        help="Location of the root of your BIDS compatible directory",
        metavar="BIDS_DIRECTORY")
    parser.add_argument(
        "output_directory",
        help="Directory where ISA-TAB files will be stored",
        metavar="OUTPUT_DIRECTORY")
    parser.add_argument(
        "-v",
        "--verbose",
        help="increase output verbosity",
        action="store_true")
    parser.add_argument(
        "--keep-unknown",
        help="""by default only explicitely white-listed parameters and
        characteristics are considered. This option will force inclusion of
        any discovered information. See --drop-parameter for additional
        tuning.""",
        action='store_true')
    parser.add_argument(
        "-d",
        "--drop-parameter",
        help="""list of parameters to ignore when composing the assay table. See
        the generated table for column IDs to ignore. For example, to remove
        column 'Parameter Value[time:samples:ContentTime]', specify
        `--drop-parameter time:samples:ContentTime`. Only considered together
        with --keep-unknown.""")
    parser.add_argument(
        "--repository-info",
        metavar=('NAME', 'ACCESSION#', 'URL'),
        help="""data repository information to be used in assay tables.
        Example: 'OpenfMRI ds000113d https://openfmri.org/dataset/ds000113d'""",
        nargs=3)
    return parser


def main(argv=None):
    parser = _get_cmdline_parser()
    args = parser.parse_args(argv)

    # Setup logging
    if args.verbose:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    logging.basicConfig(format="%(levelname)s: %(message)s", level=loglevel)

    extract(
        args.bids_directory,
        args.output_directory,
        args.drop_parameter if args.keep_unknown else 'unknown',
        args.repository_info
    )
    print("Metadata extraction complete.")


if __name__ == '__main__':
    main()


#
# Make it work seamlessly as a datalad export plugin
#
def _datalad_export_plugin_call(
        ds,
        argv=None,
        output=None,
        drop_parameter=None,
        repository_info=None):
    if argv is not None:
        # from cmdline -> go through std entrypoint
        return main(argv + [ds.path, output])

    # from Python API
    return extract(
        ds.path,
        output_directory=output,
        drop_parameter=drop_parameter,
        repository_info=repository_info)


def _datalad_get_cmdline_help():
    parser = _get_cmdline_parser()
    # return help text and info on what to replace in it to still make
    # sense when delivered through datalad
    return \
        parser.format_help(), \
        (('BIDS_DIRECTORY', 'SETBYDATALAD'),
         ('OUTPUT_DIRECTORY', 'SETBYDATALAD'))

full_title="Demo of automatic conversion of DICOMs into BIDS and managing data using DataLad"
run "set -eu  # Fail early if any error happens"
say "Heudiconv (Heuristic DICOM Converter, https://github.com/nipy/heudiconv) now allows to create DataLad datasets with your neuroimaging data as soon as it comes from the MRI scanner."

say "In this example we will use a heudiconv heuristic developed and used at DBIC (Dartmouth Brain Imaging Center) to have all collected data made available as BIDS datasets. See http://goo.gl/WEoCge describing the naming convention."

say "We will demonstrate it on some data acquired on a phantom, mimicking multiple studies/subjects/sessions setup, and already available through datalad:"
run "datalad install -r -g -J4 ///dicoms/dartmouth-phantoms/bids_test4-20161014"
say "We will now run heudiconv pointing to DBIC heuristic on data for the first five sessions (could be done one scanning session at a time, or entire directory as well), while instructing heudiconv to place produced data under DataLad control."
say "First we will download the heuristic file from heudiconv's repository:"
run "wget https://raw.githubusercontent.com/nipy/heudiconv/master/heuristics/dbic_bids.py"

say "and then run heudiconv instructing to process multiple sessions, and place all converted data under a dataset called 'demo' (for the purpose of the demo we will convert only all anatomicals):"
run "heudiconv --bids --datalad -f ./dbic_bids.py -o demo bids_test4-20161014/phantom-[1-5]/*{scout,T1w}*"

say "Heudiconv has created a hierarchy of DataLad datasets, with levels PI/Researcher/study"
run "datalad ls -r demo"

say "where separate scanning sessions detected by heudiconv were contributed as separate commits to the sub-dataset corresponding to the specific study (as discovered from 'Study Description' field in DICOM):"
run "cd demo/Halchenko/Yarik/950_bids_test4"
run "git log --pretty=oneline"

say "Not only that all DICOMs were converted into a BIDS-compliant dataset, this heuristic also provided templates for mandatory files in BIDS format, some of which were placed directly under git to ease modification and integration of changes:"
run "cat dataset_description.json"
say "and you can easily find files/fields which need adjustment with information only you might know (design, author, license, etc) by searching for TODO"
run "git grep TODO"
say "All binary data and otherwise 'sensitive' files (e.g. _scans.tsv files) where placed under git-annex control:"
run "git annex list"

say "Original DICOMS, converted anatomicals (which are not yet defaced), and _scans.tsv files also obtained a meta-data tag to allow easy identification of data which did not go through anonimization step yet and might potentially contain subject-identifying information:"
run "datalad metadata sourcedata/sub-phantom1sid1"

say "These datasets are ready to be installed from this location to the processing box. In the demo we will just perform it on the localhost and only for the current study since sub-datasets are independent of their supers:"
run 'datalad install -g -r -s localhost:$PWD ~/950_bids_test4-process'
run "cd ~/950_bids_test4-process"

say "Data now could be processed/analyzed/etc in this dataset 'sibling'."

say "According to BIDS derivative (e.g. preprocessed) data should reside under derivatives/, so we create a new subdataset"
run "datalad create -d . derivatives/preprocess1"
say "and do our thorough preprocessing (see http://bids-apps.neuroimaging.io for ready to use pipelines like mriqc and fmriprep), in our case a sample brain extraction:"
run "source /etc/fsl/fsl.sh   # to enable FSL on NeuroDebian systems"
run "mkdir -p derivatives/preprocess1/sub-phantom1sid1/ses-localizer/anat/  # create target output directory"
run "bet {,derivatives/preprocess1/}sub-phantom1sid1/ses-localizer/anat/sub-phantom1sid1_ses-localizer_T1w.nii.gz"

say "To keep control over the versions of all data we work with, we add results of pre-processing under DataLad version control"
run "datalad save -m 'added initial preprocessing (well -- BETing output)' derivatives/preprocess1/*"
say "and then also adjust meta-data templates heudiconv pre-generated for us:"
run "sed -i -e 's,First1 Last1,Data Lad,g' -e '/TODO/d' dataset_description.json"
say "We save all so far accumulated changes"
run "datalad save -m 'Finished initial preprocessing, specified PI in dataset description and removed TODOs.'"

say "Whenever more data is acquired, heudiconv conversion could be ran again to complement previously acquired datasets with new data."
run "cd"
run "heudiconv --bids --datalad -f ./dbic_bids.py -o demo bids_test4-20161014/phantom-[6-9]/*{scout,T1w}*"

say "Now we can go to the processing 'box' again and update the entire hierarchy (in our case actually just one but we could have cloned entire tree for a PI) of the datasets while incorporating with possible changes already done on the processing box, while git would track the entire history of modifications."
run "cd ~/950_bids_test4-process"
run "datalad update --merge -r"
run "git status  # all clear"
run "cat dataset_description.json  # and our changes are still in place"
say "Now you could process newly acquired data... rinse repeat, while keeping the full history of actions:"
run "git log --pretty=oneline"

say "See also demos on how data could be exported and/or published whenever you are ready to share it publicly or with your collaborators."

say "Heudiconv (Heuristic DICOM Converter, https://github.com/nipy/heudiconv) now allows to create DataLad datasets with your neuroimaging data as soon as it comes from the MRI scanner."

say "In this example we will use a heudiconv heuristic developed and used at DBIC (Dartmouth Brain Imaging Center) to have all collected data made available as BIDS datasets. See http://goo.gl/WEoCge describing the naming convention."

say "We will demonstrate it on some data acquired on a phantom, mimicking multiple studies/subjects/sessions setup, and already available through datalad:"
run "datalad install -r -g -J4 ///dicoms/dartmouth-phantoms/bids_test4-20161014"
say "We will now run heudiconv pointing to DBIC heuristic on all acquired data (could be done one scanning session at a time as well), while instructing heudiconv to place produced data under DataLad control."
say "First we will download the heuristic file from heudiconv's repository:"
run "wget https://raw.githubusercontent.com/nipy/heudiconv/master/heuristics/dbic_bids.py"

say "and then run heudiconv instructing to search entire collection of files for DICOMs, and place all converted data under a dataset called 'demo':"
run "heudiconv --bids --datalad -f ./dbic_bids.py -o demo bids_test4-20161014"

say "Heudiconv has created a hierarchy of DataLad datasets, with levels PI/Researcher/study"
run "datalad ls -r demo"

say "where separate scanning sessions detected by heudiconv were contributed as separate commits to the sub-dataset corresponding to the specific study (as discovered from 'Study Description' field in DICOM):"
run "cd demo/Halchenko/Yarik/950_bids_test4"
run "git log --pretty=oneline"

say "Not only that all DICOMs were converted into a BIDS-compliant dataset, this heuristic also provided templates for mandatory files in BIDS format, some of which were placed directly under git to ease modification and integration of changes:"
run "cat dataset_description.json"
say "All binary data and otherwise 'sensitive' files (e.g. _scans.tsv files) where placed under git-annex control:"
run "git annex list"

say "Original DICOMS, converted anatomicals (which are not yet defaced), and _scans.tsv files also obtained a meta-data tag to allow easy identification of data which did not go through anonimization step yet and might potentially contain subject-identifying information:"
run "datalad metadata sourcedata/sub-phantom1sid1/ses-localizer/anat/sub-phantom1sid1_ses-localizer_T1w.dicom.tgz"

say "These datasets are ready to be installed from this location to the processing box, and be processed, adjusted (templates modified), etc.  Whenever more data is acquired, heudiconv conversion could be ran again to complement previously acquired datasets with new data.  With 'datalad update -r --merge' ran on the processing box, the entire hierarchy of the datasets on the processing box could later be updated to fetch new data while incorporating with possible changes already done on the processing box, while git would track the entire history of modifications."
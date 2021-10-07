say "Scientific studies should be reproducible, and with the increasing accessibility of data, there is not much excuse for lack of reproducibility anymore."
say "DataLad can help with the technical aspects of reproducible science..."
say "It always starts with a dataset"
run "datalad create demo"
run "cd demo"

say "For this demo we are using two public brain imaging datasets that were published on OpenFMRI.org, and are available from DataLad's datasets.datalad.org"
run "datalad install -d . -s ///openfmri/ds000001 inputs/ds000001"

say "BTW: '///' is just short for https://datasets.datalad.org"

run "datalad install -d . -s ///openfmri/ds000002 inputs/ds000002"

say "Both datasets are now registered as subdatasets, and their precise versions are on record"
run "datalad --output-format '{path}: {revision_descr}' subdatasets"

say "However, very little data were actually downloaded (the full datasets are several gigabytes in size):"
run "du -sh inputs/"

say "DataLad datasets are fairly lightweight in size, they only contain pointers to data and history information in their minimal form."

say "Both datasets contain brain imaging data, and are compliant with the BIDS standard. This makes it really easy to locate particular images and perform analysis across datasets."
say "Here we will use a small script that performs 'brain extraction' using FSL as a stand-in for a full analysis pipeline"
run "mkdir code"
run "cat << EOT > code/brain_extraction.sh
# enable FSL
. /etc/fsl/5.0/fsl.sh

# obtain all inputs
datalad get \\\$@
# perform brain extraction
count=1
for nifti in \\\$@; do
  subdir=\"sub-\\\$(printf %03d \\\$count)\"
  mkdir -p \\\$subdir
  echo \"Processing \\\$nifti\"
  bet \\\$nifti \\\$subdir/anat -m
  count=\\\$((count + 1)) 
done
EOT"

say "Note that this script uses the 'datalad get' command which automatically obtains the required files from their remote source -- we will see this in action shortly"
say "We are saving this script in the dataset. This way we will know exactly which code was used for the analysis. Also, we track this code file with Git, so we can see more easily how it was edited over time."
run "datalad save code -m \"Brain extraction script\" --to-git"

say "In addition, we will \"tag\" this state of the dataset. This is optional, but it can help to identify important milestones more easily"
run "datalad save --version-tag setup_done"

say "Now we can run our analysis code to produce results. However, instead of running it directly, we will run it with DataLad -- this will automatically create a record of exactly how this script was executed"
say "For this demo we will just run it on the structural images of the first subject from each dataset. The uniform structure of the datasets makes this very easy. Of course we could run it on all subjects; we are simply saving some time for this demo."
say "While the command runs, you should notice a few things:"
say "1) We run this command with 'bash -e' to stop at any failure that may occur"
say "2) You'll see the required data files being obtained as they are needed -- and only those that are actually required will be downloaded"
run "datalad run bash -e code/brain_extraction.sh inputs/ds*/sub-01/anat/sub-01_T1w.nii.gz"

say "The analysis step is done, all generated results were saved in the dataset. All changes, including the command that caused them are on record"
run "git show --stat"

say "DataLad has enough information stored to be able to re-run a command."
say "On command exit, it will inspect the results and save them again, but only if they are different."
say "In our case, the re-run yields bit-identical results, hence nothing new is saved."
run "datalad rerun"

say "Now that we are done, and have checked that we can reproduce the results ourselves, we can clean up"
say "DataLad can easily verify if any part of our input dataset was modified since we configured our analysis"
run "datalad diff --revision setup_done inputs"

say "Nothing was changed."
say "With DataLad with don't have to keep those inputs around -- without losing the ability to reproduce an analysis."
say "Let's uninstall them -- checking the size on disk before and after"

run "du -sh" .
run "datalad uninstall inputs/*"
run "du -sh ."
say "All inputs are gone..."
run "ls inputs/*"

say "Only the remaining data (our code and the results) need to be kept and require a backup for long term archival. Everything else can be re-obtained as needed, when needed."

say "As DataLad knows everything needed about the inputs, including where to get the right version, we can re-run the analysis with a single command. Watch how DataLad re-obtains all required data, re-runs the code, and checks that none of the results changed and need saving"
run "datalad rerun"

say "Reproduced!"

say "This dataset could now be published and enable anyone to replicate the exact same analysis. Public data for the win!"

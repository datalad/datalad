say "Import nipype building blocks"
show "Import nipype building blocks"
run "from nipype import Node, Workflow"

say "Import relevant interfaces"
show "Import relevant interfaces"
run "from nipype.interfaces.fsl import SliceTimer, MCFLIRT, Smooth"

say "Create SliceTime correction node"
show "Create SliceTime correction node"
run "slicetimer = Node(SliceTimer(index_dir=False,
                             interleaved=True,
                             time_repetition=2.5),
                  name='slicetimer')
"

say "Create Motion correction node"
show "Create Motion correction node"
run "mcflirt = Node(MCFLIRT(mean_vol=True,
                       save_plots=True),
               name='mcflirt')
"

show "Create Smoothing node"
run "smooth = Node(Smooth(fwhm=4), name='smooth')"

show "Create Workflow"
run "preproc01 = Workflow(name='preproc01', base_dir='.')"

show "Connect nodes within the workflow"
run "preproc01.connect([(slicetimer, mcflirt, [('slice_time_corrected_file', 'in_file')]),
                   (mcflirt, smooth, [('out_file', 'in_file')])])
"

show "Create a visualization of the workflow"
run "preproc01.write_graph(graph2use='orig')"

show "Visualize the figure"
run "!eog preproc01/graph_detailed.png
"

show "Feed some input to the workflow"
run "slicetimer.inputs.in_file = 'path/to/your/func.nii.gz'"

show "Run the Workflow and stop the time"
run "%time preproc01.run('MultiProc', plugin_args={'n_procs': 5})"

show "Investigate the output"
run "!tree preproc01 -I '*js|*json|*pklz|_report|*.dot|*html'"

show "Change the size of the smoothing kernel"
run "smooth.inputs.fwhm = 2"

show "Rerun the workflow"
run "%time preproc01.run('MultiProc', plugin_args={'n_procs': 5})"

show "Create 4 additional copies of the workflow"
run "preproc02 = preproc01.clone('preproc02')
preproc03 = preproc01.clone('preproc03')
preproc04 = preproc01.clone('preproc04')
preproc05 = preproc01.clone('preproc05')
"

show "Create a new workflow - metaflow"
run "metaflow = Workflow(name='metaflow', base_dir='.')"

show "Add the 5 workflows to this metaflow"
run "metaflow.add_nodes([preproc01, preproc02, preproc03,
                    preproc04, preproc05])
"

show "Visualize the workflow"
run "metaflow.write_graph(graph2use='flat')
!eog metaflow/graph_detailed.png
"

show "Run this metaflow in parallel"
run "%time metaflow.run('MultiProc', plugin_args={'n_procs': 5})"

show "Investigate the output"
run "!tree metaflow -I '*js|*json|*pklz|_report|*.dot|*html'"

show "The End."

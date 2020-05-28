.. -*- mode: rst -*-
.. vi: set ft=rst sts=4 ts=4 sw=4 et tw=79:

.. _chap_reporting:

*********
Reporting
*********

When you trigger an error, we want to make it easy to ask for help. By adding
an integration, helpme_, DataLad can automatically send a traceback of your error
to datalad_helpme_ where the development team can help you out.

Setup
=====

To use helpme, you should have the full install of Datalad, or install helpme
separately:

.. code-block:: console

    $ pip install helpme[github]


To submit to GitHub, HelpMe only requires requests, which is already required by
Datalad, so the install above will not add any additional dependencies other
than the helpme library itself. If you don't choose to


Usage
=====

When you run a Datalad command that triggers an error that isn't well understood
(meaning that we go through many except statements and don't catch a known error)
it will hit the last statement and run a function to run helpme. HelpMe will
first verify with you environment variables to share (a basic set is shared):

.. code-block:: console

    Environment  USER|TERM|SHELL|PATH|LD_LIBRARY_PATH|PWD|JAVA_HOME|LANG|HOME|DISPLAY
    Is this list ok to share?
    Please enter your choice [Y/N/y/n] : y
    

And then the browser will open to the issue repository, where you can write more content
into the issue. Using the standard template, useful information about your system 
and libraries is shared so you don't need to do it. You can look at a sample_issue_
for an example of what is shared.

If you need a completely headless and non-interactive interaction, then you can
simply export a ``HELPME_GITHUB_TOKEN`` to the environment and it will
be discovered, and use the GitHub API to open the same issue. See the helpme_
documentation for more details.

Disable
=======

To disable submitting helpme issues, simply export this variable to the environment,
set as anything:

.. code-block:: console

    export DATALAD_HELPME_DISABLE=yes


.. _datalad_helpme: https://github.com/datalad/datalad-helpme
.. _helpme: https://vsoch.github.io/helpme/helper-github#headless
.. _sample_issue: https://github.com/datalad/datalad-helpme/issues/4

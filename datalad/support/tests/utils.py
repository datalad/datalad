# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Utils for testing support module
"""


from datalad.tests.utils import *


def check_repo_deals_with_inode_change(class_, path, temp_store):

    repo = class_(path, create=True)
    with open(opj(path, "testfile.txt"), "w") as f:
        f.write("whatever")
    repo.add("testfile.txt", commit=True, msg="some load")

    # requesting HEAD info from
    hexsha = repo.repo.head.object.hexsha

    # move everything to store
    import os
    import shutil
    old_inode = os.stat(path).st_ino
    shutil.copytree(path, temp_store, symlinks=True)
    # kill original
    rmtree(path)
    assert (not exists(path))
    # recreate
    shutil.copytree(temp_store, path, symlinks=True)
    new_inode = os.stat(path).st_ino

    if old_inode == new_inode:
        raise SkipTest("inode did not change. Nothing to test for.")

    # Now, there is a running git process by GitPython's Repo instance,
    # connected to an invalid inode!
    # The *Repo needs to make sure to stop them, whenever we access the instance
    # again (or request a flyweight instance).

    # The following two accesses fail in issue #1512:
    # 1. requesting HEAD info from old instance
    hexsha = repo.repo.head.object.hexsha

    # 2. get a "new" instance and requesting HEAD
    repo2 = class_(path)
    hexsha2 = repo2.repo.head.object.hexsha


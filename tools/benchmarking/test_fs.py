import argparse
import glob
import os
from datalad.cmd import Runner
from datalad.support.protocol import DryRunProtocol
import logging
import time
import json

DRIVES_PREFIX = "ata-ST4000NM0033-9ZM170_S1Z0"

lgr = logging.getLogger("datalad.benchmarking")

run = Runner()
dryrun = Runner()


def get_drives(prefix, even=True):
    """Return letters for corresponding drives"""
    drives = [d for d in glob.glob('/dev/disk/by-id/%s*' % prefix)
              if not '-part' in d]
    drives = sorted([
        os.path.realpath(d)[-3:]
        for d in drives
        ])
    for d in drives:
        assert(d.startswith('sd'))
    if even and len(drives) > 1:
        drives = drives[:len(drives)//2*2]
    assert(len(drives) == 1 or len(drives) % 2 == 0)
    return drives


def get_drive_size(drive):
    with open('/sys/block/%s/size' % drive) as f:
        return int(f.read())


def flush():
    dryrun("sudo sync; sudo sh -c 'echo 3 >/proc/sys/vm/drop_caches'", shell=True)


def wait_till_low_load(limit=0.4):
    # wait until load goes down
    while True:
        with open('/proc/loadavg') as f:
            if float(f.readline().split()[0]) < limit:
                return
            time.sleep(1)


def get_dasho(options):
    """Represent options in ZFS friendly ["-o", "option=value"]"""
    return sum([["-o", o] for o in options], [])


def wipe_drives(drives):
    lgr.info("Wiping drives %s" % drives)
    for drive in drives:
        lgr.debug("Wiping drive %s" % drive)
        size = get_drive_size(drive)
        ddcmd = "/bin/dd if=/dev/zero of=/dev/%s bs=512 count=34" % drive
        dryrun(ddcmd, expect_stderr=True)
        dryrun(ddcmd + " skip=%d" % (size-34), expect_stderr=True)


class FS(object):
    def __init__(self, drives, mountpoint):
        self.drives = drives
        self.mountpoint = mountpoint

    def umount(self):
        try:
            dryrun("umount %s" % self.mountpoint)
        except:
            pass

    def kill(self):
        self.umount()

    def wipe(self):
        wipe_drives(self.drives)

def get_pairs(entries, prefix="mirror"):
    out = []
    for i, e in enumerate(entries):
        if not i % 2:
            out += [prefix]
        out.append(e)
    return out

from nose.tools import eq_
def test_get_pairs():
    eq_(get_pairs('ab'), ['mirror', 'a', 'b'])
    eq_(get_pairs('abcd'), ['mirror', 'a', 'b', 'mirror', 'c', 'd'])


class ZFS(FS):
    def __init__(self, drives, mountpoint, pool_options=["ashift=12"], compression=True, tank='testtank', layout="raid6"):
        super(ZFS, self).__init__(drives, mountpoint)
        self.tank = tank
        self.pool_options = pool_options[:]
        self.zfs_options = ['sync=standard']
        if compression:
            self.zfs_options += ["compression=on"]
        self.layout = layout

    def __str__(self):
        return "ZFS_%s" % "_".join(['layout=%s' % self.layout]
                                   + sorted(self.zfs_options
                                            + self.pool_options))

    def create(self):
        self.kill()
        drives = self.drives()
        lgr.info("Creating GPT labels on %s" % drives)
        for drive in drives:
            dryrun("parted -s /dev/%s mklabel gpt" % drive)
        flush()
        # r("bash -c 'ls -l /dev/{%s}'" % ','.join(drives), shell=True)
        lgr.info("Creating the pool")
        if self.layout == 'raid6':
            layout_options = ["raidz2"] + drives
        elif self.layout == 'raid10':
            layout_options = get_pairs(drives, 'mirror')
        else:
            raise ValueError(self.layout)
        dryrun(["zpool", "create", "-f"]
               + get_dasho(self.pool_options)
               + [self.tank]
               + layout_options)
        # " ".join("%s1" % d for d in drives)))
        if "compression=on" in self.zfs_options:
            dryrun("zpool set feature@lz4_compress=enabled %s" % self.tank)
        lgr.info("Creating partition")
        dryrun(["zfs", "create", "-o", "mountpoint=%s" % self.mountpoint]
               + get_dasho(self.zfs_options)
               + ["%s/test" % self.tank])

    def kill(self, drives=None):
        super(ZFS, self).kill()
        try:
            stdout, stderr = run("zpool list %s" % self.tank)
        except:
            return
        lgr.info("Destroying ZFS pool %s" % self.tank)
        dryrun("zpool destroy %s" % self.tank)
        self.wipe(drives=drives)


class MD(object):
    """Just a base class for anything interested to use software raid as the base storage
    """
    # TODO:  do not build on top of entire drive, just generate about 100GB partition
    # and use it -- otherwise way too long process!  I know that it wouldn't be
    # exactly fair to ZFS though, so may be should be optional?  would be nice to compare
    # actually
    def __init__(self, drives, layout="raid6", recreate=False):
        self.layout = layout
        self.drives = drives
        self.recreate = recreate

    def __str__(self):
        return "MD_%s" % self.layout

    def create(self):
        if not self.recreate:
            # if exists -- we just skip
            try:
                _ = run("grep '^md10 ' /proc/mdstat")
                lgr.info("md10 exists -- skipping lengthy recreation")
                return "/dev/md10"
            except:
                pass

        self.kill()
        drives = self.drives
        dryrun(["mdadm", "--create", "--verbose", "/dev/md10",
                "--level=6", "--raid-devices=%d" % len(drives)]
                + drives, cwd="/dev")
        lgr.info("Now we will wait until it finishes generating the bloody RAID")
        while True:
            with open("/proc/mdstat") as f:
                if "%" in str(f.read()):
                    time.sleep(10)
                    #print '.',
                    continue
                break
        return "/dev/md10"

    def kill(self):
        try:
            _ = run("grep '^md10 ' /proc/mdstat")
            try:
                _ = run("umount /dev/md10")
            except:
                pass
            dryrun("mdadm --stop /dev/md10")
        except:
            pass
        if self.drives:
            wipe_drives(self.drives)


class Ext4(FS):
    def __init__(self, drives, mountpoint):
        super(Ext4, self).__init__(drives, mountpoint)

    def __str__(self):
        return "EXT4_%s" % self.drives[0]

    def create(self):
        drives = self.drives
        assert(len(drives) == 1)
        drive = drives[0]
        if isinstance(drive, MD):
            # so we were given the MD, let's create it as well
            drive = drive.create()
        self.umount()  # just to make sure it is not mounted
        dryrun("mkfs.ext4 -E lazy_itable_init=0,lazy_journal_init=0 %s" % drive)
        dryrun("mount -o relatime %s %s" % (drive, self.mountpoint))


def make_test_repo(d, nfiles=100, ndirs=1, git_options=[], annex_options=[]):
    lgr.info("Creating test repo %s with %d dirs with %d files each"
             % (d, ndirs, nfiles))
    run(["mkdir", "-p", d])
    run("git init", cwd=d)
    run(["git"] + git_options + ["annex", "init"] + annex_options, cwd=d)

    f_ = ndirs * nfiles # absolute count
    for dir_index in xrange(ndirs):
        d_ = "d%d" % dir_index
        df_ = os.path.join(d, d_)
        if not os.path.exists(df_):
            os.mkdir(df_)
        for n in xrange(nfiles):
            with open(os.path.join(df_, str(f_)), "w") as f:
                f.write("file%d" % f_)
            f_ -= 1
        run("git annex add %s/* >/dev/null" % d_, cwd=d)
        run('git commit -m "added %d files to %s" >/dev/null' % (nfiles, d_),
            cwd=d)
make_test_repo.__test__ = False


class BMRunner(Runner):
    def __init__(self, *args, **kwargs):
        super(BMRunner, self).__init__(*args, **kwargs)
        self.protocol = []

    def __call__(self, cmd, name=None, run_warm=True, **kwargs):
        if name is None:
            name = str(cmd)
        flush()
        wait_till_low_load()
        time0 = time.time()
        dryrun(cmd, cwd=self.cwd, **kwargs)
        dt = time.time() - time0
        if run_warm:
            time0 = time.time()
            dryrun(cmd, cwd=self.cwd, **kwargs)
            dt_warm = time.time() - time0
        else:
            dt_warm = -10
        print "%s: %.3g %s" % (name, dt, "%.3g" % dt_warm if dt_warm >= 0 else "")
        self.protocol.append({
            'command': name,
            'cold': dt,
            'warm': dt_warm
        })

def run_tests_ondir(testpath):
    wait_till_low_load(0.1)
    testdir = os.path.basename(testpath)
    bmrun = BMRunner(cwd=os.path.dirname(testpath), protocol=dryrun.protocol)
    bmrun("du -scm " + testdir)
    bmrun("tar -cf %s.tar %s" % (testdir, testdir), expect_stderr=True)
    bmrun("pigz %s.tar" % (testdir), run_warm=False)
    if os.path.exists(os.path.join(testpath, ".git/annex/objects")):
        bmrun("chmod +w -R %s/.git/annex/objects" % testdir)
    if os.path.exists(os.path.join(testpath, ".git")):
        bmrun("git clone %s %s.clone" % (testdir, testdir), run_warm=False, expect_stderr=True)
        bmrun("cd %s.clone; git annex get . " % testdir, run_warm=False)
        bmrun("cd %s.clone; git annex drop . " % testdir, run_warm=False)
        bmrun("du -scm %s.clone" % testdir)
    bmrun("rm -rf %s" % testdir, run_warm=False)
    bmrun("rm -rf %s.clone" % testdir, run_warm=False)
    bmrun("tar -xzf %s.tar.gz" % testdir, run_warm=False)
    return bmrun.protocol
run_tests_ondir.__test__ = False

def save_protocols(protocols, fname):
    with open(fname, 'w') as f:
        json.dump(protocols, f, indent=True)

def benchmark_fs(fs, skip_existing="TODO upstairs before even FS created"):
    """Benchmark given FS

    TODO: parametrize the test_repo
    """
    nfiles = 10; ndirs = 2; nruns = 1
    nfiles = 100; ndirs=20; nruns = 100
    test_descr = {
        "fs": str(fs),
        "test_repo": "simpleannex_ndirs=%d_nfiles=%d" % (ndirs, nfiles)
    }
    # make a list of protocols which will be self sufficient dictionaries, so
    # later we could easily load into pandas
    protocols = []
    for d in xrange(nruns):
        testdir = "test%d" % d
        testpath = os.path.join(fs.mountpoint, testdir)

        dryrun(make_test_repo, testpath, nfiles=nfiles, ndirs=ndirs)

        protocol = {
            'times': run_tests_ondir(testpath),
            'run': d
        }
        protocol.update(test_descr)
        protocols.append(protocol)

    fname = '%(test_repo)s-%(fs)s.json' % test_descr # -'.join("%s:%s.json" % (k, test_descr[k]) for k in sorted(test_descr))
    fullfname = os.path.join('test_fs_protocols', fname)
    dryrun(save_protocols, protocols, fullfname)



def parse_args(args=None):
    parser = argparse.ArgumentParser(description="A little benchmarker of file systems")
    parser.add_argument('action', choices=["benchmark", "wipe"], default="benchmark",
                        help='Action to perform')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='Perform dry run')
    # Parse command line options
    return parser.parse_args(args)


def main(action):
    drives = get_drives(DRIVES_PREFIX)
    mountpoint = "/mnt/test"
    if action == 'benchmark':
        for fs in [
            # ZFS(mountpoint=mountpoint, drives=drives, layout='raid10'),
            # ZFS(mountpoint=mountpoint, drives=drives, layout='raid6'),
            #ZFS(mountpoint=mountpoint, drives=drives, layout='raid6', pool_options=[])
            Ext4(drives=[MD(drives)], mountpoint=mountpoint)
        ]:
            lgr.info("Working on FS=%s with following drives: %s"
                     % (fs, " ".join(drives)))

            fs.create()
            benchmark_fs(fs)
    elif action == 'wipe':
        wipe_drives(drives)
    else:
        raise ValueError(action)


if __name__ == "__main__":
    args = parse_args()
    if args.dry_run:
        dryrun.protocol = DryRunProtocol()
    main(args.action)
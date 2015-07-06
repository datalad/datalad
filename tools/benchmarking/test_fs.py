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

def get_fqdrives(drives):
    """Return list pointing to drives under /dev
    """
    return [("/dev/%s" % d) if not d.startswith("/dev") else d
            for d in drives]

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
    def __init__(self, drives, mountpoint, pool_options=["ashift=12"],
                 compression=True, tank='testtank', layout="raid6"):
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
        drives = self.drives
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


class BlockDevice(object):
    """Class for any BlockDevice (software raid, LVM)"""
    def create(self):
        pass

    def kill(self):
        pass

class MD(BlockDevice):
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
        # TODO: abstract drives away so we could kill all the nested things
        if self.drives:
            wipe_drives(self.drives)


class LVM(BlockDevice):
    def __init__(self, drives, vgname="vgtest", lvname="lvtest", layout="linear"):
        self.drives = drives
        # TODO: allow for RAID5/6 via LVM
        assert(layout in ("linear", "raid6"))
        self.layout = layout
        self.vgname = vgname
        self.lvname = lvname

    def __str__(self):
        layout_str = "" if self.layout == "linear" else ("_" + self.layout)
        return "LVM%s_%s" % (layout_str, '+'.join(map(str, self.drives)))

    def create(self):
        self.kill()
        drives = []
        for drive in self.drives:
            if isinstance(drive, BlockDevice):
                # so we were given the MD, let's create it as well
                drives.append(drive.create())
            else:
                drives.append(drive)
        drives_paths = " ".join(get_fqdrives(drives))
        dryrun("pvcreate %s" % drives_paths)
        dryrun("vgcreate %s %s" % (self.vgname, drives_paths))
        if self.layout == "linear":
            lvcreate_opts = ""
        elif self.layout == "raid6":
            lvcreate_opts = "-i%d --type raid6" % (len(self.drives) - 2)
        else:
            raise ValueError(self.layout)
        dryrun("lvcreate -l 100%%FREE %s -n %s %s" % (lvcreate_opts, self.lvname, self.vgname))
        self.device = "/dev/mapper/%s-%s" % (self.vgname, self.lvname)
        return self.device

    def kill(self):
        try:
            _ = run("lvdisplay %s/%s" % (self.vgname, self.lvname))
            try:
                _ = run("umount %s" % self.device)
            except:
                pass
            dryrun("lvremove -f %s/%s || :" % (self.vgname, self.lvname), shell=True)
            dryrun("vgremove %s || :" % self.vgname, shell=True)
        except:
            pass


class BaseFS(FS):
    def __init__(self, drives, mountpoint, options=[], mount_options=[]):
        super(BaseFS, self).__init__(drives, mountpoint)
        self.options = options
        self.mount_options = mount_options

    def __str__(self):
        options_str = "_".join(sorted([x.replace(' ', '') for x in self.options]))
        if options_str:
            options_str = "_" + options_str
        return "%s_%s%s%s" % (self.__class__.__name__, self.drives[0], options_str,
                              self.get_mount_options_str('_'))

    def get_mount_options_str(self, prefix):
        mount_options_str = ",".join(sorted([x.replace(' ', '') for x in self.mount_options]))
        if mount_options_str:
            mount_options_str = prefix + mount_options_str
        return mount_options_str

    def create(self):
        self.umount()  # just to make sure it is not mounted
        drives = []
        for drive in self.drives:
            if isinstance(drive, BlockDevice):
                # so we were given the MD, let's create it as well
                drive = drive.create()
            drives.append(drive)
        if len(drives) == 1:
            self._create(drives[0])
        elif len(drives) > 1:
            self._create(drives)
        else:
            raise ValueError("need at least 1 drive")

    def _create(self):
        raise NotImplementedError

    def _mount(self, drive):
        lgr.debug("Mounting %s" % self)
        dryrun("mount -o relatime%s %s %s"
               % (self.get_mount_options_str(','), drive, self.mountpoint))



class EXT4(BaseFS):
    def _create(self, drive):
        dryrun("mkfs.ext4 -E lazy_itable_init=0,lazy_journal_init=0 %s %s" %
               (' '.join(self.options), drive))
        self._mount(drive)

class XFS(BaseFS):
    def _create(self, drive):
        dryrun("mkfs.xfs -f %s %s" %
               (' '.join(self.options), drive))
        self._mount(drive)

class BTRFS(BaseFS):

    def __str__(self):
        ostr = BaseFS.__str__(self)
        ostr = ostr.replace("BTRFS", "BTRFSv4")
        return ostr

    def _create(self, drives):
        # quick ugly for now
        if not isinstance(drives, list):
            drives = [ drives ]
        drives = get_fqdrives(drives)
        drives_str = " ".join(drives)
        dryrun("mkfs.btrfs -f %s %s" %
               (' '.join(self.options), drives_str))
        self._mount(drives[0])

class ReiserFS(BaseFS):
    def _create(self, drive):
        dryrun("mkfs.reiserfs -f -f %s %s" %
               (' '.join(self.options), drive))
        self._mount(drive)


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

    def __call__(self, cmd, name=None, run_warm=True, args=[], **kwargs):
        if name is None:
            name = str(cmd)
        flush()
        wait_till_low_load()
        time0 = time.time()
        kwargs_ = kwargs.copy()
        # TODO: ad-hoc/ugly for now
        if not cmd is make_test_repo:
            kwargs_['cwd'] = self.cwd
        dryrun(cmd, *args, **kwargs_)
        dt = time.time() - time0
        if run_warm:
            time0 = time.time()
            dryrun(cmd, *args, **kwargs_)
            dt_warm = time.time() - time0
        else:
            dt_warm = -10
        print "%s: %.3g %s" % (name, dt, "%.3g" % dt_warm if dt_warm >= 0 else "")
        self.protocol.append({
            'command': name,
            'cold': dt,
            'warm': dt_warm
        })
        # TODO: I guess we could run some bonnie++ on it as well since we have got
        # so far already

def run_tests_ondir(testpath, nfiles, ndirs):
    wait_till_low_load(0.4)
    testdir = os.path.basename(testpath)
    bmrun = BMRunner(cwd=os.path.dirname(testpath), protocol=dryrun.protocol)
    bmrun(make_test_repo, args=[testpath], run_warm=False, nfiles=nfiles, ndirs=ndirs)
    bmrun("du -scm " + testdir)
    bmrun("tar -cf %s.tar %s" % (testdir, testdir), expect_stderr=True)
    bmrun("pigz %s.tar" % (testdir), run_warm=False)
    if os.path.exists(os.path.join(testpath, ".git")):
        bmrun("git clone %s %s.clone" % (testdir, testdir), run_warm=False, expect_stderr=True)
        bmrun("cd %s.clone; git annex get . " % testdir, run_warm=False)
        bmrun("cd %s.clone; git annex drop . " % testdir, run_warm=False)
        bmrun("du -scm %s.clone" % testdir)
    if os.path.exists(os.path.join(testpath, ".git/annex/objects")):
        bmrun("cd %s; git annex direct" % testdir)
        bmrun("du  -scm " + testdir)
        bmrun("cd %s; git annex indirect" % testdir)
        bmrun("chmod +w -R %s/.git/annex/objects" % testdir)
    bmrun("rm -rf %s" % testdir, run_warm=False)
    bmrun("rm -rf %s.clone" % testdir, run_warm=False)
    bmrun("tar -xzf %s.tar.gz" % testdir, run_warm=False)
    return bmrun.protocol
run_tests_ondir.__test__ = False

def save_protocols(protocols, fname):
    with open(fname, 'w') as f:
        json.dump(protocols, f, indent=True)

def benchmark_fs(fs):
    """Benchmark given FS

    TODO: parametrize the test_repo
    """
    nfiles = 10; ndirs = 2; nruns = 1
    #nfiles = 100; ndirs = 20; nruns = 100
    nfiles = 1000; ndirs = 100; nruns = 10
    test_descr = {
        "fs": str(fs),
        "test_repo": "simpleannex-big_ndirs=%d_nfiles=%d" % (ndirs, nfiles)
    }

    # make a list of protocols which will be self sufficient dictionaries, so
    # later we could easily load into pandas
    protocols = []
    for d in xrange(nruns):
        testdir = "test%d" % d
        testpath = os.path.join(fs.mountpoint, testdir)

        #dryrun(make_test_repo, testpath, nfiles=nfiles, ndirs=ndirs)

        protocol = {
            'times': run_tests_ondir(testpath, nfiles=nfiles, ndirs=ndirs),
            'run': d
        }
        protocol.update(test_descr)
        protocols.append(protocol)

    return test_descr, protocols



def parse_args(args=None):
    parser = argparse.ArgumentParser(description="A little benchmarker of file systems")
    parser.add_argument('action', choices=["benchmark", "wipe"], default="benchmark",
                        help='Action to perform')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='Perform dry run')
    parser.add_argument('--assume-created', action='store_true',
                        help='Assume that FS was created and mounted (e.g. manually outside)')

    # Parse command line options
    return parser.parse_args(args)


def main(action, assume_created=False):
    drives = get_drives(DRIVES_PREFIX)
    mountpoint = "/mnt/test"

    #mdraid_chunksize = 512  # k -- was the ones created by mdadm by default
    def mk_ext4(ext4_bs, mdraid_chunksize=512):
        """Just a helper to generate ext4 partitions with varying bs"""
        stride_size = (mdraid_chunksize/ext4_bs)
        return EXT4(drives=[MD(drives, layout='raid6')],
                    mountpoint=mountpoint,
                    options=['-E stride=%d' % stride_size,
                             '-E stripe_width=%d' % ((len(drives)-2)*stride_size),
                             #'-b %d' % (ext4_bs*1024)
                             ])

    if action == 'benchmark':
        zfs_raid6_drives = [
                    ZFS(mountpoint=mountpoint, drives=drives, layout='raid10'),
                    ZFS(mountpoint=mountpoint, drives=drives, layout='raid6'),
                    #ZFS(mountpoint=mountpoint, drives=drives, layout='raid6', pool_options=[])
                    ]
        """ZFS benchmarks on even raid10 showed to be too slow on our sizeable testcase
           to carry out in full and were terminated

2015-07-02 12:06:19,567 [INFO   ] Creating test repo /mnt/test/test0 with 100 dirs with 1000 files each (test_fs.py:350)
<function make_test_repo at 0x7fbcec6b7ed8>: 1.14e+03
du -scm test0: 2.19e+03 2.1e+03
tar -cf test0.tar test0: 5.26e+03 4.88e+03
pigz test0.tar: 14.9
git clone test0 test0.clone: 94.2
cd test0.clone; git annex get . : 8.44e+03
cd test0.clone; git annex drop . : 1.35e+04
du -scm test0.clone: 227 39.9
cd test0; git annex direct: 1.44e+03 0.0251
du  -scm test0: 3.89e+03 3.78e+03
cd test0; git annex indirect: 1.46e+03 0.0294
chmod +w -R test0/.git/annex/objects: 4.15e+03 4.01e+03
rm -rf test0: 6.1e+03
rm -rf test0.clone: 3.63e+03

Compare to MD+LVM+BTRFS

2015-07-01 17:40:57,773 [INFO   ] Creating test repo /mnt/test/test4 with 100 dirs with 1000 files each (test_fs.py:350)
<function make_test_repo at 0x7f3de6240ed8>: 985
du -scm test4: 171 2.35
tar -cf test4.tar test4: 228 5.12
pigz test4.tar: 4.3
git clone test4 test4.clone: 114
cd test4.clone; git annex get . : 823
cd test4.clone; git annex drop . : 830
du -scm test4.clone: 144 0.973
cd test4; git annex direct: 153 0.0103
du  -scm test4: 161 2.53
cd test4; git annex indirect: 196 0.0126
chmod +w -R test4/.git/annex/objects: 55.5 2.28
rm -rf test4: 201
rm -rf test4.clone: 275
tar -xzf test4.tar.gz: 27.6

        """
        fs_md_raid6_drives = [FS(drives=[MD(drives, layout='raid6')], mountpoint=mountpoint)
                              for FS in (EXT4, BTRFS, ReiserFS, XFS)]
        fs_ext4_var_bs = [
                    mk_ext4(bs) for bs in (1, 4, 16, 128)
                    ]

        fs_lvm_md_raid6_drives = [FS[0](drives=[LVM(drives=[MD(drives, layout='raid6')])],
                                     mountpoint=mountpoint, **FS[1])
                                  for FS in (#(EXT4, {}),
                                             #(BTRFS, {}),
                                             (BTRFS, {'mount_options': ['compress=lzo',
                                                                        #'compress=zlib',
                                                                        ]}),
                                             #(ReiserFS, {}),
                                             #(XFS, {}),
                                             )]

        fs_lvm_raid6_drives = [
             BTRFS(drives=[LVM(drives=drives, layout='raid6')], mountpoint=mountpoint),
             # BTRFS(drives=[LVM(drives=drives, layout='raid6')], mountpoint=mountpoint,  mount_options=["compress=lzo"]),  # didn't run
             ReiserFS(drives=[LVM(drives=drives, layout='raid6')], mountpoint=mountpoint),
             ]
        fs_btrfs_raid6_drives = [#BTRFS(drives=drives, options=["-m raid6"], mountpoint=mountpoint),
                                 BTRFS(drives=drives, options=["-m raid6"], mount_options=["compress=lzo"], mountpoint=mountpoint),
                                 ]
        """
        2015-06-29 09:22:29,001 [ERROR  ] Failed to run 'zpool list testtank' under '.'. Exit code=1 (cmd.py:251)
Traceback (most recent call last):
  File "test_fs.py", line 547, in <module>
    main(args.action, assume_created=args.assume_created)
  File "test_fs.py", line 523, in main
    fs.create()
  File "test_fs.py", line 121, in create
    drives = self.drives()
TypeError: 'list' object is not callable
"""
        for fs in (
            fs_lvm_md_raid6_drives
            # zfs_raid6_drives
            #TODO: fixup zfs_raid6_drives
            ##  fs_md_raid6_drives + fs_ext4_var_bs +
            #FAILED TO OPERATE CORRECT  fs_lvm_raid6_drives # while trying to "lvcreate -l 100%FREE -i4 --type raid6 -n lvtest vgtest"  I am getting "device-mapper: reload ioctl on  failed: Device or resource busy"  why is that? (debian jessie with 3.16.0-4-amd64)
            # fs_btrfs_raid6_drives
                  ):
            lgr.info("Working on FS=%s with following drives: %s"
                     % (fs, " ".join(drives)))

            if not assume_created:
                fs.create()
            else:
                lgr.info("Not creating FS since asked not to")
            # TODO: move test_descr/test case out of benchmark_fs
            test_descr, protocols = benchmark_fs(fs)
            # TODO: record
            #   - versions of kernel, git, git-annex
            protocols_fname = '%(test_repo)s-%(fs)s.json' % test_descr # -'.join("%s:%s.json" % (k, test_descr[k]) for k in sorted(test_descr))
            protocols_path = os.path.join('test_fs_protocols', protocols_fname)
            dryrun(save_protocols, protocols, protocols_path)
            dryrun("umount %s" % fs.mountpoint)
            # TODO:
            # we should kill it altogether but now we are reusing md so we should stop there

    elif action == 'wipe':
        wipe_drives(drives)
    else:
        raise ValueError(action)


if __name__ == "__main__":
    args = parse_args()
    if args.dry_run:
        dryrun.protocol = DryRunProtocol()
    main(args.action, assume_created=args.assume_created)

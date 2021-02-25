#!/usr/bin/env python3

import os
import os.path as op
import sys
import subprocess

if __name__ == '__main__':
    cmd = sys.argv[1]
    extra = sys.argv[2:]
    for path in os.environ['PATH'].split(os.pathsep):
        for ext in '', '.exe', '.bat', '.com':
            exe = op.join(path, cmd + ext)
            # print(exe)
            if op.lexists(exe):
                if extra:
                    r = subprocess.run([exe] + extra, capture_output=True, check=True)
                    print(exe, r.returncode == 0 and "ok" or "failed")
                    for o in "stdout", "stderr":
                        out = getattr(r, o)
                        if out:
                            print(f'{o}:')
                            print(out.decode())
                else:
                    print(exe)

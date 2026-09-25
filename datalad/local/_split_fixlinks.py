"""git filter-branch --index-filter helper for `datalad split`

Usage: python _split_fixlinks.py N

Strips N leading '../' from the targets of git-annex symlinks in the index,
so they remain valid once files moved N directories up. Deliberately kept
free of datalad imports: it runs once per rewritten commit.
"""
import os
import subprocess
import sys
import tempfile


def git(*args, input=None):
    return subprocess.run(('git',) + args, input=input, check=True,
                          stdout=subprocess.PIPE).stdout


def main(depth):
    prefix = b'../' * depth
    links = []  # (blob sha, path)
    for entry in git('ls-files', '-s', '-z').split(b'\0'):
        if entry.startswith(b'120000 '):
            meta, path = entry.split(b'\t', 1)
            links.append((meta.split()[1], path))
    if not links:
        return
    out = git('cat-file', '--batch',
              input=b''.join(sha + b'\n' for sha, _ in links))
    fixed = []  # (path, new target)
    pos = 0
    for _, path in links:
        nl = out.index(b'\n', pos)
        size = int(out[pos:nl].split()[2])
        target = out[nl + 1:nl + 1 + size]
        pos = nl + 1 + size + 1
        if target.startswith(prefix) and b'.git/annex/objects/' in target:
            fixed.append((path, target[len(prefix):]))
    if not fixed:
        return
    with tempfile.TemporaryDirectory() as tmp:
        names = []
        for i, (_, target) in enumerate(fixed):
            names.append(os.path.join(tmp, str(i)))
            with open(names[-1], 'wb') as f:
                f.write(target)
        shas = git('hash-object', '-w', '--no-filters', '--stdin-paths',
                   input='\n'.join(names).encode()).split()
    git('update-index', '-z', '--index-info', input=b''.join(
        b'120000 ' + sha + b'\t' + path + b'\0'
        for sha, (path, _) in zip(shas, fixed)))


if __name__ == '__main__':
    main(int(sys.argv[1]))

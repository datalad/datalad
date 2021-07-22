"""
Helper to provide heavy load on stdout and stderr
"""
import sys

if __name__ == "__main__":
    x = str(list(range(1000))) + '\n'
    for i in range(100):
        s = "%d " % i + x
        sys.stdout.writelines(s)
        sys.stderr.writelines(s)

"""
Helper to provide heavy load on stdout and stderr
"""
import sys

if __name__ == "__main__":
    x = str(list(range(1000))) + '\n'
    [(sys.stdout.writelines(x), sys.stderr.writelines(x)) for i in range(100)]

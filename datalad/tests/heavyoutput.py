"""
Helper to provide heavy load on stdout and stderr
"""
import sys

x = str(list(range(1000))) + '\n'
[(sys.stdout.writelines(x), sys.stderr.writelines(x)) for i in xrange(100)]

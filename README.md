# DataLad

DataLad aims to deliver a data distribution.  Original motive was to provide
a platform for harvesting data from online portals and
exposing collected data in a readily-usable form from [Git-annex]
repositories, while fetching data load from the original data providers.

# Status

It is currently in a "prototype" state, i.e. **a mess**. It is functional for
many use-cases but not widely used since its organization and configuration will
be a subject for a considerable reorganization and standardization.  Primary
purpose of the development is to catch major use-cases and try to address them
to get a better understanding of the ultimate specs and design.

# Tests

Unfortunately there is not that much of unittests, but there are few
"functionality" tests aiming to address main use-cases.

# Dependencies

On Debian-based systems:

```sh
apt-get install patool python-bs4 python-git python-joblib git-annex
```

# License

MIT/Expat

# Disclaimer

It is in a prototype stage -- **nothing** is set in stone yet -- but
already usable in a limited scope.

[Git-annex]: http://git-annex.branchable.com

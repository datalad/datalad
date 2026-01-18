### 🚀 Enhancements and New Features

- DataLad now provides a pytest plugin that automatically registers custom markers and pytest configuration for DataLad extensions. Extensions no longer need to duplicate 31 marker definitions and pytest configuration in their tox.ini files. The plugin is automatically discovered when datalad is installed, making it easier for extensions to inherit consistent test configuration. (by [@yarikoptic](https://github.com/yarikoptic))

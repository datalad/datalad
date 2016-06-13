from datalad.tests.utils import skip_if_no_module
skip_if_no_module('scrapy')

from datalad.tests.utils import skip_if_scrapy_without_selector
skip_if_scrapy_without_selector()

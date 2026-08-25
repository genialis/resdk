======================
Resolwe SDK for Python
======================

|build| |build-e2e| |coverage| |pypi_version| |pypi_pyversions|

.. |build| image:: https://github.com/genialis/resolwe-bio-py/workflows/ReSDK%20CI/badge.svg?branch=master
    :target: https://github.com/genialis/resolwe-bio-py/actions?query=branch%3Amaster
    :alt: Build Status

.. |build-e2e| image:: https://public.ci.genialis.io/buildStatus/icon/resolwe-bio-py/master
    :target: https://ci.genialis.io/blue/organizations/jenkins/resolwe-bio-py/activity
    :alt: Build (End-to-End) Status

.. |coverage| image:: https://img.shields.io/codecov/c/github/genialis/resolwe-bio-py/master.svg
    :target: http://codecov.io/github/genialis/resolwe-bio-py?branch=master
    :alt: Coverage Status

.. |pypi_version| image:: https://img.shields.io/pypi/v/resdk.svg
    :target: https://pypi.python.org/pypi/resdk
    :alt: Version on PyPI

.. |pypi_pyversions| image:: https://img.shields.io/pypi/pyversions/resdk.svg
    :target: https://pypi.python.org/pypi/resdk
    :alt: Supported Python versions

.. |pypi_downloads| image:: https://img.shields.io/pypi/dm/resdk.svg
    :target: https://pypi.python.org/pypi/resdk
    :alt: Number of downloads from PyPI

Resolwe SDK for Python supports interaction with Resolwe_ server
and its extension `Resolwe Bioinformatics`_. You can use it to upload
and inspect biomedical data sets, contribute annotations, run
analysis, and write pipelines.

.. _Resolwe Bioinformatics: https://github.com/genialis/resolwe-bio
.. _Resolwe: https://github.com/genialis/resolwe

Docs & Help
===========

Read the detailed description in documentation_.

.. _documentation: https://docs.genialis.com/resdk/

Install
=======

Install from PyPI::

  pip install resdk

If you would like to contribute to the SDK codebase, follow the
`installation steps for developers`_.

.. note::

  If you are using Apple silicon you should use Python version 3.10 or higher.

.. _installation steps for developers: https://docs.genialis.com/resdk/contributing.html

Quick Start
===========

In this showcase we will download the aligned reads and their
index (BAM and BAI) from the server:

.. code-block:: python

   import resdk

   # Create a Resolwe object to interact with the server
   res = resdk.Resolwe(url='https://app.genialis.com')

   # Enable verbose logging to standard output
   resdk.start_logging()

   # Get sample meta-data from the server
   sample = res.sample.get('resdk-example')

   # Download files associated with the sample
   sample.download()

Both files (BAM and BAI) have downloaded to the working directory.
Check them out. To learn more about the Resolwe SDK continue with
`Getting started`_.

.. _Getting started: https://docs.genialis.com/resdk/tutorials.html

If you do not have access to the Resolwe server, contact us at
info@genialis.com.

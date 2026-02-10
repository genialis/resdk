##########
Change Log
##########

All notable changes to this project are documented in this file.

===================
22.2.2 - 2026-02-10
===================

Added
-----
- Add support for ``Python 3.14``

Fixed
-----
- Fix a bug that prevented the downloading and renaming of
  a directory from a data object
- Fix anonymous user login so it does not require interactive 
  credential input


===================
22.2.1 - 2025-11-19
===================

Fixed
-----
- Fix bug in ``get_or_run`` method
- Fix a bug in ``QCTables`` where the removal of sample name suffixes
  in MultiQC ``.txt`` files leads to incorrect parsing of MACS prepeak tables
- Rewrite ``Collection`` shortcuts to use new syntax
- Fix a bug that caused crash when saving ``Relation`` resource


===================
22.2.0 - 2025-07-02
===================

Added
-----
- Add variant related objects
- Add ``prediction_group`` to ``Resolwe`` object
- Add ``PredictionPreset`` resource
- Allow managing prediction and annotation fields associated to a collection

Fixed
-----
- AnnotationValue must be ordered by the ``created`` instead of ``modified``
  field


===================
22.1.0 - 2025-04-14
===================

Fixed
-----
- Fix a bug in QCTables caused by an orphan Data


===================
22.0.0 - 2025-03-28
===================

Added
-----
- Add an argument for custom file naming of downloaded files
  and propagate this change in ``Data`` resource
- Add support for predictions
- Add version to annotation field
- Add a resolwe method for fetching the server module versions
- Add support for ``Python 3.13``
- Add ``QCTables`` class to the ``tables`` module

Changed
-------
- Drop support for ``Python 3.8``
- Propagate the option of showing the progress bar in the download method

Fixed
-----
- Fix multi-file download stopped after downolading html file
- Modify ``clear_cache`` method of ``BaseTables`` to clear only the
  cache of the specified collection
- Add ``inputs`` field to ``PredictionField`` resource
- Allow updating ``PredictionField`` resource

Changed
-------
- Change ``_resource_setter`` to work with list of resources
- Fix ``QCTables`` class to work with the new version of MultiQC
  and ensure that legacy reports are still supported


===================
21.2.1 - 2024-10-08
===================

Fixed
-----
- Fix fetching ``qc`` data from deploys with local data storage


===================
21.2.0 - 2024-07-10
===================

Changed
-------
- Remove ``RNA-SeQC`` metrics from ``RNATables`` QC fields

Added
-----
- Add ``restart`` method to the ``Data`` resource

Fixed
-----
- Fix fetching ``RNATables`` for collections with missing MultiQC objects by
  using nullable integer data type ``Int64`` for integer columns.
- Fix ``VariantTables`` to correctly handle multiallelic variants


===================
21.1.0 - 2023-02-09
===================

Added
-----
- Optionally show progress bar when downloading files
- Optionally show progress bar when uploading files
- Add ``modified`` as read-only field to the ``AnnotationValue`` resource
- Add md5 checksum after file is downloaded
- Add support for Python3.12

Fixed
-----
- Invalidate cache in resdk tables on AnnotationValue updates


===================
21.0.0 - 2023-01-15
===================

Changed
-------
- **BACKWARD INCOMPATIBLE:** Remove ``inherit_collection`` parameter in
  ``Data.duplicate()`` and ``Sample.duplicate()``
- Minimal supported version is checked when connection to the server is
  established and warning is printed on mismatch
- ``RNATables.build`` now emits warning instead of error in case there are
  multiple different builds in the same collection
- Return more descriptive error message when setting a single annotation value
  on a sample and the annotation field does not exist

Added
-----
- Add ``set_annotations`` on ``Sample`` resource to allow bulk annotation
  update
- Add ``get_annotations`` on ``Sample`` which returns all annotations on a
  sample as a dictionary

Fixed
-----
- Fix downloading tables data
- Fix download stopped with incomplete data received: urllib3 version 2.0 has
  ``enforce_content_length`` set to ``True`` by default which raises error
  if not enough data was received
- Require ``urllib`` version ``2.0`` or higher only for ``Python 3.10+`` due to
  compatibility issues with ``Python 3.9`` or lower


===================
20.0.0 - 2023-10-27
===================

Changed
-------
- **BACKWARD INCOMPATIBLE:** Remove ``update_descriptor`` method from the
  ``Sample`` resource
- Extend the list of supported QC fields in ``RNATables``
  to accommodate assigned reads by STAR quantification
- Extend the list of supported QC fields in ``RNATables``
  to accommodate metrics reported by RNA-SeQC
- Warn user in case ``resdk.tables.RNATables.readable_columns`` cannot find
  mappings for all genes.
- Add annotation models


===================
19.0.1 - 2023-08-22
===================

Changed
-------
- Update documentation for interactive user login


===================
19.0.0 - 2023-08-22
===================

Added
-----
- Add support for ``Python 3.11``
- Drop support for ``Python 3.7``

Changed
-------
- Change login to use the new SAML authentication method
- Fix `aiohttp` version to 3.8

Fixed
-----
- Fix ``RNATables`` in case of very large collection


===================
18.0.0 - 2023-05-18
===================

Fixed
-----
- Fix ``delete`` endpoint can return background task object


===================
17.0.0 - 2023-04-24
===================

Added
-----
- Add ``build`` property to ``RNATables``.
- Optionally show progress bar in ``resdk.Query.iterate()``
- Add ``build`` info to ``RNATables.rc.attrs`` and ``RNATables.exp.attrs``

Changed
-------
- Add deprecation warning to the following methods:

  - ``Sample.get_reads``
  - ``Sample.get_bam``
  - ``Sample.get_primary_bam``
  - ``Sample.get_macs``
  - ``Sample.get_cuffquant``
  - ``Sample.get_expression``

- Rework ``VariantTables``:

  - Index in VariantTables.variants is simplified and does not include
    ammino-acid change anymore.
  - Argument ``mutations`` in ``VariantTables`` constructor is renamed to
    ``geneset``. Besides holding a list fo genes, this can also be a valid ID /
    slug for Geneset object on Genialis Platform.

Fixed
-----
- Fix ``Sample.get_reads()`` utility method
- Fix ``duplicate`` endpoint now returns background task object
- The data endpoint serializes ``collection`` information only on the top level, the
  ``collection`` entry  inside ``entity`` is now a collection primary key
- Fix ReSDK tables in case of local server storage


===================
16.0.0 - 2022-10-19
===================

Added
-----
- Support setting billing account on ``Collection`` resource
- Support setting ``descriptor`` and ``DescriptorSchema`` on ``Relation``
  resource

Changed
-------
- **BACKWARD INCOMPATIBLE:** Deprecate ``resdk.tables.RNATables.id_to_symbol``
  attribute.

Fixed
-----
- Fix ``ResolweQuery`` to also accept Resource objects as query parameters,
  not just their ID's
- Upload to ``S3`` bucket failing in ``Windows`` due to use of backslash in the
  destination path


===================
15.0.0 - 2022-06-06
===================

Added
-----
- Support upload directly to S3 bucket
- Add support for ``Python3.9``, ``Python3.10`` and drop support for
  ``Python3.6``
- Add ``resdk.tables.VariantTables`` class to handle variant data
- Add ``resdk.tables.MLTables`` class to handle ML-ready data

Fixed
-----
- Fix parsing of new metadata format in ``resdk.tables.BaseTables.meta``

Changed
-------
- ``Metadata.set_index(df)`` add column if sample name / slug is in ``df`` index


===================
14.1.0 - 2022-03-25
===================

Added
-----
- Add ``Metadata`` resource

Fixed
-----
- Fix the way ``RNATables`` are imported in the docs


===================
14.0.0 - 2022-01-19
===================

Changed
-------
- Deprecate ``resdk.CollectionTables``, use ``resdk.tables.RNATables`` instead
- Update ``resdk.resourcec.kb.Feature.query_endpoint`` to sync with change in
  Resolwe-bio
- Deprecate the following methods for setting permissions:

  - ``add_public()`` and ``remove_public()``
  - ``add_user()`` and ``remove_user()``
  - ``add_group()`` and ``remove_group()``


===================
13.8.0 - 2021-12-07
===================

Added
-----
- Support retrieval of QC values in ReSDK tables via ``qc`` attribute
- Add ``resdk.tables.MATables`` for microarray data support

Changed
-------
- In ResdkTables, warn user if multiple Data of same
  ``ResdkTables.process_type`` are in one sample. If they are, use
  only the newest one.


===================
13.7.0 - 2021-11-17
===================

Added
-----
- Enable setting ``process_resources`` as an attribute on ``Data`` as
  well as on input to method ``run``. This makes it possible to raise
  process resources (cores, memory, storage) beyond what is specified in
  the process definition.

Changed
-------
- Sync with permission changes in Resolwe. This introduces new methods
  for setting permissions::

  - ``add_public()`` and ``remove_public()`` are replaced by ``set_public()``
  - ``add_user()`` and ``remove_user()`` are replaced by ``set_user()``
  - ``add_group()`` and ``remove_group()`` are replaced by ``set_group()``

  For details about their usage see function docs. Old methods still
  work and will be kept until Q1 2022 but they will raise a deprecation
  warning.
- Index of ``resdk.tables`` is now based on sample ID rather than on sample
  name. To ease the naming ``readable_index`` property is added - it maps
  sample ID's to sample names.


===================
13.6.0 - 2021-10-20
===================

Changed
-------
- Sync permissions handling with backend changes. This means that
  setting permissions will only be possible with this version of ReSDK
  (or higher) as of 2021-10-20.

Fixed
-----
- Fix ReSDK Tables caching: loading of cached tables fails in resdk
  ``13.5.1``


===================
13.5.1 - 2021-09-16
===================

Fixed
-----
- Fix ReSDK Tables so they can cache also very large collections
  (greater than 4Gb in memory)


===================
13.5.0 - 2021-09-13
===================

Added
-----
- ``CollectionTables`` functionality is now generalized to also
  accommodate different types of data: RNA and methylation. Calling
  ``CollectionTables`` remains backwards compatible, but will issue a
  deprecation warning. Users are encouraged to use new modules as

    - resdk.tables.RNATables
    - resdk.tables.MethylationTables

Changed
-------
- ``CollectionTables`` is now faster in merging expressions, especially
  if there are different sets of genes in different samples
- Return ``Genset.genes`` as sorted list instead of set


===================
13.4.0 - 2021-08-12
===================

Added
-----
- Add ``Geneset`` resource. This should significantly simplify the
  manipulation of genesets.

Changed
-------
- Replace Travis CI with GitHub actions

Fixed
-----
- Fix mismatched meta and expression data index


===================
13.3.0 - 2021-05-18
===================

Added
-----
- Add ``progress_callable`` argument to ``CollectionTables`` constructor. This
  enables that progress of expressions download is reported to any callable
- Add check that prevents crating ``CollectionTables`` with heterogeneous
  collections
- Add ``expression_source`` and ``expression_process_slug`` filters to
  ``CollectionTables`` constructor. This enables to use just a specific,
  homogeneous part of the collection


===================
13.2.0 - 2021-05-03
===================

Changed
-------
- Faster download of files in ``CollectionTables.rc`` and
  ``CollectionTables.exp`` by using async download
- Setting permissions on Sample / Collection will also propagate them
  to all included Data / Samples

Fixed
-----
- Fix some minor inconsistencies in docs
- Fix and strengthen e2e tests


===================
13.1.0 - 2021-03-17
===================

Added
-----
- Add knowledge base docs
- Add ``CollectionTables`` docs
- Additional metadata in ``CollectionTables.meta`:

  - Sample relations
  - Orange clinical metadata


===================
13.0.0 - 2020-12-17
===================

Changed
-----
- **BACKWARD INCOMPATIBLE:** Update API and add performance
  enhancements for ``CollectionTables``


===================
12.4.0 - 2020-11-23
===================

Added
-----
- Add docs on how to prepare a release
- Add ``CollectionTables`` class to ease access to expressions and
  metadata of a given collection


===================
12.3.0 - 2020-10-29
===================

Added
-----
- Support login with email

Fixed
-----
- Fix broken sample assignment in ``Data`` resource
- Fix authentication when downloading directory or stdout


===================
12.2.0 - 2020-09-15
===================

Added
-----
- Add ``<dst>.permissions.copy_from(<src>)`` method that copies permissions
  from ``<src>`` to ``<dst>`` resource. e.g. To copy permissions from
  Sample ``s1`` to Sample ``s2``: ``s2.permissions.copy_from(s1)``


===================
12.1.1 - 2020-05-21
===================

Fixed
-----
- Add cookies to request on redirect


===================
12.1.0 - 2020-05-18
===================

Added
-----
- Add support for Python 3.8
- Add attributes ``owners``, ``editors`` and ``viewers`` to
  ``PermissionsManager``. For example, one can now see who are owners of
  Collection ``c1`` with ``c1.permissions.owners``
- Add ``iterate`` method to ``ResolweQuery``. This solves the
  ``504 Gateway Time-out`` when one wants to fetch all (or hundreds)
  objects from server.
- Support collection inheritance in ``Data.duplicate()``

Fixed
-----
- Fix date format for filtering with ``created__gt`` / ``created__lt``
  in tutorial script


===================
12.0.0 - 2019-11-19
===================

Changed
-------
* **BACKWARD INCOMPATIBLE:** Remove ``Sample.descriptor_completed`` attribute
  and start deprecation procedure for ``Sample.confirm_is_annotated`` method
* **BACKWARD INCOMPATIBLE:** Remove ``add`` and ``download`` permission to
  sync with changes in Resolwe

Added
-----
- Add duplicate method to collection, sample and data resources

Fix
---
* Fix documentation for ``Resolwe.run`` ``collection`` parameter


===================
11.0.1 - 2019-08-19
===================

Fix
---
* Fix ``ResolweQuery.get`` method. This fix handles the case when object is
  not uniquely defined by ``slug`` (but it is with ``slug`` and ``version``)


===================
11.0.0 - 2019-08-14
===================

Changed
-------
* **BACKWARD INCOMPATIBLE:** Remove scripts folder. This removes
  ``resolwe-upload-reads`` command line utility.
* **BACKWARD INCOMPATIBLE:** Remove analysis folder. This removes many
  methods that could be run on multiple resources::

    - ``bamsplit``, ``macs``, ``rose2``
    - ``cuffdiff``
    - ``cuffquant``, ``cuffnorm``
    - ``bamplot``, ``bamliquidator``
    - ``prepare_geo``, ``prepare_geo_chipseq``, ``prepare_geo_rnaseq``

  These methods are not needed anymore as most of the functionality that
  they provide can be handled by relations in UI.
* **BACKWARD INCOMPATIBLE:** The following utilty functions were removed as
  they were not used anymore: ``find_field``, ``get_samples``,
  ``get_resource_collection`` and ``get_resolwe``
* **BACKWARD INCOMPATIBLE:** Resolwe server now enforces that Data can
  only be in one sample and one collection. Sample can only be in one
  collection as well. This implies the following changes:

  - Before, ``Data``/``Sample`` was added/removed to ``Sample``/``Collection``
    through ``add_data``, ``remove_data``, ``add_samples`` and
    ``remove_samples`` methods. These are removed. From now on, ``Data``
    resource has writable attributes ``collection`` and ``sample`` and Sample
    resource has ``collection`` attribute. Adding ``Data`` to ``Collection``
    is as simple as ``Data.collection = <Collection instance>`` and than
    ``Data.save()``
  - Method ``delete()`` on Samples and Collections does not accept
    ``delete_content`` parameter anymore. From now, when Collection or Sample
    is deleted, all of it's content is deleted automatically.
  - Resolwe.run method now has ``collection`` argument instead of
    ``collections``. This argument can accept Collection resource or it's id.
* **BACKWARD INCOMPATIBLE:** Data resource now has a ``process``
  attribute, which is an instance of ``Process`` resource. Therefore the
  following Data attributes are removed as they can be acessed through
  Data.process::

  - process_name
  - process_slug
  - process_type
  - process_input_schema
  - process_output_schema

Added
-----
* Add ``fetch_object`` classmethod to ``BaseResource`` class.
* Add ``get_query_by_resource`` method to ``Resolwe`` class. It gives the
  correct ResolweQuerry for a given resource class/instance.


===================
10.1.0 - 2019-07-18
===================

Changed
-------
* Sync ``Data.parents`` and ``Data.children`` with backend changes

Fix
---
* Replace obsolete workflow in tutorial with a newer one
* Remove Python 2 references from docs


===================
10.0.0 - 2019-05-08
===================

Changed
-------
* **BACKWARD INCOMPATIBLE:** Remove support for Python 2
* Remove tests for old Python3 versions: Python 3.4 and 3.5
* Filtering is now updated with latest changes in Resolwe. A lot of
  inconsistencies are fixed and error messages should be more clear now.

Added
-----
* Add ``delete_content`` parameter to ``Collection.delete()`` and
  ``Sample.delete()`` methods. This not only deletes given
  Samples / Collections but also contained Data / Samples.
* Add support for Python 3.7
* In addition to data and sample statistics ``Resolwe.data_usage`` method
  now also reports collection statistics.


==================
9.0.0 - 2019-02-19
==================

Changed
-------
* **BACKWARD INCOMPATIBLE:** Remove unused ``ResolweQuery.post`` method
* Make contributor attribute a User object
* Cast date-time attributes to datetime objects. This means, for example,
  that ``created`` attribute is now Python datetime object instead of string.
* Update prepare_geo_chipseq analysis to reflect process chnages

Added
-----
* Implement full text search method in ``ResolweQuery`` for ``Data``,
  ``Sample`` and ``Collection`` resources
* Support ``delete_content`` parameter in ``delete()`` method for Samples and
  Collections. This enables one to also delete all of the Data / Samples
  in a given Sample / Collection


==================
8.0.0 - 2018-11-20
==================

Changed
-------
* **BACKWARD INCOMPATIBLE:** Rename argument ``file_type`` to ``field_name``
  in ``BaseCollection.download`` method
* **BACKWARD INCOMPATIBLE:** Remove ``Data.annotation`` attribute

Added
-----
* Add missing resource classes in the Reference section of documentation
* Add ``Resolwe.data_usage`` method. It displays number of samples, data
  objects and sum of data object sizes for currently logged-in user. For admin
  users, it displays data for all users.
* Add the support for using ``file`` and ``file_temp`` dictionary syntax
  when uploading remote (URL, FTP) files in Resolwe upload processes

Fixed
-----
* Handle samples with multiple ``fastq`` objects in ``get_reads`` method. By
  default the latest of all data whose ``process_type`` starts with
  ``data:reads:fastq`` is returned. If any other of the ``fastq`` objects is
  required, user can provide additional ``filter`` arguments and limits search
  to one result.
* Recreate resource queries (e.g. ``Resolwe.data``, ``Resolwe.relation``, ...)
  at each login. Previously it could happen that e.g. ``Resolwe.data`` listed
  only public data while ``Resolwe.data.all()`` displayed all objects with
  view permission. This behaviour is now unified: user can see all objects for
  which he has view permission.


==================
7.0.0 - 2018-10-15
==================

Changed
-------
* **BACKWARD INCOMPATIBLE:** Remove ``sequp`` script
* **BACKWARD INCOMPATIBLE:** Remove ``data_upload`` directory
* **BACKWARD INCOMPATIBLE:** Remove ``replicates`` input in ``cuffnorm``
  analysis
* Move ``tags`` attribute from ``Sample`` to ``BaseCollection``
* Major refactoring of documentation tutorials, including automatic testing
  of tutorial scripts

Added
-----
* Add ``add_users`` and ``remove_users`` method to Group resource
* Add ``is_active`` field to ``Process`` resource
* Add ``parents`` and ``children`` property to ``Data``
* Add url validation in ``Resolwe`` constructor


==================
6.0.0 - 2018-09-20
==================

Changed
-------
* **BACKWARD INCOMPATIBLE:** Disable writing processes from ReSDK
* **BACKWARD INCOMPATIBLE:** Remove ``print_annotation`` methods
* **BACKWARD INCOMPATIBLE:** Remove collection methods ``import_relations`` and
  ``export_relations`` that were used to bulk import/export relations
* **BACKWARD INCOMPATIBLE:** Modify ``Relation`` class to reflect changes in
  ``Resolwe``
* Add ``login()`` method that enables to enter your credentials interactively.
  This prevents others from seeing your password in terminal history.
* Support inputs of type ``list`` in ``get_resource_collection``

Added
-----
* Add many missing fields to SDK resource classes
* Add ``relations`` property to ``Sample``
* Add ``background`` and ``is_background`` property to ``Sample``

Fixed
-----
* Fix filtering in cases where query parameter is a list


==================
5.0.0 - 2018-08-13
==================

Changed
-------
* **BACKWARD INCOMPATIBLE:** Remove ``threads`` parameter from
  ``cuffdiff`` helper function

Added
-----
* Enable direct comparison of two objects
* Add ``prepare_geo_chipseq``, ``prepare_geo_rnaseq`` and
  ``prepare_geo`` helper functions
* Add ``bamsplit`` helper function
* Add ``annotate`` and ``export_annotation`` functions for collections
* Add ``upload_reads`` and ``upload_demulti`` functions for collections

Fixed
-----
* Make ``genome`` input work in ``cuffdiff`` helper function
* Increase chunk size in ``Data.stdout`` method. This significantly increases
  the speed in case of a large stdout file.


==================
4.0.0 - 2018-04-18
==================

Changed
-------
* **BACKWARD INCOMPATIBLE:** Make ReSDK compatible with Resolwe 8.x:

  - remove trailing colons in Data filters by types
  - change filters by ``sample`` to ``entity`` before making the request to
    the backend
* **BACKWARD INCOMPATIBLE:** Change parameter ``email`` to ``username`` in
  Resolwe constructor


==================
3.0.0 - 2018-02-21
==================

Added
-----
* Add ``get_primary_bam`` utility function

Changed
-------
* **BACKWARD INCOMPATIBLE:** Update cuffquant ``gff`` input to
  ``annotation`` in helper and test functions
* **BACKWARD INCOMPATIBLE:** Remove ``update_knowledge_base`` script
* Change ``macs14`` helper function to work on unannotated samples
* Update contributing, start, and differential expression tutorial docs
* Support primary bam files in ``macs`` helper function
* Update and reorganize uploads and annotations tutorial doc
* Update resources and advanced queries tutorial doc

Fixed
-----
* Fix register in ``<resolwe>.run`` function to work with processes
  (referended in ``src`` attribute) with no output field
* Make ``Data.annotation`` an instance attribute instead of class
  attribute
* Fix ``get_*`` calls in tests by including species and build inputs
* Remove invalid collection assignments in ``get_*`` calls


==================
2.0.0 - 2017-09-11
==================

Added
-----
* ``User`` and ``Group`` resources
* ``DescriptorSchema`` resource
* Support for permissions management on resolwe resources

Changed
-------
* **BACKWARD INCOMPATIBLE:** Remove ``id`` and ``slug`` parameters from
  init functions of resources. Query object should be used instead, i.e.
  ``<resolwe>.<resource>.get(...)``

Fixed
-----
* Fix ``Relation`` resource to work if ``entities`` attribute is set to
  ``None``
* Fixed resource representations to correctly handle non-english letters
  in Python 2


===================
1.10.0 - 2017-09-11
===================

Changed
-----
* Remove ``threads`` parameter from ``cuffquant`` and ``cuffnorm``
  helper functions

Fixed
-----
* Fix delete functionality for non-boolean ``force`` parameter types


==================
1.9.0 - 2017-08-07
==================

Added
-----
* Add all parameters to bowtie2 helper function
* Raise more descriptive error if sample is not annotated in macs
  function

Changed
-------
* Use values instead of abbreviations for genome sizes in chip_seq
* Utility functions return only one element instead of list when thay
  are run on a ``Data`` object
* Refactor documentation structure and add a tutorials section


==================
1.8.3 - 2017-06-09
==================

Added
-----
* Add cuffdiff helper function
* Support data as a resource for bowtie2 and hisat2 helper functions

Fixed
-----
* Fix adding samples to relations with ``<collection>.import_relations``
  function


==================
1.8.2 - 2017-05-22
==================

Changed
-----
* Remove labels input from cuffnorm


==================
1.8.1 - 2017-04-23
==================

Added
-----
* Support ``tags`` in ``Sample`` and ``Data`` resources
* Support running macs on more organisms (`drosophila melanogaster`,
  `caenorhabditis elegans` and `rattus norvegicus`)
* Automatically run E2E tests on Genialis' Jenkins
* Utility function for running bamliquidator process

Changed
-------
* Update E2E tests
* ``rose2`` and ``macs`` functions fail if they are run on a single
  sample with ``use_background=True`` and there is no background for
  that sample
* ``create_*_relation`` functions return created relation
* Add ``RN4`` and ``RN6`` as valid genomes to ``bamplot`` function
* Add ``MM8``, ``RN4`` and ``RN6`` genomes as valid to ``rose2``
  function

Fixed
-----
* Samples in relations are sorted in the same order as positions


==================
1.8.0 - 2017-03-30
==================

Added
-----
* Support relations endpoint
* Analysis functions for running ``bowtie2`` and ``hisat2`` aligners

Changed
-------
* Move ``run_*`` functions to separate ``resdk.analysis`` module

Fixed
-----
* Latest API returns process version in string instead of integer
* Fix ``run_macs`` function to use up-to-date descriptor schema


==================
1.7.0 - 2017-02-20
==================

Added
-----
* Option to set API url with ``RESOLWE_HOST_URL`` environment varaible

Added
-----
* ``count``, ``delete`` and ``create`` methods to query
* Support downloading ``basic:dir:`` fields

Changed
-------
* Remove ``presample`` endpoint, as it doesn't exist in resolwe anymore
* Update the way to mark ``sample`` as annotated
* Add confirmation before deleting an object

Fixed
-----
* Fix related queries (i.e. ``collection.data``, ``collection.samples``...)
  for newly created objects and raise error if they are accessed before object
  is saved


==================
1.6.4 - 2017-02-17
==================

Fixed
-----
* Use ``process`` resource to get process in ``run`` function


==================
1.6.3 - 2017-02-06
==================

Added
-----
* Add extra parameters to ``run_cuffquant`` function


==================
1.6.2 - 2017-01-24
==================

Added
-----
* Queries support paginated responses
* ``run_cuffnorm`` utility function to the ``Resolwe`` object
* ``run_cuffquant`` utility function to the ``Sample`` object


==================
1.6.1 - 2017-01-11
==================

Fixed
-----
* Use right function to get bed files in ``run_rose2`` function
* Return None if background slug is not given and ``fail_silently``
  is ``True``

==================
1.6.0 - 2017-01-11
==================

Added
-----
* ``get_bam``, ``get_macs``, ``run_rose2`` and ``run_macs`` utility
  functions in ``Sample`` class
* ``run_bamplot`` utility function in ``Resolwe`` class

==================
1.5.2 - 2016-12-22
==================

Added
-----
* Support ``RESOLWE_API_HOST``, ``RESOLWE_API_USERNAME`` and
  ``RESOLWE_API_PASSWORD`` environmental variables


==================
1.5.1 - 2016-12-20
==================

Added
-----
* Knowledge base feature mapping lookup

Changed
-------
* Polish documentation style
* Improve handling of server errors

Fixed
-----
* Remove file logger


==================
1.5.0 - 2016-11-07
==================

Added
-----
* ``get_or_run`` method to ``Resolwe`` class to return matching
  object if already exists, otherwise create it
* ``add_samples`` and ``remove_samples`` methods to ``collection``
  resource
* ``samples`` attribute to ``collection`` resource
* ``collections`` attribute to ``data`` and ``sample`` resources

Changed
-------
* Include all necessary files for running the tests in source distribution
* Exclude tests from built/installed version of the package
* File field passed to ``run`` function can be url address
* Connect to a local server as public user by default

Fixed
-----
* Fix ``files`` and ``download`` methods in ``collection`` resource to
  work with hydrated list of Data objects
* ``inputs`` and ``collections`` are automatically dehydrated if whole
  objects are passed to ``run`` function
* Set chunk size for uploading files to 8MB
* Original value of ``input`` parameter is kept when running ``run``
  funtion
* Clear cache when updating resources
* Queryes become lazy and composable


==================
1.4.0 - 2016-10-19
==================

Added
-----
* ``sample`` and ``presample`` properties to ``data`` resource
* ``add_data`` and ``remove_data`` methods on collection and sample
  resource for adding data objects to them

Changed
-------
* Auto-add 'output' prefix to ``field_name`` parameter for
  downloading files
* Auto-wrapp ``list:*`` fields into list if they are not already
* Data objects in ``data`` field on collection resource are
  automatically hydrated
* ``data`` attribute on collection/sample resource is now read
  only

Fixed
-----
* Fix the descriptor to match the updated sample and reads descriptor schemas


==================
1.3.7 - 2016-10-05
==================

Added
-----
* Check PEP 8 and PEP 257
* Feature resource and resolwe-update-kb script
* Remove resources with the delete() method
* Create and update resources with the save() method
* Validate read only and update protected fields

Changed
-------
* Remove resolwe-upload-reads-batch script
* Add option to enable logger (verbose reporting) in scripts

Fixed
-----
* Fix resolwe-upload-reads script
* Rename ResolweQuerry to ResolweQuery
* Add missing HTTP referer header


==================
1.3.6 - 2016-08-15
==================

Fixed
-----
* Fix descriptor in the sequp script


==================
1.3.5 - 2016-08-04
==================

Changed
-------
* Improved documentation organization and text


==================
1.3.4 - 2016-08-01
==================

Added
-----
* Support logging
* Add process resource
* Docs: Getting started and writing pipelines
* Add unit tests for almost all modules of the package
* Support ``list:basic:file:`` field
* Support managing Samples on presample endpoint

Changed
-------
* Track test coverage with Codecov
* Modify scripts.py to work with added features


==================
1.3.3 - 2016-05-18
==================

Fixed
-----
* Fix docs examples
* Fix error handling in ID/slug resource query


==================
1.3.2 - 2016-05-17
==================

Fixed
-----
* Fix docs use case


==================
1.3.1 - 2016-05-16
==================

Added
-----
* Writing processes docs

Changed
-------
* Rename ``upload`` method to ``run`` and refactor to run any process
* Move ``downlad`` method from ``resolwe.py`` to ``resource/base.py``


==================
1.3.0 - 2016-05-10
==================

Added
-----
* Endpoints ``data``, ``sample`` and ``collections`` in ``Resolwe`` class
* ``ResolweQuery`` class with ``get`` and ``filter`` methods
* ``Sample`` class with ``files`` and ``download`` methods
* Tox configuration for running tests
* Travis configuration for automated testing

Changed
-------
* Rename resolwe_api to resdk
* Add ``data``, ``sample``, ``collections`` to ``Resolwe`` class and create
  ``ResolweQuery`` class
* Move ``data.py``, ``collections.py`` ... to ``resources`` folder
* Remove ``collection``, ``collection_data`` and ``data`` methods from
  ``Resolwe`` and from tests.

Fixed
-----
* ``Sequp`` for paired-end data
* Pylint & PEP8 formatting
* Packaging - add missing files and packages


==================
1.2.0 - 2015-11-17
==================

Fixed
-----
* Documentation supports new namespace.
* Scripts support new namespace.


==================
1.1.2 - 2015-05-27
==================

Changed
-------
* Use urllib.urlparse.
* Slumber version bump (>=0.7.1).


==================
1.1.1 - 2015-04-27
==================

Added
-----
* Query data directly.

Changed
-------
* Query projects by slug or ID.

Fixed
-----
* Renamed genapi module in README.
* Renamed some methods for fetching resources.


==================
1.1.0 - 2015-04-27
==================

Changed
-------
* Renamed genesis-genapi to genesis-pyapi.
* Renamed genapi to genesis.
* Refactored API architecture.


==================
1.0.3 - 2015-04-22
==================

Fixed
-----
* Fix not in cache bug at download.


==================
1.0.2 - 2015-04-22
==================

Added
-----
* Universal flag set in setup.cfg.

Changed
-------
* Docs updated to work for recent changes.


==================
1.0.1 - 2015-04-21
==================

Added
-----
* Added label field to annotation.

Fixed
-----
* URL set to dictyexpress.research.bcm.edu by default.
* Id and name attribute are set on init.


==================
1.0.0 - 2015-04-17
==================

Changed
-------
* Upload files in chunks of 10MB.

Fixed
-----
* Create resources fixed for SSL.

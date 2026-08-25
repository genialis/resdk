.. _tutorial-create:

================================
Create, modify and organize data
================================

To begin, we need some sample data to work with. You may use your own reads
(.fastq) files, or download an example set we have provided:

.. literalinclude:: files/tutorial-create.py
   :lines: 2-13

.. note::

  To avoid copy-pasting of the commands, you can
  :download:`download all the code <files/tutorial-create.py>` used in this section.

Organize resources
==================

Before all else, one needs to prepare space for work. In our case, this
means creating a "container" where the produced data will reside. So
let's create a collection and than put some data inside!

.. literalinclude:: files/tutorial-create.py
   :lines: 15-16

Upload files
============

We will upload fastq single end reads with the `upload-fastq-single`_ process.

.. _upload-fastq-single: https://docs.genialis.com/resolwe-bio/catalog-definitions.html#process-upload-fastq-single

.. literalinclude:: files/tutorial-create.py
   :lines: 18-25

What just happened? First, we chose a process to run, using its slug
``upload-fastq-single``. Each process requires some inputs---in this case there
is only one input with name ``src``, which is the location of reads on our
computer. Uploading a fastq file creates a new ``Data`` on the server
containing uploaded reads. Additionally, we ensured that the new
``Data`` is put inside ``test_collection``.

The upload process also created a Sample object for the reads data to be
associated with. You can access it by:

.. literalinclude:: files/tutorial-create.py
   :lines: 27

.. note::

  You can also upload your files by providing url. Just replace path to your
  local files with the url. This comes handy when your files are large and/or
  are stored on a remote server and you don't want to download them to your
  computer just to upload them to Resolwe server again...

Modify data
===========

Both ``Data`` with reads and ``Sample`` are owned by you and you have
permissions to modify them. For example:

.. literalinclude:: files/tutorial-create.py
   :lines: 29-31

Note the ``save()`` part! Without this, the change is only applied locally (on
your computer). But calling ``save()`` also takes care that all changes are
applied on the server.

.. note::

  Some fields cannot (and should not) be changed. For example, you cannot
  modify ``created`` or ``contributor`` fields. You will get an error if you
  try.

Annotate Samples
================

The next thing to do after uploading some data is to annotate samples this data
belongs to. This can be done by assigning a value to a predefined field on a
given sample. See the example below.

Each sample should be assigned a species. This is done by attaching the
``general.species`` field on a sample and assigning it a value, e.g.
``Homo sapiens``.

.. literalinclude:: files/tutorial-create.py
   :lines: 33


Annotation Fields
-----------------

You might be wondering why the example above requires ``general.species`` string
instead of e.g. just ``species``. The answer to this are ``AnnotationField``\ s.
These are predefined *objects* that are available to annotate samples. These
objects primarily have a name, but also other properties. Let's examine some of
those:

.. literalinclude:: files/tutorial-create.py
   :lines: 35-42


.. note::

   Each field is uniquely defined by the combination of ``name`` and ``group``.

If you wish to examine what fields are available, use a query

.. literalinclude:: files/tutorial-create.py
   :lines: 44-46


You may be wondering whether you can create your own fields / groups. The answer
is no. Time has proven that keeping things organized requires the usage
of a selected set of predefined fields. If you absolutely feel that you need an
additional annotation field, let us know or use resources such as :ref:`metadata`.


Annotation Values
-----------------

As mentioned before, fields are only one part of the annotation. The other part
are annotation values, stored as a standalone resource ``AnnotationValues``.
They connect the field with the actual value.

.. literalinclude:: files/tutorial-create.py
   :lines: 48-55


As a shortcut, you can get all the ``AnnotationValue``\ s for a given sample by:

.. literalinclude:: files/tutorial-create.py
   :lines: 57


Helper methods
--------------

Sometimes it is convenient to represent the annotations with the dictionary,
where keys are field names and values are annotation values. You can get all
the annotation for a given sample in this format by calling:

.. literalinclude:: files/tutorial-create.py
   :lines: 58

Multiple annotations stored in the dictionary can be assigned to sample by:

.. literalinclude:: files/tutorial-create.py
   :lines: 59-62

Annotation is deleted from the sample by setting its value to ``None`` when
calling ``set_annotation`` or ``set_annotations`` helper methods. To avoid
confirmation prompt, you can set ``force=True``.

.. literalinclude:: files/tutorial-create.py
   :lines: 63

Run analyses
============

Various bioinformatic processes are available to properly analyze sequencing
data. Many of these pipelines are available via Resolwe SDK, and are listed in
the `Process catalog`_ of the `Resolwe Bioinformatics documentation`_.

.. _Process catalog: https://docs.genialis.com/resolwe-bio/catalog.html
.. _Resolwe Bioinformatics documentation: https://docs.genialis.com/resolwe-bio/

After uploading reads file, the next step is to align reads to a genome. We
will use STAR aligner, which is wrapped in a process with slug
``alignment-star``. Inputs and outputs of this process are described in
`STAR process catalog`_. We will define input files and the process will run
its algorithm that transforms inputs into outputs.

.. _STAR process catalog: https://docs.genialis.com/resolwe-bio/catalog-definitions.html#process-alignment-star

.. literalinclude:: files/tutorial-create.py
   :lines: 67-76

Lets take a closer look to the code above. We defined the alignment process, by
its slug ``'alignment-star'``. For inputs we defined data objects ``reads``
and ``genome``. ``Reads`` object was created with 'upload-fastq-single'
process, while ``genome`` data object was already on the server and we just
used its slug to identify it. The ``alignment-star`` processor will
automatically take the right files from data objects, specified in inputs and
create output files: ``bam`` alignment file, ``bai`` index and some more...

You probably noticed that we get the result almost instantly, while the
typical assembling process runs for hours. This is because
processing runs asynchronously, so the returned data object does not
have an OK status or outputs when returned.

.. literalinclude:: files/tutorial-create.py
   :lines: 78-85

Status ``OK`` indicates that processing has finished successfully, but you will
also find other statuses. They are given with two-letter abbreviations. To
understand their meanings, check the
:obj:`status reference <resdk.resources.Data.status>`. When processing is done,
all outputs are written to disk and you can inspect them:

.. literalinclude:: files/tutorial-create.py
   :lines: 87-88

Until now, we used ``run()`` method twice: to upload reads (yes, uploading
files is just a matter of using an upload process) and to run alignment. You
can check the full signature of the :obj:`run() <resdk.Resolwe.run>` method.

Run workflows
=============

Typical data analysis is often a sequence of processes. Raw data or initial
input is analysed by running a process on it that outputs some data. This data
is fed as input into another process that produces another set of outputs. This
output is then again fed into another process and so on. Sometimes, this
sequence is so commonly used that one wants to simplify it's execution. This
can be done by using so called "workflow". Workflows are special processes that
run a stack of processes. On the outside, they look exactly the same as a
normal process and have a process slug, inputs... For example, we
can run workflow "General RNA-seq pipeline" on our reads:

.. literalinclude:: files/tutorial-create.py
   :lines: 90-100

Solving problems
================

Sometimes the data object will not have an "OK" status. In such case, it is
helpful to be able to check what went wrong (and where). The :obj:`stdout()
<resdk.resources.Data.stdout>` method on data objects can help---it returns the
standard output of the data object (as string). The output is long but
exceedingly useful for debugging. Also, you can inspect the info, warning and
error logs.

.. literalinclude:: files/tutorial-create.py
   :lines: 104-117

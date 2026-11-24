.. _resdk-tables:

============
ReSDK Tables
============

ReSDK tables are helper classes for aggregating collection data in
tabular format. Currently, we have six flavours:

    - :ref:`rna-tables`
    - :ref:`methylation-tables`
    - :ref:`microarray-tables`
    - :ref:`variant-tables`
    - :ref:`fusion-tables`
    - :ref:`qc-tables`


.. _rna-tables:

RNATables
=========

Imagine you are modelling gene expression data from a given collection.
Ideally, you would want all expression values organized in a table where
rows represents samples and columns represent genes. Class
``RNATables`` gives you just that (and more).

We will present the functionality of ``RNATables`` through an
example. We will:

- Create an instance of ``RNATables`` and examine it's attributes
- Fetch raw expressions and select `TIS signature genes`_ with
  sufficient coverage
- Normalize expression values (log-transform) and visualize samples in a
  simple PCA plot

.. _`TIS signature genes`: https://translational-medicine.biomedcentral.com/articles/10.1186/s12967-019-2100-3

First, connect to a Resolwe server, pick a collection and create
and instance of ``RNATables``::

    import resdk
    from resdk.tables import RNATables
    res = resdk.Resolwe(url='https://app.genialis.com/')
    res.login()
    collection = res.collection.get("sum149-fresh-for-rename")
    sum149 = RNATables(collection)

Object ``sum149`` is an instance of ``RNATables`` and has many attributes. For a complete list see
the :ref:`reference`, here we list the most commonly used ones::

    # Expressions raw counts
    sum149.rc

    # Expressions normalized counts
    sum149.exp
    # See normalization method
    sum149.exp.attrs["exp_type"]

    # Sample metadata
    sum149.meta

    # Dictionary that maps gene ID's into gene symbols
    sum149.readable_columns
    # This is handy to rename column names (gene ID's) to gene symbols
    sum149.rc.rename(columns=sum149.readable_columns)


.. note::

  Expressions and metadata are cached in memory as well as on disk. At
  each time they are re-requested a check is made that local and server side
  of data is synced. If so, cached data is used. Otherwise, new data
  will be pulled from server.

In our example we will only work with a set of `TIS signature genes`_::

    TIS_GENES = ["CD3D", "IDO1", "CIITA", "CD3E", "CCL5", "GZMK", "CD2", "HLA-DRA", "CXCL13", "IL2RG", "NKG7", "HLA-E", "CXCR6", "LAG3", "TAGAP", "CXCL10", "STAT1", "GZMB"]

We will identify low expressed genes and only keep the ones with average raw
expression above 20::

    tis_rc = sum149.rc.rename(columns=sum149.readable_columns)[TIS_GENES]
    mean = tis_rc.mean(axis=0)
    high_expressed_genes = mean.loc[mean > 20].index

Now, lets select TPM normalized expressions and keep only highly
expressed tis genes. We also transform to ``log2(TPM + 1)``::

    import numpy as np
    tis_tpm = sum149.exp.rename(columns=sum149.readable_columns)[high_expressed_genes]
    tis_tpm_log = np.log(tis_tpm + 1)

Finally, we perform PCA and visualize the results::

    from sklearn.decomposition import PCA
    pca = PCA(n_components=2, whiten=True)
    Y = pca.fit_transform(tis_tpm_log)

    import matplotlib.pyplot as plt
    for ((x, y), sample_name) in zip(Y, tis_tpm.index):
        plt.plot(x, y, 'bo')
        plt.text(x, y, sample_name)
    plt.xlabel(f"PC1 ({pca.explained_variance_ratio_[0]})")
    plt.ylabel(f"PC2 ({pca.explained_variance_ratio_[1]})")
    plt.show()


.. _methylation-tables:

MethylationTables
=================

Similar as ``RNATables`` provide access to raw counts and normalized
expression values of RNA data, ``MethylationTables`` allow for fast
access of beta and m-values of methylation data::

    meth = resdk.tables.MethylationTables(<collection-with-methylation-data>)

    # Methylation beta-values
    meth.beta

    # Methylation m-values
    meth.mval


.. _microarray-tables:

MATables
========

Similar as ``RNATables`` provide access to raw counts and normalized
expression values of RNA data, ``MATables`` allow for fast
access of expression values per probe of microarray::

    ma = resdk.tables.MATables(<collection-with-microarray-data>)

    # Microarray expressions values (columns are probe ID's)
    ma.exp

.. _variant-tables:

VariantTables
=============

Similar as ``RNATables`` provide access to raw counts and normalized
expression values of RNA data, ``VariantTables`` allow for fast
access of variant data present in Data of type ``data:mutationstable``::

    vt = resdk.tables.VariantTables(<collection-with-variant-data>)
    vt.variants

The output of the above would look something like this:

=========  ============  ============
sample_id  chr1_123_C>T  chr1_126_T>C
=========  ============  ============
101        2             NaN
102        0             2
=========  ============  ============


In rows, there are sample ID's. In columns there are variants where each
variant is given as:
``<chromosome>_<position>_<nucleotide-change>``.
Values in table can be:

    - 0 (wild-type / no mutation)
    - 1 (heterozygous mutation),
    - 2 (homozygous mutation)
    - NaN (QC filters are failing - mutation status is unreliable)


Inspecting depth
----------------

The reason for NaN values may be that the read depth on certain position
is too low for GATK to reliably call a variant. In such case, it is
worth inspecting the depth or depth per base::

    # Similar as above but one gets depth on particular variant / sample
    vt.depth
    # One can also get depth for specific base
    vt.depth_a
    vt.depth_c
    vt.depth_t
    vt.depth_g


Filtering mutations
-------------------

Process ``mutations-table`` on Genialis Platform accepts either ``mutations`` or
``geneset`` input which specifies the genes of interest. It restricts the scope
of mutation search to just a few given genes.

However, it can happen that not all the samples have the same ``mutations`` or
``geneset`` input. In such cases, it makes little sense to merge the information
about mutations from multiple samples. By default, ``VariantTables`` checks that
all Data is computed with same ``mutations`` / ``geneset`` input. If this is
not true, it will raise an error.

But if you provide additional argument ``geneset`` it will limit the
mutations to only those in the given geneset. An example::

    # Sample 101 has mutations input "FHIT, BRCA2"
    # Sample 102 has mutations input "BRCA2"

    # This would cause error, since the mutations inputs are not the same
    vt = resdk.tables.VariantTables(<collection>)
    vt.variants

    # This would limit the variants to just the ones in BRCA2 gene.
    vt = resdk.tables.VariantTables(<collection>, geneset=["BRCA2"])
    vt.variants

.. _fusion-tables:

FusionTables
============

``FusionTables`` gives access to gene fusions detected by Arriba, present
in Data of type ``data:genefusions:arriba``::

    ft = resdk.tables.FusionTables(<collection-with-fusion-data>)
    ft.fusions

Unlike the tables above, fusions are returned as a long table with one row
per fusion. The first column is ``sample_id``, followed by the columns of the
Arriba ``fusions.tsv`` file (``gene1``, ``gene2``, ``breakpoint1``,
``breakpoint2``, ``type``, ``confidence``, ...). A few of these columns:

=========  =====  =====  =============  ==========  ===
sample_id  gene1  gene2  type           confidence  ...
=========  =====  =====  =============  ==========  ===
101        CCDC6  RET    inversion      high        ...
101        EML4   ALK    inversion      medium      ...
103        BCR    ABL1   translocation  high        ...
=========  =====  =====  =============  ==========  ===

Values that Arriba reports as ``.`` (missing or not applicable) are given as
NaN. Samples without detected fusions have no rows in ``ft.fusions``, but are
still listed in ``ft.meta``. To add metadata to each fusion, merge the two
tables::

    ft.fusions.merge(ft.meta, left_on="sample_id", right_index=True)

For a description of the columns, see the `Arriba output files`_
documentation.

.. _`Arriba output files`: https://github.com/suhrig/arriba/blob/master/documentation/05-Output-files.md

.. _qc-tables:

QCTables
=============

``QCTables`` provides a tabular format access to quality control metrics of samples
present in Data of type ``data:multiqc``. It parses the relevant ``.txt`` files
generated by the MultiQC tool and provides a convenient way to access the metrics.

The individual sets of metrics can be accessed as attributes of the object::

    qt = resdk.tables.QCTables(<collection-with-qc-data>)

    # Alignment metrics
    qt.general_alignment
    qt.samtools_flagstat
    # ...

    # One can also access relevant metrics that are reported during a Resolwe pipeline run
    qt.rnaseq
    qt.wgs
    # ...


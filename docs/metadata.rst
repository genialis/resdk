.. _metadata:

========
Metadata
========

Samples are normally annotated with the use of ``AnnotationField``\ s and
``AnnotationValue``\ s. However in some cases the available
``AnnotationField``\ s do not suffice and it comes handy to upload sample
annotations in a table where each row holds information about some
sample in collection. In general, there can be multiple rows referring
to the same sample in the collection (for example one sample received
two or more distinct treatments). In such cases one can upload this
tables with the process `Metadata table`_. However, quite often there is
exactly one-on-one mapping between rows in such table and samples in
collection. In such case, please use the "unique" flavour of the above
process, `Metadata table (one-to-one)`_.

.. _Metadata table: https://docs.genialis.com/resolwe-bio/catalog-definitions.html#process-upload-metadata
.. _Metadata table (one-to-one): https://docs.genialis.com/resolwe-bio/catalog-definitions.html#process-upload-metadata-unique

Metadata in ReSDK is just a special kind of ``Data`` resource that
simplifies retrieval of the above mentioned tables. In addition to all
of the functionality of ``Data``, it also has two additional attributes:
``df`` and ``unique``::

    # The "df" attribute is pandas.DataFrame of the output named "table"
    # The index of df are sample ID's
    m.df
    # Attribute "unique" is signalling if this is metadata is unique or not
    m.unique

.. note::

    Behind the scenes, ``df`` is not an attribute but rather a property.
    So it has getter and setter methods (``get_df`` and ``set_df``).
    This comes handy if the default parsing logic does not suffice. In
    such cases you can provide your own parser and keyword arguments for
    it. Example::

        import pandas
        m.get_df(parser=pandas.read_csv, sep="\t", skiprows=[1, 2, 3])

In the most common case, Metadata objects exist somewhere on Resolwe
server and user just fetches them::

    # Get one metadata by slug
    m = res.metadata.get("my-slug")

    # Filter metadata by some conditions, e.g. get all metadata
    # from a given collection:
    ms = res.metadata.filter(collection=<my-collection>):

Sometimes, these objects need to be updated, and one can easily do that.
However, ``df`` and ``unique`` are upload protected - they can be set
during object creation but cannot be set afterwards::

    m.unique = False  # Will fail on already existing object
    m.df = <new-df>  # Will fail on already existing object

Sometimes one wishes to create a new Metadata. This can be achieved in
the same manner as for other ReSDK resources::

    m = res.metadata.create(df=<my-df>, collection=<my-collection>)

    # Creating metadata without specifying  df / collection will fail
    m = res.metdata.create()  # Fail
    m = res.metdata.create(collection=<my-collection>)  # Fail
    m = res.metdata.create(df=<my-df>)  # Fail

Alternatively, one can also build this object gradually from scratch and
than call ``save()``::

    m = Metadata(resolwe=<resolwe>)
    m.collection = <my-collection>
    my_df = m.set_index(<my-df>)
    m.df = my_df
    m.save()

where ``m.set_index(<my-df>)`` is a helper function that finds ``Sample name/slug/ID``
column or index name, maps it to ``Sample ID`` and sets it as index.
This function is recommended to use because the validation step is trying to
match ``m.df`` index with ``m.collection`` sample ID's.

Deleting Metadata works the same as for any other resource. Be careful,
this cannot be undone and you need to have sufficient permissions::

    m.delete()

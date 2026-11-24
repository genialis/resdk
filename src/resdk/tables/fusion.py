""".. Ignore pydocstyle D400.

============
FusionTables
============

.. autoclass:: FusionTables
    :members:
    :inherited-members:

    .. automethod:: __init__

"""

from functools import lru_cache

import pandas as pd

from .base import BaseTables


class FusionTables(BaseTables):
    """A helper class to fetch collection's gene fusions and meta data.

    Gene fusions are read from the ``fusions`` output of Data of type
    ``data:genefusions:arriba``. They are returned as a long table with
    one row per fusion. The first column is ``sample_id``, followed by
    the columns of the Arriba ``fusions.tsv`` file. Values that Arriba
    reports as ``.`` (missing or not applicable) are returned as NaN.

    Samples without detected fusions have no rows in the fusions table,
    but they are still listed in :attr:`FusionTables.meta`.

    A simple example:

    .. code-block:: python

        # Get Collection object
        collection = res.collection.get("collection-slug")

        tables = FusionTables(collection)
        fusions = tables.fusions
        meta = tables.meta

        # Add metadata to each fusion
        fusions.merge(meta, left_on="sample_id", right_index=True)

    """

    process_type = "data:genefusions:arriba"
    FUSIONS = "fusions"

    data_type_to_field_name = {
        FUSIONS: "fusions",
    }

    @property
    @lru_cache()
    def fusions(self) -> pd.DataFrame:
        """Return gene fusions table as a pandas DataFrame object.

        :return: table of fusions, one row per fusion
        """
        return self._load_fetch(self.FUSIONS)

    def _parse_file(self, file_obj, sample_id, data_type) -> pd.DataFrame:
        """Parse Arriba fusions file and return one row per fusion."""
        sample_data = pd.read_csv(
            file_obj,
            sep="\t",
            compression="gzip",
            na_values=["."],
            low_memory=False,
        )
        # Arriba prefixes the header line with "#", e.g. "#gene1".
        sample_data.columns = [column.lstrip("#") for column in sample_data.columns]
        sample_data.insert(0, "sample_id", sample_id)
        return sample_data

    def _merge_parsed(self, parsed: list[pd.DataFrame]) -> pd.DataFrame:
        """Stack per-sample fusions into a long table sorted by sample id."""
        # A file without fusions parses into an empty frame with all columns
        # of object dtype. Leave such frames out, so that numeric columns
        # (e.g. split_reads1) do not get cast to object.
        non_empty = [sample_data for sample_data in parsed if not sample_data.empty]
        if not non_empty:
            return parsed[0]

        df = pd.concat(non_empty, ignore_index=True)
        # Stable sort keeps Arriba's per-sample order (highest confidence first).
        return df.sort_values("sample_id", kind="stable", ignore_index=True)

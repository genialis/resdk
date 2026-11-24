""".. Ignore pydocstyle D400.

============
ReSDK Tables
============

Helper classes for aggregating collection data in tabular format.

Table classes
=============

.. autoclass:: resdk.tables.fusion.FusionTables
   :members:
   :inherited-members:

   .. automethod:: __init__

.. autoclass:: resdk.tables.microarray.MATables
   :members:
   :inherited-members:

   .. automethod:: __init__

.. autoclass:: resdk.tables.ml_ready.MLTables
   :members:
   :inherited-members:

   .. automethod:: __init__

.. autoclass:: resdk.tables.rna.RNATables
   :members:
   :inherited-members:

   .. automethod:: __init__

.. autoclass:: resdk.tables.methylation.MethylationTables
   :members:
   :inherited-members:

   .. automethod:: __init__

.. autoclass:: resdk.tables.variant.VariantTables
   :members:
   :inherited-members:

   .. automethod:: __init__

"""

from .fusion import FusionTables  # noqa
from .methylation import MethylationTables  # noqa
from .microarray import MATables  # noqa
from .ml_ready import MLTables  # noqa
from .qc import QCTables  # noqa
from .rna import RNATables  # noqa
from .variant import VariantTables  # noqa

__all__ = (
    "FusionTables",
    "MATables",
    "MLTables",
    "MethylationTables",
    "QCTables",
    "RNATables",
    "VariantTables",
)

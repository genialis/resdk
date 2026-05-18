import os
import shutil
import tempfile
import time

import numpy as np

import resdk
from resdk.tables import QCTables, RNATables, VariantTables

from ..base import BaseResdkFunctionalTest

TABLES_LIVE_URL = "https://app.genialis.com"
TABLES_USER_EMAIL = "jure+e2e@genialis.com"
TABLES_USER_PASSWORD = "safe4ever&ever"


class TestTables(BaseResdkFunctionalTest):
    def setUp(self):
        self.cache_dir = tempfile.mkdtemp()
        self.test_server_url = TABLES_LIVE_URL
        self.test_collection_slug = "resdk-test-collection-tables"
        self.res = resdk.Resolwe(
            url=self.test_server_url,
            username=TABLES_USER_EMAIL,
            password=TABLES_USER_PASSWORD,
        )
        self.collection = self.res.collection.get(self.test_collection_slug)
        self.ct = RNATables(self.collection, cache_dir=self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.cache_dir)

    def test_meta(self):
        self.assertEqual(self.ct.meta.shape, (4, 1))
        self.assertIn(146756, self.ct.meta.index)
        self.assertIn("general.species", self.ct.meta.columns)

    def test_qc(self):
        self.assertEqual(self.ct.qc.shape, (6, 24))
        self.assertIn(146756, self.ct.qc.index)
        self.assertIn("total_read_count_raw", self.ct.qc.columns)
        self.assertEqual(int(self.ct.qc.loc[146756, "total_read_count_raw"]), 46910187)
        self.assertEqual(
            int(self.ct.qc.loc[146756, "estimated_fragment_count_raw"]), 46910187
        )

    def test_rc(self):
        self.assertEqual(self.ct.rc.shape, (4, 62710))
        self.assertIn(146756, self.ct.rc.index)
        self.assertIn("ENSG00000000003", self.ct.rc.columns)
        self.assertEqual(self.ct.rc.iloc[0, 0], 918)
        self.assertIsInstance(self.ct.rc.iloc[0, 0], np.int32)

    def test_exp(self):
        self.assertEqual(self.ct.exp.shape, (4, 62710))
        self.assertIn(146756, self.ct.exp.index)
        self.assertIn("ENSG00000000003", self.ct.exp.columns)
        self.assertAlmostEqual(self.ct.exp.iloc[0, 0], 25.004105, places=3)
        self.assertIsInstance(self.ct.exp.iloc[0, 0], np.float32)

    def test_consistent_index(self):
        self.assertTrue(all(self.ct.exp.index == self.ct.meta.index))
        self.assertTrue(all(self.ct.rc.index == self.ct.meta.index))

    def test_caching(self):
        # Call rc first time with self.ct to populate the cache
        t0 = time.time()
        rc1 = self.ct.rc
        t1 = time.time() - t0

        # Make sure that cache file is created
        cache_file = self.ct._cache_file(self.ct.RC)
        self.assertTrue(os.path.isfile(cache_file))

        # Make new table instance (to prevent loading from memory)
        ct2 = RNATables(self.collection, cache_dir=self.cache_dir)
        # Call rc second time, with it should load from disk cache
        t0 = time.time()
        rc2 = ct2.rc
        t2 = time.time() - t0
        self.assertTrue((rc1 == rc2).all(axis=None))
        self.assertTrue(t2 < t1)

        # Call rc second time with rc2 to test loading from memory
        t0 = time.time()
        rc3 = ct2.rc
        t3 = time.time() - t0
        self.assertTrue((rc2 == rc3).all(axis=None))
        self.assertTrue(t3 < t2)


class TestVariantTables(BaseResdkFunctionalTest):
    def setUp(self):
        self.cache_dir = tempfile.mkdtemp()
        self.test_server_url = TABLES_LIVE_URL
        self.test_collection_slug = "varianttables_demo"
        self.res = resdk.Resolwe(
            url=self.test_server_url,
            username=TABLES_USER_EMAIL,
            password=TABLES_USER_PASSWORD,
        )
        self.collection = self.res.collection.get(self.test_collection_slug)
        self.vt = VariantTables(self.collection, cache_dir=self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.cache_dir)

    def test_geneset(self):
        self.assertIn("CYTH3", self.vt.geneset)

    def test_variants(self):
        self.assertEqual(self.vt.variants.shape, (2, 32))
        self.assertEqual(self.vt.variants.index.tolist(), [112166, 112167])
        self.assertIn("14_52004545_C>CT", self.vt.variants.columns)
        self.assertEqual(self.vt.variants.loc[112166, "14_52004545_C>CT"], 1.0)

    def test_depth(self):
        self.assertEqual(self.vt.depth.shape, (2, 32))
        self.assertEqual(self.vt.depth.index.tolist(), [112166, 112167])
        self.assertIn("14_52004545_C>CT", self.vt.depth.columns)
        self.assertEqual(self.vt.depth.loc[112166, "14_52004545_C>CT"], 185.0)

    def test_filter(self):
        self.assertEqual(self.vt.filter.shape, (2, 32))
        self.assertEqual(self.vt.filter.index.tolist(), [112166, 112167])
        self.assertIn("14_52004545_C>CT", self.vt.filter.columns)
        self.assertEqual(self.vt.filter.loc[112166, "14_52004545_C>CT"], "PASS")


class TestQCTables(BaseResdkFunctionalTest):
    def setUp(self):
        self.cache_dir = tempfile.mkdtemp()
        self.test_server_url = TABLES_LIVE_URL
        self.test_collection_slug = "resdk-test-collection-tables"
        self.res = resdk.Resolwe(
            url=self.test_server_url,
            username=TABLES_USER_EMAIL,
            password=TABLES_USER_PASSWORD,
        )
        self.collection = self.res.collection.get(self.test_collection_slug)
        self.qt = QCTables(self.collection, cache_dir=self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.cache_dir)

    def test_general_alignment(self):
        self.assertEqual(
            self.qt.general_alignment.loc[146756, "mapped_reads"], 36750221
        )

    def test_rnaseq_qc(self):
        self.assertEqual(self.qt.rnaseq.loc[146756, "gc_content_raw"], 50.0)

    def test_chipseq_qc(self):
        self.assertEqual(
            self.qt.chipseq.loc[146774, "control_prepeak_mapped_percentage"],
            0.9018,
        )

    def test_wgs_qc(self):
        self.assertEqual(
            self.qt.wgs.loc[146779, "picard_insert_min_size"],
            2.0,
        )

    def test_meta(self):
        self.assertIn("general.species", self.qt.meta.columns)

    def test_collection_slug(self):
        self.assertEqual(self.qt.collection.slug, self.test_collection_slug)

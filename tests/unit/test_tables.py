import unittest
from datetime import datetime
from io import StringIO
from time import sleep, time

import pandas as pd
import pytz
from mock import MagicMock, NonCallableMagicMock, patch
from pandas.testing import assert_frame_equal

from resdk.resources import AnnotationField, AnnotationValue, Sample
from resdk.tables import RNATables
from resdk.tables.qc import _mate_file_groups, general_multiqc_parser

from .utils import server_resource


class TestTables(unittest.TestCase):
    def setUp(self):
        self.resolwe = MagicMock()
        self.resolwe.url = "https://server.com"

        self.sample = NonCallableMagicMock(spec=Sample)
        self.sample.id = 123
        self.sample.name = "Sample123"
        self.sample.modified = datetime(
            2020, 11, 1, 12, 15, 0, 0, tzinfo=pytz.UTC
        ).astimezone(pytz.timezone("Europe/Ljubljana"))
        self.af1 = server_resource(
            AnnotationField,
            id=1,
            resolwe=self.resolwe,
            name="PFS",
            group=dict(name="general"),
            type="DECIMAL",
        )
        self.av1 = server_resource(
            AnnotationValue,
            resolwe=self.resolwe,
            value=1,
            entity=self.sample,
            field=self.af1,
        )
        self.resolwe.annotation_value.filter.return_value = [
            self.av1,
        ]

        self.data = MagicMock()
        self.data.id = 12345
        self.data.sample.id = self.sample.id
        self.data.process.slug = "process-slug"
        self.data.output.__getitem__.side_effect = {
            "species": "Homo sapiens",
            "source": "ENSEMBL",
            "exp_type": "TPM",
        }.__getitem__

        self.orange_data = MagicMock()
        self.orange_data.id = 89
        self.orange_data.files.return_value = ["table.tsv"]
        self.orange_data.modified = datetime(
            2020, 9, 1, 12, 15, 0, 0, tzinfo=pytz.UTC
        ).astimezone(pytz.timezone("Europe/Ljubljana"))

        self.ann_value = MagicMock()
        self.ann_value.id = 1024
        self.ann_value.modified = datetime(
            2020, 9, 2, 12, 15, 0, 0, tzinfo=pytz.UTC
        ).astimezone(pytz.timezone("Europe/Ljubljana"))

        self.collection = MagicMock()
        self.collection.slug = "slug"
        self.collection.name = "Name"
        self.collection.samples.filter().iterate = self.web_request([self.sample])
        self.collection.data.filter().iterate = self.web_request([self.data])
        self.collection.resolwe = self.resolwe

        self.relation = MagicMock()
        self.relation.modified = datetime(
            2020, 10, 1, 12, 15, 0, 0, tzinfo=pytz.UTC
        ).astimezone(pytz.timezone("Europe/Ljubljana"))
        self.relation.category = "Category"
        self.relation.partitions = [
            {"id": 1, "entity": 123, "position": None, "label": "L1"}
        ]
        self.collection.relations.filter = self.web_request([self.relation])
        self.metadata_df = pd.DataFrame([[0]], index=[123], columns=["PFS"])

        self.expressions_df = pd.DataFrame(
            [[0, 1, 2], [1, 2, 3], [2, 3, 4]],
            index=["0", "1", "2"],
            columns=["ENSG001", "ENSG002", "ENSG003"],
        )

        self.gene_map = {"ENSG001": "GA", "ENSG002": "GB", "ENSG003": "GC"}

    @staticmethod
    def web_request(return_value):
        def slow(*args, **kwargs):
            sleep(0.1)
            return return_value

        return slow

    @patch("resdk.tables.base.cache_dir_resdk", MagicMock(return_value="/tmp/resdk/"))
    @patch("os.path.exists")
    def test_init(self, exists_mock):
        ct = RNATables(self.collection)

        self.assertIs(ct.collection, self.collection)
        self.assertEqual(ct.cache_dir, "/tmp/resdk/")
        exists_mock.assert_called_with("/tmp/resdk/")

        # using different cache dir
        ct = RNATables(self.collection, cache_dir="/tmp/cache_dir/")
        self.assertEqual(ct.cache_dir, "/tmp/cache_dir/")
        exists_mock.assert_called_with("/tmp/cache_dir/")

    def test_heterogeneous_collections(self):
        """Test detecton of heterogeneous collections.

        Check is done in __init__, so it is sufficient to initialize
        RNATables with an appropriate collection.
        """
        # Different processes
        data2 = MagicMock()
        data2.id = 12345
        data2.process.slug = "process-slug2"
        data2.output.__getitem__.side_effect = {"source": "ENSEMBL"}.__getitem__
        self.collection.data.filter().iterate = self.web_request([self.data, data2])

        with self.assertRaisesRegex(ValueError, r"Expressions of all samples.*"):
            RNATables(self.collection)

        # Different source
        data2 = MagicMock()
        data2.id = 12345
        data2.process.slug = "process-slug"
        data2.output.__getitem__.side_effect = {"source": "GENCODE"}.__getitem__
        self.collection.data.filter().iterate = self.web_request([self.data, data2])

        with self.assertRaisesRegex(ValueError, r"Alignment of all samples.*"):
            RNATables(self.collection)

    @patch.object(RNATables, "_load_fetch")
    def test_meta(self, load_mock):
        load_mock.side_effect = self.web_request(self.metadata_df)

        ct = RNATables(self.collection)
        t = time()
        meta = ct.meta
        self.assertTrue(time() - t > 0.1)
        self.assertIs(meta, self.metadata_df)
        load_mock.assert_called_with(RNATables.META)

        # use cache
        t = time()
        meta = ct.meta
        self.assertTrue(time() - t < 0.1)
        self.assertIs(meta, self.metadata_df)

    @patch.object(RNATables, "_load_fetch")
    def test_qc(self, load_mock):
        qc_df = pd.DataFrame(
            [[None, 30], [12, 42]],
            index=["0", "1"],
            columns=["total_read_count_raw", "total_read_count_trimmed"],
        )
        load_mock.side_effect = self.web_request(qc_df)

        ct = RNATables(self.collection)
        t = time()
        meta = ct.meta
        self.assertTrue(time() - t > 0.1)
        self.assertIs(meta, qc_df)
        load_mock.assert_called_with(RNATables.META)

        # use cache
        t = time()
        meta = ct.meta
        self.assertTrue(time() - t < 0.1)
        self.assertIs(meta, qc_df)

    @patch.object(RNATables, "_load_fetch")
    def test_exp(self, load_mock):
        load_mock.side_effect = self.web_request(self.expressions_df)

        ct = RNATables(self.collection)
        t = time()
        exp = ct.exp
        self.assertTrue(time() - t > 0.1)
        self.assertIs(exp, self.expressions_df)
        load_mock.assert_called_with(RNATables.EXP)
        self.assertListEqual(ct.gene_ids, ["ENSG001", "ENSG002", "ENSG003"])

        # use cache
        t = time()
        exp = ct.exp
        self.assertTrue(time() - t < 0.1)
        self.assertIs(exp, self.expressions_df)

    @patch.object(RNATables, "_load_fetch")
    def test_rc(self, load_mock):
        load_mock.side_effect = self.web_request(self.expressions_df)

        ct = RNATables(self.collection)
        t = time()
        rc = ct.rc
        self.assertTrue(time() - t > 0.1)
        self.assertIs(rc, self.expressions_df)
        load_mock.assert_called_with(RNATables.RC)
        self.assertListEqual(ct.gene_ids, ["ENSG001", "ENSG002", "ENSG003"])

        # use cache
        t = time()
        rc = ct.rc
        self.assertTrue(time() - t < 0.1)
        self.assertIs(rc, self.expressions_df)

    @patch.object(RNATables, "_mapping")
    def test_readable_columns(self, mapping_mock):
        mapping_mock.side_effect = self.web_request(self.gene_map)

        ct = RNATables(self.collection)
        with self.assertRaises(ValueError):
            mapping = ct.readable_columns

        ct = RNATables(self.collection)
        ct.gene_ids = ["ENSG001", "ENSG002", "ENSG003"]
        t = time()
        mapping = ct.readable_columns
        self.assertTrue(time() - t > 0.1)
        mapping_mock.assert_called_with(
            ["ENSG001", "ENSG002", "ENSG003"], "ENSEMBL", "Homo sapiens"
        )
        self.assertIs(mapping, self.gene_map)

        # test if use case works
        new_exp = self.expressions_df.rename(columns=ct.readable_columns)
        self.assertListEqual(new_exp.columns.tolist(), ["GA", "GB", "GC"])

        # use cache
        t = time()
        mapping = ct.readable_columns
        self.assertTrue(time() - t < 0.1)
        self.assertIs(mapping, self.gene_map)

    def test_metadata_version(self):
        self.collection.samples.get = self.web_request(self.sample)
        self.collection.relations.get = self.web_request(self.relation)
        self.collection.data.get = self.web_request(self.orange_data)
        self.collection.resolwe.annotation_value.get = self.web_request(self.ann_value)

        ct = RNATables(self.collection)
        version = ct._metadata_version
        self.assertEqual(version, str(hash("2020-11-01T12:15:00Z")))

        # use cache
        t = time()
        version = ct._metadata_version
        self.assertTrue(time() - t < 0.1)

        self.collection.samples.get = MagicMock(side_effect=LookupError())
        ct1 = RNATables(self.collection)
        with self.assertRaises(ValueError):
            version = ct1._metadata_version

    def test_data_version(self):
        ct = RNATables(self.collection)
        version = ct._data_version
        self.assertEqual(version, str(hash(tuple([12345]))))

        # use cache
        t = time()
        version = ct._data_version
        self.assertTrue(time() - t < 0.1)

        self.collection.data.filter().iterate = MagicMock(return_value=[])
        ct = RNATables(self.collection)
        with self.assertRaises(ValueError):
            version = ct._data_version

    @patch("resdk.tables.base.cache_dir_resdk", MagicMock(return_value="/tmp/resdk/"))
    @patch("resdk.tables.base.load_pickle")
    @patch("resdk.tables.base.save_pickle")
    @patch.object(RNATables, "_download_metadata")
    @patch.object(RNATables, "_download_data")
    def test_load_fetch(self, data_mock, meta_mock, save_mock, load_mock):
        data_mock.return_value = self.expressions_df
        meta_mock.return_value = self.metadata_df
        load_mock.return_value = None

        self.collection.samples.get = self.web_request(self.sample)
        self.collection.relations.get = self.web_request(self.relation)
        self.collection.data.get = self.web_request(self.orange_data)
        self.collection.resolwe.annotation_value.get = self.web_request(self.ann_value)
        ct = RNATables(self.collection)
        data = ct._load_fetch(RNATables.META)
        self.assertIs(data, self.metadata_df)
        save_mock.assert_called_with(
            self.metadata_df,
            f"/tmp/resdk/slug_meta_None_None_{str(hash('2020-11-01T12:15:00Z'))}.pickle",
        )

        save_mock.reset_mock()
        data = ct._load_fetch(RNATables.EXP)
        self.assertIs(data, self.expressions_df)
        data_mock.assert_called_with(RNATables.EXP)
        save_mock.assert_called_with(
            self.expressions_df,
            f"/tmp/resdk/slug_exp_None_None_{str(hash((12345,)))}.pickle",
        )

        data_mock.reset_mock()
        save_mock.reset_mock()
        data = ct._load_fetch(RNATables.RC)
        self.assertIs(data, self.expressions_df)
        data_mock.assert_called_with(RNATables.RC)
        save_mock.assert_called_with(
            self.expressions_df,
            f"/tmp/resdk/slug_rc_None_None_{str(hash((12345,)))}.pickle",
        )

        data_mock.reset_mock()
        load_mock.return_value = self.expressions_df
        data = ct._load_fetch(RNATables.EXP)
        self.assertIs(data, self.expressions_df)
        data_mock.assert_not_called()

    def test_get_descriptors(self):
        ct = RNATables(self.collection)
        anns = ct._get_annotations()

        expected = pd.DataFrame([1], columns=["general.PFS"], index=[123], dtype=float)
        expected.index.name = "sample_id"

        assert_frame_equal(anns, expected, check_names=False)

    def test_get_relations(self):
        ct = RNATables(self.collection)
        relations = ct._get_relations()

        expected = pd.DataFrame(["L1"], columns=["Category"], index=[123])
        expected.index.name = "sample_id"

        assert_frame_equal(relations, expected)

    def test_get_orange_object(self):
        # Orange Data is found ad-hoc
        self.collection.data.get = self.web_request(self.orange_data)
        ct = RNATables(self.collection)
        obj = ct._get_orange_object()
        self.assertEqual(obj, self.orange_data)

    def test_get_orange_data(self):
        response = MagicMock()
        response.content = b"mS#Sample ID\tCol1\n123\t42"
        self.collection.resolwe.session.get.return_value = response
        self.collection.data.get = self.web_request(self.orange_data)

        ct = RNATables(self.collection)
        orange_data = ct._get_orange_data()

        expected = pd.DataFrame([42], columns=["Col1"], index=[123])
        expected.index.name = "sample_id"

        assert_frame_equal(orange_data, expected)

    @patch.object(RNATables, "_get_annotations")
    @patch.object(RNATables, "_get_relations")
    @patch.object(RNATables, "_get_orange_data")
    def test_download_metadata(self, orange_mock, relations_mock, annotations_mock):
        annotations_mock.return_value = self.metadata_df
        relations_mock.return_value = pd.DataFrame(
            [["A"]], index=[123], columns=["Replicate"]
        )
        orange_mock.return_value = pd.DataFrame(
            [["X"]], index=[123], columns=["Clinical"]
        )

        ct = RNATables(self.collection)
        meta = ct._download_metadata()

        expected_content = [[0, "A", "X"]]
        expected_columns = ["PFS", "Replicate", "Clinical"]
        expected_meta = pd.DataFrame(
            expected_content, columns=expected_columns, index=[123]
        )
        expected_meta.index.name = "sample_id"

        assert_frame_equal(meta, expected_meta)

    def test_get_data_uri(self):
        self.data.files.return_value = ["exp_file.csv"]

        ct = RNATables(self.collection)
        file_url = ct._get_data_uri(self.data, RNATables.EXP)
        self.assertEqual(file_url, "12345/exp_file.csv")

        self.data.files.return_value = []
        with self.assertRaises(LookupError):
            file_url = ct._get_data_uri(self.data, RNATables.EXP)

        self.data.files.return_value = ["exp_file1.csv", "exp_file2.csv"]
        with self.assertRaises(LookupError):
            file_url = ct._get_data_uri(self.data, RNATables.EXP)

    @patch("resdk.tables.base.cache_dir_resdk", MagicMock(return_value="/tmp/resdk/"))
    @patch("resdk.tables.rna.load_pickle")
    @patch("resdk.tables.rna.save_pickle")
    @patch.object(RNATables, "_download_mapping")
    def test_mapping(self, download_mock, save_mock, load_mock):
        load_mock.return_value = None
        download_mock.return_value = self.gene_map

        ct = RNATables(self.collection)
        mapping = ct._mapping(
            ["ENSG001", "ENSG002", "ENSG003"], "ENSEMBL", "Homo sapiens"
        )
        self.assertDictEqual(mapping, self.gene_map)
        self.assertListEqual(
            sorted(download_mock.call_args[0][0]), ["ENSG001", "ENSG002", "ENSG003"]
        )
        save_mock.assert_called_with(
            self.gene_map, "/tmp/resdk/ENSEMBL_Homo sapiens.pickle", override=True
        )

        # download only missing values
        download_mock.reset_mock()
        load_mock.return_value = {"ENSG002": "GB", "ENSG003": "GC"}
        mapping = ct._mapping(
            ["ENSG001", "ENSG002", "ENSG003"], "ENSEMBL", "Homo sapiens"
        )
        self.assertDictEqual(mapping, self.gene_map)
        self.assertListEqual(sorted(download_mock.call_args[0][0]), ["ENSG001"])

    def test_download_mapping(self):
        def create_feature(fid, name):
            m = MagicMock(feature_id=fid)
            # name can't be set on initialization
            m.name = name
            return m

        self.resolwe.feature.filter.return_value = [
            create_feature(fid, name) for fid, name in self.gene_map.items()
        ]

        ct = RNATables(self.collection)
        mapping = ct._download_mapping(
            ["ENSG001", "ENSG002", "ENSG003"], "ENSEMBL", "Homo sapiens"
        )

        self.resolwe.feature.filter.assert_called_once()
        self.resolwe.feature.filter.assert_called_once_with(
            source="ENSEMBL",
            species="Homo sapiens",
            feature_id__in=["ENSG001", "ENSG002", "ENSG003"],
        )
        self.assertDictEqual(mapping, self.gene_map)


class TestMateFileGroups(unittest.TestCase):
    def test_paired_end(self):
        # The reads object merges lanes into one file per mate on its output.
        reads_output = {
            "fastq": [{"file": "sampleA_R1.fastq.gz"}],
            "fastq2": [{"file": "sampleA_R2.fastq.gz"}],
        }
        self.assertEqual(
            _mate_file_groups(reads_output),
            [["sampleA_R1"], ["sampleA_R2"]],
        )

    def test_single_end(self):
        reads_output = {"fastq": [{"file": "sampleB.fastq.gz"}]}
        self.assertEqual(
            _mate_file_groups(reads_output),
            [["sampleB"]],
        )


class TestFragmentCounts(unittest.TestCase):
    # ``fastqc_raw-total_sequences`` is reported in millions and scaled by 1e6
    # by GENERAL_FASTQ_MAP, so a value of 10 corresponds to 10_000_000 reads.
    RAW_COLUMN = "fastqc_raw-total_sequences"

    def _parse(self, rows, fastq_names_per_mate):
        from resdk.tables.qc_mappings import GENERAL_FASTQ_MAP

        lines = [f"Sample\t{self.RAW_COLUMN}"]
        lines += [f"{name}\t{value}" for name, value in rows]
        return general_multiqc_parser(
            file_object=StringIO("\n".join(lines)),
            name=123,
            column_map=GENERAL_FASTQ_MAP,
            fastq_names_per_mate=fastq_names_per_mate,
        )

    def test_paired_end_sums_per_mate(self):
        # MultiQC labels rows as "<sample name> | <mate name>"; only the part
        # after the "|" is matched to the reads object output file names.
        series = self._parse(
            rows=[
                ("sampleA | sampleA_L001_R1", 10),
                ("sampleA | sampleA_L002_R1", 5),
                ("sampleA | sampleA_L001_R2", 10),
                ("sampleA | sampleA_L002_R2", 5),
            ],
            fastq_names_per_mate=[
                ["sampleA_L001_R1", "sampleA_L002_R1"],
                ["sampleA_L001_R2", "sampleA_L002_R2"],
            ],
        )
        # Per-mate totals are 15M each; their mean is the fragment (pair) count.
        self.assertEqual(series["estimated_fragment_count_raw"], 15_000_000)

    def test_single_end_sums_all_lanes(self):
        series = self._parse(
            rows=[
                ("sampleB | sampleB_L001", 8),
                ("sampleB | sampleB_L002", 2),
            ],
            fastq_names_per_mate=[["sampleB_L001", "sampleB_L002"]],
        )
        self.assertEqual(series["estimated_fragment_count_raw"], 10_000_000)

import asyncio
import gzip
import shutil
import tempfile
import unittest
from io import BytesIO

import pandas as pd
from mock import AsyncMock, MagicMock, PropertyMock, patch

from resdk.tables import FusionTables

# Columns of the Arriba 2.4.0 fusions.tsv file, as produced by the
# resolwe-bio arriba process.
COLUMNS = [
    "gene1",
    "gene2",
    "strand1(gene/fusion)",
    "strand2(gene/fusion)",
    "breakpoint1",
    "breakpoint2",
    "site1",
    "site2",
    "type",
    "split_reads1",
    "split_reads2",
    "discordant_mates",
    "coverage1",
    "coverage2",
    "confidence",
    "reading_frame",
    "tags",
    "retained_protein_domains",
    "closest_genomic_breakpoint1",
    "closest_genomic_breakpoint2",
    "gene_id1",
    "gene_id2",
    "transcript_id1",
    "transcript_id2",
    "direction1",
    "direction2",
    "filters",
    "fusion_transcript",
    "peptide_sequence",
    "read_identifiers",
]

CCDC6_RET = [
    "CCDC6",
    "RET",
    "-/-",
    "+/+",
    "minigenome:609384",
    "minigenome:490475",
    "CDS/splice-site",
    "CDS/splice-site",
    "inversion",
    "1",
    "0",
    "7",
    "112",
    "38",
    "high",
    "in-frame",
    ".",
    ".",
    ".",
    ".",
    "CCDC6",
    "RET",
    "CCDC6^ENST00000263102.6",
    "RET^ENST00000355710.3",
    "upstream",
    "upstream",
    ".",
    "CGCCGTTCCGCC|GAGGATCCAAAG",
    "PFRLEEL|EDPKWEF",
    "",
]

CCDC6_INTERGENIC = [
    "CCDC6",
    "CCDC6(40)",
    "-/-",
    "./-",
    "minigenome:609871",
    "minigenome:609958",
    "5'UTR",
    "intergenic",
    "deletion/read-through",
    "0",
    "0",
    "0",
    "10",
    "8",
    "low",
    ".",
    ".",
    ".",
    ".",
    ".",
    "CCDC6",
    ".",
    ".",
    ".",
    "downstream",
    "upstream",
    "read_through",
    ".",
    ".",
    "",
]


def arriba_file(rows):
    """Return content of a gzipped Arriba fusions file."""
    header = "#" + "\t".join(COLUMNS)
    lines = [header] + ["\t".join(row) for row in rows]
    return gzip.compress(("\n".join(lines) + "\n").encode("utf-8"))


def response_context(content):
    """Return a mock of ``session.get(url)`` that serves the given content."""
    response = MagicMock(status=200, ok=True, headers={})
    response.content.read = AsyncMock(return_value=content)
    context = MagicMock()
    context.__aenter__.return_value = response
    return context


class TestFusionTables(unittest.TestCase):
    def setUp(self):
        self.cache_dir = tempfile.mkdtemp()
        self.collection = MagicMock()
        self.collection.resolwe.url = "https://server.com"
        self.ft = FusionTables(self.collection, cache_dir=self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.cache_dir)

    def make_data(self, data_id, sample_id, file_name):
        data = MagicMock()
        data.id = data_id
        data.sample.id = sample_id
        data.files.return_value = [file_name]
        return data

    def test_data(self):
        data = self.make_data(1001, 101, "a_fusions.tsv.gz")
        self.collection.data.filter.return_value.iterate.return_value = [data]

        self.assertEqual(self.ft._data, [data])
        self.assertEqual(
            self.collection.data.filter.call_args.kwargs["type"],
            "data:genefusions:arriba",
        )

    def test_get_data_uri(self):
        data = self.make_data(1001, 101, "a_fusions.tsv.gz")

        self.assertEqual(
            self.ft._get_data_uri(data, FusionTables.FUSIONS),
            "1001/a_fusions.tsv.gz",
        )
        data.files.assert_called_once_with(field_name="fusions")

    @patch.object(FusionTables, "_load_fetch")
    def test_fusions(self, load_mock):
        self.assertIs(self.ft.fusions, load_mock.return_value)
        load_mock.assert_called_once_with("fusions")

    def test_parse_file(self):
        file_obj = BytesIO(arriba_file([CCDC6_RET, CCDC6_INTERGENIC]))

        df = self.ft._parse_file(file_obj, 101, FusionTables.FUSIONS)

        self.assertEqual(df.columns.tolist(), ["sample_id"] + COLUMNS)
        self.assertEqual(df["sample_id"].tolist(), [101, 101])
        self.assertEqual(df["gene2"].tolist(), ["RET", "CCDC6(40)"])
        # Cells with "." are missing values, other values with dots are kept.
        self.assertTrue(df["tags"].isna().all())
        self.assertEqual(df["gene_id2"].tolist()[0], "RET")
        self.assertTrue(pd.isna(df["gene_id2"].tolist()[1]))
        self.assertEqual(df["strand2(gene/fusion)"].tolist()[1], "./-")
        self.assertTrue(pd.api.types.is_integer_dtype(df["split_reads1"]))

    def test_parse_file_without_fusions(self):
        df = self.ft._parse_file(BytesIO(arriba_file([])), 101, FusionTables.FUSIONS)

        self.assertTrue(df.empty)
        self.assertEqual(df.columns.tolist(), ["sample_id"] + COLUMNS)

    @patch("resdk.tables.base.EXP_ASYNC_CHUNK_SIZE", 1)
    @patch.object(FusionTables, "_download_session")
    @patch.object(FusionTables, "_get_data_urls")
    @patch.object(FusionTables, "_data", new_callable=PropertyMock)
    def test_download_data(self, data_mock, urls_mock, download_session_mock):
        data_mock.return_value = [
            self.make_data(1002, 102, "b_fusions.tsv.gz"),
            self.make_data(1001, 101, "a_fusions.tsv.gz"),
            self.make_data(1000, 100, "c_fusions.tsv.gz"),
        ]
        files = {
            "https://storage/1002/b_fusions.tsv.gz": arriba_file([]),
            "https://storage/1001/a_fusions.tsv.gz": arriba_file(
                [CCDC6_RET, CCDC6_INTERGENIC]
            ),
            "https://storage/1000/c_fusions.tsv.gz": arriba_file([CCDC6_INTERGENIC]),
        }
        urls_mock.side_effect = lambda uris: {
            uri: f"https://storage/{uri}" for uri in uris
        }
        session = MagicMock()
        session.get.side_effect = lambda url, **kwargs: response_context(files[url])
        download_session_mock.return_value.__aenter__.return_value = session

        df = asyncio.run(self.ft._download_data(FusionTables.FUSIONS))

        # One chunk per Data object.
        self.assertEqual(urls_mock.call_count, 3)
        self.assertEqual(df.columns.tolist(), ["sample_id"] + COLUMNS)
        # Sorted by sample, Arriba order is kept within a sample, and the
        # sample without fusions has no rows.
        self.assertEqual(df["sample_id"].tolist(), [100, 101, 101])
        self.assertEqual(df["gene2"].tolist(), ["CCDC6(40)", "RET", "CCDC6(40)"])
        pd.testing.assert_index_equal(df.index, pd.RangeIndex(3))
        # The sample without fusions does not change the column types.
        self.assertTrue(pd.api.types.is_integer_dtype(df["split_reads1"]))

    def test_merge_parsed_without_fusions(self):
        parsed = [
            self.ft._parse_file(BytesIO(arriba_file([])), sample_id, "fusions")
            for sample_id in (101, 102)
        ]

        df = self.ft._merge_parsed(parsed)

        self.assertTrue(df.empty)
        self.assertEqual(df.columns.tolist(), ["sample_id"] + COLUMNS)

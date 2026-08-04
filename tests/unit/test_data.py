"""
Unit tests for resdk/resources/data.py file.
"""

import os
import shutil
import tempfile
import unittest

from mock import MagicMock, patch

from resdk.resources.data import Data
from resdk.resources.descriptor import DescriptorSchema
from resdk.resources.fields import FieldStatus
from resdk.resources.process import Process

from .utils import server_resource


class TestData(unittest.TestCase):
    def test_sample(self):
        data = server_resource(
            Data, resolwe=MagicMock(), id=1, entity={"id": 5, "name": "XYZ"}
        )

        self.assertEqual(data.sample.id, 5)
        self.assertEqual(data.sample.name, "XYZ")

    def test_collection(self):
        data = server_resource(
            Data, resolwe=MagicMock(), id=1, collection={"id": 5, "name": "XYZ"}
        )

        # test getting collections attribute
        self.assertEqual(data.collection.id, 5)
        self.assertEqual(data.collection.name, "XYZ")

    def test_descriptor_schema(self):
        resolwe = MagicMock()
        data = server_resource(Data, id=1, resolwe=resolwe)
        data._descriptor_schema = server_resource(
            DescriptorSchema, resolwe=resolwe, id=2
        )

        # test getting descriptor schema attribute
        self.assertEqual(data.descriptor_schema.id, 2)

        # descriptor schema is not set
        data._descriptor_schema = None
        self.assertEqual(data.descriptor_schema, None)

        # hydrated descriptor schema
        descriptor_schema = {
            "slug": "test-schema",
            "name": "Test schema",
            "version": "1.0.0",
            "schema": [
                {
                    "default": "56G",
                    "type": "basic:string:",
                    "name": "description",
                    "label": "Object description",
                }
            ],
            "id": 1,
        }
        data = server_resource(
            Data, id=1, descriptor_schema=descriptor_schema, resolwe=MagicMock()
        )
        self.assertTrue(isinstance(data.descriptor_schema, DescriptorSchema))

        self.assertEqual(data.descriptor_schema.slug, "test-schema")
        self.assertEqual(
            data.descriptor_schema.schema[0]["label"], "Object description"
        )

    def test_parents(self):
        # Data with no id should fail.
        data = Data(resolwe=MagicMock())
        with self.assertRaisesRegex(ValueError, "Instance must be saved *"):
            data.parents

        # Core functionality should be checked with e2e tests.

        # Check that cache is cleared at update.
        data = server_resource(Data, id=42, resolwe=MagicMock())
        data._parents = "foo"
        data.update()
        self.assertEqual(data._parents, None)

    def test_children(self):
        # Data with no id should fail.
        data = Data(resolwe=MagicMock())
        with self.assertRaisesRegex(ValueError, "Instance must be saved *"):
            data.children

        # Core functionality should be checked with e2e tests.

        # Check that cache is cleared at update.
        data = server_resource(Data, id=42, resolwe=MagicMock())
        data._children = "foo"
        data.update()
        self.assertEqual(data._children, None)

    def test_files(self):
        resolwe = MagicMock()
        data = server_resource(Data, id=123, resolwe=resolwe)
        data._get_dir_files = MagicMock(
            side_effect=[["first_dir/file1.txt"], ["fastq_dir/file2.txt"]]
        )

        data._output_status = FieldStatus.SET
        data._output = {
            "list": [{"file": "element.gz"}],
            "dir_list": [{"dir": "first_dir"}],
            "fastq": {"file": "file.fastq.gz"},
            "fastq_archive": {"file": "archive.gz"},
            "fastq_dir": {"dir": "fastq_dir"},
        }
        data._process_status = FieldStatus.SET
        data._process = Process(
            resolwe=resolwe,
            output_schema=[
                {"name": "list", "label": "List", "type": "list:basic:file:"},
                {"name": "dir_list", "label": "Dir_list", "type": "list:basic:dir:"},
                {"name": "fastq", "label": "Fastq", "type": "basic:file:fastq:"},
                {
                    "name": "fastq_archive",
                    "label": "Fastq_archive",
                    "type": "basic:file:",
                },
                {"name": "fastq_dir", "label": "Fastq_dir", "type": "basic:dir:"},
            ],
        )

        file_list = data.files()
        self.assertCountEqual(
            file_list,
            [
                "element.gz",
                "archive.gz",
                "file.fastq.gz",
                "first_dir/file1.txt",
                "fastq_dir/file2.txt",
            ],
        )
        file_list = data.files(file_name="element.gz")
        self.assertEqual(file_list, ["element.gz"])
        file_list = data.files(field_name="output.fastq")
        self.assertEqual(file_list, ["file.fastq.gz"])

        data._output_status = FieldStatus.SET
        data._output = {
            "list": [{"no_file_field_here": "element.gz"}],
        }
        data.process.output_schema = [
            {"name": "list", "label": "List", "type": "list:basic:file:"},
        ]
        with self.assertRaisesRegex(KeyError, "does not contain 'file' key."):
            data.files()

        data = Data(resolwe=MagicMock())
        with self.assertRaisesRegex(ValueError, "must be saved before"):
            data.files()

    @patch("resdk.resolwe.Resolwe")
    def test_dir_files(self, resolwe_mock):
        resolwe_mock.url = "http://resolwe.url"
        resolwe_mock.session.get.side_effect = [
            MagicMock(
                content=b'[{"type": "file", "name": "file1.txt"}, '
                b'{"type": "directory", "name": "subdir"}]'
            ),
            MagicMock(content=b'[{"type": "file", "name": "file2.txt"}]'),
        ]
        data = server_resource(Data, id=123, resolwe=resolwe_mock)
        files = data._get_dir_files("test_dir")
        self.assertEqual(files, ["test_dir/file1.txt", "test_dir/subdir/file2.txt"])

    @patch("resdk.resources.data.Data", spec=True)
    def test_download_fail(self, data_mock):
        message = "Only one of file_name or field_name may be given."
        with self.assertRaisesRegex(ValueError, message):
            Data.download(data_mock, file_name="a", field_name="b")

    @patch("resdk.resources.data.Data", spec=True)
    def test_download_ok(self, data_mock):
        data_mock.configure_mock(id=123, **{"resolwe": MagicMock()})
        data_mock.configure_mock(
            **{
                "files.return_value": ["file1.txt", "file2.fq.gz"],
            }
        )

        Data.download(data_mock)
        data_mock.resolwe._download_files.assert_called_once_with(
            files=["123/file1.txt", "123/file2.fq.gz"],
            download_dir=None,
            show_progress=True,
            skip_existing=False,
        )

        data_mock.reset_mock()
        Data.download(data_mock, download_dir="/some/path/")
        data_mock.resolwe._download_files.assert_called_once_with(
            files=["123/file1.txt", "123/file2.fq.gz"],
            download_dir="/some/path/",
            show_progress=True,
            skip_existing=False,
        )

        data_mock.reset_mock()
        Data.download(data_mock, skip_existing=True)
        data_mock.resolwe._download_files.assert_called_once_with(
            files=["123/file1.txt", "123/file2.fq.gz"],
            download_dir=None,
            show_progress=True,
            skip_existing=True,
        )

    @patch("resdk.resolwe.Resolwe")
    @patch("resdk.resources.data.urljoin")
    @patch("resdk.resources.data.Data", spec=True)
    def test_stdout_ok(self, data_mock, urljoin_mock, resolwe_mock):
        # Configure mocks:
        process_mock = MagicMock(type="data:index")
        data_mock.configure_mock(
            id=123, status="OK", resolwe=resolwe_mock, process=process_mock
        )
        urljoin_mock.return_value = "some_url"
        resolwe_mock.configure_mock(url="a", auth="b")

        # If response.ok = True:
        resolwe_mock.session.get.return_value = MagicMock(
            ok=True, **{"iter_content.return_value": [b"abc", b"def"]}
        )
        out = Data.stdout(data_mock)

        self.assertEqual(out, "abcdef")
        urljoin_mock.assert_called_once_with("a", "data/123/stdout.txt")

        resolwe_mock.session.get.assert_called_once_with(
            "some_url", stream=True, auth="b"
        )

        # If response.ok = False:
        response = MagicMock(ok=False)
        resolwe_mock.session.get.return_value = response

        out = Data.stdout(data_mock)

        self.assertEqual(response.raise_for_status.call_count, 1)


class TestDataDownloadCustomAssetName(unittest.TestCase):
    def data_with_assets(self, file_names, dir_names=()):
        """Data object whose files and directories are already known."""
        data = server_resource(Data, resolwe=MagicMock(), id=123)
        data.files = MagicMock(return_value=list(file_names))
        data._files_dirs = MagicMock(return_value=list(dir_names))
        return data

    def test_file_is_saved_under_custom_name(self):
        data = self.data_with_assets(["filtered_variants.vcf.gz"])

        asset_names = data.download(
            field_name="vcf",
            download_dir="/some/path",
            skip_existing=True,
            custom_asset_name="sample1.vcf.gz",
        )

        data.resolwe._download_files.assert_called_once_with(
            files=["123/filtered_variants.vcf.gz"],
            download_dir="/some/path",
            show_progress=True,
            skip_existing=True,
            custom_file_name="sample1.vcf.gz",
        )
        self.assertEqual(asset_names, ["sample1.vcf.gz"])

    def test_directory_is_renamed_after_download(self):
        data = self.data_with_assets(
            ["outdir/file1.txt", "outdir/file2.txt"], ["outdir"]
        )

        with patch("os.rename") as rename_mock:
            asset_names = data.download(
                field_name="out",
                download_dir="/some/path",
                custom_asset_name="sample1",
            )

        # A directory has to be downloaded under its name on the server first.
        data.resolwe._download_files.assert_called_once_with(
            files=["123/outdir/file1.txt", "123/outdir/file2.txt"],
            download_dir="/some/path",
            show_progress=True,
            skip_existing=False,
        )
        rename_mock.assert_called_once_with("/some/path/outdir", "/some/path/sample1")
        self.assertEqual(asset_names, ["sample1"])

    def test_existing_directory_is_not_downloaded_again(self):
        data = self.data_with_assets(["outdir/file1.txt"], ["outdir"])
        download_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, download_dir)
        os.makedirs(os.path.join(download_dir, "sample1"))

        asset_names = data.download(
            field_name="out",
            download_dir=download_dir,
            skip_existing=True,
            custom_asset_name="sample1",
        )

        data.resolwe._download_files.assert_not_called()
        self.assertEqual(asset_names, ["sample1"])

    def test_multiple_assets_fail(self):
        data = self.data_with_assets(["file1.txt", "file2.txt"])

        message = (
            "'custom_asset_name' can only be applied when downloading exactly one asset"
        )
        with self.assertRaisesRegex(ValueError, message):
            data.download(custom_asset_name="single_file.txt")

        data.resolwe._download_files.assert_not_called()

    def test_download_and_rename_delegates_to_download(self):
        data = self.data_with_assets(["filtered_variants.vcf.gz"])
        data.download = MagicMock()

        data.download_and_rename(
            custom_asset_name="sample1.vcf.gz",
            field_name="vcf",
            download_dir="/some/path",
        )

        data.download.assert_called_once_with(
            file_name=None,
            field_name="vcf",
            download_dir="/some/path",
            skip_existing=True,
            custom_asset_name="sample1.vcf.gz",
        )

        data.download.reset_mock()
        data.download_and_rename(
            custom_asset_name="sample1.vcf.gz",
            overwrite_existing=True,
            field_name="vcf",
        )

        self.assertEqual(
            data.download.call_args.kwargs["skip_existing"],
            False,
        )


if __name__ == "__main__":
    unittest.main()

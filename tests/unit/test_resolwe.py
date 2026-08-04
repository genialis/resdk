"""
Unit tests for resdk/resolwe.py file.
"""

import hashlib
import json
import os
import shutil
import tempfile
import unittest

import requests
from mock import MagicMock, patch
from slumber.exceptions import SlumberHttpBaseException

from resdk.exceptions import ResolweServerError, ValidationError
from resdk.resolwe import ResAuth, Resolwe, ResolweResource
from resdk.resources import Collection, Data, Process
from resdk.resources.fields import DataSource
from resdk.uploader import Uploader

from .utils import server_resource

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestResolweResource(unittest.TestCase):
    def setUp(self):
        self.resource = ResolweResource()
        self.method_mock = MagicMock(
            side_effect=[42, SlumberHttpBaseException(content="error mesage")]
        )

    def test_get_wrapped(self):
        self.resource.get = self.method_mock
        self.assertEqual(self.resource.get(), 42)

        with self.assertRaises(ResolweServerError):
            self.resource.get()

    def test_options_wrapped(self):
        self.resource.options = self.method_mock
        self.assertEqual(self.resource.options(), 42)

        with self.assertRaises(ResolweServerError):
            self.resource.options()

    def test_head_wrapped(self):
        self.resource.head = self.method_mock
        self.assertEqual(self.resource.head(), 42)

        with self.assertRaises(ResolweServerError):
            self.resource.head()

    def test_post_wrapped(self):
        self.resource.post = self.method_mock
        self.assertEqual(self.resource.post(), 42)

        with self.assertRaises(ResolweServerError):
            self.resource.post()

    def test_patch_wrapped(self):
        self.resource.patch = self.method_mock
        self.assertEqual(self.resource.patch(), 42)

        with self.assertRaises(ResolweServerError):
            self.resource.patch()

    def test_put_wrapped(self):
        self.resource.put = self.method_mock
        self.assertEqual(self.resource.put(), 42)

        with self.assertRaises(ResolweServerError):
            self.resource.put()

    def test_delete_wrapped(self):
        self.resource.delete = self.method_mock
        self.assertEqual(self.resource.delete(), 42)

        with self.assertRaises(ResolweServerError):
            self.resource.delete()


class TestResolwe(unittest.TestCase):
    @patch("resdk.resolwe.logging")
    @patch("resdk.resolwe.ResolweAPI")
    @patch("resdk.resolwe.slumber")
    @patch("resdk.resolwe.ResAuth")
    @patch("resdk.resolwe.Resolwe", spec=Resolwe)
    def test_init(
        self, resolwe_mock, resauth_mock, slumber_mock, resolwe_api_mock, log_mock
    ):
        Resolwe.__init__(resolwe_mock, "a", "b", "http://some/url")
        self.assertEqual(log_mock.getLogger.call_count, 1)

    def test_validate_url(self):
        resolwe = MagicMock(spec=Resolwe)

        message = "Server url must start with .*"
        with self.assertRaisesRegex(ValueError, message):
            Resolwe._validate_url(resolwe, "starts.without.http")

        resolwe.session = MagicMock(
            get=MagicMock(side_effect=requests.exceptions.ConnectionError())
        )
        message = "The site can't be reached: .*"
        with self.assertRaisesRegex(ValueError, message):
            Resolwe._validate_url(resolwe, "http://invalid.url")

    @patch("resdk.resolwe.ResolweAPI")
    @patch("resdk.resolwe.ResAuth")
    @patch("resdk.resolwe.Resolwe", spec=Resolwe)
    def test_login(self, resolwe_mock, resauth_mock, resolwe_api_mock):
        resolwe_mock.url = "http://some/url"
        resauth_mock.cookies = {}
        resolwe_mock.uploader = MagicMock(spec=Uploader)
        Resolwe._login(resolwe_mock, "a", "b")
        self.assertEqual(resauth_mock.call_count, 1)
        self.assertEqual(resolwe_api_mock.call_count, 1)

    def test_repr(self):
        resolwe_mock = MagicMock(spec=Resolwe, url="www.abc.com")

        resolwe_mock.auth = MagicMock(username="user")
        rep = Resolwe.__repr__(resolwe_mock)
        self.assertEqual(rep, "Resolwe <url: www.abc.com, username: user>")

        resolwe_mock.auth = MagicMock(username=None)
        rep = Resolwe.__repr__(resolwe_mock)
        self.assertEqual(rep, "Resolwe <url: www.abc.com>")

    @patch("resdk.resolwe.requests")
    @patch("resdk.resolwe.ResAuth")
    def test_env_variables(self, resauth_mock, requests_mock):
        # Ensure environmental variables are not set.
        os.environ.pop("RESOLWE_HOST_URL", None)
        os.environ.pop("RESOLWE_API_USERNAME", None)
        os.environ.pop("RESOLWE_API_PASSWORD", None)

        # Default URL should be used by default.
        resolwe_api = Resolwe()
        self.assertEqual(resolwe_api.url, "http://localhost:8000")
        self.assertEqual(resauth_mock.call_args[0][0], None)
        self.assertEqual(resauth_mock.call_args[0][1], None)

        # If environment variable is set, it overrides the default URL.
        os.environ["RESOLWE_API_USERNAME"] = "foo"
        os.environ["RESOLWE_API_PASSWORD"] = "bar"
        os.environ["RESOLWE_HOST_URL"] = "http://resolwe-api:8000"
        resolwe_api = Resolwe()
        self.assertEqual(resolwe_api.url, "http://resolwe-api:8000")
        self.assertEqual(resauth_mock.call_args[0][0], "foo")
        self.assertEqual(resauth_mock.call_args[0][1], "bar")


class TestProcessFileField(unittest.TestCase):
    @patch("resdk.resolwe.os", autospec=True)
    @patch("resdk.resolwe.Resolwe", autospec=True)
    def test_invalid_file_name(self, resolwe_mock, os_mock):
        os_mock.configure_mock(**{"path.isfile.return_value": False})
        resolwe_mock.uploader = MagicMock(spec=Uploader)

        message = r"File .* not found."
        with self.assertRaisesRegex(ValueError, message):
            Resolwe._process_file_field(resolwe_mock, "/bad/path/to/file")
        self.assertEqual(resolwe_mock.uploader.upload.call_count, 0)

    @patch("resdk.resolwe.os")
    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_if_upload_fails(self, resolwe_mock, os_mock):
        # Good file, upload fails
        os_mock.configure_mock(**{"path.isfile.return_value": True})
        resolwe_mock.uploader = MagicMock(spec=Uploader)
        resolwe_mock.uploader.upload = MagicMock(return_value=None)

        message = r"Upload failed for .*"
        with self.assertRaisesRegex(Exception, message):
            Resolwe._process_file_field(resolwe_mock, "/good/path/to/file")
        self.assertEqual(resolwe_mock.uploader.upload.call_count, 1)

    @patch("resdk.resolwe.ntpath")
    @patch("resdk.resolwe.os")
    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_if_upload_ok(self, resolwe_mock, os_mock, ntpath_mock):
        # Good file, upload fails
        os_mock.configure_mock(**{"path.isfile.return_value": True})
        resolwe_mock.uploader = MagicMock(spec=Uploader)
        resolwe_mock.uploader.upload = MagicMock(return_value="temporary_file")
        ntpath_mock.basename.return_value = "Basename returned!"

        output = Resolwe._process_file_field(resolwe_mock, "/good/path/to/file.txt")
        self.assertEqual(
            output, {"file": "Basename returned!", "file_temp": "temporary_file"}
        )

        resolwe_mock.uploader.upload.assert_called_once_with("/good/path/to/file.txt")

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_url(self, resolwe_mock):
        output = Resolwe._process_file_field(
            resolwe_mock, "http://www.example.com/reads.fq.gz"
        )
        self.assertEqual(
            output,
            {"file": "reads.fq.gz", "file_temp": "http://www.example.com/reads.fq.gz"},
        )


class TestRun(unittest.TestCase):
    def setUp(self):
        self.process_mock = MagicMock(spec=Process)
        self.process_mock.slug = "some:prc:slug:"
        self.process_mock.input_schema = [
            {
                "label": "NGS reads (FASTQ)",
                "type": "basic:file:",
                "required": "false",
                "name": "src",
            },
            {
                "label": "list of NGS reads",
                "type": "list:basic:file:",
                "required": "false",
                "name": "src_list",
            },
            {
                "label": "Genome object",
                "type": "data:genome:fasta:",
                "required": "false",
                "name": "genome",
            },
            {
                "label": "List of reads objects",
                "type": "list:data:reads:fastg:",
                "required": "false",
                "name": "reads",
            },
        ]

    @patch("resdk.resolwe.Data")
    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_run_process(self, resolwe_mock, data_mock):
        resolwe_mock.api = MagicMock(**{"process.get.return_value": self.process_mock})

        Resolwe.run(resolwe_mock)
        self.assertEqual(resolwe_mock.api.data.post.call_count, 1)

    @patch("resdk.resolwe.Data")
    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_get_or_run(self, resolwe_mock, data_mock):
        resolwe_mock.api = MagicMock(**{"process.get.return_value": self.process_mock})

        Resolwe.get_or_run(resolwe_mock)
        self.assertEqual(resolwe_mock.api.data.get_or_create.post.call_count, 1)

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_wrap_list(self, resolwe_mock):
        process = self.process_mock

        Resolwe._process_inputs(resolwe_mock, {"src_list": ["/path/to/file"]}, process)
        resolwe_mock._process_file_field.assert_called_once_with("/path/to/file")

        resolwe_mock.reset_mock()
        Resolwe._process_inputs(resolwe_mock, {"src_list": "/path/to/file"}, process)
        resolwe_mock._process_file_field.assert_called_once_with("/path/to/file")

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_keep_input(self, resolwe_mock):
        process = self.process_mock

        input_dict = {"src_list": ["/path/to/file"]}
        Resolwe._process_inputs(resolwe_mock, input_dict, process)
        self.assertEqual(input_dict, {"src_list": ["/path/to/file"]})

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_bad_descriptor_input(self, resolwe_mock):
        # Raise error is only one of deswcriptor/descriptor_schema is given:
        message = "Set both or neither descriptor and descriptor_schema."
        with self.assertRaisesRegex(ValueError, message):
            Resolwe.run(resolwe_mock, descriptor="a")
        with self.assertRaisesRegex(ValueError, message):
            Resolwe.run(resolwe_mock, descriptor_schema="a")

    @patch("resdk.resolwe.os")
    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_bad_inputs(self, resolwe_mock, os_mock):
        # Good file, upload fails becouse of bad input keyword
        os_mock.path.isfile.return_value = True
        process = self.process_mock

        resolwe_mock._upload_file = MagicMock(return_value=None)
        message = r"Field .* not in process .* input schema."
        with self.assertRaisesRegex(ValidationError, message):
            Resolwe._process_inputs(
                resolwe_mock, {"bad_key": "/good/path/to/file"}, process
            )

    @patch("resdk.resolwe.Data")
    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_file_processing(self, resolwe_mock, data_mock):
        resolwe_mock.api = MagicMock(
            **{
                "process.get.return_value": self.process_mock,
                "data.post.return_value": {},
            }
        )
        resolwe_mock._process_file_field = MagicMock(
            side_effect=[
                {"file": "file_name1", "file_temp": "temp_file1"},
                {"file": "file_name2", "file_temp": "temp_file2"},
                {"file": "file_name3", "file_temp": "temp_file3"},
            ]
        )
        data_mock.return_value = "Data object"

        Resolwe.run(
            resolwe_mock,
            input={
                "src": "/path/to/file1",
                "src_list": ["/path/to/file2", "/path/to/file3"],
            },
        )

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_dehydrate_data(self, resolwe_mock):
        data_obj = server_resource(Data, id=1, resolwe=MagicMock())
        process = self.process_mock

        result = Resolwe._process_inputs(resolwe_mock, {"genome": data_obj}, process)
        self.assertEqual(result, {"genome": 1})

        result = Resolwe._process_inputs(resolwe_mock, {"reads": [data_obj]}, process)
        self.assertEqual(result, {"reads": [1]})

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_dehydrate_collection(self, resolwe_mock):
        resolwe_mock._get_process.return_value = Process(
            resolwe=MagicMock(), slug="process-slug"
        )
        resolwe_mock._process_inputs.return_value = {}
        resolwe_mock.api = MagicMock(**{"data.post.return_value": {}})

        Resolwe.run(
            self=resolwe_mock,
            slug="process-slug",
            collection=server_resource(Collection, id=1, resolwe=MagicMock()),
        )
        resolwe_mock.api.data.post.assert_called_once_with(
            {
                "process": {"slug": "process-slug"},
                "input": {},
                "collection": {"id": 1},
            }
        )

    @patch("resdk.resolwe.Data")
    @patch("resdk.resolwe.os")
    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_call_with_all_args(self, resolwe_mock, os_mock, data_mock):
        resolwe_mock.api = MagicMock(
            **{
                "process.get.return_value": self.process_mock,
                "data.post.return_value": {"data": "some_data"},
            }
        )
        resolwe_mock.uploader = MagicMock(spec=Uploader)
        data_mock.return_value = "Data object"

        data = Resolwe.run(
            resolwe_mock,
            data_name="some_name",
            descriptor="descriptor",
            descriptor_schema="descriptor_schema",
            collection=1,
        )
        # Confirm that no files to upload in input:
        self.assertEqual(resolwe_mock.uploader.upload.call_count, 0)
        data_mock.assert_called_with(
            data="some_data",
            resolwe=resolwe_mock,
            initial_data_source=DataSource.SERVER,
        )
        self.assertEqual(data, "Data object")


class TestUploadFile(unittest.TestCase):
    def setUp(self):
        self.file_path = os.path.join(BASE_DIR, "files", "example.fastq")
        self.config = {
            "url": "http://some/url",
            "auth": MagicMock(),
            "logger": MagicMock(),
        }

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_always_ok(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)
        # Immitate response form server - always status 200:
        requests_response = {"files": [{"temp": "fake_name"}]}
        resolwe_mock.session.post.return_value = MagicMock(
            status_code=200, **{"json.return_value": requests_response}
        )

        response = Uploader(resolwe_mock)._upload_local(self.file_path)
        self.assertEqual(response, "fake_name")

    @patch("resdk.resolwe.requests")
    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_always_bad(self, resolwe_mock, requests_mock):
        resolwe_mock.configure_mock(**self.config)
        # Immitate response form server - always status 400
        requests_mock.post.return_value = MagicMock(status_code=400)

        response = Uploader(resolwe_mock)._upload_local(self.file_path)
        # response = Resolwe._upload_file(resolwe_mock, self.file_path)

        self.assertIsNone(response)
        self.assertEqual(resolwe_mock.logger.warning.call_count, 4)

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_one_bad_other_ok(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)
        resolwe_mock.uploader = MagicMock(spec=Uploader)
        requests_response = {"files": [{"temp": "fake_name"}]}
        response_ok = MagicMock(
            status_code=200, **{"json.return_value": requests_response}
        )
        response_fails = MagicMock(status_code=400)
        # Immitate response form server - one status 400, but other 200:
        resolwe_mock.session.post.side_effect = [
            response_fails,
            response_ok,
            response_ok,
        ]
        response = Uploader(resolwe_mock)._upload_local(self.file_path)

        self.assertEqual(response, "fake_name")
        self.assertEqual(resolwe_mock.logger.warning.call_count, 1)


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.file_list = ["/the/first/file.txt", "/the/second/file.py"]
        self.config = {
            "url": "http://some/url",
            "auth": MagicMock(),
            "logger": MagicMock(),
        }
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.isdir(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_fail_if_bad_dir(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)

        message = "Download directory does not exist: .*"
        with self.assertRaisesRegex(ValueError, message):
            Resolwe._download_files(
                resolwe_mock, files=self.file_list, download_dir="/does/not/exist/"
            )

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_empty_file_list(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)

        Resolwe._download_files(resolwe_mock, files=[], download_dir=self.tmp_dir)

        resolwe_mock.logger.info.assert_called_once_with("No files to download.")

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_bad_response(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)
        response = {"raise_for_status.side_effect": Exception("abc")}
        sizes = [{"name": "file.txt", "size": 1, "type": "file", "md5": 123}]
        resolwe_mock.session.get.side_effect = [
            MagicMock(content=json.dumps(sizes)),
            MagicMock(ok=False, **response),
        ]

        with self.assertRaisesRegex(Exception, "abc"):
            Resolwe._download_files(
                resolwe_mock,
                files=self.file_list[:1],
                download_dir=self.tmp_dir,
            )
        self.assertEqual(resolwe_mock.logger.info.call_count, 2)

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_good_response(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)

        size_file1 = [
            {
                "name": "file.txt",
                "size": 1,
                "type": "file",
                "md5": "e3cdf70a99c1d6890c54ad56bd4a5de1",
            }
        ]
        size_file2 = [
            {
                "name": "file.py",
                "size": 2,
                "type": "file",
                "md5": "f1a8bf29b1df09dd9082f8f8fece0839",
            }
        ]
        resolwe_mock.session.get.side_effect = [
            MagicMock(content=json.dumps(size_file1)),
            MagicMock(ok=True, **{"iter_content.return_value": [b"11", b"12", b"13"]}),
            MagicMock(content=json.dumps(size_file2)),
            MagicMock(ok=True, **{"iter_content.return_value": [b"21", b"22", b"23"]}),
        ]

        Resolwe._download_files(
            resolwe_mock,
            files=self.file_list,
            download_dir=self.tmp_dir,
            show_progress=False,
        )
        self.assertEqual(resolwe_mock.logger.info.call_count, 3)

    def _write_local_file(self, file_uri, content):
        """Create a local copy of the given file and return its path."""
        # The data id is stripped from the file path on download.
        file_path = os.path.dirname(file_uri).split("/", 1)[1]
        directory = os.path.join(self.tmp_dir, file_path)
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, os.path.basename(file_uri))
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_skip_existing_intact_file(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)
        content = b"111213"
        path = self._write_local_file(self.file_list[0], content)

        listing = [
            {
                "name": "file.txt",
                "size": len(content),
                "type": "file",
                "md5": hashlib.md5(content).hexdigest(),
            }
        ]
        resolwe_mock.session.get.side_effect = [MagicMock(content=json.dumps(listing))]

        Resolwe._download_files(
            resolwe_mock,
            files=self.file_list[:1],
            download_dir=self.tmp_dir,
            show_progress=False,
            skip_existing=True,
        )

        # Only the directory listing is fetched, the file itself is not.
        self.assertEqual(resolwe_mock.session.get.call_count, 1)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), content)
        resolwe_mock.logger.info.assert_called_with(
            "* %s (skipped, already downloaded)", os.path.join("the/first", "file.txt")
        )

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_skip_existing_corrupted_file(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)
        content = b"111213"
        path = self._write_local_file(self.file_list[0], b"truncated")

        listing = [
            {
                "name": "file.txt",
                "size": len(content),
                "type": "file",
                "md5": hashlib.md5(content).hexdigest(),
            }
        ]
        resolwe_mock.session.get.side_effect = [
            MagicMock(content=json.dumps(listing)),
            MagicMock(ok=True, **{"iter_content.return_value": [content]}),
        ]

        Resolwe._download_files(
            resolwe_mock,
            files=self.file_list[:1],
            download_dir=self.tmp_dir,
            show_progress=False,
            skip_existing=True,
        )

        # The local file does not match the checksum, so it is downloaded again.
        self.assertEqual(resolwe_mock.session.get.call_count, 2)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), content)

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_skip_existing_missing_file(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)
        content = b"111213"

        listing = [
            {
                "name": "file.txt",
                "size": len(content),
                "type": "file",
                "md5": hashlib.md5(content).hexdigest(),
            }
        ]
        resolwe_mock.session.get.side_effect = [
            MagicMock(content=json.dumps(listing)),
            MagicMock(ok=True, **{"iter_content.return_value": [content]}),
        ]

        Resolwe._download_files(
            resolwe_mock,
            files=self.file_list[:1],
            download_dir=self.tmp_dir,
            show_progress=False,
            skip_existing=True,
        )

        self.assertEqual(resolwe_mock.session.get.call_count, 2)
        with open(os.path.join(self.tmp_dir, "the/first/file.txt"), "rb") as handle:
            self.assertEqual(handle.read(), content)

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_skip_existing_html_file(self, resolwe_mock):
        """Html files are always downloaded, their checksums are not verified."""
        resolwe_mock.configure_mock(**self.config)
        file_uri = "/the/first/report.html"
        content = b"<html></html>"
        path = self._write_local_file(file_uri, content)

        listing = [
            {
                "name": "report.html",
                "size": len(content),
                "type": "file",
                "md5": "checksum-that-cannot-be-reproduced-locally",
            }
        ]
        resolwe_mock.session.get.side_effect = [
            MagicMock(content=json.dumps(listing)),
            MagicMock(ok=True, **{"iter_content.return_value": [content]}),
        ]

        Resolwe._download_files(
            resolwe_mock,
            files=[file_uri],
            download_dir=self.tmp_dir,
            show_progress=False,
            skip_existing=True,
        )

        self.assertEqual(resolwe_mock.session.get.call_count, 2)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), content)

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_intact_file_downloaded_by_default(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)
        content = b"111213"
        self._write_local_file(self.file_list[0], content)

        listing = [
            {
                "name": "file.txt",
                "size": len(content),
                "type": "file",
                "md5": hashlib.md5(content).hexdigest(),
            }
        ]
        resolwe_mock.session.get.side_effect = [
            MagicMock(content=json.dumps(listing)),
            MagicMock(ok=True, **{"iter_content.return_value": [content]}),
        ]

        Resolwe._download_files(
            resolwe_mock,
            files=self.file_list[:1],
            download_dir=self.tmp_dir,
            show_progress=False,
        )

        self.assertEqual(resolwe_mock.session.get.call_count, 2)

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_custom_file_name(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)
        content = b"111213"

        listing = [
            {
                "name": "file.txt",
                "size": len(content),
                "type": "file",
                "md5": hashlib.md5(content).hexdigest(),
            }
        ]
        resolwe_mock.session.get.side_effect = [
            MagicMock(content=json.dumps(listing)),
            MagicMock(ok=True, **{"iter_content.return_value": [content]}),
        ]

        Resolwe._download_files(
            resolwe_mock,
            files=self.file_list[:1],
            download_dir=self.tmp_dir,
            show_progress=False,
            custom_file_name="renamed.txt",
        )

        # The size and the checksum are looked up under the name on the server,
        # while the local copy gets the custom name.
        with open(os.path.join(self.tmp_dir, "the/first/renamed.txt"), "rb") as handle:
            self.assertEqual(handle.read(), content)
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp_dir, "the/first/file.txt"))
        )

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_skip_existing_custom_file_name(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)
        content = b"111213"
        # The name of the local copy decides whether the file is skipped.
        self._write_local_file("/the/first/renamed.txt", content)

        listing = [
            {
                "name": "file.txt",
                "size": len(content),
                "type": "file",
                "md5": hashlib.md5(content).hexdigest(),
            }
        ]
        resolwe_mock.session.get.side_effect = [MagicMock(content=json.dumps(listing))]

        Resolwe._download_files(
            resolwe_mock,
            files=self.file_list[:1],
            download_dir=self.tmp_dir,
            show_progress=False,
            skip_existing=True,
            custom_file_name="renamed.txt",
        )

        # Only the directory listing is fetched, the file itself is not.
        self.assertEqual(resolwe_mock.session.get.call_count, 1)
        resolwe_mock.logger.info.assert_called_with(
            "* %s (skipped, already downloaded)",
            os.path.join("the/first", "renamed.txt"),
        )

    @patch("resdk.resolwe.Resolwe", spec=True)
    def test_custom_file_name_with_multiple_files(self, resolwe_mock):
        resolwe_mock.configure_mock(**self.config)

        message = "custom_file_name can only be given for a single file, got 2."
        with self.assertRaisesRegex(ValueError, message):
            Resolwe._download_files(
                resolwe_mock,
                files=self.file_list,
                download_dir=self.tmp_dir,
                custom_file_name="renamed.txt",
            )

        resolwe_mock.session.get.assert_not_called()


class TestResAuth(unittest.TestCase):
    @patch("resdk.resolwe.ResAuth", spec=True)
    def setUp(self, auth_mock):
        auth_mock.interactive_login_url = "https://url.com/remote-auth/"
        auth_mock.configure_mock(sessionid=None, csrftoken=None)
        self.auth_mock = auth_mock

    def test_init(self):
        ResAuth.__init__(self.auth_mock, "uname", "pw", "https://url.com")
        self.auth_mock.automatic_login.assert_called_once_with("uname", "pw")
        self.auth_mock.interactive_login.assert_not_called()

    def test_interactive_fallback_no_username(self):
        """Only fall back to automatic login if username is not provided."""
        ResAuth.__init__(
            self.auth_mock,
            username="test",
            password="pass",
            url="https://url.com",
            interactive=True,
        )
        self.auth_mock.interactive_login.assert_not_called()
        self.auth_mock.reset_mock()

        # Attempt interactive login only when no username is given.
        ResAuth.__init__(
            self.auth_mock, password="pw", url="https://url.com", interactive=True
        )
        self.auth_mock.interactive_login.assert_called_once_with()

    @patch("resdk.resolwe.requests")
    @patch("resdk.resolwe.webbrowser")
    @patch("resdk.resolwe.print")
    @patch("resdk.resolwe.time")
    def test_interactive_login(
        self, time_mock, print_mock, webbrowser_mock, requests_mock
    ):
        requests_mock.get.return_value = MagicMock(
            status_code=200, **{"json.return_value": {"auth_id": "123"}}
        )
        requests_mock.Session.return_value.get.side_effect = [
            MagicMock(status_code=204),
            MagicMock(
                status_code=200,
                json=MagicMock(
                    return_value={"csrftoken": "my-token", "sessionid": "my-id"}
                ),
            ),
        ]
        self.assertDictEqual(
            ResAuth.interactive_login(self.auth_mock),
            {"csrftoken": "my-token", "sessionid": "my-id"},
        )
        webbrowser_mock.open.assert_called_once_with("https://url.com/remote-auth/")
        requests_mock.get.assert_called_once_with(
            "https://url.com/remote-auth/auth-id/"
        )
        print_mock.assert_called_once()
        time_mock.sleep.assert_called_once_with(1)
        self.assertEqual(requests_mock.Session.return_value.get.call_count, 2)
        requests_mock.Session.return_value.get.assert_called_with(
            "https://url.com/remote-auth/poll/"
        )

    @patch("resdk.resolwe.requests")
    def test_automatic_login(self, requests_mock):
        requests_mock.post.return_value = MagicMock(status_code=204)
        requests_mock.post.return_value.cookies.get_dict.return_value = {
            "csrftoken": "my-token",
            "sessionid": "my-id",
        }
        self.auth_mock.logger = MagicMock()
        self.auth_mock.automatic_login_url = "http://www.abc.com/saml-auth/api-login/"
        cookies = ResAuth.automatic_login(
            self.auth_mock, username="me", password="pass"
        )
        self.auth_mock.logger.info.assert_called_once()
        self.assertDictEqual(cookies, {"csrftoken": "my-token", "sessionid": "my-id"})

    def test_call(self):
        res_auth = MagicMock(
            spec=ResAuth, sessionid=None, csrftoken=None, url="www.abc.com"
        )
        resp = ResAuth.__call__(res_auth, MagicMock(headers={}))
        self.assertDictEqual(resp.headers, {"referer": "www.abc.com"})

        res_auth = MagicMock(
            spec=ResAuth,
            cookies={"csrftoken": "my-token", "sessionid": "my-id"},
            url="abc.com",
        )
        resp = ResAuth.__call__(res_auth, MagicMock(headers={}))
        self.assertDictEqual(
            resp.headers,
            {"X-CSRFToken": "my-token", "referer": "abc.com"},
        )


if __name__ == "__main__":
    unittest.main()

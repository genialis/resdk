"""Data resource."""

import json
import logging
import os
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urljoin

from resdk.constants import CHUNK_SIZE

from ..utils.decorators import assert_object_exists
from .background_task import BackgroundTask
from .base import BaseResolweResource
from .fields import (
    BooleanField,
    DataSource,
    DateTimeField,
    DictField,
    DictResourceField,
    FieldAccessType,
    IntegerField,
    StringField,
)
from .utils import flatten_field

if TYPE_CHECKING:
    from resdk.resolwe import Resolwe


class Data(BaseResolweResource):
    """Resolwe Data resource.

    :param resolwe: Resolwe instance
    :type resolwe: Resolwe object
    :param model_data: Resource model data

    """

    endpoint = "data"
    full_search_paramater = "text"

    checksum = StringField(access_type=FieldAccessType.READ_ONLY)
    descriptor_dirty = BooleanField(access_type=FieldAccessType.READ_ONLY)
    duplicated = DateTimeField(access_type=FieldAccessType.READ_ONLY)
    process_cores = IntegerField(access_type=FieldAccessType.READ_ONLY)
    process_error = StringField(access_type=FieldAccessType.READ_ONLY, many=True)
    process_info = StringField(access_type=FieldAccessType.READ_ONLY, many=True)
    process_memory = IntegerField(access_type=FieldAccessType.READ_ONLY)
    process_progress = IntegerField(access_type=FieldAccessType.READ_ONLY)
    process_rc = IntegerField(access_type=FieldAccessType.READ_ONLY)
    process_warning = StringField(access_type=FieldAccessType.READ_ONLY, many=True)
    output = DictField(access_type=FieldAccessType.READ_ONLY)
    scheduled = DateTimeField(access_type=FieldAccessType.READ_ONLY)
    size = IntegerField(access_type=FieldAccessType.READ_ONLY)
    status = StringField(access_type=FieldAccessType.READ_ONLY)

    input = DictField(access_type=FieldAccessType.UPDATE_PROTECTED)
    process = DictResourceField(
        resource_class_name="Process",
        property_name="slug",
        access_type=FieldAccessType.UPDATE_PROTECTED,
    )
    collection = DictResourceField(
        resource_class_name="Collection", access_type=FieldAccessType.WRITABLE
    )
    descriptor = DictField(access_type=FieldAccessType.WRITABLE)
    descriptor_schema = DictResourceField(
        resource_class_name="DescriptorSchema",
        property_name="slug",
        access_type=FieldAccessType.WRITABLE,
    )
    process_resources = DictField(access_type=FieldAccessType.WRITABLE)

    sample = DictResourceField(
        resource_class_name="Sample",
        server_field_name="entity",
        access_type=FieldAccessType.WRITABLE,
    )
    tags = StringField(access_type=FieldAccessType.WRITABLE, many=True)
    started = DateTimeField(access_type=FieldAccessType.READ_ONLY)
    finished = DateTimeField(access_type=FieldAccessType.READ_ONLY)

    def __init__(self, resolwe: "Resolwe", **model_data: dict):
        """Initialize attributes."""
        self.logger = logging.getLogger(__name__)

        #: ``ResolweQuery`` containing parent ``Data`` objects (lazy loaded)
        self._parents = None
        #: ``ResolweQuery`` containing child ``Data`` objects (lazy loaded)
        self._children = None

        #: process status - Possible values:
        #: UP (Uploading - for upload processes),
        #: RE (Resolving - computing input data objects)
        #: WT (Waiting - waiting for process since the queue is full)
        #: PP (Preparing - preparing the environment for processing)
        #: PR (Processing)
        #: OK (Done)
        #: ER (Error)
        #: DR (Dirty - Data is dirty)

        super().__init__(resolwe, **model_data)

    def _update_fields(
        self, payload: dict[str, Any], data_source: DataSource = DataSource.USER
    ):
        """Update fields of the local resource based on the server values."""
        # The payload contains collection information and sample information on the top
        # level. The collection also contains the sample information, but only as id.
        # Replace the id with the actual info.
        if collection_payload := payload.get("collection"):
            if sample_payload := payload.get("entity"):
                sample_payload["collection"] = collection_payload
        self._children = None
        self._parents = None
        super()._update_fields(payload, data_source)

    @property
    @assert_object_exists
    def parents(self):
        """Get parents of this Data object."""
        if self._parents is None:
            ids = [
                item["id"]
                for item in self.resolwe.api.data(self.id).parents.get(fields="id")
            ]
            if not ids:
                return []
            # Resolwe querry must be returned:
            self._parents = self.resolwe.data.filter(id__in=ids)

        return self._parents

    @property
    @assert_object_exists
    def children(self):
        """Get children of this Data object."""
        if self._children is None:
            ids = [
                item["id"]
                for item in self.resolwe.api.data(self.id).children.get(fields="id")
            ]
            if not ids:
                return []
            # Resolwe querry must be returned:
            self._children = self.resolwe.data.filter(id__in=ids)

        return self._children

    def restart(
        self,
        storage: Optional[int] = None,
        memory: Optional[int] = None,
        cores: Optional[int] = None,
    ):
        """Restart the data object.

        The units for storage are gigabytes and for memory are megabytes.

        The resources that are not specified (or set no None) are reset to their
        default values.
        """
        overrides = {
            key: value
            for key, value in {
                "storage": storage,
                "memory": memory,
                "cores": cores,
            }.items()
            if value is not None
        }
        self.resolwe.api.data(self.id).restart.post(
            {"resource_overrides": {self.id: overrides}}
        )

    def _files_dirs(
        self,
        field_type: str,
        file_name: Optional[str] = None,
        field_name: Optional[str] = None,
    ) -> list[str]:
        """Get list of downloadable fields."""
        download_list = []

        def put_in_download_list(elm, fname):
            """Append only files od dirs with equal name."""
            if field_type in elm:
                if file_name is None or file_name == elm[field_type]:
                    download_list.append(elm[field_type])
            else:
                raise KeyError(
                    "Item {} does not contain '{}' key.".format(fname, field_type)
                )

        if field_name and not field_name.startswith("output."):
            field_name = "output.{}".format(field_name)

        flattened = flatten_field(self.output, self.process.output_schema, "output")
        for ann_field_name, ann in flattened.items():
            if (
                ann_field_name.startswith("output")
                and (field_name is None or field_name == ann_field_name)
                and ann["value"] is not None
            ):
                if ann["type"].startswith("basic:{}:".format(field_type)):
                    put_in_download_list(ann["value"], ann_field_name)
                elif ann["type"].startswith("list:basic:{}:".format(field_type)):
                    for element in ann["value"]:
                        put_in_download_list(element, ann_field_name)

        return download_list

    def _get_dir_files(self, dir_name: str) -> list[str]:
        files_list: list[str] = []
        dir_list: list[str] = []

        dir_url = urljoin(self.resolwe.url, "data/{}/{}".format(self.id, dir_name))
        if not dir_url.endswith("/"):
            dir_url += "/"
        assert self.resolwe.session is not None
        response = self.resolwe.session.get(dir_url, auth=self.resolwe.auth)
        response = json.loads(response.content.decode("utf-8"))

        assert isinstance(response, list), "Invalid response from server."
        for obj in response:
            assert isinstance(obj, dict), "Invalid response from server."
            obj_path = "{}/{}".format(dir_name, obj["name"])
            if obj["type"] == "directory":
                dir_list.append(obj_path)
            else:
                files_list.append(obj_path)

        if dir_list:
            for new_dir in dir_list:
                files_list.extend(self._get_dir_files(new_dir))

        return files_list

    @assert_object_exists
    def files(
        self, file_name: Optional[str] = None, field_name: Optional[str] = None
    ) -> list[str]:
        """Get list of downloadable file fields.

        Filter files by file name or output field.
        """
        file_list = self._files_dirs("file", file_name, field_name)

        for dir_name in self._files_dirs("dir", file_name, field_name):
            file_list.extend(self._get_dir_files(dir_name))

        return file_list

    def download(
        self,
        file_name: Optional[str] = None,
        field_name: Optional[str] = None,
        download_dir: Optional[str] = None,
        show_progress: bool = True,
        return_dir_names: bool = False,
        skip_existing: bool = False,
        custom_asset_name: Optional[str] = None,
    ) -> list[str]:
        """Download Data object's files and directories.

        Download files and directories from the Resolwe server to the
        download directory (defaults to the current working directory).

        Data objects can contain multiple files and directories. All are
        downloaded by default, but may be filtered by name or output
        field:

        * re.data.get(42).download(file_name='alignment7.bam')
        * re.data.get(42).download(field_name='bam')

        The function returns a list of downloaded file names. In case the
        Data object contains directories, the user can specify to return directory names
        instead of file names contained in those directories via the return_dir_names argument.
        WARNING: If neither file_name nor field_name is specified and return_dir_names is set
        to True, the method will download both directories and files when the Data object
        contains both. However, the returned list will include only the directory names.

        Set skip_existing to True to skip the download of files that are already present
        in the download directory and whose md5 checksums match the checksums of the
        files on the server. Files with the ``.html`` extension are always downloaded,
        since their checksums cannot be verified locally. The returned list of names is
        not affected by skipping: it always contains all the requested assets.

        Set custom_asset_name to save the downloaded asset under a different name, which
        is useful when the same output field is downloaded from several Data objects into
        a single directory:

        * re.data.get(42).download(field_name='vcf', custom_asset_name='sample1.vcf.gz')

        A custom name applies to a single asset, so exactly one file or one directory
        must be matched. The returned list then contains the custom name only.
        """
        if file_name and field_name:
            raise ValueError("Only one of file_name or field_name may be given.")

        file_names = self.files(file_name, field_name)
        files = ["{}/{}".format(self.id, fname) for fname in file_names]

        if not files:
            raise ValueError(
                f"Data object contains no files with "
                f"{'file name: ' + repr(file_name) if file_name else 'field name: ' + repr(field_name)}."
            )

        dir_names = self._files_dirs("dir", file_name, field_name)

        if custom_asset_name:
            # Files of a downloaded directory are listed in file_names as well,
            # so a matched directory counts as a single asset.
            matched_assets = dir_names if dir_names else file_names
            if len(matched_assets) != 1:
                raise ValueError(
                    f"A 'custom_asset_name' can only be applied when downloading "
                    f"exactly one asset. Found {matched_assets} matching assets "
                    f"instead."
                )
            return self._download_renamed(
                custom_asset_name=custom_asset_name,
                files=files,
                source_dir_name=dir_names[0] if dir_names else None,
                download_dir=download_dir,
                show_progress=show_progress,
                skip_existing=skip_existing,
            )

        self.resolwe._download_files(
            files=files,
            download_dir=download_dir,
            show_progress=show_progress,
            skip_existing=skip_existing,
        )

        return dir_names if (dir_names and return_dir_names) else file_names

    def _download_renamed(
        self,
        custom_asset_name: str,
        files: list[str],
        source_dir_name: Optional[str],
        download_dir: Optional[str],
        show_progress: bool,
        skip_existing: bool,
    ) -> list[str]:
        """Download a single asset and save it as custom_asset_name.

        A file is written under the custom name directly, while a directory
        has to be downloaded under its own name first and renamed afterwards.
        """
        if source_dir_name is None:
            self.resolwe._download_files(
                files=files,
                download_dir=download_dir,
                show_progress=show_progress,
                skip_existing=skip_existing,
                custom_file_name=custom_asset_name,
            )
            return [custom_asset_name]

        download_dir = download_dir or os.getcwd()
        destination = os.path.join(download_dir, custom_asset_name)

        # Unlike a file, a downloaded directory cannot be verified against a
        # checksum, so only its existence is checked. Renaming onto an existing
        # directory would fail anyway.
        if skip_existing and os.path.exists(destination):
            self.logger.info("* %s (skipped, already downloaded)", custom_asset_name)
            return [custom_asset_name]

        self.resolwe._download_files(
            files=files,
            download_dir=download_dir,
            show_progress=show_progress,
            skip_existing=skip_existing,
        )

        self.logger.info(
            "Renaming the downloaded asset from '%s' to '%s'.",
            source_dir_name,
            custom_asset_name,
        )
        os.rename(os.path.join(download_dir, source_dir_name), destination)

        return [custom_asset_name]

    def download_and_rename(
        self,
        custom_asset_name: str,
        overwrite_existing: bool = False,
        field_name: Optional[str] = None,
        file_name: Optional[str] = None,
        download_dir: Optional[str] = None,
    ):
        """Download and rename an asset from the Data object.

        .. deprecated::
            Use ``download`` with the ``custom_asset_name`` argument instead.
            Note that a file is only kept when its md5 checksum matches the
            checksum on the server, while this method keeps any existing file.
        """
        self.download(
            file_name=file_name,
            field_name=field_name,
            download_dir=download_dir,
            skip_existing=not overwrite_existing,
            custom_asset_name=custom_asset_name,
        )

    def stdout(self) -> str:
        """Return process standard output (stdout.txt file content).

        Fetch stdout.txt file from the corresponding Data object and return the
        file content as string. The string can be long and ugly.

        :rtype: string

        """
        if self.process.type.startswith("data:workflow"):
            raise ValueError("stdout.txt file is not available for workflows.")
        output = b""
        url = urljoin(self.resolwe.url, "data/{}/stdout.txt".format(self.id))
        assert self.resolwe.session is not None
        response = self.resolwe.session.get(url, stream=True, auth=self.resolwe.auth)
        if not response.ok and self.status in ["UP", "RE", "WT", "PP", "DR"]:
            raise ValueError(
                f"stdout.txt file is not available for Data with status {self.status}"
            )
        if not response.ok:
            response.raise_for_status()
        else:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                output += chunk

        return output.decode("utf-8")

    @assert_object_exists
    def duplicate(self) -> "Data":
        """Duplicate (make copy of) ``data`` object.

        :return: Duplicated data object
        """
        task_data = self.api().duplicate.post({"ids": [self.id]})
        background_task = BackgroundTask(
            resolwe=self.resolwe, initial_data_source=DataSource.SERVER, **task_data
        )
        return self.resolwe.data.get(id__in=background_task.result())

"""Collection resources."""

import logging
from typing import TYPE_CHECKING, Iterable, Optional
from urllib.parse import urljoin

from resdk.shortcuts.collection import CollectionRelationsMixin

from ..utils.decorators import assert_object_exists
from .background_task import BackgroundTask
from .base import BaseResolweResource
from .data import Data
from .fields import (
    BooleanField,
    DataSource,
    DateTimeField,
    DictField,
    DictResourceField,
    FieldAccessType,
    QueryRelatedField,
    StringField,
)
from .utils import _get_billing_account_id

if TYPE_CHECKING:
    from resdk.resolwe import Resolwe
    from resdk.resources.annotations import AnnotationField
    from resdk.resources.predictions import PredictionField


class BaseCollection(BaseResolweResource):
    """Abstract collection resource.

    One and only one of the identifiers (slug, id or model_data)
    should be given.

    :param resolwe: Resolwe instance
    :type resolwe: Resolwe object
    :param model_data: Resource model data

    """

    full_search_paramater = "text"
    delete_warning_single = (
        "Do you really want to delete {} and all of it's content?[yN]"
    )
    delete_warning_bulk = (
        "Do you really want to delete {} objects and all of their content?[yN]"
    )

    descriptor_dirty = BooleanField()
    duplicated = DateTimeField()

    description = StringField(access_type=FieldAccessType.WRITABLE)
    descriptor = DictField(access_type=FieldAccessType.WRITABLE)
    descriptor_schema = DictResourceField(
        resource_class_name="DescriptorSchema",
        property_name="slug",
        access_type=FieldAccessType.WRITABLE,
    )
    settings = DictField(access_type=FieldAccessType.WRITABLE)
    tags = StringField(access_type=FieldAccessType.WRITABLE, many=True)

    def __init__(self, resolwe: "Resolwe", **model_data: dict):
        """Initialize attributes."""
        super().__init__(resolwe, **model_data)

        self.logger = logging.getLogger(__name__)

    @property
    def data(self) -> Iterable["Data"]:
        """Return list of attached Data objects."""
        raise NotImplementedError("This should be implemented in subclass")

    def update(self):
        """Clear cache and update resource fields from the server."""
        super().update()

    def data_types(self) -> list[str]:
        """Return a list of data types (process_type)."""
        return sorted({datum.process.type for datum in self.data})

    def files(self, file_name: Optional[str] = None, field_name: Optional[str] = None):
        """Return list of files in resource."""
        file_list: list[str] = []
        for data in self.data:
            file_list.extend(
                fname
                for fname in data.files(file_name=file_name, field_name=field_name)
            )

        return file_list

    def download(
        self,
        file_name: Optional[str] = None,
        field_name: Optional[str] = None,
        download_dir: Optional[str] = None,
        skip_existing: bool = False,
    ):
        """Download output files of associated Data objects.

        Download files from the Resolwe server to the download
        directory (defaults to the current working directory).

        Collections can contain multiple Data objects and Data objects
        can contain multiple files. All files are downloaded by default,
        but may be filtered by file name or Data object type:

        * re.collection.get(42).download(file_name='alignment7.bam')
        * re.collection.get(42).download(data_type='bam')

        Set skip_existing to True to skip the download of files that are
        already present in the download directory and whose md5 checksums
        match the checksums of the files on the server. Files with the
        ``.html`` extension are always downloaded, since their checksums
        cannot be verified locally.
        """
        files = []

        if field_name and not isinstance(field_name, str):
            raise ValueError("Invalid argument value `field_name`.")

        for data in self.data:
            data_files = data.files(file_name, field_name)
            files.extend("{}/{}".format(data.id, file_name) for file_name in data_files)

        self.resolwe._download_files(files, download_dir, skip_existing=skip_existing)


class Collection(CollectionRelationsMixin, BaseCollection):
    """Resolwe Collection resource.

    :param resolwe: Resolwe instance
    :type resolwe: Resolwe object
    :param model_data: Resource model data

    """

    endpoint = "collection"

    data = QueryRelatedField("Data")
    samples = QueryRelatedField("Sample")
    relations = QueryRelatedField("Relation")

    def __init__(self, resolwe: "Resolwe", **model_data: dict):
        """Initialize attributes."""
        super().__init__(resolwe, **model_data)
        self.logger = logging.getLogger(__name__)
        self._annotation_fields = None
        self._prediction_fields = None

    @assert_object_exists
    def duplicate(self) -> "Collection":
        """Duplicate (make copy of) ``collection`` object.

        :return: Duplicated collection
        """
        task_data = self.api().duplicate.post({"ids": [self.id]})
        background_task = BackgroundTask(
            resolwe=self.resolwe, **task_data, initial_data_source=DataSource.SERVER
        )
        return self.resolwe.collection.get(id__in=background_task.result())

    @assert_object_exists
    def assign_to_billing_account(self, billing_account_name: str):
        """Assign given collection to a billing account."""
        billing_account_id = _get_billing_account_id(self.resolwe, billing_account_name)

        # Assign collection to a billing account
        response = self.resolwe.session.post(
            urljoin(
                self.resolwe.url, f"api/billingaccount/{billing_account_id}/collection"
            ),
            data={"collection_id": self.id},
        )
        response.raise_for_status()

    def set_annotation_fields(self, annotation_fields: Iterable["AnnotationField"]):
        """Set collection annotation fields.

        The change is applied instantly.
        """
        self.api(self.id).set_annotation_fields.post(
            {"annotation_fields": [{"id": field.id} for field in annotation_fields]}
        )
        self._annotation_fields = None

    def get_annotation_fields(self) -> Iterable["AnnotationField"]:
        """Get annotation fields associated with the collection."""
        if self._annotation_fields is None:
            self._annotation_fields = self.resolwe.annotation_field.filter(
                collection=self.id
            )
        assert self._annotation_fields is not None
        return self._annotation_fields

    def set_prediction_fields(self, prediction_fields: Iterable["PredictionField"]):
        """Set collection prediction fields.

        The change is applied instantly.
        """
        self.api(self.id).set_prediction_fields.post(
            {"prediction_fields": [{"id": field.id} for field in prediction_fields]}
        )
        self._prediction_fields = None

    def get_prediction_fields(self) -> Iterable["PredictionField"]:
        """Get prediction fields associated with the collection."""
        if self._prediction_fields is None:
            self._prediction_fields = self.resolwe.prediction_field.filter(
                collections=self.id
            )
        assert self._prediction_fields is not None
        return self._prediction_fields

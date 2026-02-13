""".. Ignore pydocstyle D400.

=============
Resolwe Query
=============

.. autoclass:: resdk.ResolweQuery
   :members:

"""

import collections
import copy
import logging
import operator
from typing import TYPE_CHECKING, Iterable, Union

import tqdm

from resdk.resources import DescriptorSchema, Process
from resdk.resources.base import BaseResource
from resdk.resources.fields import DataSource, DictResourceField, FieldStatus

if TYPE_CHECKING:
    from resdk import Resolwe
    from resdk.resources import AnnotationField, PredictionField


class ResolweQuery:
    """Query resource endpoints.

    A Resolwe instance (for example "res") has several endpoints:

        - res.data
        - res.collection
        - res.sample
        - res.process
        - ...

    Each such endpoint is an instance of the ResolweQuery class. ResolweQuery
    supports queries on corresponding objects, for example:

    .. code-block:: python

        res.data.get(42)  # return Data object with ID 42.
        res.sample.filter(contributor=1)  # return all samples made by contributor 1

    This object is lazy loaded which means that actual request is made only
    when needed. This enables composing multiple filters, for example:

    .. code-block:: python

        res.data.filter(contributor=1).filter(name='My object')

    is the same as:

    .. code-block:: python

        res.data.filter(contributor=1, name='My object')

    This is especially useful, because all endpoints at Resolwe instance
    are such queries and can be filtered further before transferring
    any data.

    To get a list of all supported query parameters, use one that does
    not exist and you will et a helpful error message with a list of
    allowed ones.

    .. code-block:: python

        res.data.filter(foo="bar")

    """

    _cache = None
    _count = (
        None  # number of objects in current query (without applied limit and offset)
    )
    _limit = None
    _offset = None
    _filters = None

    resolwe = None
    resource = None
    slug_field = None
    endpoint = None
    api = None
    logger = None

    def __init__(
        self, resolwe: "Resolwe", resource: type[BaseResource], slug_field: str = "slug"
    ):
        """Initialize attributes."""
        self.resolwe = resolwe
        self.resource = resource
        self.slug_field = slug_field
        self.endpoint = resource.query_endpoint or resource.endpoint
        self.api = operator.attrgetter(self.endpoint)(resolwe.api)

        self._filters = collections.defaultdict(list)

        self.logger = logging.getLogger(__name__)

    def _non_string_iterable(self, item: Iterable) -> bool:
        """Return True when item is iterable but not string."""
        return isinstance(item, collections.abc.Iterable) and not isinstance(item, str)

    def __getitem__(
        self, index: Union[slice, int]
    ) -> Union["BaseResource", "ResolweQuery"]:
        """Retrieve an item or slice from the set of results."""
        if not isinstance(index, (slice, int)):
            raise TypeError
        if (
            (not isinstance(index, slice) and index < 0)
            or (
                isinstance(index, slice) and index.start is not None and index.start < 0
            )
            or (isinstance(index, slice) and index.stop is not None and index.stop < 0)
        ):
            raise ValueError("Negative indexing is not supported.")
        if isinstance(index, slice) and index.step is not None:
            raise ValueError("`step` parameter in slice is not supported")

        if self._cache is not None:
            return self._cache[index]

        new_query = self._clone()

        if isinstance(index, slice):
            if self._offset or self._limit:
                raise NotImplementedError("You cannot slice already sliced query.")

            start = 0 if index.start is None else int(index.start)
            stop = (
                1000000 if index.stop is None else int(index.stop)
            )  # default to something big
            new_query._offset = start
            new_query._limit = stop - start
            return new_query

        new_query._offset = self._offset + index if self._offset else index
        new_query._limit = 1

        query_list = list(new_query)
        if not query_list:
            raise IndexError("list index out of range")
        return query_list[0]

    def __iter__(self):
        """Return iterator over the current object."""
        self._fetch()
        return iter(self._cache)

    def __repr__(self) -> str:
        """Return string representation of the current object."""
        self._fetch()
        rep = "[{}]".format(",\n ".join(str(obj) for obj in self._cache))
        return rep

    def __len__(self) -> int:
        """Return length of results of current query."""
        return self.count()

    def _clone(self) -> "ResolweQuery":
        """Return copy of current object with empty cache."""
        new_obj = self.__class__(self.resolwe, self.resource)
        new_obj._filters = copy.deepcopy(self._filters)
        new_obj._limit = self._limit
        new_obj._offset = self._offset
        return new_obj

    def _dehydrate_resources(self, obj):
        """Iterate through object and replace all objects with their ids."""
        if isinstance(obj, BaseResource):
            return obj.id
        if isinstance(obj, dict):
            return {key: self._dehydrate_resources(value) for key, value in obj.items()}
        if self._non_string_iterable(obj):
            return [self._dehydrate_resources(element) for element in obj]

        return obj

    def _add_filter(self, filter_: dict):
        """Add filtering parameters."""
        for key, value in filter_.items():
            # Make best-effort to rename fields to server fields.
            resource = self.resource
            filter_parts = key.split("__")
            for part_num in range(len(filter_parts)):
                resource_fields = resource._find_fields()
                part = filter_parts[part_num]
                # Bail out, we lost track of the book keeping.
                if part not in resource_fields:
                    break
                field = resource_fields[part]
                filter_parts[part_num] = resource_fields[part].server_field
                # Continue only if the field represents a resource.
                if not isinstance(field, DictResourceField):
                    break
                resource = field.Resource

            key = "__".join(filter_parts)
            value = self._dehydrate_resources(value)
            if self._non_string_iterable(value):
                value = ",".join(map(str, value))
            if self.resource.query_method == "GET":
                self._filters[key].append(value)
            elif self.resource.query_method == "POST":
                self._filters[key] = value
            else:
                raise NotImplementedError(
                    "Unsupported query_method: {}".format(self.resource.query_method)
                )

    def _compose_filters(self):
        """Convert filters to dict and add pagination filters."""
        filters = self._filters

        if self._limit is not None:
            filters["limit"] = self._limit
        if self._offset is not None:
            filters["offset"] = self._offset

        return dict(filters)

    def _populate_resource(self, data: dict) -> BaseResource:
        """Populate resource with given data."""
        return self.resource(
            resolwe=self.resolwe, **data, initial_data_source=DataSource.SERVER
        )

    def _fetch_data(self):
        """Fetch data from the server."""
        if self._cache is not None:
            # Already fetched.
            return

        filters = self._compose_filters()
        if self.resource.query_method == "GET":
            items = self.api.get(**filters)
        elif self.resource.query_method == "POST":
            items = self.api.post(filters)
        else:
            raise NotImplementedError(
                "Unsupported query_method: {}".format(self.resource.query_method)
            )

        # Extract data from paginated response
        if isinstance(items, dict) and "results" in items:
            count = items["count"]
            items = items["results"]
        # Store count when list of objects is received without limit.
        if isinstance(items, list) and self._limit is None:
            count = len(items)
        return items, count

    def _fetch(self):
        """Make request to the server and populate cache."""
        items, count = self._fetch_data()
        self._count = count
        self._cache = [self._populate_resource(data) for data in items]

    def clear_cache(self):
        """Clear cache."""
        self._cache = None
        self._count = None

    def count(self) -> int:
        """Return number of objects in current query."""
        if self._count is None:
            count_query = self._clone()
            count_query._offset = 0
            count_query._limit = 1
            count_query._fetch()
            self._count = count_query._count

        if self._limit is None:
            return self._count

        remaining = self._count - self._offset
        return max(0, min(self._limit, remaining))

    def values(self, fields: list[str]) -> list[dict]:
        """Return only values for the given fields.

        Used to reduce the data transferred from the server.

        TODO: Should we support pagination? How do we support it?
        """
        field_query = self.filter(fields=fields)
        items, _count = field_query._fetch_data()
        return items

    def get(self, *args, **kwargs):
        """Get object that matches given parameters.

        If only one non-keyworded argument is given, it is considered
        as id if it is number and as slug otherwise.

        :param uid: unique identifier - ID or slug
        :type uid: int for ID or string for slug

        :rtype: object of type self.resource

        :raises ValueError: if non-keyworded and keyworded arguments
            are combined or if more than one non-keyworded argument is
            given
        :raises LookupError: if none or more than one objects are
            returned

        """
        if args:
            if len(args) > 1:
                raise ValueError("Only one non-keyworded argument can be given")
            if kwargs:
                raise ValueError(
                    "Non-keyworded arguments cannot be combined with keyworded ones."
                )

            arg = args[0]
            kwargs = {"id": arg} if isinstance(arg, int) else {self.slug_field: arg}

        if self.slug_field in kwargs:
            if issubclass(self.resource, (Process, DescriptorSchema)):
                kwargs["ordering"] = kwargs.get("ordering", "-version")

            kwargs["limit"] = kwargs.get("limit", 1)

        new_query = self._clone()
        new_query._add_filter(kwargs)

        response = list(new_query)

        if not response:
            raise LookupError("Matching object does not exist.")

        if len(response) > 1:
            raise LookupError("get() returned more than one object.")

        return response[0]

    def create(self, **model_data: dict) -> BaseResource:
        """Return new instance of current resource."""
        resource = self.resource(self.resolwe, **model_data)
        resource.save()
        return resource

    def filter(self, **filters: dict) -> "ResolweQuery":
        """Return clone of current query with added given filters."""
        new_query = self._clone()
        new_query._add_filter(filters)
        return new_query

    def delete(self, force: bool = False):
        """Delete objects in current query.

        :param bool force: Do not trigger confirmation prompt. WARNING: Be
            sure that you really know what you are doing as deleted objects
            are not recoverable.

        """
        if force is not True:
            user_input = input(self.resource.delete_warning_bulk.format(self.count()))
            if user_input.strip().lower() != "y":
                return

        for obj in self:
            obj.delete(force=True)

        self.clear_cache()

    def all(self) -> "ResolweQuery":
        """Return copy of the current queryset.

        This is handy function to get newly created query without any
        filters.
        """
        return self._clone()

    def search(self, text: str) -> "ResolweQuery":
        """Full text search."""
        if not self.resource.full_search_paramater:
            raise NotImplementedError()

        new_query = self._clone()
        new_query._add_filter({self.resource.full_search_paramater: text})
        return new_query

    def iterate(
        self, chunk_size: int = 100, show_progress: bool = False
    ) -> Iterable["BaseResource"]:
        """
        Iterate through query.

        This can come handy when one wishes to iterate through hundreds or
        thousands of objects and would otherwise get "504 Gateway-timeout".

        The method cannot be used together with the following filters:
        limit, offset and ordering, and will raise a ``ValueError``.
        """
        # For simplicity, let's assume that this method will only be used when
        # limit and offset are not used as query parameters. We can relax
        # these limitations at some later point. Also, ordering is
        # prohibited for now.
        if self._limit is not None:
            raise ValueError(
                "Parameter 'limit' should not be used in combination with method iterate."
            )
        if self._offset is not None:
            raise ValueError(
                "Parameter 'offset' should not be used in combination with method iterate."
            )
        if "ordering" in self._filters:
            raise ValueError(
                "Specifying order in combination with method iterate is not allowed."
            )

        count = self.count()

        iterate_query = self._clone()
        min_id = 0
        obj_count = 0
        with tqdm.tqdm(total=count, disable=not show_progress) as pbar:
            while obj_count < count:
                for obj in iterate_query.filter(
                    id__gt=min_id, limit=chunk_size, ordering="id"
                ):
                    obj_count += 1
                    min_id = obj.id
                    pbar.update(1)
                    yield obj


class AnnotationFieldQuery(ResolweQuery):
    """Add additional method to the annotation field query."""

    def from_path(self, full_path: str) -> "AnnotationField":
        """Get the AnnotationField from full path.

        :raises LookupError: when field at the specified path does not exist.
        """
        group_name, field_name = full_path.split(".", maxsplit=1)
        return self.get(name=field_name, group__name=group_name)


class AnnotationValueQuery(ResolweQuery):
    """Populate Annotation fields with a single query."""

    def _fetch(self):
        """Make request to the server and populate cache.

        Fetch all values and their fields with 2 queries.
        """
        # Execute the query in a single request.
        super()._fetch()

        missing_fields = collections.defaultdict(set)
        missing_samples = collections.defaultdict(set)
        for value in self._cache:
            if value._sample_status == FieldStatus.LAZY:
                missing_samples[value._sample_original].add(value)
            if value._field_status == FieldStatus.LAZY:
                missing_fields[value._field_original].add(value)

        if missing_fields:
            # Get corresponding annotation field details in a single query and attach it to
            # the values.
            for field in self.resolwe.annotation_field.filter(
                id__in=missing_fields.keys()
            ).iterate():
                for value in missing_fields[field.id]:
                    value._field = field
                    value._field_original = field
                    value._field_status = FieldStatus.SET

        if missing_samples:
            # Get corresponding annotation field details in a single query and attach it to
            # the values.
            for sample in self.resolwe.sample.filter(
                id__in=missing_samples.keys()
            ).iterate():
                for value in missing_samples[sample.id]:
                    value._sample = sample
                    value._sample_original = sample
                    value._sample_status = FieldStatus.SET


class PredictionFieldQuery(ResolweQuery):
    """Add additional method to the prediction field query."""

    def from_path(self, full_path: str) -> "PredictionField":
        """Get the PredictionField from full path.

        :raises LookupError: when field at the specified path does not exist.
        """
        group_name, field_name = full_path.split(".", maxsplit=1)
        return self.get(name=field_name, group__name=group_name)


class PredictionValueQuery(ResolweQuery):
    """Populate prediction fields with a single query."""

    def _fetch(self):
        """Make request to the server and populate cache.

        Fetch all values and their fields with 2 queries.
        """
        # Execute the query in a single request.
        super()._fetch()

        missing = collections.defaultdict(list)
        for value in self._cache:
            if value._field is None:
                missing[value.field_id].append(value)

        if missing:
            # Get corresponding annotation field details in a single query and attach it to
            # the values.
            for field in self.resolwe.prediction_field.filter(
                id__in=missing.keys()
            ).iterate():
                for value in missing[field.id]:
                    value._field = field
                    value._original_values["field"] = field._original_values

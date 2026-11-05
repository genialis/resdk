"""Fields used in resources."""

import abc
import copy
import importlib
from datetime import datetime
from enum import Enum, auto
from sys import version_info
from typing import TYPE_CHECKING, Callable, Iterable, Optional

if TYPE_CHECKING:
    from resdk.resources.base import BaseResource

# Remove this when Python 3.11 is the minimum supported version.
date_parser = (
    datetime.fromisoformat
    if version_info >= (3, 11)
    else lambda value: datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")
)


class DataSource(Enum):
    """The origin of the data."""

    USER = auto()
    SERVER = auto()


class FieldAccessType(Enum):
    """Field access types."""

    READ_ONLY = auto()
    UPDATE_PROTECTED = auto()
    WRITABLE = auto()


class FieldStatus(Enum):
    """Field status."""

    UNSET = auto()
    SET = auto()
    LAZY = auto()


class BaseValueValidator(abc.ABC):
    """Base class for value validation."""

    @abc.abstractmethod
    def validate(self, value, field: "BaseField", instance: "BaseResource"):
        """Validate the value."""


class TypeValidator(BaseValueValidator):
    """Validator for type checking."""

    def __init__(self, accepted_types):
        """Initialize the instance."""
        self._accepted_types = accepted_types

    def validate(self, value, field: "BaseField", instance: "BaseResource"):
        """Validate the value.

        :raises ValueError: if the value is not valid.
        """
        if not isinstance(value, self._accepted_types):
            class_name = instance.__class__.__name__
            many = "a list of " if field._many else ""
            types = f"{', '.join(_type.__name__ for _type in self._accepted_types)}"
            raise ValueError(
                f"Type of '{class_name}.{field.public_name}' must be {many}'{types}'."
            )


class BaseField:
    """Class representing a base field."""

    def __init__(
        self,
        access_type=FieldAccessType.READ_ONLY,
        required=False,
        description="",
        server_field_name=None,
        assert_exists=False,
        allow_null=True,
        many=False,
        validators: Optional[Iterable[BaseValueValidator]] = None,
    ):
        """Initialize the instance.

        :attr access_type: access type of the field.
        :attr required: a boolean indicating the field is required.
        :attr server_field_name: sometimes a field name in the API is different from the
            public field name.
        :attr assert_exists: a boolean indicating if the instance must exist before
            accessing the field.
        :attr allow_null: a boolean indication if None value is allowed.
        :attr many: a boolean indicating if the field represents a single value or a
            list of values.
        :attr validators: value validators.
        """
        self._access_type = access_type
        # Sometimes the public field name and the name used in the API are different.
        # This field is used to indicate how the value must be serialized.
        self._server_field_name = server_field_name
        self._assert_exists = assert_exists
        self._many = many
        self.required = required
        self._allow_null = allow_null
        self._value_validators = validators or []
        self.description = description
        super().__init__()

    def __set_name__(self, owner: type["BaseResource"], name: str):
        """Store the public name and set attribute names."""
        self.public_name = name
        self._owner = owner
        self._value_attribute_name = f"_{name}"
        self._original_attribute_name = f"{self._value_attribute_name}_original"
        self._status_attribute_name = f"{self._value_attribute_name}_status"

    def _check_exists(self, instance: "BaseResource"):
        """Check if the instance exists when assert_exists is set.

        :raises ValueError: if the instance is not yet saved.
        """
        if self._assert_exists and instance.id is None:
            raise ValueError(
                "Instance must be saved before accessing attribute "
                f"'{self.public_name}'."
            )

    def _data_source(self, instance: "BaseResource") -> DataSource:
        """Return the data source."""
        return getattr(instance, "_initial_data_source", DataSource.USER)

    def _check_writeable(self, instance: "BaseResource"):
        """Check if the value can be saved to instance.

        The value can be set to the read-only and update-protected field only once.

        :raises AttributeError: if the field is read-only or update-protected.
        """
        created = instance.id is not None
        from_server = self._data_source(instance) == DataSource.SERVER

        if not from_server:
            if self._access_type == FieldAccessType.READ_ONLY:
                raise AttributeError(f"Field {self.public_name} is read only.")

            if self._access_type == FieldAccessType.UPDATE_PROTECTED and created:
                raise AttributeError(f"Field {self.public_name} is update protected.")

    def _check_many(self, value, instance):
        """Check that the many attribute is respected.

        :raises ValueError: when the value is not a list or ResolweQuery and many
            attribute is set to True.
        """
        from resdk.query import ResolweQuery

        if self._many and value is not None:
            if not isinstance(value, (list, ResolweQuery)):
                raise ValueError(
                    (
                        f"Type of '{instance.__class__.__name__}.{self.public_name}' "
                        f"must be a list or query."
                    )
                )

    def _check_allow_null(self, value):
        """Check if the value is allowed to be None.

        :raises ValueError: if the value is None and allow_null is False.
        """
        if not self._allow_null and value is None:
            raise ValueError(f"Field {self.public_name} does not allow None value.")

    def _checks_before_get(self, instance: "BaseResource"):
        """Perform all checks before getting the value."""
        self._check_exists(instance)

    def _check_validators(self, value, instance):
        """Run custom validators."""
        if value is None:
            return

        for validator in self._value_validators:
            for item in value if self._many else [value]:
                validator.validate(item, self, instance)

    def _checks_before_set(self, instance: "BaseResource", value):
        """Perform all checks before setting the value."""
        self._check_exists(instance)
        self._check_many(value, instance)
        self._check_writeable(instance)
        self._check_allow_null(value)
        self._check_validators(value, instance)

    def status(self, instance: "BaseResource") -> FieldStatus:
        """Return the field status."""
        if not hasattr(instance, self._status_attribute_name):
            setattr(instance, self._status_attribute_name, FieldStatus.UNSET)
        return getattr(instance, self._status_attribute_name)

    def changed(self, instance: "BaseResource") -> bool:
        """Check if the field value has changed."""
        # If the instance is not yet created, all writable and update-protected fields
        # must be considered changed.
        status = self.status(instance)
        creating = instance.id is None
        lazy = status == FieldStatus.LAZY

        # Read only and unset and lazy fields are not considered changed.
        # Lazy status can only be set by the API-originating data.
        if status == FieldStatus.UNSET or lazy:
            return False

        # When creating instance all writable and update-protected fields are changed.
        access_types = (FieldAccessType.WRITABLE, FieldAccessType.UPDATE_PROTECTED)
        if creating and self._access_type in access_types:
            return True

        # We have to deal with the instance that is already created.
        # This means data has been loaded from the server so original data is set.
        # To determine if field has been changed compare the original and current value.

        original_json = getattr(instance, self._original_attribute_name)
        current_python = getattr(instance, self._value_attribute_name)
        return not self._compare(original_json, current_python)

    def _compare(self, original_json, current_python):
        """Compare the original JSON and current Python value."""
        return original_json == current_python

    def reset(self, instance: "BaseResource"):
        """Reset the field value."""
        status = FieldStatus.UNSET
        value = None
        setattr(instance, self._value_attribute_name, value)
        setattr(instance, self._original_attribute_name, value)
        setattr(instance, self._status_attribute_name, status)

    @property
    def server_field(self):
        """The name of the field used in the API."""
        return self._server_field_name or self.public_name

    def _to_json_single(self, value):
        """Serialize the single value."""
        return value

    def _to_python_single(self, value, instance=None):
        """Deserialize the single value."""
        return value

    def to_json(self, value):
        """Return the JSON serializable value."""
        if value is None:
            return None
        if self._many:
            return [self._to_json_single(item) for item in value]
        else:
            return self._to_json_single(value)

    def to_python(self, value, instance):
        """Return the Python object from JSON value."""
        if value is None:
            return None
        if self._many:
            self._check_many(value, instance)
            return [self._to_python_single(item, instance) for item in value]
        else:
            return self._to_python_single(value, instance)

    def __get__(
        self, instance: "BaseResource", owner: Optional[type["BaseResource"]] = None
    ):
        """Get the field value."""
        self._checks_before_get(instance)
        return getattr(instance, self._value_attribute_name, None)

    def _set_server(self, instance: "BaseResource", json_data: dict):
        """Set the data from the server."""
        self.reset(instance)
        setattr(instance, self._original_attribute_name, copy.deepcopy(json_data))
        value = self.to_python(json_data, instance)
        self.__set__(instance, value)

    def __set__(self, instance: "BaseResource", value):
        """Set the field value to Python object."""
        self._checks_before_set(instance, value)
        setattr(instance, self._value_attribute_name, value)
        setattr(instance, self._status_attribute_name, FieldStatus.SET)

    def __repr__(self) -> str:
        """Returt the string representation."""
        return f"<{self.__class__.__name__} {self.public_name}>"

    def __str__(self) -> str:
        """Return the field name."""
        return self.public_name


class JSONField(BaseField):
    """The JSON field."""


class IntegerField(BaseField):
    """The integer field."""

    def __init__(self, *args, **kwargs):
        """Initialize the instance."""
        super().__init__(*args, **kwargs, validators=[TypeValidator((int,))])


class DateTimeField(BaseField):
    """The datetime objects are serialized to/from iso format."""

    def __init__(self, *args, **kwargs):
        """Initialize the instance."""
        super().__init__(*args, **kwargs, validators=[TypeValidator((datetime,))])

    def _to_json_single(self, value, resolwe=None):
        """Serialize the given field value."""
        return value.isoformat()

    def _to_python_single(self, value, instance=None):
        """Deserialize the given field value."""
        return date_parser(value)

    def _compare(self, original_json, current_python):
        """Compare the original JSON and current Python value."""
        return self.to_python(original_json, None) == current_python


class StringField(BaseField):
    """The string field."""

    def __init__(self, *args, **kwargs):
        """Initialize the instance."""
        super().__init__(*args, **kwargs, validators=[TypeValidator((str,))])


class DictField(BaseField):
    """The dictionary field."""

    def __init__(self, *args, **kwargs):
        """Initialize the instance."""
        super().__init__(*args, **kwargs, validators=[TypeValidator((dict,))])


class FloatField(BaseField):
    """The float field."""

    def __init__(self, *args, **kwargs):
        """Initialize the instance."""
        super().__init__(*args, **kwargs, validators=[TypeValidator((float,))])


class BooleanField(BaseField):
    """The boolean field."""

    def __init__(self, *args, **kwargs):
        """Initialize the instance."""
        super().__init__(*args, **kwargs, validators=[TypeValidator((bool,))])


class DictResourceField(BaseField):
    """Class representing a dictionary field with resources."""

    def __init__(self, resource_class_name: str, property_name: str = "id", **kwargs):
        """Initialize the instance.

        :attr resource_class: a string representing the resource class.
        :attr property_name: a string representing the property name of the resource to
            use in serialization.
        :attr many: a boolean indicating if the field represents a single resource or a
            list of resources.
        """
        self._resource_class_name = resource_class_name
        self._resource_class: Optional[type["BaseResource"]] = None
        self._property_name = property_name
        super().__init__(**kwargs)

    @property
    def Resource(self):
        """Return the resource class."""

        from resdk.resources.base import BaseResource  # Avoid circular import

        if self._resource_class is None:
            self._resource_class = getattr(
                importlib.import_module("resdk.resources"), self._resource_class_name
            )
            assert issubclass(self._resource_class, BaseResource), (
                f"Invalid resource class '{self._resource_class_name}'."
            )
        return self._resource_class

    def _to_json_single(self, value):
        """Serialize one item."""
        return {self._property_name: getattr(value, self._property_name)}

    def _to_python_single(self, value, instance: Optional["BaseResource"] = None):
        """Deserialize one item.

        This should be a dictionaly representing a resource. When a value is not a
        dictionary return it unchanged.
        """
        from resdk.resources.base import BaseResource

        assert instance is not None, "Instance must be provided."
        assert isinstance(value, (dict, BaseResource)), (
            "Raw value for DictResourceFiled must be a dict or BaseResource."
        )
        if isinstance(value, dict):
            value = self.Resource(
                resolwe=instance.resolwe,
                initial_data_source=self._data_source(instance),
                **value,
            )
        return value

    def _compare(self, original_json, current_python):
        """Compare the original JSON and current Python value."""
        # Handle the edge case of None values.
        if original_json is None:
            return current_python is None

        if self._many:
            json_id = [entry.get(self._property_name) for entry in original_json]
            python_id = [
                getattr(entry, self._property_name) for entry in current_python
            ]
        else:
            json_id = original_json.get(self._property_name)
            python_id = getattr(current_python, self._property_name)

        return json_id == python_id


class LazyResourceField(DictResourceField):
    """Read-only resource field with lazy loading."""

    def __init__(
        self,
        resource_class_name: str,
        initial_loader: Callable[["BaseResource"], Iterable["BaseResource"]],
        *args,
        **kwargs,
    ):
        """Initialize the instance."""
        self._lazy_loader = initial_loader
        super().__init__(
            resource_class_name,
            *args,
            **kwargs,
            assert_exists=True,
            access_type=FieldAccessType.READ_ONLY,
            many=True,
        )

    def __get__(
        self, instance: "BaseResource", owner: Optional[type["BaseResource"]] = None
    ):
        """Get the field value."""
        # Execute the lazy_loader to retrieve the value for the first time.
        if self.status(instance) == FieldStatus.UNSET:
            value = self._lazy_loader(instance)
            setattr(instance, self._value_attribute_name, value)
            setattr(instance, self._status_attribute_name, FieldStatus.SET)

        self._checks_before_get(instance)
        return getattr(instance, self._value_attribute_name, None)

    def changed(self, instance: "BaseResource") -> bool:
        """Check if the field value has changed."""
        # Lazy resource fields are read-only so they can never be changed.
        return False


class QueryRelatedField(LazyResourceField):
    """Lazy load resources from another resource query.

    The resources are lodade by the query for the resource and filtered by the id of
    the instance.
    """

    def __init__(self, resource_class_name, filter_field_name=None, *args, **kwargs):
        """Initialize the instance.

        When no filter_field_name is provided, it is infered from the endpoint name.
        """
        super().__init__(
            resource_class_name,
            initial_loader=lambda instance: instance.resolwe.get_query_by_resource(
                self.Resource
            ).filter(**{filter_field_name or instance.endpoint: instance.id}),
            *args,
            **kwargs,
        )


class IdResourceField(DictResourceField):
    """Resource field with id serialization."""

    def to_python(self, value, instance):
        """Return the base resource from the payload data."""
        if value is None:
            return None
        # Handle the case when value is int (or list of ints). Lazy loading is used in
        # this case.
        if not self._many and isinstance(value, int):
            query = instance.resolwe.get_query_by_resource(self.Resource)
            return query.filter(id__in=value)
        elif (
            self._many
            and isinstance(value, list)
            and all(isinstance(item, int) for item in value)
        ):
            query = instance.resolwe.get_query_by_resource(self.Resource)
            return query.filter(id__in=value)
        return super().to_python(value, instance)

    def __set__(self, instance, value):
        """Handle the case when the value is an int or a query."""

        from resdk.query import ResolweQuery

        super().__set__(instance, value)
        # If the value is an int, we need to set the status to LAZY.
        if not self._many and isinstance(value, ResolweQuery):
            setattr(instance, self._status_attribute_name, FieldStatus.LAZY)

    def __get__(
        self, instance: "BaseResource", owner: Optional[type["BaseResource"]] = None
    ):
        """When field is not set it has to be lazy loaded from the id."""
        # The value may have to be lazy loaded from the id.
        if self.status(instance) == FieldStatus.LAZY:
            value = getattr(instance, self._value_attribute_name).get()
            setattr(instance, self._value_attribute_name, value)
            setattr(instance, self._status_attribute_name, FieldStatus.SET)
        return super().__get__(instance, owner)

    def _compare(self, original_json, current_python):
        """Compare the original JSON and current Python value."""
        # Handle the edge case of None values.
        if original_json is None:
            return current_python is None

        if self._many:
            json_id = [entry for entry in original_json]
            python_id = [
                getattr(entry, self._property_name) for entry in current_python
            ]
        else:
            json_id = original_json
            python_id = getattr(current_python, self._property_name)

        return json_id == python_id

    def to_json(self, value):
        """Return the serialized value."""
        if self._many:
            return [item.id for item in value]
        return value.id

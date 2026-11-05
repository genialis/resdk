"""
Unit tests for resdk/resolwe.py file.
"""

import unittest

import slumber
from mock import MagicMock, patch

from resdk.resources import (
    Collection,
    Data,
    DescriptorSchema,
    Group,
    Process,
    Relation,
    Sample,
    User,
)
from resdk.resources.base import BaseResolweResource, BaseResource
from resdk.resources.fields import FieldAccessType, IntegerField, JSONField, StringField
from resdk.resources.kb import Feature, Mapping

from .utils import server_resource

# This is normally set in subclass
BaseResolweResource.endpoint = "endpoint"
BaseResource.endpoint = "endpoint"


class TestBaseResolweResource(unittest.TestCase):
    @patch("resdk.resolwe.Resolwe")
    def setUp(self, resolwe_mock):
        self.resolwe_mock = resolwe_mock

    def test_field_constraints(self):

        class TestResource(BaseResolweResource):
            writable_scalar = StringField(access_type=FieldAccessType.WRITABLE)
            updatable_scalar = IntegerField(
                access_type=FieldAccessType.UPDATE_PROTECTED
            )
            read_only_scalar = IntegerField()

        base_resource = TestResource(resolwe=self.resolwe_mock)
        message = "Field read_only_scalar is read only."
        with self.assertRaisesRegex(AttributeError, message):
            base_resource.read_only_scalar = 42

        # The update protected field can be changed only if the resource is not created.
        base_resource.updatable_scalar = 24
        base_resource.writable_scalar = "42"
        self.assertEqual(base_resource.writable_scalar, "42")
        self.assertEqual(base_resource.updatable_scalar, 24)
        self.assertEqual(base_resource.read_only_scalar, None)

        # When ID is set, no read-only or update-protected field can be changed.
        base_resource = server_resource(
            TestResource,
            resolwe=self.resolwe_mock,
            id=1,
            writable_scalar="42",
            updatable_scalar=24,
        )
        message = "Field read_only_scalar is read only."
        with self.assertRaisesRegex(AttributeError, message):
            base_resource.read_only_scalar = 42
        message = "Field updatable_scalar is update protected."
        with self.assertRaisesRegex(AttributeError, message):
            base_resource.updatable_scalar = 10
        base_resource.writable_scalar = "24"
        self.assertEqual(base_resource.writable_scalar, "24")
        self.assertEqual(base_resource.updatable_scalar, 24)
        self.assertEqual(base_resource.read_only_scalar, None)

    def test_update_fields(self):

        class TestResource(BaseResolweResource):
            first_field = IntegerField(access_type=FieldAccessType.WRITABLE)

        resource = TestResource(resolwe=self.resolwe_mock)
        resource.first_field = None

        payload = {"first_field": 42}
        resource._update_fields(payload)
        self.assertEqual(resource.first_field, 42)

    def test_eq(self):
        obj_1 = server_resource(BaseResource, self.resolwe_mock, id=1)
        obj_2 = server_resource(BaseResource, self.resolwe_mock, id=1)
        obj_3 = server_resource(BaseResource, self.resolwe_mock, id=2)
        obj_4 = server_resource(BaseResolweResource, self.resolwe_mock, id=1)

        self.assertEqual(obj_1 == obj_2, True)
        self.assertEqual(obj_1 == obj_3, False)
        self.assertEqual(obj_1 == obj_4, False)


class TestBaseMethods(unittest.TestCase):
    @patch("resdk.resources.base.BaseResolweResource", spec=True)
    def test_save_post(self, base_mock):
        resolwe_mock = MagicMock()
        test_resource = server_resource(BaseResolweResource, resolwe_mock, slug="test")
        update_mock = MagicMock()
        test_resource._update_fields = update_mock
        test_resource.save()
        self.assertEqual(update_mock.call_count, 1)
        self.assertTrue(
            update_mock.call_args[0][0]._extract_mock_name().endswith("post()")
        )

    @patch("resdk.resources.base.BaseResolweResource", spec=True)
    def test_save_post_read_only(self, base_mock):
        class TestResource(BaseResolweResource):
            read_only_dict = JSONField(access_type=FieldAccessType.READ_ONLY)

        resource = server_resource(TestResource, resolwe=MagicMock(), read_only_dict={})
        resource.read_only_dict["change"] = "change-not-allowed"
        message = "Not allowed to change fields read_only_dict"
        with self.assertRaisesRegex(ValueError, message):
            resource.save()

    @patch("resdk.resources.base.BaseResolweResource", spec=True)
    def test_save_post_update_protected(self, base_mock):
        class TestResource(BaseResolweResource):
            update_protected_dict = JSONField(
                access_type=FieldAccessType.UPDATE_PROTECTED
            )

        resource = TestResource(
            resolwe=MagicMock(),
            slug="test",
            update_protected_dict={"create": "create-allowed"},
        )
        resource.api = MagicMock(
            return_value=MagicMock(
                **{
                    "post.return_value": {
                        "id": 1,
                        "slug": "test",
                        "update_protected_dict": {"create": "create-allowed"},
                    }
                }
            )
        )
        resource.save()
        self.assertEqual(resource.id, 1)
        self.assertEqual(resource.slug, "test")
        self.assertEqual(resource.update_protected_dict, {"create": "create-allowed"})

    @patch("resdk.resources.base.BaseResolweResource", spec=True)
    def test_save_post_client_error(self, base_mock):
        test_resource = BaseResolweResource(MagicMock(), slug="test")
        test_resource.api = MagicMock(
            return_value=MagicMock(
                **{
                    "post.side_effect": slumber.exceptions.HttpClientError(
                        message="", content="", response=""
                    )
                }
            )
        )
        with self.assertRaises(slumber.exceptions.HttpClientError):
            test_resource.save()

    @patch("resdk.resources.base.BaseResolweResource", spec=True)
    def test_save_patch(self, base_mock):
        resolwe_mock = MagicMock()
        test_resource = server_resource(
            BaseResolweResource, resolwe_mock, id=1, slug="slug-old"
        )
        test_resource.slug = "slug"
        update_mock = MagicMock()
        test_resource._update_fields = update_mock
        test_resource.save()
        self.assertEqual(update_mock.call_count, 1)
        self.assertTrue(
            update_mock.call_args[0][0]._extract_mock_name().endswith("patch()")
        )

    @patch("resdk.resources.base.BaseResolweResource", spec=True)
    def test_save_patch_read_only(self, base_mock):
        class TestResource(BaseResolweResource):
            read_only_dict = JSONField()

        resource = server_resource(
            TestResource, resolwe=MagicMock(), id=1, read_only_dict={}
        )
        resource.read_only_dict["change"] = "change-not-allowed"
        message = "Not allowed to change fields read_only_dict"
        with self.assertRaisesRegex(ValueError, message):
            resource.save()

    @patch("resdk.resources.base.BaseResolweResource", spec=True)
    def test_save_patch_update_protect(self, base_mock):
        class TestResource(BaseResolweResource):
            update_protected_dict = JSONField(
                access_type=FieldAccessType.UPDATE_PROTECTED
            )

        resource = server_resource(
            TestResource,
            resolwe=MagicMock(),
            id=1,
            slug="test",
            update_protected_dict={},
        )
        resource.update_protected_dict["change"] = "change-not-allowed"
        message = "Not allowed to change fields update_protected_dict"
        with self.assertRaisesRegex(ValueError, message):
            resource.save()

    @patch("resdk.resources.base.BaseResolweResource", spec=True)
    def test_repr(self, base_mock):
        base_mock.configure_mock(id=1, slug="a", name="b")
        out = BaseResolweResource.__repr__(base_mock)
        self.assertEqual(out, "BaseResolweResource <id: 1, slug: 'a', name: 'b'>")


class TestAttributesDefined(unittest.TestCase):
    def test_attributes_are_defined(self):
        classes = [
            BaseResource,
            BaseResolweResource,
            Collection,
            Data,
            DescriptorSchema,
            Feature,
            Group,
            Mapping,
            Process,
            Relation,
            Sample,
            User,
        ]

        resolwe = MagicMock()

        for class_ in classes:
            resource = class_(resolwe)
            for field in resource._resource_fields:
                # Some fields are properties that can only be accessed when
                # object has id != None. Otherwise they return ValueError.
                # We therefore skip these ValueError's
                try:
                    assert hasattr(resource, field)
                except ValueError:
                    continue


if __name__ == "__main__":
    unittest.main()

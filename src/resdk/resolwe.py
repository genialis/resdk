""".. Ignore pydocstyle D400.

=======
Resolwe
=======

.. autoclass:: resdk.Resolwe
   :members:

"""

import getpass
import json
import logging
import ntpath
import os
import re
import time
import webbrowser
from collections import defaultdict
from contextlib import suppress
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Iterable, Optional, TypedDict, Union
from urllib.parse import urlencode, urljoin, urlparse

import requests
import slumber
import tqdm
from packaging import version

from resdk.uploader import Uploader

from .constants import CHUNK_SIZE
from .exceptions import ResolweServerError, ValidationError, handle_http_exception
from .query import (
    AnnotationFieldQuery,
    AnnotationValueQuery,
    PredictionFieldQuery,
    PredictionValueQuery,
    ResolweQuery,
)
from .resources import (
    AnnotationField,
    AnnotationValue,
    Collection,
    Data,
    DescriptorSchema,
    Geneset,
    Group,
    Metadata,
    PredictionField,
    PredictionGroup,
    PredictionPreset,
    PredictionValue,
    Process,
    Relation,
    Sample,
    User,
    Variant,
    VariantAnnotation,
    VariantCall,
    VariantExperiment,
)
from .resources.base import BaseResource
from .resources.fields import DataSource
from .resources.kb import Feature, Mapping
from .resources.utils import get_collection_id, get_data_id, is_data, iterate_fields
from .utils import md5

DEFAULT_URL = "http://localhost:8000"
AUTOMATIC_LOGIN_POSTFIX = "saml-auth/api-login/"
INTERACTIVE_LOGIN_POSTFIX = "saml-auth/remote-login/"
MINIMAL_SUPPORTED_VERSION_POSTFIX = "api/resdk_minimal_supported_version"
SERVER_MODULE_VERSIONS_POSTFIX = "/about/versions"


class ResolweResource(slumber.Resource):
    """Wrapper around slumber's Resource with custom exceptions handler."""

    def __getattribute__(self, item):
        """Return class attribute and wrapp request methods in exception handler."""
        attr = super().__getattribute__(item)
        if item in ["get", "options", "head", "post", "patch", "put", "delete"]:
            return handle_http_exception(attr)
        return attr

    def delete(self, *args, **kwargs):
        """Delete resource object.

        This is mostly Slumber default implementation except that it returns the
        processed response when status is not 204 (No Content).
        """
        resp = self._request("DELETE", params=kwargs)
        if 200 <= resp.status_code <= 299:
            if resp.status_code == 204:
                return True
            else:
                return self._process_response(resp)
        else:
            return False


class ResolweAPI(slumber.API):
    """Use custom ResolweResource resource class in slumber's API."""

    resource_class = ResolweResource


class Resolwe:
    """Connect to a Resolwe server.

    :param username: user's email
    :type username: str
    :param password: user's password
    :type password: str
    :param url: Resolwe server instance
    :type url: str

    """

    # Map between resource and Query map. Default in ResorweQuery, only overrides must
    # be listed here.
    resource_query_class = {
        AnnotationField: AnnotationFieldQuery,
        AnnotationValue: AnnotationValueQuery,
        PredictionField: PredictionFieldQuery,
        PredictionValue: PredictionValueQuery,
    }

    # Map resource class to ResolweQuery name
    resource_query_mapping = {
        AnnotationField: "annotation_field",
        AnnotationValue: "annotation_value",
        Collection: "collection",
        Data: "data",
        DescriptorSchema: "descriptor_schema",
        Feature: "feature",
        Geneset: "geneset",
        Group: "group",
        Mapping: "mapping",
        Metadata: "metadata",
        PredictionField: "prediction_field",
        PredictionGroup: "prediction_group",
        PredictionPreset: "prediction_preset",
        PredictionValue: "prediction_value",
        Process: "process",
        Relation: "relation",
        Sample: "sample",
        User: "user",
        Variant: "variant",
        VariantAnnotation: "variant_annotation",
        VariantCall: "variant_calls",
        VariantExperiment: "variant_experiment",
    }
    # Map ResolweQuery name to it's slug_field
    slug_field_mapping = {
        "user": "username",
        "group": "name",
    }
    # Map ResolweQuery name to it's default query filter
    query_filter_mapping = {
        "geneset": {"type": "data:geneset"},
        "metadata": {"type": "data:metadata"},
    }

    data = None
    collection = None
    sample = None
    relation = None
    process = None
    descriptor_schema = None
    user = None
    group = None
    feature = None
    mapping = None
    geneset = None
    metadata = None

    session = None

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        url: Optional[str] = None,
    ):
        """Initialize attributes."""
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        self.uploader = Uploader(self)
        if url is None:
            # Try to get URL from environmental variable, otherwise fallback to default.
            url = os.environ.get("RESOLWE_HOST_URL", DEFAULT_URL)

        self._validate_url(url)

        if username is None:
            username = os.environ.get("RESOLWE_API_USERNAME", None)

        if password is None:
            password = os.environ.get("RESOLWE_API_PASSWORD", None)

        self.url = url

        # Check minimal supported version.
        self.version_check()

        self._login(username=username, password=password)

    def version_check(self):
        """Check that the server is compatible with the client."""
        url = urljoin(self.url, MINIMAL_SUPPORTED_VERSION_POSTFIX)
        try:
            response = requests.get(url)
            minimal_version = version.parse(
                response.json()["minimal_supported_version"]
            )
            my_version = version.parse(package_version("resdk"))
            if my_version < minimal_version:
                message = (
                    f"Warning: your version of ReSDK ('{my_version}') is not compatible with "
                    f"the server: minimal supported version is '{minimal_version}'. "
                    "To update the package run\n\n"
                    "python -m pip install --upgrade resdk\n\n"
                    "from the command line."
                )
                self.logger.warning(message)
        except Exception:
            self.logger.warning(
                "Warning: unable to read the minimal supported version from the server."
            )

    def version_output(self) -> dict:
        """Output the version of the server modules."""
        url = urljoin(self.url, SERVER_MODULE_VERSIONS_POSTFIX)
        try:
            response = requests.get(url)
        except requests.exceptions.RequestException:
            raise ResolweServerError("Unable to read the server version.")
        return response.json()

    def _validate_url(self, url: str):
        """Validate server URL.

        :raises ValueError: if the URL is not valid or the server is unreachable.
        """
        if not re.match(r"https?://", url):
            raise ValueError("Server url must start with http(s)://")

        try:
            self.session.get(urljoin(url, "/api/"))
        except requests.exceptions.ConnectionError:
            raise ValueError("The site can't be reached: {}".format(url))

    def _initialize_queries(self):
        """Initialize ResolweQuery's."""
        for resource, query_name in self.resource_query_mapping.items():
            slug_field = self.slug_field_mapping.get(query_name, "slug")
            QueryClass = self.resource_query_class.get(resource, ResolweQuery)
            query = QueryClass(self, resource, slug_field=slug_field)
            if query_name in self.query_filter_mapping:
                query = query.filter(**self.query_filter_mapping[query_name])
            setattr(self, query_name, query)

    def _login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        interactive: bool = False,
    ):
        self.auth = ResAuth(username, password, self.url, interactive=interactive)
        self.session.cookies = requests.utils.cookiejar_from_dict(self.auth.cookies)
        self.api = ResolweAPI(
            urljoin(self.url, "/api/"),
            self.auth,
            session=self.session,
            append_slash=False,
        )
        self._initialize_queries()
        self.uploader.invalidate_cache()

        # Retrieve the logged in user and save it to auth. Necessary for interactive
        # login.
        with suppress(Exception):
            logged_in_user = self.user.get(current_only=True)
            self.auth.username = logged_in_user.email

    def login(self, username: Optional[str] = None, password: Optional[str] = None):
        """Perform the interactive login.

        If only username is given prompt the user for password via shell.
        If username is not given, prompt for interactive login.
        """
        if username is None:
            self._login(interactive=False)
            return

        if password is None:
            password = getpass.getpass("Password: ")

        self._login(username=username, password=password, interactive=True)

    def get_query_by_resource(self, resource: type[BaseResource]) -> ResolweQuery:
        """Get ResolweQuery for a given resource.

        :raises ValueError: if the resource is not a subclass of BaseResource.
        """
        if isinstance(resource, BaseResource):
            resource = resource.__class__
        elif not issubclass(resource, BaseResource):
            raise ValueError(
                "Provide a Resource class or it's instance as a resource argument."
            )

        return getattr(self, self.resource_query_mapping.get(resource))

    def __repr__(self) -> str:
        """Return string representation of the current object."""
        if self.auth.username:
            return "Resolwe <url: {}, username: {}>".format(
                self.url, self.auth.username
            )
        return "Resolwe <url: {}>".format(self.url)

    def _process_file_field(self, path: Union[str, Path, dict]) -> dict:
        """Process file field and return it in resolwe-specific format.

        Upload referenced file if it is stored locally and return
        original filename and it's temporary location.

        :param path: path to file (local or url)
        :type path: str/path

        :rtype: dict
        """
        if isinstance(path, dict) and "file" in path and "file_temp" in path:
            return path

        url_regex = (
            r"^(https?|ftp)://[-A-Za-z0-9\+&@#/%?=~_|!:,.;]*[-A-Za-z0-9\+&@#/%=~_|]$"
        )
        if re.match(url_regex, path):
            file_name = path.split("/")[-1].split("#")[0].split("?")[0]
            return {"file": file_name, "file_temp": path}

        if not os.path.isfile(path):
            raise ValueError("File {} not found.".format(path))

        file_temp = self.uploader.upload(path)

        if not file_temp:
            raise Exception("Upload failed for {}.".format(path))

        file_name = ntpath.basename(path)
        return {
            "file": file_name,
            "file_temp": file_temp,
        }

    def _get_process(self, slug: Optional[str] = None) -> Process:
        """Return process with given slug.

        Raise error if process doesn't exist or more than one is returned.
        """
        return self.process.get(slug=slug)

    def _process_inputs(self, inputs: dict, process: Process) -> dict:
        """Process input fields.

        Processing includes:
        * wrapping ``list:*`` to the list if they are not already
        * dehydrating values of ``data:*`` and ``list:data:*`` fields
        * uploading files in ``basic:file:`` and ``list:basic:file:``
          fields
        """

        def deep_copy(current):
            """Copy inputs."""
            if isinstance(current, dict):
                return {key: deep_copy(val) for key, val in current.items()}
            elif isinstance(current, list):
                return [deep_copy(val) for val in current]
            elif is_data(current):
                return current.id
            else:
                return current

        # leave original intact
        inputs = deep_copy(inputs)

        try:
            for schema, fields in iterate_fields(inputs, process.input_schema):
                field_name = schema["name"]
                field_type = schema["type"]
                field_value = fields[field_name]

                # XXX: Remove this when supported on server.
                # Wrap `list:` fields into list if they are not already
                if field_type.startswith("list:") and not isinstance(field_value, list):
                    fields[field_name] = [field_value]
                    field_value = fields[
                        field_name
                    ]  # update value for the rest of the loop

                # Dehydrate `data:*` fields
                if field_type.startswith("data:"):
                    fields[field_name] = get_data_id(field_value)

                # Dehydrate `list:data:*` fields
                elif field_type.startswith("list:data:"):
                    fields[field_name] = [get_data_id(data) for data in field_value]

                # Upload files in `basic:file:` fields
                elif field_type == "basic:file:":
                    fields[field_name] = self._process_file_field(field_value)

                # Upload files in list:basic:file:` fields
                elif field_type == "list:basic:file:":
                    fields[field_name] = [
                        self._process_file_field(obj) for obj in field_value
                    ]

        except KeyError as key_error:
            field_name = key_error.args[0]
            slug = process.slug
            raise ValidationError(
                "Field '{}' not in process '{}' input schema.".format(field_name, slug)
            )

        return inputs

    def run(
        self,
        slug: Optional[str] = None,
        input: dict = {},
        descriptor: Optional[dict] = None,
        descriptor_schema: Optional[str] = None,
        collection: Optional[Collection] = None,
        data_name: str = "",
        process_resources: Optional[dict] = None,
    ) -> Data:
        """Run process and return the corresponding Data object.

        1. Upload files referenced in inputs
        2. Create Data object with given inputs
        3. Command is run that processes inputs into outputs
        4. Return Data object

        The processing runs asynchronously, so the returned Data
        object does not have an OK status or outputs when returned.
        Use data.update() to refresh the Data resource object.

        :param str slug: Process slug (human readable unique identifier)
        :param dict input: Input values
        :param dict descriptor: Descriptor values
        :param str descriptor_schema: A valid descriptor schema slug
        :param int/resource collection: Collection resource or it's id
            into which data object should be included
        :param str data_name: Default name of data object
        :param dict process_resources: Process resources

        :return: data object that was just created
        :rtype: Data object
        """
        if (descriptor and not descriptor_schema) or (
            not descriptor and descriptor_schema
        ):
            raise ValueError("Set both or neither descriptor and descriptor_schema.")

        process = self._get_process(slug)
        data = {
            "process": {"slug": process.slug},
            "input": self._process_inputs(input, process),
        }

        if descriptor and descriptor_schema:
            data["descriptor"] = descriptor
            data["descriptor_schema"] = {"slug": descriptor_schema}

        if collection:
            data["collection"] = {"id": get_collection_id(collection)}

        if data_name:
            data["name"] = data_name

        if process_resources is not None:
            if not isinstance(process_resources, dict):
                raise ValueError("Argument process_resources must be a dictionary.")
            if set(process_resources.keys()) - set(["cores", "memory", "storage"]):
                raise ValueError(
                    "Argument process_resources can only have cores, memory or storage keys."
                )
            data["process_resources"] = process_resources

        model_data = self.api.data.post(data)
        return Data(resolwe=self, **model_data, initial_data_source=DataSource.SERVER)

    def get_or_run(self, slug: Optional[str] = None, input: dict = {}):
        """Return existing object if found, otherwise create new one.

        :param str slug: Process slug (human readable unique identifier)
        :param dict input: Input values
        """
        process = self._get_process(slug)
        inputs = self._process_inputs(input, process)

        data = {
            "process": {"slug": process.slug},
            "input": inputs,
        }

        model_data = self.api.data.get_or_create.post(data)
        return Data(resolwe=self, **model_data, initial_data_source=DataSource.SERVER)

    def _download_files(
        self,
        files: Iterable[Union[str, Path]],
        download_dir: Union[str, None] = None,
        show_progress: bool = True,
    ):
        """Download files.

        Download files from the Resolwe server to the download
        directory (defaults to the current working directory).

        :param files: files to download
        :param download_dir: download directory
            If not specified, the current working directory is used.

        """
        if not download_dir:
            download_dir = os.getcwd()

        if not os.path.isdir(download_dir):
            raise ValueError(
                "Download directory does not exist: {}".format(download_dir)
            )

        if not files:
            self.logger.info("No files to download.")
        else:
            self.logger.info("Downloading files to %s:", download_dir)
            # Store the sizes of files in the given directory.
            # Use the dictionary to cache the responses.
            sizes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            checksums: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

            for file_uri in files:
                file_name = os.path.basename(file_uri)
                file_path = os.path.dirname(file_uri)
                file_url = urljoin(self.url, "data/{}".format(file_uri))

                # Remove data id from path
                file_path = file_path.split("/", 1)[1] if "/" in file_path else ""
                full_path = os.path.join(download_dir, file_path)
                if not os.path.isdir(full_path):
                    os.makedirs(full_path)

                self.logger.info("* %s", os.path.join(file_path, file_name))

                file_directory = os.path.dirname(file_url)
                if file_directory not in sizes:
                    content = self.session.get(file_directory, auth=self.auth).content
                    for entry in json.loads(content):
                        if entry["type"] != "file":
                            continue
                        sizes[file_directory][entry["name"]] = entry["size"]
                        checksums[file_directory][entry["name"]] = entry["md5"]

                file_size = sizes[file_directory][file_name]

                with (
                    tqdm.tqdm(
                        total=file_size,
                        disable=not show_progress,
                        desc=f"Downloading file {file_name}",
                    ) as progress_bar,
                    open(
                        os.path.join(download_dir, file_path, file_name), "wb"
                    ) as file_handle,
                ):
                    response = self.session.get(file_url, stream=True, auth=self.auth)

                    if not response.ok:
                        response.raise_for_status()
                    else:
                        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                            file_handle.write(chunk)
                            progress_bar.update(len(chunk))

                # Verify md5 checksum:
                if file_name.endswith(".html"):
                    # Due to backend processing, html file fields have
                    # checksums that are difficult to reproduce here.
                    continue
                expected_md5 = checksums[file_directory][file_name]
                computed_md5 = md5(os.path.join(download_dir, file_path, file_name))
                if expected_md5 != computed_md5:
                    raise ValueError(
                        f"Checksum ({computed_md5}) of downloaded file {file_name} does not match the expected value of {expected_md5}."
                    )

    def data_usage(self, **query_params):
        """Get per-user data usage information.

        Display number of samples, data objects and sum of data object
        sizes for currently logged-in user. For admin users, display
        data for **all** users.
        """
        return self.api.base.data_usage.get(**query_params)


class AuthCookie(TypedDict):
    """Authentication cookie dict."""

    csrftoken: str
    sessionid: str


class ResAuth(requests.auth.AuthBase):
    """HTTP Resolwe Authentication for Request object.

    :param str username: user's email
    :param str password: user's password
    :param str url: Resolwe server address
    :param str cookies: user's sessionid and csrftoken cookies

    """

    #: Dictionary of authentication cookes.
    cookies: AuthCookie = {"csrftoken": "", "sessionid": ""}

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        url: str = DEFAULT_URL,
        interactive: bool = False,
    ):
        """Authenticate user on Resolwe server."""
        self.logger = logging.getLogger(__name__)
        self.username = username
        self.url = url
        self.automatic_login_url = urljoin(self.url, AUTOMATIC_LOGIN_POSTFIX)
        self.interactive_login_url = urljoin(self.url, INTERACTIVE_LOGIN_POSTFIX)

        if not interactive and (username is None or password is None):
            # Anonymous authentication
            return

        if username and password:
            self.cookies = self.automatic_login(username, password)
            self.logger.info(f"Successfully logged in as {username}.")
        else:
            self.cookies = self.interactive_login()
            self.logger.info("Successfully logged in.")

    def automatic_login(self, username: str, password: str) -> AuthCookie:
        """Attempt to perform automatic SAML login.

        :returns: authentication cookie dict on success, None on failure.
        """
        self.logger.info("Attempting automatic login.")
        response = requests.post(
            self.automatic_login_url,
            data={"email": username, "password": password},
        )
        cookies = response.cookies.get_dict()
        # Status should be either 204 (No Content) or 200 (OK).
        if (
            response.status_code not in [200, 204]
            or "sessionid" not in cookies
            or "csrftoken" not in cookies
        ):
            raise RuntimeError("Automatic login failed.")

        return {
            "sessionid": cookies["sessionid"],
            "csrftoken": cookies["csrftoken"],
        }

    def interactive_login(self, polling_interval: int = 1) -> AuthCookie:
        """Prompt user to log in with a web browser.

        :returns: authentication cookie dict on success, None on failure.
        """
        auth_id_url = urljoin(self.interactive_login_url, "auth-id/")
        auth_id = requests.get(auth_id_url).json()["auth_id"]

        # Use login url without the auth_id, as the system call could be intercepted.
        browser_opened = webbrowser.open(self.interactive_login_url)
        login_url_with_auth_id = (
            urlparse(self.interactive_login_url)
            ._replace(query=urlencode({"auth_id": auth_id}))
            .geturl()
        )
        message_automatic = f"""Enter the following code in the opened browser window:

{auth_id}

Alternatively, you may visit the following URL which will autofill the code upon loading:
{login_url_with_auth_id}\n"""
        message_not_automatic = f"""Open the following URL which will autofill the code upon loading:

{login_url_with_auth_id}\n"""

        message = f"Browser {'could not' if not browser_opened else 'will'} be automatically opened.\n"
        message += message_automatic if browser_opened else message_not_automatic

        # Do not use logger here, because we want the url to be visible even if logging
        # is disabled.
        print(message)

        poll_url = urljoin(self.interactive_login_url, "poll/")
        session = requests.Session()
        session.cookies.set("auth_id", auth_id)
        response = session.get(poll_url)
        while response.status_code == 204:
            time.sleep(polling_interval)
            response = session.get(poll_url)

        cookie_dict = response.json()

        if (
            response.status_code != 200
            or "sessionid" not in cookie_dict
            or "csrftoken" not in cookie_dict
        ):
            raise RuntimeError("Interactive login failed.")

        return cookie_dict

    def __call__(self, request: requests.Request) -> requests.Request:
        """Set request headers."""
        if "csrftoken" in self.cookies:
            request.headers["X-CSRFToken"] = self.cookies["csrftoken"]

        request.headers["referer"] = self.url

        # Not needed until we support HTTP Push with the API
        # if r.path_url != '/upload/':
        #     r.headers['X-SubscribeID'] = self.subscribe_id
        return request

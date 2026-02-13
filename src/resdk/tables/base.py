""".. Ignore pydocstyle D400.

===========
Base Tables
===========

.. autoclass:: BaseTables
    :members:

    .. automethod:: __init__

"""

import abc
import asyncio
import json
import os
import warnings
from collections import Counter, defaultdict
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp
import pandas as pd
import pytz
from tqdm import tqdm

from resdk.resources import Collection, Data, Sample
from resdk.utils.table_cache import cache_dir_resdk, load_pickle, save_pickle

# See _download_data function for in-depth explanation of this.
EXP_ASYNC_CHUNK_SIZE = 50


class TqdmWithCallable(tqdm):
    """Tqdm class that also calls a given callable."""

    def __init__(self, *args, **kwargs):
        """Initialize class."""
        self.callable = kwargs.pop("callable", None)
        super().__init__(*args, **kwargs)

    def update(self, n=1):
        """Update."""
        super().update(n=n)
        if self.callable:
            self.callable(self.n / self.total)


class BaseTables(abc.ABC):
    """A base class for *Tables."""

    process_type = None
    META = "meta"

    SAMPLE_FIELDS = [
        "id",
        "slug",
        "name",
    ]
    DATA_FIELDS = [
        "id",
        "slug",
        "modified",
        "entity__name",
        "entity__id",
        "output",
        "process__output_schema",
        "process__slug",
    ]

    def __init__(
        self,
        collection: Collection,
        cache_dir: Optional[str] = None,
        progress_callable: Optional[Callable] = None,
    ):
        """Initialize class.

        :param collection: collection to use
        :param cache_dir: cache directory location, if not specified system specific
                          cache directory is used
        :param progress_callable: custom callable that can be used to report
                                  progress. By default, progress is written to
                                  stderr with tqdm
        """
        self.resolwe = collection.resolwe  # type: Resolwe
        self.collection = collection

        self.tqdm = TqdmWithCallable
        self.progress_callable = progress_callable

        self.cache_dir = cache_dir
        if self.cache_dir is None:
            self.cache_dir = cache_dir_resdk()
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    @property
    @lru_cache()
    def meta(self) -> pd.DataFrame:
        """Return samples metadata table as a pandas DataFrame object.

        :return: table of metadata
        """
        return self._load_fetch(self.META)

    def clear_cache(self) -> None:
        """Remove ReSDK cache files from the default cache directory."""
        # Clear cache for the collection
        cache_dir = cache_dir_resdk()
        for f in Path(cache_dir).iterdir():
            if f.name.startswith(self.collection.slug):
                f.unlink()

    @property
    @lru_cache()
    def _samples(self) -> List[Sample]:
        """Fetch sample objects.

        Fetch all samples from given collection and cache the results in memory. Only
        the needed subset of fields is fetched.

        :return: list od Sample objects
        """
        sample_ids = set([d.sample.id for d in self._data])

        query = self.collection.samples.filter(fields=self.SAMPLE_FIELDS).iterate()
        return [s for s in query if s.id in sample_ids]

    @property
    def readable_index(self) -> Dict[int, str]:
        """Get mapping from index values to readable names."""
        names = [s.name for s in self._samples]
        if len(set(names)) != len(names):
            repeated = [item for item, count in Counter(names).items() if count > 1]
            repeated = ", ".join(repeated)
            warnings.warn(
                f"The following names are repeated in index: {repeated}", UserWarning
            )

        return {s.id: s.name for s in self._samples}

    @property
    @lru_cache()
    def _data(self) -> List[Data]:
        """Fetch data objects.

        Fetch Data of type ``self.process_type`` from given collection
        and cache the results in memory. Only the needed subset of
        fields is fetched.

        :return: list of Data objects
        """
        sample2data = {}
        repeated_sample_ids = set()
        for datum in self.collection.data.filter(
            type=self.process_type,
            status="OK",
            fields=self.DATA_FIELDS,
            # Do not include data that does not belong to a sample
            entity__isnull=False,
        ).iterate():
            # We are using iterate to prevent 504 Bad Gateways
            # This means that data is given from oldest to newest
            if datum.sample.id in sample2data:
                repeated_sample_ids.add(datum.sample.id)
            sample2data[datum.sample.id] = datum

        if repeated_sample_ids:
            repeated = ", ".join(map(str, repeated_sample_ids))
            warnings.warn(
                f"The following samples have multiple data of type {self.process_type}: "
                f"{repeated}. Using only the newest data of this sample.",
                UserWarning,
            )

        return list(sample2data.values())

    @property
    @lru_cache()
    def _metadata_version(self) -> str:
        """Return server metadata version.

        The versioning of metadata on the server is determined by the
        newest of these values:

            - newest modified sample
            - newest modified relation
            - newest modified orange Data
            - newest modified AnnotationValue

        :return: metadata version
        """
        timestamps = []
        kwargs = {
            "ordering": "-modified",
            "fields": ["id", "modified"],
            "limit": 1,
        }

        # Get newest sample timestamp
        try:
            newest_sample = self.collection.samples.get(**kwargs)
            timestamps.append(newest_sample.modified)
        except LookupError:
            raise ValueError(
                f"Collection {self.collection.name} has no samples!"
            ) from None

        # Get newest relation timestamp
        try:
            newest_relation = self.collection.relations.get(**kwargs)
            timestamps.append(newest_relation.modified)
        except LookupError:
            pass

        # Get newest orange object timestamp
        try:
            orange = self._get_orange_object()
            timestamps.append(orange.modified)
        except LookupError:
            pass

        # Get newest AnnotationValue timestamp
        try:
            newest_stamps = []
            # Getting annotation values for large collection breaks the server.
            # Instead make smaller queries for a single batch of samples
            batch_size = 100
            for i in self.tqdm(
                range(0, len(self._samples), batch_size),
                desc="Getting latest annotation_value timestamp",
            ):
                batch_sample_ids = [s.id for s in self._samples[i : i + batch_size]]
                newest_ann_value = self.resolwe.annotation_value.get(
                    entity__in=batch_sample_ids,
                    ordering="-created",
                    limit=1,
                )
                newest_stamps.append(newest_ann_value.modified)

            timestamps.append(sorted(newest_stamps)[-1])

        except LookupError:
            pass

        newest_modified = sorted(timestamps)[-1]
        # transform into UTC so changing timezones won't effect cache
        version = (
            newest_modified.astimezone(pytz.utc).isoformat().replace("+00:00", "Z")
        )
        # On Windows, datetime stamps are not appropriate as a part of file name.
        # The reason is the colon char (":")
        version = str(hash(version))
        return version

    @property
    @lru_cache()
    def _data_version(self) -> str:
        """Return server data version.

        The versioning of Data on the server is determined by the hash of
        the tuple of sorted data objects ids.

        :return: data version
        """
        if len(self._data) == 0:
            raise ValueError(
                f"Collection {self.collection.name} has no {self.process_type} data!"
            )
        data_ids = tuple(sorted(d.id for d in self._data))
        version = str(hash(data_ids))
        return version

    def _load_fetch(self, data_type: str) -> pd.DataFrame:
        """Load data from disc or fetch it from server and cache it on disc."""
        data = load_pickle(self._cache_file(data_type))
        if data is None:
            if data_type == self.META:
                data = self._download_metadata()
            else:
                data = asyncio.run(self._download_data(data_type))

            save_pickle(data, self._cache_file(data_type))
        return data

    def _cache_file(self, data_type: str) -> str:
        """Return full cache file path."""
        if data_type == self.META:
            version = self._metadata_version
        else:
            version = self._data_version

        cache_file = f"{self.collection.slug}_{data_type}_{version}.pickle"
        return os.path.join(self.cache_dir, cache_file)

    def _get_annotations(self) -> pd.DataFrame:
        TYPE_TO_DTYPE = {
            "STRING": str,
            # Pandas cannot cast NaN's to int, but it can cast them
            # to pd.Int64Dtype
            "INTEGER": pd.Int64Dtype(),
            "DECIMAL": float,
            "DATE": "datetime64[ns]",
        }

        sample_data = defaultdict(dict)
        sample_dtypes = defaultdict(dict)
        # Getting annotation values for large collection breaks the server.
        # Instead make smaller queries for a single batch of samples
        batch_size = 100
        for i in self.tqdm(
            range(0, len(self._samples), batch_size), desc="Downloading annotations"
        ):
            batch_sample_ids = [s.id for s in self._samples[i : i + batch_size]]
            avs = self.resolwe.annotation_value.filter(
                entity__in=batch_sample_ids,
            )
            for ann_value in avs:
                sample_data[ann_value.sample.id][str(ann_value.field)] = ann_value.value
                sample_dtypes[ann_value.sample.id][str(ann_value.field)] = (
                    TYPE_TO_DTYPE[ann_value.field.type.upper()]
                )

        annotations = []
        for sample in self._samples:
            data = sample_data.get(sample.id, {})
            dtypes = sample_dtypes.get(sample.id, {})
            annotations.append(pd.DataFrame(data, index=[sample.id]).astype(dtypes))

        return pd.concat(annotations, axis=0)

    def _get_relations(self) -> pd.DataFrame:
        relations = pd.DataFrame(index=[s.id for s in self._samples])
        relations.index.name = "sample_id"

        for relation in self.collection.relations.filter():
            # Only consider relations that include only samples in self.samples
            relation_entities_ids = set([p["entity"] for p in relation.partitions])
            if not relation_entities_ids.issubset({s.id for s in self._samples}):
                pass

            relations[relation.category] = pd.Series(
                index=relations.index, dtype="object"
            )

            for partition in relation.partitions:
                value = ""
                if partition["label"] and partition["position"]:
                    value = f"{partition['label']} / {partition['position']}"
                elif partition["label"]:
                    value = partition["label"]
                elif partition["position"]:
                    value = partition["position"]

                relations[relation.category][partition["entity"]] = value

        return relations

    @lru_cache()
    def _get_orange_object(self) -> Data:
        return self.collection.data.get(
            type="data:metadata:unique",
            ordering="-modified",
            fields=self.DATA_FIELDS,
            limit=1,
        )

    def _get_orange_data(self) -> pd.DataFrame:
        def map_and_filter_samples(
            df: pd.DataFrame, column_name: str, mapping: dict
        ) -> pd.DataFrame:
            """Map a predefined column name to a column named ``sample_id``, drop the original
            and return the constructed DataFrame.
            Omit samples for which mapping is not defined. These samples do not
            have any data objects with the defined process type.
            """
            df = df[df[column_name].isin(mapping.keys())]
            df["sample_id"] = df[column_name].map(mapping)
            df = df.drop(columns=[column_name])
            return df

        try:
            orange_meta = self._get_orange_object()
        except LookupError:
            return pd.DataFrame()

        file_name = orange_meta.files(field_name="table")[0]
        url = urljoin(self.resolwe.url, f"data/{orange_meta.id}/{file_name}")
        response = self.resolwe.session.get(url, auth=self.resolwe.auth)
        response.raise_for_status()

        with BytesIO() as f:
            f.write(response.content)
            f.seek(0)
            if file_name.endswith("xls"):
                df = pd.read_excel(f, engine="xlrd")
            elif file_name.endswith("xlsx"):
                df = pd.read_excel(f, engine="openpyxl")
            elif any(file_name.endswith(ext) for ext in ["tab", "tsv"]):
                df = pd.read_csv(f, sep="\t")
            elif file_name.endswith("csv"):
                df = pd.read_csv(f)
            else:
                # TODO: logging, warning?
                return pd.DataFrame()

        if "Sample ID" in df.columns:
            df = df.rename(columns={"Sample ID": "sample_id"})
        elif "mS#Sample ID" in df.columns:
            df = df.rename(columns={"mS#Sample ID": "sample_id"})
        elif "Sample slug" in df.columns:
            mapping = {s.slug: s.id for s in self._samples}
            df = map_and_filter_samples(
                df=df, column_name="Sample slug", mapping=mapping
            )
        elif "mS#Sample slug" in df.columns:
            mapping = {s.slug: s.id for s in self._samples}
            df = map_and_filter_samples(
                df=df, column_name="mS#Sample slug", mapping=mapping
            )
        elif "Sample name" in df.columns or "Sample name" in df.columns:
            mapping = {s.name: s.id for s in self._samples}
            if len(mapping) != len(self._samples):
                raise ValueError(
                    "Duplicate sample names. Cannot map orange table data to other metadata"
                )
            df = map_and_filter_samples(
                df=df, column_name="Sample name", mapping=mapping
            )
        elif "mS#Sample name" in df.columns:
            mapping = {s.name: s.id for s in self._samples}
            if len(mapping) != len(self._samples):
                raise ValueError(
                    "Duplicate sample names. Cannot map orange table data to other metadata"
                )
            df = map_and_filter_samples(
                df=df, column_name="mS#Sample name", mapping=mapping
            )
        return df.set_index("sample_id")

    def _download_metadata(self) -> pd.DataFrame:
        """Download samples metadata and transform into table."""
        meta = pd.DataFrame(None, index=[s.id for s in self._samples])

        # Add annotations metadata
        annotations = self._get_annotations()
        meta = meta.merge(annotations, how="left", left_index=True, right_index=True)

        # Add relations metadata
        relations = self._get_relations()
        meta = meta.merge(relations, how="left", left_index=True, right_index=True)

        # Add Orange clinical metadata
        orange_data = self._get_orange_data()
        meta = meta.merge(orange_data, how="left", left_index=True, right_index=True)

        meta = meta.sort_index()
        meta.index.name = "sample_id"

        return meta

    def _get_data_uri(self, data: Data, data_type: str) -> str:
        field_name = self.data_type_to_field_name[data_type]
        files = data.files(field_name=field_name)

        if not files:
            raise LookupError(f"Data {data.slug} has no files named {field_name}!")
        elif len(files) > 1:
            raise LookupError(
                f"Data {data.slug} has multiple files named {field_name}!"
            )

        return f"{data.id}/{files[0]}"

    def _get_data_urls(self, uris):
        response = self.resolwe.session.post(
            urljoin(self.resolwe.url, "resolve_uris/"),
            json={"uris": list(uris)},
            auth=self.resolwe.auth,
        )
        response.raise_for_status()
        uri_to_url = json.loads(response.content.decode("utf-8"))

        def resolve_url(url):
            """
            Resolve url.

            In case files are stored locally on a server, a local path
            is provided. Url has to be prepended with self.resolwe.url.
            """
            if not urlparse(url).scheme:
                return urljoin(self.resolwe.url, url)
            return url

        uri_to_url = {uri: resolve_url(url) for uri, url in uri_to_url.items()}

        return uri_to_url

    @abc.abstractmethod
    def _parse_file(self, file_obj, sample_id, data_type):
        """Parse file object and return a one DataFrame line."""
        pass

    async def _download_file(self, url, session, sample_id, data_type):
        async with session.get(url) as response:
            response.raise_for_status()
            with BytesIO() as f:
                f.write(await response.content.read())
                f.seek(0)
                sample_data = self._parse_file(f, sample_id, data_type)
        return sample_data

    async def _download_data(self, data_type: str) -> pd.DataFrame:
        """Download data files and merge them into a pandas DataFrame.

        During normal download of a single file a signed url is created on AWS
        and user is than redirected from Genialis server to the signed url.

        However, this process (signing urls and redirecting) takes time.
        To speedup things, we create a dedicated endpoint that accepts a bunch
        of file uris and return a bunch of signed url's. All in one request.

        However, these signed urls have expiration time of 60 s. In case of
        large number of uris requested (> 100 uris) it is likely that url is
        signed by Resolwe server and not downloaded for 60 seconds or more.
        Therefore we split the uris in smaller chunks, namely
        EXP_ASYNC_CHUNK_SIZE.

        :param data_type: data type
        :return: table with data, features in columns, samples in rows
        """
        df = None
        for i in self.tqdm(
            range(0, len(self._data), EXP_ASYNC_CHUNK_SIZE),
            desc="Downloading data",
            ncols=100,
            file=open(os.devnull, "w") if self.progress_callable else None,
            callable=self.progress_callable,
        ):
            data_subset = self._data[i : i + EXP_ASYNC_CHUNK_SIZE]

            # Mapping from file uri to sample id
            uri_to_id = {
                self._get_data_uri(d, data_type): d.sample.id for d in data_subset
            }

            source_urls = self._get_data_urls(uri_to_id.keys())
            urls_ids = [(url, uri_to_id[uri]) for uri, url in source_urls.items()]

            async with aiohttp.ClientSession(
                cookies=self.resolwe.auth.cookies
            ) as session:
                futures = [
                    self._download_file(url, session, id_, data_type)
                    for url, id_ in urls_ids
                ]
                data = await asyncio.gather(*futures)
                data = pd.concat(data, axis=1)
            df = pd.concat([df, data], axis=1)

        df = df.T.sort_index().sort_index(axis=1)
        df.index.name = "sample_id"
        return df

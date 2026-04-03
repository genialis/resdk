import os
import shutil
import sys
import tempfile
from unittest.mock import patch

from resdk import Resolwe

from ..base import URL, USER_EMAIL, USER_PASSWORD, BaseResdkFunctionalTest

TEST_FILES_DIR = os.path.abspath(
    os.path.normpath(os.path.join(__file__, "../../../files"))
)
DOCS_SCRIPTS_DIR = os.path.abspath(
    os.path.normpath(os.path.join(__file__, "../../../../docs/files"))
)
sys.path.insert(0, DOCS_SCRIPTS_DIR)


class BaseResdkDocsFunctionalTest(BaseResdkFunctionalTest):
    sample_slug = "resdk-example"
    reads_slug = "resdk-example-reads"
    genome_slug = "resdk-example-genome"
    genome_index_slug = "resdk-example-genome-index"
    annotation_slug = "resdk-example-annotation"
    rrna_slug = "resdk-example-rrna"
    rrna_index_slug = "resdk-example-rrna-index"
    globin_slug = "resdk-example-globin"
    globin_index_slug = "resdk-example-globin-index"
    collection_slug = "resdk-example-collection"

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmpdir)

        self.collection = self.res.collection.create(slug=self.collection_slug)
        self.collection.permissions.set_public("view")

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmpdir)

        if hasattr(self, "collection"):
            self.collection.delete(force=True)

    def run_tutorial_script(self, script_name, replace_lines=None):
        """Run a script from tutorial folder.

        If given, ``replace_lines`` should be in a list of 2-tuples::

            replace lines = [
                (0, 'replace the content of first line with this')
                (2, 'replace the content of third line with this')
            ]

        First element of tuple is line index and the second is line
        content.

        """
        script_path = os.path.join(DOCS_SCRIPTS_DIR, script_name)
        with open(script_path) as handle:
            content = handle.readlines()

        if replace_lines:
            for line_index, line_content in replace_lines:
                content[line_index] = line_content

        with patch("resdk.resolwe.AUTOMATIC_LOGIN_POSTFIX", "rest-auth/login/"):
            exec("".join(content))

    def upload_reads(self, res):
        reads = res.run(
            slug="upload-fastq-single",
            input={"src": os.path.join(TEST_FILES_DIR, "reads.fastq.gz")},
            collection=self.collection,
        )
        self.set_slug(reads, self.reads_slug)
        self.set_slug(reads.sample, self.sample_slug)

        return reads

    def upload_genome(self, res, fasta, slug):
        genome = res.run(
            slug="upload-fasta-nucl",
            input={
                "src": os.path.join(TEST_FILES_DIR, fasta),
                "species": "Dictyostelium discoideum",
                "build": "dd-05-2009",
            },
            collection=self.collection,
        )
        self.set_slug(genome, slug)

        return genome

    def upload_annotation(self, res):
        annotation = res.run(
            slug="upload-gtf",
            input={
                "src": os.path.join(TEST_FILES_DIR, "annotation.gtf.gz"),
                "source": "DICTYBASE",
                "species": "Dictyostelium discoideum",
                "build": "dd-05-2009",
            },
            collection=self.collection,
        )
        self.set_slug(annotation, self.annotation_slug)

        return annotation

    def create_genome_index(self, res, fasta, slug):
        genome_index = res.run(
            slug="alignment-star-index",
            input={
                "ref_seq": fasta,
            },
            collection=self.collection,
        )
        self.set_slug(genome_index, slug)

        return genome_index

    def allow_run_process(self, res, slug):
        process = res.process.get(slug=slug)
        process.permissions.set_public("view")

    def allow_use_descriptor_schema(self, res, slug):
        descriptor_schema = res.descriptor_schema.get(slug=slug)
        descriptor_schema.permissions.set_public("view")


class TestIndex(BaseResdkDocsFunctionalTest):
    def setUp(self):
        super().setUp()
        self.reads = self.upload_reads(self.res)

    def test_index(self):
        """Test example code used in ``README.rst`` and ``index.rst``."""
        self.run_tutorial_script(
            "index.py",
            replace_lines=[(4, "res = resdk.Resolwe(url='{}')\n".format(URL))],
        )


class TestStart(BaseResdkDocsFunctionalTest):
    def setUp(self):
        super().setUp()

        # Create data for tests:
        self.reads = self.upload_reads(self.res)
        self.genome = self.upload_genome(self.res, "genome.fasta.gz", self.genome_slug)
        self.genome_index = self.create_genome_index(
            self.res, self.genome, self.genome_index_slug
        )

        # Set permissions for running processes:
        self.allow_run_process(self.res, "alignment-star")

    def test_start(self):
        """Test getting started."""
        self.run_tutorial_script(
            "start.py",
            replace_lines=[
                (4, "res = resdk.Resolwe(url='{}')\n".format(URL)),
                (5, "res.login('{}', '{}')\n".format(USER_EMAIL, USER_PASSWORD)),
                # Skip download, since data objects have not finished processing
                (49, "\n"),
            ],
        )


class TestTutorialGet(BaseResdkDocsFunctionalTest):
    def setUp(self):
        super().setUp()

        self.reads = self.upload_reads(self.res)

    def test_tutorial_get(self):
        """Test tutorial-get."""
        self.run_tutorial_script(
            "tutorial-get.py",
            replace_lines=[
                (4, "res = resdk.Resolwe(url='{}')\n".format(URL)),
                (5, "res.login('{}', '{}')\n".format(USER_EMAIL, USER_PASSWORD)),
            ],
        )


class TestTutorialCreate(BaseResdkDocsFunctionalTest):
    def setUp(self):
        super().setUp()

        self.reads = self.upload_reads(self.res)

        self.annotation = self.upload_annotation(self.res)

        self.genome = self.upload_genome(self.res, "genome.fasta.gz", self.genome_slug)
        self.genome_index = self.create_genome_index(
            self.res, self.genome, self.genome_index_slug
        )

        self.rrna = self.upload_genome(self.res, "rrna.fasta", self.rrna_slug)
        self.rrna_index = self.create_genome_index(
            self.res, self.rrna, self.rrna_index_slug
        )
        self.globin = self.upload_genome(self.res, "globin.fasta", self.globin_slug)
        self.globin_index = self.create_genome_index(
            self.res, self.globin, self.globin_index_slug
        )

        # Set permissions for running processes:
        self.allow_run_process(self.res, "upload-fastq-single")
        self.allow_run_process(self.res, "alignment-star")
        self.allow_run_process(self.res, "workflow-bbduk-star-featurecounts-qc")
        # Set permissions for using descriptor_schema.
        self.allow_use_descriptor_schema(self.res, "reads")

    def test_tutorial_create(self):
        """Test tutorial-create."""
        self.run_tutorial_script(
            "tutorial-create.py",
            replace_lines=[
                (3, "res = resdk.Resolwe(url='{}')\n".format(URL)),
                (4, "res.login('{}', '{}')\n".format(USER_EMAIL, USER_PASSWORD)),
                (
                    21,
                    "        'src': '{}'\n".format(
                        os.path.join(TEST_FILES_DIR, "reads.fastq.gz")
                    ),
                ),
                # Data object is not finished, so something like this
                # (107, "foo = res.data.get('{}').stdout()\n".format(self.reads_slug)),
                # is replaced with an empty line. There is now way to perform
                # download if data objects are still processing and/or have not
                # produced any stdout.txt. So just write an empty line:
                (9, "\n"),
                (10, "\n"),
                (11, "\n"),
                (12, "\n"),
                (107, "\n"),
            ],
        )


class TestTutorialResources(BaseResdkFunctionalTest):
    def test_tutorial_resources(self):
        """Verify existence of resources required for tutorial."""
        res = Resolwe(url="https://app.genialis.com")

        sample_slugs = [
            BaseResdkDocsFunctionalTest.sample_slug,
        ]
        for sample_slug in sample_slugs:
            res.sample.get(sample_slug)

        data_slugs = [
            BaseResdkDocsFunctionalTest.reads_slug,
            BaseResdkDocsFunctionalTest.genome_slug,
            BaseResdkDocsFunctionalTest.annotation_slug,
            BaseResdkDocsFunctionalTest.genome_index_slug,
            BaseResdkDocsFunctionalTest.rrna_slug,
            BaseResdkDocsFunctionalTest.rrna_index_slug,
            BaseResdkDocsFunctionalTest.globin_slug,
            BaseResdkDocsFunctionalTest.globin_index_slug,
        ]
        for data_slug in data_slugs:
            res.data.get(slug=data_slug, fields="id")

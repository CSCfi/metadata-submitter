"""Test queries submissions and objects."""
import asyncio
import logging

from tests.integration.conf import objects_url, test_fega_xml_files
from tests.integration.helpers import delete_object, post_object

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestQueries:
    """Test querying."""

    async def test_querying_works(self, client_logged_in, submission_fega):
        """Test query endpoint with working and failing query.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: id of the submission used to group submission objects
        """
        files = await asyncio.gather(
            *[
                post_object(client_logged_in, schema, submission_fega, filename)
                for schema, filename in test_fega_xml_files
            ]
        )

        queries = {
            "study": [
                ("studyTitle", "integrated"),
                ("studyType", "Other"),
                ("studyAbstract", "arabidopsis thaliana"),
                ("studyAttributes", "prjna107265"),
                ("studyAttributes", "parent_bioproject"),
            ],
            "sample": [
                ("title", "HapMap sample"),
                ("description", "human hapmap individual"),
                ("centerName", "hapmap"),
                ("sampleName", "homo sapiens"),
                ("scientificName", "homo sapiens"),
                ("sampleName", 9606),
            ],
            "run": [
                ("fileType", "srf"),
                ("experimentReference", "g1k-bgi-na18542"),
                ("experimentReference", "erx000037"),
            ],
            "experiment": [("studyReference", "1000Genomes project pilot")],
            "analysis": [
                ("fileType", "other"),
                ("studyReference", "HipSci___RNAseq___"),
                ("sampleReference", "HPSI0114i-eipl_3"),
            ],
        }

        async def do_one_query(schema, key, value, expected_status):
            async with client_logged_in.get(f"{objects_url}/{schema}?{key}={value}") as resp:
                assert resp.status == expected_status, f"HTTP Status code error, got {resp.status}"

        for schema, schema_queries in queries.items():
            LOG.debug(f"Querying {schema} collection with working params")
            await asyncio.gather(*[do_one_query(schema, key, value, 200) for key, value in schema_queries])
            LOG.debug(f"Querying {schema} collection with non-working params")
            invalid = "yoloswaggings"
            await asyncio.gather(*[do_one_query(schema, key, invalid, 404) for key, _ in schema_queries])

        await asyncio.gather(*[delete_object(client_logged_in, schema, accession_id) for accession_id, schema in files])


class TestQueryPagination:
    """Testing getting objects & pagination."""

    async def test_getting_all_objects_from_schema_works(self, client_logged_in, submission_fega):
        """Check that /objects/study returns objects with correct pagination.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: id of the submission used to group submission objects
        """
        # Add objects
        files = await asyncio.gather(
            *[post_object(client_logged_in, "sample", submission_fega, "SRS001433.xml") for _ in range(13)]
        )

        # Test default values
        async with client_logged_in.get(f"{objects_url}/sample") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["page"] == 1
            assert ans["page"]["size"] == 10
            assert ans["page"]["totalPages"] == 2
            assert ans["page"]["totalObjects"] == 13, ans["page"]["totalObjects"]
            assert len(ans["objects"]) == 10

        # Test with custom pagination values
        async with client_logged_in.get(f"{objects_url}/sample?page=2&per_page=3") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["page"] == 2
            assert ans["page"]["size"] == 3
            assert ans["page"]["totalPages"] == 5, ans["page"]["totalPages"]
            assert ans["page"]["totalObjects"] == 13, ans["page"]["totalObjects"]
            assert len(ans["objects"]) == 3

        # Test with wrong pagination values
        async with client_logged_in.get(f"{objects_url}/sample?page=-1") as resp:
            assert resp.status == 400
        async with client_logged_in.get(f"{objects_url}/sample?per_page=0") as resp:
            assert resp.status == 400

        # Delete objects
        await asyncio.gather(*[delete_object(client_logged_in, "sample", accession_id) for accession_id, _ in files])

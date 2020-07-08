"""
Run integration tests against backend api endpoints.

Deleting from db is currently not supported, objects added to db in different
should be taken into account.
"""

import asyncio
import aiofiles
import aiohttp
import logging
from aiohttp import FormData
from pathlib import Path

FORMAT = "[%(asctime)s][%(name)s][%(process)d %(processName)s]" \
         "[%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)

TESTFILES_ROOT = Path(__file__).parent.parent / 'test_files'

test_files = [
    ("study", "SRP000539.xml"),
    ("sample", "SRS001433.xml"),
    ("run", "ERR000076.xml"),
    ("experiment", "ERX000119.xml"),
    ("analysis", "ERZ266973.xml")
]


async def create_submission_data(schema, filename):
    """Create request data from pairs of schemas and filenames.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    data = FormData()
    path_to_file = TESTFILES_ROOT / schema / filename
    path = path_to_file.as_posix()
    async with aiofiles.open(path, mode='r') as f:
        data.add_field(schema.upper(),
                       await f.read(),
                       filename=filename,
                       content_type='text/xml')
    return data


async def test_post_and_get_works(schema, filename):
    """Test REST api POST, GET and DELETE reqs.

    Tries to create new object, gets accession id and checks if correct
    resource is returned with that id. Finally deletes the object.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    async with aiohttp.ClientSession() as sess:
        base_url = "http://localhost:5430/objects"
        data = await create_submission_data(schema, filename)
        async with sess.post(f"{base_url}/{schema}", data=data) as resp:
            LOG.debug(f"Adding new object to {schema}")
            assert resp.status == 201, 'HTTP Status code error'
            ans = await resp.json()
            accession_id = ans["accessionId"]
        async with sess.get(f"{base_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Getting info of accession {accession_id} in {schema}")
            assert resp.status == 200, 'HTTP Status code error'
        async with sess.delete(f"{base_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Deleting object {accession_id} in {schema}")
            assert resp.status == 204, 'HTTP Status code error'
        async with sess.get(f"{base_url}/{schema}/{accession_id}") as resp:
            LOG.debug(f"Checking that json object {accession_id} was deleted")
            assert resp.status == 404, 'HTTP Status code error'
        async with sess.get(f"{base_url}/{schema}/{accession_id}"
                            f"?format=xml") as resp:
            LOG.debug(f"Checking that xml object {accession_id} was deleted")
            assert resp.status == 404, 'HTTP Status code error'


async def test_querying_works():
    """Test query endpoint with working and failing query."""
    async with aiohttp.ClientSession() as sess:
        base_url = "http://localhost:5430/objects"
        accession_ids = []

        async def post_one(schema, filename):
            data = await create_submission_data(schema, filename)
            async with sess.post(f"{base_url}/{schema}", data=data) as resp:
                assert resp.status == 201, 'HTTP Status code error'
                ans = await resp.json()
                accession_ids.append((schema, ans["accessionId"]))

        await asyncio.gather(*[post_one(schema, filename) for
                               schema, filename in test_files])

        # Generic query endpoints
        LOG.debug("Querying collections with generic params")
        query = "sample?title=HapMap sample"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        query = "sample?description=human hapmap individual"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        query = "sample?centerName=hapmap"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'

        # TODO: query name param here

        # Study related query endpoints

        LOG.debug("Querying study collection with non-working params")
        query = "study?studyTitle=yoloswaggingsandthefellowshipofthebling"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 404, 'HTTP Status code error'
        query = "study?studyType=yoloswaggingsandthefellowshipofthebling"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 404, 'HTTP Status code error'
        query = "study?studyAbstract=yoloswaggingsandthefellowshipofthebling"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 404, 'HTTP Status code error'
        query = "study?studyAttributes=yoloswaggingsandthefellowshipofthebling"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 404, 'HTTP Status code error'

        LOG.debug("Querying study collection with working params")
        query = "study?studyTitle=integrated"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        query = "study?studyType=Other"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        query = "study?studyAbstract=arabidopsis thaliana"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        query = "study?studyAttributes=prjna107265"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        query = "study?studyAttributes=parent_bioproject"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'

        # Sample-related query endpoints
        LOG.debug("Querying sample collection with working params")
        query = "sample?sampleName=homo sapiens"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        query = "sample?scientificName=homo sapiens"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'

        # Run-related query endpoints
        LOG.debug("Querying run collection with working params")
        query = "run?fileType=srf"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        query = "run?experimentReference=g1k-bgi-na18542"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        query = "run?experimentReference=erx000037"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'

        # Experiment-related query endpoints
        LOG.debug("Querying experiment collection with working params")
        query = "experiment?studyReference=1000Genomes project pilot"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'

        # Analysis-related query endpoints
        LOG.debug("Querying analysis collection with working params")
        query = "analysis?studyReference=HipSci___RNAseq___"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        query = "analysis?sampleReference=HPSI0114i-eipl_3"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'

        # Delete files
        async def delete_one(schema, accession_id):
            url = f"{base_url}/{schema}/{accession_id}"
            async with sess.delete(f"{url}") as resp:
                assert resp.status == 204, 'HTTP Status code error'

        LOG.debug("Deleting objects from study")
        await asyncio.gather(*[delete_one(schema, accession_id) for
                               schema, accession_id in accession_ids])


async def test_getting_all_objects_from_schema_works():
    """Check that /objects/study returns objects with correct pagination."""
    async with aiohttp.ClientSession() as sess:
        accession_ids = []
        base_url = "http://localhost:5430/objects/study"

        async def post_one():
            data = await create_submission_data("study", "SRP000539.xml")
            async with sess.post(f"{base_url}", data=data) as resp:
                assert resp.status == 201, 'HTTP Status code error'
                ans = await resp.json()
                accession_ids.append(ans["accessionId"])

        LOG.debug("Adding new objects to study")
        await asyncio.gather(*[post_one() for _ in range(13)])

        # Test default values
        async with sess.get(f"{base_url}") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["page"] == 1
            assert ans["page"]["size"] == 10
            assert ans["page"]["totalPages"] == 2
            assert ans["page"]["totalObjects"] == 13
            assert len(ans["objects"]) == 10

        # Test with custom pagination values
        async with sess.get(f"{base_url}?page=2&per_page=3") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["page"] == 2
            assert ans["page"]["size"] == 3
            assert ans["page"]["totalPages"] == 5
            assert ans["page"]["totalObjects"] == 13
            assert len(ans["objects"]) == 3

        # Test with wrong pagination values
        async with sess.get(f"{base_url}?page=-1") as resp:
            assert resp.status == 400
        async with sess.get(f"{base_url}?per_page=0") as resp:
            assert resp.status == 400

        async def delete_one(accession_id):
            async with sess.delete(f"{base_url}/{accession_id}") as resp:
                assert resp.status == 204, 'HTTP Status code error'

        LOG.debug("Deleting objects from study")
        await asyncio.gather(*[delete_one(accession_id) for accession_id
                               in accession_ids])


async def main():
    """Launch different test tasks and run them."""
    # Test adding and getting files
    await asyncio.gather(
        *[test_post_and_get_works(schema, file) for schema, file in test_files]
    )

    # Test queries
    await test_querying_works()

    # Test /objects/study endpoint for query pagination
    await test_getting_all_objects_from_schema_works()

if __name__ == '__main__':
    asyncio.run(main())

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
    async with aiohttp.Clientsess() as sess:
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
    async with aiohttp.Clientsess() as sess:
        base_url = "http://localhost:5430/objects"

        # Study-related query endpoints
        data = await create_submission_data("study", "SRP000539.xml")
        async with sess.post(f"{base_url}/study", data=data) as resp:
            LOG.debug("Adding new object to study")
            assert resp.status == 201, 'HTTP Status code error'
            ans = await resp.json()
            accession_id = ans["accessionId"]
        LOG.debug("Querying study collection")
        query = "study?studyTitle=yoloswaggingsandthefellowshipofthebling"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 404, 'HTTP Status code error'
        query = "study?studyTitle=integrated"
        async with sess.get(f"{base_url}/{query}") as resp:
            assert resp.status == 200, 'HTTP Status code error'
        async with sess.delete(f"{base_url}/study/{accession_id}") as resp:
            LOG.debug(f"Deleting object {accession_id} in study")
            assert resp.status == 204, 'HTTP Status code error'


async def test_getting_all_objects_from_schema_works():
    """Check that /objects/study returns objects that were added."""
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
        await asyncio.gather(*[post_one() for _ in range(5)])

        async with sess.get(f"{base_url}") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert len(ans) == 5

        async def delete_one(accession_id):
            async with sess.delete(f"{base_url}/{accession_id}") as resp:
                assert resp.status == 204, 'HTTP Status code error'

        LOG.debug("Deleting objects from study")
        await asyncio.gather(*[delete_one(accession_id) for accession_id
                               in accession_ids])


async def main():
    """Launch different test tasks and run them.

    Change value in range for how many times to repeat the tests.
    Set to high value (e.g. 500) if you want to stress test server.
    """
    # Test adding and getting files
    test_files = [
        ("study", "SRP000539.xml"),
        ("sample", "SRS001433.xml"),
        ("run", "ERR000076.xml"),
        ("experiment", "ERX000119.xml"),
        ("analysis", "ERZ266973.xml")
    ]
    await asyncio.gather(
        *[test_post_and_get_works(schema, file) for schema, file in test_files]
    )

    # Test queries
    # await test_querying_works()

    # Test /objects/study endpoint
    # await test_getting_all_objects_from_schema_works()

if __name__ == '__main__':
    asyncio.run(main())

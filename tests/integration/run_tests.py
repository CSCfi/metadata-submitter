"""Run integration tests against backend api endpoints."""
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
    """Test REST api post and get requests.

    Tries to create new object, gets accession id and checks if correct
    resource is returned with that id.

    :param schema: name of the schema (folder) used for testing
    :param filename: name of the file used for testing.
    """
    async with aiohttp.ClientSession() as session:
        LOG.debug(f"Testing POST with {schema}")
        base_url = "http://localhost:5430/object"
        data = await create_submission_data(schema, filename)
        async with session.post(f"{base_url}/{schema}", data=data) as resp:
            assert resp.status == 201, 'HTTP Status code error'
            ans = await resp.json()
            accession_id = ans["accessionId"]
        LOG.debug(f"Testing GET with {schema}")
        async with session.get(f"{base_url}/{schema}/{accession_id}") as resp:
            assert resp.status == 200, 'HTTP Status code error'


async def main():
    """Launch bunch of test tasks and run them asyncronously."""
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

if __name__ == '__main__':
    asyncio.run(main())

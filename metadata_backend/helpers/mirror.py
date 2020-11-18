"""Mirror EGA Metadata using REST endpoints.

Reworked from implementation found here: https://github.com/neicnordic/sda-metadata-mirror
"""
from typing import Generator, Iterable, Dict
import itertools
import requests
import json

from aiohttp import web

from ..helpers.logger import LOG

BASE_URL = "https://ega-archive.org/metadata/v2/"
ENDPOINTS = ["analyses", "dacs", "samples", "studies"]
SESSION = requests.Session()


class MetadataMirror:
    """Methods for mirroring metadata from EGA."""

    def mirror_dataset(self, dataset: str) -> Dict:
        """Write data to JSON file."""
        if not dataset.startswith("EGAD"):
            reason = f"{dataset} does not appear to be a valid EGA dataset."
            raise web.HTTPBadRequest(reason=reason)
        r = SESSION.get(f"{BASE_URL}datasets/{dataset}")
        if r.status_code == 200:
            LOG.info(f"Retrieving dataset {dataset}.")
            response = r.json()
            dataset = json.dumps(response["response"]["result"][0])
            addable = {"dataset": dataset}

            objects = self.get_dataset_objects(dataset)
            for idx, val in enumerate(objects):
                the_data = list(val)
                object = json.dumps(the_data)
                addable[ENDPOINTS[idx]] = object
            return addable
        else:
            raise web.HTTPBadRequest(reason="Something went wrong")

    def get_dataset_objects(self, dataset_id: str) -> Generator:
        """Retrieve information associated to dataset."""
        raw_events: Iterable = iter(())
        for endpoint in ENDPOINTS:
            LOG.info(f"Processing {endpoint} for {dataset_id} ...")
            yield itertools.chain(raw_events, self.get_dataset_object(endpoint, dataset_id))

    def get_dataset_object(self, data_type: str, dataset_id: str) -> Generator:
        """Retrieve data by object type and dataset ID."""
        skip: int = 0
        limit: int = 10
        has_more = True
        payload = {"queryBy": "dataset", "queryId": dataset_id, "skip": str(skip), "limit": str(limit)}
        while has_more:
            r = SESSION.get(f"{BASE_URL}{data_type}", params=payload)
            if r.status_code == 200:
                response = r.json()
                results_nb = int(response["response"]["numTotalResults"])
                LOG.info(f"Retrieving {limit} {data_type} for {dataset_id} from {results_nb} results.")
                for res in response["response"]["result"]:
                    yield res

                if results_nb >= limit:
                    limit += 10
                    skip += 10
                else:
                    has_more = False
            else:
                reason = f"Error retrieving {data_type} for {dataset_id}. API call returned a {r.status_code}"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

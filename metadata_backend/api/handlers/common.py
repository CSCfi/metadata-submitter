"""Functions shared between handlers."""
import csv
import string
from typing import Any, Dict, List, Tuple

from aiohttp import BodyPartReader, MultipartReader, hdrs, web
from aiohttp.web import Request
from defusedxml.ElementTree import ParseError
from xmlschema import XMLResource

from ...conf.conf import schema_types
from ...helpers.logger import LOG
from ...helpers.parser import CSVToJSONParser


async def multipart_content(
    req: Request, extract_one: bool = False, expect_xml: bool = False
) -> Tuple[List[Tuple[Any, str, str]], str]:
    """Get content(s) and schema type(s) of a multipart request (from either csv or xml format).

    Note: for multiple files support check: https://docs.aiohttp.org/en/stable/multipart.html#hacking-multipart

    :param req: POST request containing "multipart/form-data" upload
    :param extract_one: boolean stating whether multiple files should be handled
    :param expect_xml: boolean stating if file can be expected to be XML
    :raises: HTTPBadRequest for multiple different reasons
    :returns: content and schema type for each uploaded file and file type of the upload
    """
    xml_files: List[Tuple[str, str, str]] = []
    csv_files: List[Tuple[Dict, str, str]] = []
    try:
        reader = await req.multipart()
    except AssertionError as exc:
        reason = "Request does not have valid multipart/form content."
        LOG.exception(reason)
        raise web.HTTPBadRequest(reason=reason) from exc
    while True:
        part = await reader.next()
        # we expect a simple body part (BodyPartReader) instance here
        # otherwise, it will be another MultipartReader instance for the nested multipart.
        # we don't need to cast the part BodyPartReader, we fail if we get anything else.
        # MultipartReader is aimed at ``multiplart/mixed``, ``multipart/related`` content
        # we will be working with ``multipart/form-data`` only.
        if isinstance(part, MultipartReader):
            reason = "We cannot work nested multipart content."
            LOG.error(reason)
            raise web.HTTPUnsupportedMediaType(reason=reason)
        if not part:
            break
        filename = part.filename if part.filename else ""
        if extract_one and (xml_files or csv_files):
            reason = "Only one file can be sent to this endpoint at a time."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        # we check the multipart request header to see file type
        # or we expect XML file directly
        # additionally we check that the content is XML or CSV to be accurate
        if expect_xml or part.headers[hdrs.CONTENT_TYPE] == "text/xml":
            content, schema_type = await _extract_upload(part)
            _check_xml(content)
            xml_files.append((content, schema_type, filename))
        elif part.headers[hdrs.CONTENT_TYPE] == "text/csv":
            content, schema_type = await _extract_upload(part)
            _check_csv(content)
            csv_content = CSVToJSONParser().parse(schema_type, content)
            for row in csv_content:
                csv_files.append((row, schema_type, filename))
        else:
            reason = "Submitted file was not proper XML nor CSV."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    # Return extracted content
    return _get_content_with_type(xml_files, csv_files)


async def _extract_upload(part: BodyPartReader) -> Tuple[str, str]:
    """Extract a submitted file from upload.

    :param part: Multipart reader for single body part
    :raises: HTTPNotFound if schema was not found
    :returns: content as text and schema type for uploaded file
    """
    schema_type = part.name.lower() if part.name else "none"
    if schema_type not in schema_types:
        reason = f"Specified schema {schema_type} was not found."
        LOG.error(reason)
        raise web.HTTPNotFound(reason=reason)
    data = []
    while True:
        chunk = await part.read_chunk()
        if not chunk:
            break
        data.append(chunk)
    xml_content = "".join(x.decode("UTF-8") for x in data)
    LOG.debug("Processed file in collection: %r.", schema_type)
    return xml_content, schema_type


def _check_csv(content: str) -> bool:
    """Check if content is in CSV format.

    :param content: Text of file content
    :raises: HTTPBadRequest if both CSV validation fails
    :returns: true if file is CSV
    """
    try:
        # Check for non-printable characters which should not be in CSV files
        if not all(c in string.printable or c.isprintable() for c in content):
            raise csv.Error
        csv.Sniffer().sniff(content)
        # No errors indicates validity of CSV
        LOG.info("Valid CSV content was extracted.")
        return True
    except csv.Error:
        reason = "Submitted file was not proper formatted as CSV."
        LOG.exception(reason)
        return False


def _check_xml(content: str) -> bool:
    """Check if content is in XML format.

    :param content: Text of file content
    :raises: HTTPBadRequest if both XML validation fails
    :returns: name of file type
    """
    try:
        XMLResource(content, allow="local", defuse="always")
        LOG.info("Valid XML content was extracted.")
        return True
    except ParseError as err:
        reason = f"Submitted file was not proper XML, err: {err}"
        LOG.exception(reason)
        return False


def _get_content_with_type(
    xml_files: List[Tuple[str, str, str]], csv_files: List[Tuple[Dict, str, str]]
) -> Tuple[List[Tuple[Any, str, str]], str]:
    """Return either list of XML or CSV files with the file type info.

    :param xml_files: List of xml contents with schema types
    :param csv_files: List of csv contents with schema types
    :raises: HTTPBadRequest if both lists are populated or empty
    :returns: List of xml or csv files with string stating which file type
    """
    if xml_files and csv_files:
        reason = "Request contained both xml and csv file types. Only one file type can be processed in this endpoint."
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)
    if xml_files:
        # Files are sorted to spesific order by their schema priorities
        # (e.g. submission should be processed before study).
        return sorted(xml_files, key=lambda x: schema_types[x[1]]["priority"]), "xml"
    if csv_files:
        return csv_files, "csv"

    reason = "Request data seems empty."
    LOG.error(reason)
    raise web.HTTPBadRequest(reason=reason)

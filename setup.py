from setuptools import setup
from metadata_backend import __version__, __author__, __title__

_main_module = 'metadata_backend'

with open("requirements.txt") as reqs:
    requirements = reqs.read().splitlines()

setup(
    # There are some restrictions on what makes a valid project name
    # specification here:
    # https://packaging.python.org/specifications/core-metadata/#name
    name='metadata_backend',  # Required

    # Versions should comply with PEP 440:
    # https://www.python.org/dev/peps/pep-0440/
    #
    # For a discussion on single-sourcing the version across setup.py and the
    # project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version=__version__,  # Required

    # This is a one-line description or tagline of what your project does. This
    # corresponds to the "Summary" metadata field:
    # https://packaging.python.org/specifications/core-metadata/#summary
    description=__title__,  # Required

    author=__author__,  # Optional

    classifiers=[
        'License :: OSI Approved :: MIT License'
    ],

    # Alternative for listing individual packages
    packages=[_main_module],

    install_requires=requirements,

    extras_require={
        'test': ['coverage', 'pytest', 'pytest-asyncio', 'pytest-cov',
                 'coveralls', 'tox']
    },

    package_data={'': ['schemas/*.xsd']},
    include_package_data=True,

    entry_points={
        'console_scripts': [
            'metadata_submitter=metadata_backend.server:main',
        ],
    },

    project_urls={
        'Source': 'https://github.com/CSCfi/metadata_submitter',
    },
)

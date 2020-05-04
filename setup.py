from setuptools import setup
from metadata_backend import __version__, __author__, __title__

_main_module = 'metadata_backend'

with open("requirements.txt") as reqs:
    requirements = reqs.read().splitlines()

setup(
    name='metadata_backend',
    version=__version__,
    description=__title__,
    author=__author__,

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

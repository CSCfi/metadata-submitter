from setuptools import setup, find_packages
from metadata_backend import __author__, __title__, __version__

with open("requirements.txt") as reqs:
    requirements = reqs.read().splitlines()

setup(
    name='metadata_backend',
    version=__version__,
    description=__title__,
    author=__author__,

    # Instead of listing each package manually, we can use find_packages() to
    # automatically discover all packages and subpackages.
    packages=find_packages(exclude=["tests"]),

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

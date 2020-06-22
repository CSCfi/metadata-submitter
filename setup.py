"""Settings for building package."""

from setuptools import find_packages, setup

from metadata_backend import __author__, __title__, __version__

with open("requirements.txt") as reqs:
    requirements = reqs.read().splitlines()

setup(
    # There are some restrictions on what makes a valid project name
    # specification here:
    # https://packaging.python.org/specifications/core-metadata/#name
    name='metadata_backend',

    # Versions should comply with PEP 440:
    # https://www.python.org/dev/peps/pep-0440/
    # For a discussion on single-sourcing the version across setup.py and the
    # project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version=__version__,

    # This is a one-line description or tagline of what your project does. This
    # corresponds to the "Summary" metadata field:
    # https://packaging.python.org/specifications/core-metadata/#summary
    description=__title__,

    author=__author__,

    classifiers=[
        'License :: OSI Approved :: MIT License'
    ],

    # Instead of listing each package manually, we can use find_packages() to
    # automatically discover all packages and subpackages.
    packages=find_packages(exclude=["tests"]),

    install_requires=requirements,

    extras_require={
        'test': ['coverage', 'pytest', 'pytest-cov', 'coveralls', 'tox',
                 'mongomock'],
        'docs': ['sphinx >= 1.4', 'sphinx_rtd_theme'],
    },

    package_data={'': ['schemas/*.xsd', 'frontend/*', 'frontend/static/js/*']},
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

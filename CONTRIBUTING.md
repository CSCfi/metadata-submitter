## How to contribute

If you're reading this, it means you saw something that is not right, you want to add a new feature or your manager asked you to contribute to this. In any case we are glad and it would be awesome if you can contribute.

### Testing

We have a handful of unit tests and integration tests. In our Git workflow unit tests are run on every Push and Pull Request, while integration tests run on every Pull Request.

### Submitting Issues

We have templates for submitting new issues, that you can fill out. For example if you found a bug, use the following [template to report a bug](https://github.com/CSCfi/metadata-submitter/issues/new?template=bug_report.md).


### Submitting changes

When you made some changes you are happy with please send a [GitHub Pull Request to metadata-submitter](https://github.com/CSCfi/metadata-submitter/pull/new/dev) to `main` branch with a clear list of what you've done (read more about [pull requests](https://help.github.com/en/articles/about-pull-requests)). When you create that Pull Request, we will forever be in your debt if you include unit tests. For extra bonus points you can always use add some more integration tests.

Please follow our Git branches model and coding conventions (both below), and make sure all of your commits are atomic (preferably one feature per commit) and it is recommended a Pull Request addresses one functionality or fixes one bug.

Always write a clear log message for your commits, and if there is an issue open, reference that issue. This guide might help: [How to Write a Git Commit Message](https://chris.beams.io/posts/git-commit/).

Once submitted, the Pull Request will go through a review process, meaning we will judge your code :smile:.

#### Git Branches

We use `main` branch as the default branch of the repository.
All merge/pull requests related to features should be done against `main` branch. Specific release versions of the code can be acquired via git tags.

Give your branch a short descriptive name (like the names between the `<>` below) and prefix the name with something representative for that branch:

   * `feature/<feature-name>` - used when an enhancement or new feature was implemented
   * `docs/<what-the-docs>` - missing docs or keeping them up to date
   * `bugfix/<caught-it>` - solved a bug
   * `test/<thank-you>` - adding missing tests for a feature, we would prefer they would come with the `feature` but still `thank you`
   * `refactor/<that-name-is-confusing>` - well we hope we don't mess anything and we don't get to use this
   * `hotfix/<oh-no>` - for when things needed to be fixed yesterday


### Coding conventions

We do optimize for readability, and it would be awesome if you go through the code and see what conventions we've used so far, some are also explained here:
- Indentation should be 4 *spaces*
- 120 character limit is almost strict, but can be broken in documentation when
 hyperlinks go over the limits
- We use [black](https://github.com/psf/black) for code format and also check for [pep8](https://www.python.org/dev/peps/pep-0008/) and [pep257](https://www.python.org/dev/peps/pep-0257/) with some small exceptions. You can see the stated exceptions in `tox.ini` configuration file
- We like to keep things simple, so when possible avoid importing any big libraries.
- Tools to help you:
  - Tox is configured to run bunch of tests: black, flake8, docstrings, missing type hints, mypy, pylint, vulture as well as checking JSON schemas and meta schemas;
  - Tox is also ran in our CI, so please run tox before each push to this repository;
  - If you like things to happen in an automated manner, you can add pre-commit hook to your git workflow! Hook can be found from [scripts-folder](scripts) and it includes settings for tox and [pyspelling](https://facelessuser.github.io/pyspelling/) (which is there just for, well, spelling errors);
  - some [pre-commit-hooks](https://github.com/pre-commit/pre-commit-hooks) are configured under the `.pre-commit-config.yaml` config file.

Thanks,
CSC developers

Releasing
=========

This project uses ``setuptools-scm`` for version management from git tags.

Release Process
---------------

1. Ensure all tests pass on ``main``:

   .. code-block:: bash

      ./scripts/run-all-checks.sh

2. Create a git tag:

   .. code-block:: bash

      git tag -a v1.2.3 -m "Release v1.2.3"
      git push origin v1.2.3

3. Create a GitHub Release from the tag. The ``publish_to_pypi.yml`` workflow
   will automatically build and publish to PyPI.

4. Verify the release on PyPI:

   .. code-block:: bash

      pip install rms-link-checker==1.2.3
      link_check --version

Version Numbering
-----------------

We follow `Semantic Versioning <https://semver.org/>`_:

- ``MAJOR``: incompatible API changes
- ``MINOR``: new backwards-compatible features
- ``PATCH``: backwards-compatible bug fixes

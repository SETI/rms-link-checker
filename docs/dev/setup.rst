Developer Setup
===============

Prerequisites
-------------

- Python 3.10 or later
- git

Clone and Install
-----------------

.. code-block:: bash

   git clone https://github.com/SETI/rms-link-checker.git
   cd rms-link-checker
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e ".[dev]"

Verify the installation:

.. code-block:: bash

   link_check --version
   pytest -n auto --cov

Running All Checks
------------------

.. code-block:: bash

   ./scripts/run-all-checks.sh

This runs ruff, mypy, pytest (with coverage), Sphinx build, and PyMarkdown.

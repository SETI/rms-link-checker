Testing
=======

Running Tests
-------------

Run the full test suite with parallel execution and coverage:

.. code-block:: bash

   pytest -n auto --cov

Run a single test file:

.. code-block:: bash

   pytest tests/test_url_utils.py -v

Run with coverage report:

.. code-block:: bash

   pytest --cov --cov-report=html
   open htmlcov/index.html

Coverage Target
---------------

We target **80% line coverage** across the entire codebase.

Writing Tests
-------------

All tests live in ``tests/``. We follow TDD (Red-Green-Refactor):

1. Write a failing test that specifies the expected behavior.
2. Implement the minimum code to make the test pass.
3. Refactor while keeping tests green.

All HTTP interactions are mocked using the ``responses`` library — the test
suite must not make real network requests.

Test Structure
--------------

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Test file
     - What it tests
   * - ``test_url_utils.py``
     - URL normalization, prefix matching, depth
   * - ``test_config.py``
     - Config loading, YAML parsing, CLI override
   * - ``test_classifier.py``
     - URL decision tree, asset type classification
   * - ``test_http_client.py``
     - HTTP requests, retries, redirects, SSL
   * - ``test_html_parser.py``
     - Link extraction, anchor collection
   * - ``test_results.py``
     - Thread-safe results aggregation
   * - ``test_report.py``
     - All report sections
   * - ``test_crawler.py``
     - End-to-end crawl scenarios
   * - ``test_cli.py``
     - Argument parsing, exit codes
   * - ``test_progress.py``
     - Progress reporter

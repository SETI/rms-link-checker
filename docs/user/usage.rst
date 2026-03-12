Usage
=====

Synopsis
--------

.. code-block:: text

   link_check [OPTIONS] [ROOT_URL]

``ROOT_URL`` is the URL to start crawling from. It may also be specified in a
:doc:`configuration file <configuration>`.

Options
-------

.. list-table::
   :widths: 25 10 15 50
   :header-rows: 1

   * - Flag
     - Type
     - Default
     - Description
   * - ``ROOT_URL``
     - string
     - (required)
     - Root URL to begin crawling.
   * - ``-o``, ``--output``
     - path
     - stdout
     - File path for the final plain-text report.
   * - ``--log-file``
     - path
     - stderr
     - File path for log messages.
   * - ``--log-level``
     - string
     - ``INFO``
     - Minimum log level: ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``.
   * - ``--timeout``
     - int
     - ``10``
     - Timeout in seconds for each HTTP request.
   * - ``--retries``
     - int
     - ``3``
     - Number of retry attempts for transient failures.
   * - ``--max-requests``
     - int
     - unlimited
     - Maximum total HTTP requests to issue.
   * - ``--max-depth``
     - int
     - unlimited
     - Maximum directory depth to crawl.
   * - ``--max-threads``
     - int
     - ``10``
     - Maximum number of concurrent threads.
   * - ``--max-referencing-pages``
     - int
     - ``10``
     - Max referencing pages per URL in report.
   * - ``--config-file``
     - path
     - none
     - Path to a YAML configuration file.
   * - ``--version``
     - flag
     - —
     - Print version and exit.

Examples
--------

Check a website with default settings:

.. code-block:: bash

   link_check https://example.com

Save report to a file, limit depth and threads:

.. code-block:: bash

   link_check https://example.com --max-depth 3 --max-threads 20 -o report.txt

Use a configuration file:

.. code-block:: bash

   link_check --config-file config.yaml

Override config file timeout on the command line:

.. code-block:: bash

   link_check --config-file config.yaml --timeout 30

Exit Codes
----------

.. list-table::
   :widths: 10 90
   :header-rows: 1

   * - Code
     - Meaning
   * - ``0``
     - All checks passed: no broken links, no non-200 responses, no broken anchors,
       no misplaced assets, no SSL errors.
   * - ``1``
     - One or more problems detected.
   * - ``2``
     - Fatal error: invalid arguments, config file not found, etc.

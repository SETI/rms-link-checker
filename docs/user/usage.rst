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
     - required unless set in config
     - Root URL to begin crawling when not provided by ``--config-file``.
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
     - Minimum log level: ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``,
       ``CRITICAL``. Case-insensitive (e.g. ``debug`` and ``DEBUG`` both work).
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

Enable debug logging to a file:

.. code-block:: bash

   link_check https://example.com --log-level debug --log-file crawl.log

Progress Reporting
------------------

While a crawl is running, a progress line is printed to stderr every 5 seconds::

   [Progress] 365/~410 URLs checked | 12.2 URLs/s | 45 in queue | 8 threads active | 0m 30s elapsed

The fields are:

- **checked/~estimate** — URLs fully processed so far, and an estimate of the
  total (checked + currently queued).
- **URLs/s** — average request rate since the crawl started.
- **in queue** — URLs waiting to be submitted to the thread pool.
- **threads active** — worker threads currently executing (bounded by
  ``--max-threads``).
- **elapsed** — wall-clock time since the crawl started.

Interrupting a Crawl
--------------------

Press **Ctrl-C** once to abort. Any in-flight HTTP requests are allowed to
finish, then a partial report is generated from results collected so far and
written to the configured output destination. A second Ctrl-C issues an
immediate hard kill.

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
     - Fatal error: invalid arguments, config file not found or has unknown keys, etc.
   * - ``130``
     - Crawl was interrupted with Ctrl-C; report contains partial results.

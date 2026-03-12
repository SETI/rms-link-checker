Configuration File
==================

An optional YAML file may be passed with ``--config-file`` to set defaults for
all CLI options and define URL classification lists.

YAML Schema
-----------

.. code-block:: yaml

   # --- CLI option overrides (all optional) ---
   root_url: "https://example.com/docs"
   timeout: 15
   retries: 5
   max_requests: 1000
   max_depth: 8
   max_threads: 20
   max_referencing_pages: 20
   log_level: "DEBUG"
   output: "report.txt"
   log_file: "crawl.log"

   # --- URL classification lists (all optional) ---
   asset_urls:
     - "https://example.com/static/images"
     - "https://example.com/static/docs"

   no_crawl_urls:
     - "https://example.com/archive"

   ignore_urls:
     - "https://example.com/legacy"

URL Classification Lists
------------------------

``asset_urls``
~~~~~~~~~~~~~~

Expected locations for asset files (images, PDFs, etc.). When defined and
non-empty, any asset discovered outside these prefixes is reported as
**misplaced**.

``no_crawl_urls``
~~~~~~~~~~~~~~~~~

URLs matching these prefixes are **checked for existence** (HTTP request issued)
but are **never crawled** — their HTML content is not parsed and links are not
extracted.

``ignore_urls``
~~~~~~~~~~~~~~~

URLs matching these prefixes are **completely skipped** — no HTTP request is
made. They appear in the report's "Ignore URL Matches" section so you can see
which ignored URLs are still being referenced.

Prefix Matching Rules
---------------------

All prefix lists use **path-segment boundary** matching. A prefix ``P`` matches
a candidate URL ``C`` if:

1. The hosts are identical (case-insensitive, scheme ignored).
2. The path of ``C`` equals the path of ``P``, or starts with ``P``'s path
   followed by ``/``.

For example, prefix ``https://example.com/dir1`` matches:

- ``https://example.com/dir1`` ✓
- ``https://example.com/dir1/`` ✓
- ``https://example.com/dir1/foo/bar`` ✓
- ``http://example.com/dir1/foo`` ✓ (scheme-insensitive)

But does **not** match:

- ``https://example.com/dir1-foo`` ✗
- ``https://example.com/dir10`` ✗

CLI Precedence
--------------

When an option appears in both the config file and on the command line, the
**command-line value takes precedence**.

Troubleshooting
===============

Common Issues
-------------

**"root_url is required" error**

You must provide the root URL either as a positional argument or in the
``--config-file``:

.. code-block:: bash

   link_check https://example.com
   # or
   link_check --config-file config.yaml  # config.yaml must contain root_url

**Too many requests / hitting rate limits**

Reduce concurrency and add a longer timeout:

.. code-block:: bash

   link_check https://example.com --max-threads 2 --timeout 30

**SSL certificate errors**

``rms-link-checker`` always validates SSL certificates and logs one warning per
affected domain. There is no ``--no-verify-ssl`` option by design. Check with
your server administrator to fix the certificate.

**Crawl takes too long**

Use ``--max-depth`` and ``--max-requests`` to limit the scope:

.. code-block:: bash

   link_check https://example.com --max-depth 3 --max-requests 500

**Config file not found**

Ensure the path is correct and the file exists:

.. code-block:: bash

   link_check --config-file /absolute/path/to/config.yaml

**Links on the same domain are treated as external**

``rms-link-checker`` treats subdomains as external. If your root URL is
``https://example.com``, links to ``https://sub.example.com`` will be checked
but not crawled.

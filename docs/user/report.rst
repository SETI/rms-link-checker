Report Format
=============

The final report is plain text written to ``--output`` (default: stdout).
It contains 11 sections in the order described below. Each major section is
separated by two blank lines for readability.

Section 1: Configuration Summary
---------------------------------

Shows the effective configuration used for the crawl, including all URL
classification lists.

Section 2: Statistics Summary
------------------------------

Overall crawl statistics including elapsed time, total requests, bytes
downloaded, and per-domain request breakdown.

Section 3: Broken Links
------------------------

Links that returned 4xx or 5xx HTTP status codes or connection errors.
Grouped by the source page that contained the link.

Section 4: Broken Anchors
--------------------------

Fragment references (e.g. ``#section``) where the target anchor ID does not
exist in the target page. Grouped by the target URL and fragment.

Section 5: Non-200 Responses
-----------------------------

All URLs that returned a non-200 final status after redirects. Includes broken
links (4xx/5xx) and also other non-200 responses (e.g. 403 Forbidden).
Grouped by HTTP status code.

Section 6: Redirects
--------------------

URLs where the server issued a 3xx redirect to a different final URL. Shows
the original URL, final URL, and the HTTP status code of the first redirect
hop (e.g. 301, 302). Redirects that ultimately resolve to 200 do *not* cause
a non-zero exit code — they are informational only.

.. note::

   Redirects are recorded using the status code of the first redirect response
   (e.g. 301), not the final 200. Only genuine server-side redirects to
   different URLs are listed; same-URL redirects caused by URL normalization
   are suppressed.

Section 7: Misplaced Assets
----------------------------

Only present when ``asset_urls`` is configured. Assets found outside their
expected locations, grouped by asset type (Image, Document, Data,
Infrastructure, Other).

Section 8: Ignore URL Matches
------------------------------

URLs that matched an ``ignore_urls`` prefix and were skipped entirely.
Listed so site owners know which ignored URLs are still being referenced.

Section 9: Non-HTTP Scheme Links
---------------------------------

Links with non-HTTP schemes (``mailto:``, ``tel:``, ``ftp:``, etc.) that were
encountered during the crawl.

Section 10: SSL Warnings
-------------------------

Domains that had SSL certificate errors. Grouped by domain. Crawling continues
after SSL errors.

Section 11: Unvalidated Anchors
---------------------------------

Fragment references that could not be validated because the target page's HTML
was not parsed (due to no-crawl, depth limit, or external status).

Referencing Page Truncation
-----------------------------

In all sections that list referencing pages, the count is limited to
``--max-referencing-pages`` (default 10). When exceeded, a note is appended::

   ... and N more referencing pages

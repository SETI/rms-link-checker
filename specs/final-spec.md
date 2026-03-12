# rms-link-checker — Final Specification

## 1. Overview

**rms-link-checker** is a Python command-line application that crawls a website starting
from a given root URL, checks all discovered links for validity, detects misplaced asset
files, and produces a plain-text report summarizing the results.

| Property             | Value                                        |
| -------------------- | -------------------------------------------- |
| Repository name      | `rms-link-checker`                           |
| PyPI package name    | `rms-link-checker`                           |
| CLI command name     | `link_check`                                 |
| Language             | Python ≥ 3.10                                |
| License              | (inherit from existing repo)                 |

## 2. Installation

### End-user

```
pipx install rms-link-checker
```

### Developer

```
git clone https://github.com/SETI/rms-link-checker
cd rms-link-checker
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## 3. Command-Line Interface

### Synopsis

```
link_check [OPTIONS] [ROOT_URL]
```

`ROOT_URL` is a positional argument specifying exactly one root URL to crawl. It is
optional on the command line only if `root_url` is provided in the configuration file
(see §4). If supplied in both places, the CLI argument takes precedence.

### Options

| Flag / Option             | Type   | Default     | Description                                                                                  |
| ------------------------- | ------ | ----------- | -------------------------------------------------------------------------------------------- |
| `ROOT_URL`                | string | (required)  | The root URL to begin crawling. May be provided here or in the config file.                  |
| `-o`, `--output`          | path   | stdout      | File path for the final plain-text report.                                                   |
| `--log-file`              | path   | stderr      | File path for in-progress log messages.                                                      |
| `--log-level`             | string | `INFO`      | Minimum log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.                          |
| `--timeout`               | int    | `10`        | Timeout in seconds for each HTTP request.                                                    |
| `--retries`               | int    | `3`         | Number of retry attempts for transient failures (429, 503, network timeout). See §9.5.       |
| `--max-requests`          | int    | unlimited   | Maximum total HTTP requests to issue. Useful for debugging.                                  |
| `--max-depth`             | int    | unlimited   | Maximum directory depth to crawl relative to the root URL path.                              |
| `--max-threads`           | int    | `10`        | Maximum number of concurrent threads for HTTP requests.                                      |
| `--max-referencing-pages`        | int    | `10`        | Maximum number of referencing pages listed per URL in report sections. See §10.               |
| `--config-file`           | path   | none        | Path to a YAML configuration file (`.yaml` or `.yml`). See §4.                               |
| `--version`               | flag   | —           | Print version and exit.                                                                      |

### Precedence

All options listed above may also appear in the configuration file (§4). When an option
is specified in both the config file and the command line, the **command-line value wins**.

## 4. Configuration File

An optional YAML file (`.yaml` or `.yml`) that provides defaults for all CLI options
and defines URL classification lists. Every section and every key is optional.

### 4.1 Schema

```yaml
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
```

### 4.2 URL classification lists

Each list contains literal URL prefixes matched on a **path-segment boundary** (see §5.7
for matching rules). The three lists are:

#### `asset_urls`

Expected locations for asset files (non-HTML resources). When this list is present, every
discovered asset reference is checked against it:

- If the asset URL falls under one of the listed prefixes, the asset is **in place** and
  simply recorded in statistics.
- If the asset URL does **not** fall under any of the listed prefixes, the asset is
  **misplaced** and reported in the output (grouped by asset type, then filename, then
  referencing page).

When `asset_urls` is absent or empty, no misplaced-asset analysis is performed.

#### `no_crawl_urls`

URLs under these prefixes are **checked for existence** (an HTTP request is issued) but
are **never crawled** — their HTML content is not parsed and no links are extracted from
them. This applies regardless of whether the URL is internal or external.

#### `ignore_urls`

URLs under these prefixes are **not checked**: no HTTP request is issued and no existence
check is performed. However, they are **logged at DEBUG level** and **recorded in the
report** (§10.9) grouped by target URL with a list of pages that referenced them. This
allows site owners to see which ignored URLs are still being linked to.

### 4.3 URL prefix scope

Prefixes in all three lists may point to locations that are:

- Under the main crawl root.
- Parallel to the main crawl root (same domain, different path subtree).
- On an external domain.

## 5. Crawling Behavior

### 5.1 Single root

Exactly one root URL is accepted per invocation. The root URL defines:

- The **domain** — only URLs on this exact domain (same host, same port) are considered
  internal. Subdomains are treated as external (e.g., if root is `https://example.com`,
  then `https://sub.example.com` is external).
- The **root path** — the path component of the root URL. The crawler never visits
  internal pages whose path is above (a parent of) the root path.

### 5.2 Path containment

Given a root URL of `https://example.com/a/b/c`:

- `https://example.com/a/b/c` — **crawlable** (the root itself).
- `https://example.com/a/b/c/d/e` — **crawlable** (under root path).
- `https://example.com/a/b` — **not crawlable** (above root path). If encountered as a
  link, it is checked for existence only (treated like an external link for crawl
  purposes) since it is still on the same domain.
- `https://example.com/a/b/other` — **not crawlable** (parallel to root path, not under
  it). Same treatment as above.

### 5.3 Visit-once guarantee

Every unique URL is visited (HTTP request issued) **at most once**. URL identity for
deduplication is determined by:

- **Scheme-insensitive**: `http://example.com/page` and `https://example.com/page` are
  the same URL. Whichever is encountered first is the one that gets requested.
- **Query-parameter-insensitive**: `https://example.com/page` and
  `https://example.com/page?foo=bar` are the same URL. Query parameters are stripped
  before deduplication.
- **Fragment-insensitive for request purposes**: The fragment (`#section`) is stripped
  before issuing an HTTP request. However, fragment validation is performed separately
  (see §5.4).

### 5.4 Fragment (anchor) validation

When a link contains a fragment (e.g., `https://example.com/page#section`), the crawler:

1. Checks/crawls `https://example.com/page` as usual (subject to the visit-once rule).
2. Parses the HTML of that page and collects all element `id` attributes and `<a name>`
   attributes into a cached **anchor registry** (see §14.2). This happens once during the
   initial crawl/fetch of the page; the page is never re-fetched for anchor validation.
3. When a fragment reference is encountered for an already-visited page, the cached anchor
   set is consulted — no additional HTTP request is issued.
4. Verifies that `section` matches one of the collected IDs/names.
5. If the anchor target does not exist, it is reported as a **broken anchor** in the
   report, listing the source page and the target page + fragment.

**Anchors on non-crawled pages**: If the target page was fetched but not crawled (i.e.,
checked with HEAD only — because it matched a `no_crawl_urls` prefix, exceeded the depth
limit, or is external), then no HTML content was parsed and no anchor set is available.
In this case:

- Anchor validation is **skipped** for that target page.
- A WARNING is logged indicating that the anchor cannot be validated because the page
  content was not parsed (with the reason: no-crawl, depth-limited, or external).
- The unvalidated anchor is **not** reported as broken. It is recorded in a separate
  informational section of the report (see §10.12).

### 5.5 Depth limiting

`--max-depth N` limits crawling to pages whose path depth relative to the root URL path
is at most `N`. Depth 0 is the root page itself. Depth 1 includes pages one directory
level below the root, and so on.

Pages beyond the depth limit are **checked for existence** but not crawled (their content
is not parsed for further links).

### 5.6 External links

A URL is **external** if:

- Its host differs from the root URL host (including subdomains), OR
- Its path is above or parallel to the root path (same host but not under the root).

External links are **checked for existence** via an HTTP HEAD request (see §9.1) but
are **never crawled** (their content is never parsed for further links).

### 5.7 URL prefix matching (config lists)

Config URL prefixes are matched against candidate URLs using **path-segment boundary**
matching, not string-prefix matching.

A prefix `P` matches a candidate URL `C` if and only if:

1. The **host** of `P` and `C` are identical (case-insensitive comparison). The
   **scheme** is completely ignored — `http` and `https` are treated as equivalent.
2. The path of `C` equals the path of `P`, OR the path of `C` starts with the path of
   `P` followed by a `/`.

**Examples** (prefix = `https://example.com/dir1`):

| Candidate URL                            | Matches? |
| ---------------------------------------- | -------- |
| `https://example.com/dir1`               | Yes      |
| `https://example.com/dir1/`              | Yes      |
| `https://example.com/dir1/foo/bar`       | Yes      |
| `https://example.com/dir1-foo`           | **No**   |
| `https://example.com/dir10`              | **No**   |
| `http://example.com/dir1/foo`            | Yes      |

## 6. URL Classification and Handling

When the crawler encounters a URL, it is processed through this decision tree in order:

1. **Non-HTTP scheme** (`mailto:`, `tel:`, `ftp:`, `javascript:`, `data:`, etc.):
   Log at DEBUG level. Record in statistics. Include in report under a "Non-HTTP Schemes"
   section. Do not issue any HTTP request. No further processing.

2. **Ignored** (matches an `ignore_urls` prefix): No HTTP request is issued. Log the
   ignored URL at DEBUG level. Record the URL and the page that referenced it for
   inclusion in the Ignore URL Matches report section (§10.9).

3. **Deduplicated** (already visited): Skip. If the URL has a fragment, perform anchor
   validation against the previously fetched page (§5.4). No new HTTP request.

4. **No-crawl** (matches a `no_crawl_urls` prefix): Issue an HTTP request to check
   existence. Record the result. Do **not** parse content or follow links within. If the
   URL has a fragment, anchor validation is skipped and a warning is logged (see §5.4).

5. **External**: Issue an HTTP HEAD request to check existence (see §9.1). Record the
   result. Do not parse content. If the URL has a fragment, anchor validation is skipped
   and a warning is logged (see §5.4).

6. **Internal, beyond depth limit**: Issue an HTTP request to check existence. Record
   the result. Do not parse content. If the URL has a fragment, anchor validation is
   skipped and a warning is logged (see §5.4).

7. **Internal, within scope**: Issue an HTTP GET request. Parse HTML content. Extract
   links (§7). Enqueue discovered links for processing.

At every step, the HTTP response status code and any redirect chain are recorded.

## 7. Link Extraction

### 7.1 HTML elements parsed

Links are extracted from the following HTML elements and attributes:

| Element      | Attribute(s)        | Treatment                                  |
| ------------ | ------------------- | ------------------------------------------ |
| `<a>`        | `href`              | Crawl if internal HTML; check if external  |
| `<img>`      | `src`, `srcset`     | Check existence only (asset)               |
| `<link>`     | `href`              | Check existence only (asset/resource)      |
| `<script>`   | `src`               | Check existence only (asset)               |
| `<iframe>`   | `src`               | Crawl if internal HTML; check if external  |
| `<source>`   | `src`, `srcset`     | Check existence only (asset)               |
| `<video>`    | `src`, `poster`     | Check existence only (asset)               |
| `<audio>`    | `src`               | Check existence only (asset)               |
| `<object>`   | `data`              | Check existence only (asset)               |
| `<embed>`    | `src`               | Check existence only (asset)               |
| `<form>`     | `action`            | Check existence only                       |

### 7.2 `<base href>` handling

If a `<base href="...">` tag is present in the page's `<head>`, all relative URLs on
that page are resolved against the base URL instead of the page's own URL.

### 7.3 Relative URL resolution

Relative URLs are resolved to absolute URLs using the base URL (§7.2) or the page's own
URL, following RFC 3986.

### 7.4 Determining crawlable vs. asset

A URL is treated as a potential HTML page (and thus crawlable, if internal and in scope)
if:

- Its path ends with `.htm`, `.html`, `.shtml`, `.php`, `.asp`, `.jsp`, or `.cgi`, OR
- Its path has **no file extension** (e.g., `/about`, `/docs/guide`).

A URL is treated as an **asset** (never crawled, only checked for existence) if its path
has a file extension not in the above list.

**Special case**: If an extension-less URL is requested and the HTTP response
`Content-Type` header indicates a non-HTML media type (e.g., `application/json`,
`application/octet-stream`), this is recorded as an **error** — the link is reported as
pointing to non-HTML content where HTML was expected.

## 8. Asset Classification

Assets are categorized by file extension into the following types:

### 8.1 Image

`.jpg`, `.jpeg`, `.png`, `.gif`, `.svg`, `.webp`, `.ico`, `.bmp`, `.tiff`, `.tif`,
`.avif`

### 8.2 Document

`.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`, `.txt`, `.csv`, `.rtf`,
`.odt`, `.ods`, `.odp`

### 8.3 Data

`.tab`, `.xml`, `.lbl`, `.lblx`, `.img`

Note: `.img` in the Data category refers to scientific/PDS image label data files, not
to be confused with the Image category.

### 8.4 Infrastructure

`.js`, `.mjs`, `.css`, `.woff`, `.woff2`, `.ttf`, `.eot`, `.otf`, `.map`,
`.json` (when linked as a resource)

### 8.5 Other

Any file extension not listed in the above categories.

### 8.6 Misplaced asset detection

Misplaced asset detection is active only when `asset_urls` is defined and non-empty in
the configuration file.

An asset is **misplaced** if **all** of the following conditions are true:

1. It does not fall under any of the `asset_urls` prefixes (using path-segment matching
   per §5.7).
2. It is **not** external (different domain or above/parallel to root path).
3. It is **not** matched by an `ignore_urls` prefix.
4. It is **not** a non-crawlable URL (e.g., matched by a `no_crawl_urls` prefix).

In other words, only internal, in-scope, non-ignored, non-no-crawl assets that are
outside the expected `asset_urls` locations are flagged as misplaced.

Misplaced assets are reported in the output grouped by asset type (§8.1–8.5), then by
filename, then by each page that referenced the asset.

## 9. HTTP Request Behavior

### 9.1 Request methods

| Scenario                              | Method | Notes                                      |
| ------------------------------------- | ------ | ------------------------------------------ |
| Internal page to crawl                | GET    | Response body is parsed for links.         |
| Internal page existence check only    | HEAD   | Used for no-crawl, above-root, etc.        |
| External link                         | HEAD   | If HEAD returns a method-not-allowed error (405) or other ambiguous failure, fall back to GET. |
| Asset existence check                 | HEAD   | Fall back to GET on 405.                   |

### 9.2 User-Agent

All requests use the User-Agent string:

```
rms-link-checker/<VERSION>
```

where `<VERSION>` is the installed package version (from `importlib.metadata`).

### 9.3 Timeout

Each individual HTTP request has a timeout of `--timeout` seconds (default 10). This
applies to connection establishment, TLS handshake, and response headers. If the timeout
is exceeded, the request is treated as a transient failure eligible for retry.

### 9.4 Redirect handling

Redirects (HTTP 301, 302, 303, 307, 308) are **followed automatically**, up to a maximum
of **10 redirects** per request chain. If the limit is exceeded, the URL is reported as
an error ("too many redirects").

All redirects are **recorded**:

- The original URL, the final URL, and each intermediate URL in the chain.
- The HTTP status code of each redirect hop.

Redirects are reported in the final output (see §10.6) and counted in statistics.

For internal redirects, the **final target URL** is crawled (if it is internal and in
scope) subject to the visit-once rule.

For external redirects, the final response status is recorded and reported.

### 9.5 Retry logic

Transient failures are retried up to `--retries` times (default 3). A failure is
considered transient if:

- HTTP status 429 (Too Many Requests)
- HTTP status 503 (Service Unavailable)
- Network timeout (request exceeded `--timeout`)
- Connection reset or connection refused

**Backoff**: Between retries, the crawler waits for `--timeout` seconds (i.e., the same
value as the request timeout). This is a fixed backoff, not exponential.

If all retries are exhausted, the URL is recorded as a failure with the last observed
error.

Non-transient errors (4xx other than 429, 5xx other than 503, DNS resolution failure)
are **not retried**.

### 9.6 SSL/TLS certificate errors

If an SSL certificate validation error occurs, the crawler:

1. Logs a WARNING with the URL and error details — but **only once per domain**. If
   multiple URLs on the same domain produce SSL errors, only the first is logged; the
   rest are silently recorded.
2. Records every affected URL as having an SSL error for the report (§10.11). The report
   groups SSL errors by domain rather than listing every individual URL.
3. Continues crawling other URLs (does not abort).

No `--no-verify-ssl` option is provided. Invalid certificates are always warned about
but never silently accepted.

### 9.7 Cookies

Cookies are **not stored or sent**. Each request is stateless with respect to cookies.

### 9.8 robots.txt

The crawler **ignores** `robots.txt`. This tool is intended for use by site owners
checking their own sites.

## 10. Report Format

The final report is plain text written to `--output` (default: stdout). Sections appear
in the order below. Empty sections (no items to report) display "None" or are omitted
with a note.

### 10.1 Configuration Summary

```
=== Configuration Summary ===
Root URL:        https://example.com/docs
Timeout:         10s
Retries:         3
Max threads:     10
Max depth:       unlimited
Max requests:    unlimited
Max ref. pages:  10
Config file:     config.yaml

Asset URL prefixes:
  - https://example.com/static/images
  - https://example.com/static/docs

No-crawl URL prefixes:
  - https://example.com/archive

Ignore URL prefixes:
  - https://example.com/legacy
```

### 10.2 Statistics Summary

```
=== Statistics Summary ===
Elapsed time:            2m 34s
Total HTTP requests:     1,247
Requests per second:     8.1
Total bytes downloaded:  45.2 MB

Internal pages crawled:  312
Internal pages checked:  48
External links checked:  887

Broken links:            5
Broken anchors:          3
Unvalidated anchors:     3
Redirects encountered:   42
Misplaced assets:        12
SSL warnings:            1 domain

Non-HTTP scheme links:   23
  mailto:  18
  tel:     3
  ftp:     2

Per-domain request breakdown:
  cdn.example.net:       412
  example.com:           360
  github.com:            275
  stackoverflow.com:     120
  docs.python.org:       80
```

The per-domain breakdown always lists **every** domain individually, sorted by request
count descending. There is no "other" or aggregate bucket.

### 10.3 Broken Links

Grouped by source page. Each broken link entry includes the target URL, the HTTP status
code (or error description), and the status code's meaning. The section header includes
the total count of distinct broken URLs.

```
=== Broken Links (3) ===

Page: https://example.com/docs/guide.html
  - https://example.com/docs/old-page.html  →  404 Not Found
  - https://external.com/missing            →  410 Gone

Page: https://example.com/docs/faq.html
  - https://example.com/docs/old-page.html  →  404 Not Found
```

If a broken link appears on multiple pages, it is listed under **each** page.

### 10.4 Broken Anchors

Grouped by target page and anchor. The section header includes the total count.

```
=== Broken Anchors (2) ===

Target: https://example.com/docs/api.html#old-method
  Referenced by:
    - https://example.com/docs/guide.html
    - https://example.com/docs/tutorial.html

Target: https://example.com/docs/faq.html#removed-section
  Referenced by:
    - https://example.com/docs/index.html
```

### 10.5 Non-200 Responses

All URLs that returned a final (after redirects) non-200 status code, grouped by status
code. This includes broken links but also other non-200 responses (e.g., 403 Forbidden).
The section header includes the total count of distinct non-200 URLs.

```
=== Non-200 Responses (3) ===

403 Forbidden:
  - https://example.com/private/admin.html
    Referenced by:
      - https://example.com/docs/index.html

404 Not Found:
  - https://example.com/docs/old-page.html
    Referenced by:
      - https://example.com/docs/guide.html
      - https://example.com/docs/faq.html
```

### 10.6 Redirects

Grouped by the original (redirected-from) URL, showing the final destination and all
pages that referenced the original URL. The section header includes the total count.

```
=== Redirects (2) ===

https://example.com/docs/old-name.html  →  https://example.com/docs/new-name.html (301)
  Referenced by:
    - https://example.com/docs/index.html
    - https://example.com/docs/guide.html

https://example.com/moved  →  https://example.com/docs/moved.html (302)
  Referenced by:
    - https://example.com/docs/links.html
```

### 10.7 Misplaced Assets

Only present when `asset_urls` is configured. Grouped by asset type (§8), then by
asset filename, then by referencing page. The section header includes the total count of
distinct misplaced asset URLs.

```
=== Misplaced Assets (4) ===

Image:
  logo.png (https://example.com/docs/logo.png)
    Referenced by:
      - https://example.com/docs/index.html
      - https://example.com/docs/about.html

  banner.jpg (https://example.com/docs/pages/banner.jpg)
    Referenced by:
      - https://example.com/docs/pages/welcome.html

Document:
  report.pdf (https://example.com/docs/report.pdf)
    Referenced by:
      - https://example.com/docs/downloads.html

Data:
  (none)

Infrastructure:
  custom.js (https://example.com/docs/custom.js)
    Referenced by:
      - https://example.com/docs/index.html

Other:
  (none)
```

### 10.8 No-Crawl URL Matches

URLs that matched a `no_crawl_urls` prefix and were therefore checked but not crawled.
Grouped by matched URL, then listing each page that referenced it. The section header
includes the total count.

```
=== No-Crawl URL Matches (2) ===

https://example.com/archive/page1.html
  Referenced by:
    - https://example.com/docs/history.html

https://example.com/archive/page2.html
  Referenced by:
    - https://example.com/docs/history.html
    - https://example.com/docs/index.html
```

### 10.9 Ignore URL Matches

URLs that matched an `ignore_urls` prefix. No HTTP request was issued for these URLs,
but they are listed here so site owners can see which ignored URLs are still being linked
to. Grouped by target URL, then listing each page that contained the link. The section
header includes the total count.

```
=== Ignore URL Matches (1) ===

https://example.com/legacy/old-api.html
  Referenced by:
    - https://example.com/docs/migration.html
```

### 10.10 Non-HTTP Scheme Links

URLs with non-HTTP schemes that were encountered and skipped. The section header includes
the total count.

```
=== Non-HTTP Scheme Links (2) ===

mailto:support@example.com
  Referenced by:
    - https://example.com/docs/contact.html
    - https://example.com/docs/index.html

tel:+1-555-0100
  Referenced by:
    - https://example.com/docs/contact.html
```

### 10.11 SSL Warnings

Domains that had SSL certificate errors, grouped by domain. Each domain entry shows the
error and lists the individual URLs affected along with their referencing pages. The
section header includes the count of affected domains.

```
=== SSL Warnings (1 domain) ===

expired-cert.example.com — certificate has expired
  Affected URLs:
    - https://expired-cert.example.com/resource
      Referenced by:
        - https://example.com/docs/partners.html
    - https://expired-cert.example.com/api/v2
      Referenced by:
        - https://example.com/docs/integrations.html
```

### 10.12 Unvalidated Anchors

Fragment references that could not be validated because the target page's HTML content
was not parsed (due to no-crawl, depth limit, or external status). The section header
includes the total count.

```
=== Unvalidated Anchors (3) ===

https://example.com/archive/doc.html#intro (no-crawl)
  Referenced by:
    - https://example.com/docs/guide.html

https://external.com/api.html#auth (external)
  Referenced by:
    - https://example.com/docs/setup.html

https://example.com/deep/nested/page.html#note (depth-limited)
  Referenced by:
    - https://example.com/docs/reference.html
```

### 10.13 Referencing page truncation

In **all** report sections that list referencing pages under a URL (§10.3–10.12), the
number of referencing pages shown per URL is limited to `--max-referencing-pages` (default 10).
When the limit is exceeded, a truncation notice is appended:

```
  Referenced by:
    - https://example.com/docs/page1.html
    - https://example.com/docs/page2.html
    - https://example.com/docs/page3.html
    ... and 47 more referencing pages
```

## 11. Progress Updates

During the crawl, periodic status updates are written to **stderr** (regardless of
`--log-file` setting). Updates are emitted approximately every 5 seconds and include:

```
[Progress] 245/~1200 URLs checked | 34 in queue | 5 threads active | 1m 12s elapsed
```

The estimated total is approximate (based on URLs discovered so far).

## 12. Exit Codes

| Code | Meaning                                                                          |
| ---- | -------------------------------------------------------------------------------- |
| `0`  | All checks passed: no broken links, no non-200 final responses, no broken anchors, no misplaced assets, no SSL errors, no non-HTML content errors. |
| `1`  | One or more problems detected (broken links, non-200 responses, misplaced assets, broken anchors, SSL errors, or non-HTML content errors). |
| `2`  | Fatal error: invalid arguments, config file not found, root URL unreachable, etc. |

Redirects that ultimately resolve to HTTP 200 do **not** cause a non-zero exit code.
They are reported for informational purposes only.

## 13. Logging

Use Python's standard `logging` module.

### 13.1 Logger name

The root logger for the application is named `link_checker`.

### 13.2 Log levels

| Level    | Content                                                                  |
| -------- | ------------------------------------------------------------------------ |
| DEBUG    | Every URL enqueued, every HTTP request sent/received, redirect hops, anchor collection, deduplication skips, non-HTTP scheme encounters, ignored URL matches. |
| INFO     | Pages crawled, external links checked, summary milestones (every 100 URLs). |
| WARNING  | Non-200 responses, SSL errors (once per domain), retries, redirect chains, misplaced assets, broken anchors, unvalidated anchors (no-crawl/depth/external), non-HTML content from extension-less URLs. |
| ERROR    | Broken links (final status 4xx/5xx), request failures after all retries exhausted, too-many-redirects. |
| CRITICAL | Fatal startup errors (bad config, unreachable root URL).                 |

### 13.3 Log output

- Default: log messages go to stderr.
- If `--log-file` is specified, log messages go to that file instead.
- The final report (§10) goes to `--output` (default: stdout) and is **separate** from
  log output.

## 14. Threading Model

### 14.1 Architecture

Use a thread pool (e.g., `concurrent.futures.ThreadPoolExecutor`) with at most
`--max-threads` worker threads.

### 14.2 Shared state

The following shared state must be protected against race conditions:

- **Visited URL set**: tracks which URLs have been requested (for the visit-once
  guarantee).
- **URL work queue**: the queue of URLs pending processing.
- **Results collection**: accumulated statistics, broken links, redirects, etc.
- **Anchor registry**: mapping from page URL to set of anchor IDs found in that page.
  Populated once when a page is crawled (GET); consulted for all subsequent fragment
  references to that page without re-fetching. Pages fetched via HEAD only (no-crawl,
  external, depth-limited) have no entry in the registry.

Use appropriate synchronization primitives (`threading.Lock`, `queue.Queue`,
`concurrent.futures` built-in synchronization) to ensure correctness.

### 14.3 Thread safety contract

- No data races on any shared structure.
- The visit-once guarantee must hold even under concurrent access: if two threads
  discover the same URL simultaneously, exactly one thread issues the HTTP request.
- The `--max-requests` limit is enforced atomically: the total number of HTTP requests
  never exceeds the configured value.

## 15. Testing Requirements

### 15.1 Framework

- `pytest` with `pytest-cov` and `pytest-xdist`.
- Run with `-n auto` for parallel execution.
- All tests must be independent (no shared mutable state, no ordering dependency).

### 15.2 No real network access

The full test suite must run **without access to real websites**. All HTTP interactions
are mocked (e.g., using `responses`, `requests-mock`, `respx`, or similar).

### 15.3 Test-driven development

Follow Red → Green → Refactor:

1. Write failing tests based on this specification.
2. Implement the minimum code to make tests pass.
3. Refactor while keeping tests green.

### 15.4 Coverage

Target at least **80%** line coverage across the entire codebase.

### 15.5 Assertion and correctness standards

These rules apply to every test (per `.cursor/rules/python_best_practices.mdc`):

- Each `assert` tests **exactly one condition** (no `and` in assertions).
- Always test for **precise expected values**, not ranges or existence checks.
- When testing exceptions, use `pytest.raises` as a context manager and assert on the
  exception **message content**, not just the type.
- When multiple tests call the same function, use **distinct inputs** to maximize branch
  coverage, including edge cases and boundary values.
- Never write a test that passes by ignoring an incorrect result or swallowing an
  exception.
- Never write tests whose sole purpose is exercising code paths without asserting
  correctness.
- All test functions must have **type annotations**.

### 15.6 Key test scenarios

The test suite must cover at minimum:

- **Basic crawl**: single page, multiple pages, links between pages.
- **External link checking**: HEAD request, fallback to GET on 405, various status codes.
- **Redirect handling**: single redirect, redirect chain, redirect loop (max 10),
  internal-to-external redirect. Verify redirect report entries.
- **Fragment validation**: valid anchor, missing anchor, anchor on already-visited page
  (uses cache, no re-fetch).
- **Unvalidated anchors**: anchor on no-crawl page, anchor on depth-limited page, anchor
  on external page — all produce warnings and appear in §10.12 report section.
- **Depth limiting**: pages at various depths, enforcement of max-depth.
- **Visit-once**: same URL via different schemes, same URL with/without query params,
  same URL discovered from multiple pages.
- **Config file parsing**: all sections, empty sections, missing file, invalid YAML,
  CLI-overrides-config precedence.
- **Asset classification**: each category (image, document, data, infrastructure, other).
- **Misplaced asset detection**: with and without `asset_urls` configured; verify
  external/ignored/non-crawlable assets are excluded from misplaced detection.
- **No-crawl behavior**: URL under no-crawl prefix is checked but not crawled.
- **Ignore behavior**: URL under ignore prefix is not checked but appears in report.
- **URL prefix matching**: path-segment boundary (match `dir1/foo`, reject `dir1-foo`);
  scheme-insensitive matching.
- **Non-HTTP schemes**: `mailto:`, `tel:`, `ftp:`, `javascript:`, `data:` — logged and
  reported.
- **Retry logic**: transient errors retried, non-transient errors not retried, backoff
  timing, retry exhaustion. Verify retry count matches `--retries` option.
- **SSL errors**: warning logged once per domain, crawl continues, report groups by
  domain.
- **Threading**: concurrent operations, visit-once under contention, max-requests limit.
- **CLI argument parsing**: all options, defaults, config-file-with-CLI-override,
  `--max-referencing-pages`.
- **Report generation**: all sections (§10.1–10.12), empty sections, correct grouping,
  item counts in headers.
- **Referencing page truncation**: verify `--max-referencing-pages` truncation message appears
  when limit is exceeded.
- **Exit codes**: 0 when clean, 1 when problems, 2 on fatal error.
- **Timeout handling**: request timeout triggers retry.
- **Max requests limit**: crawl stops after N requests.
- **Non-HTML content from extension-less URL**: reported as error.
- **`<base href>` resolution**: relative URLs resolved against base.
- **Path containment**: links above root checked but not crawled.
- **Subdomain treated as external**: verified not crawled.
- **Progress updates**: emitted to stderr.
- **Per-domain statistics**: all domains listed individually, no "other" bucket.

## 16. Documentation Requirements

### 16.1 README.md

Update the existing README (preserve the existing header) to include:

- Project description and purpose.
- PyPI and ReadTheDocs badges.
- Quickstart: installation and a minimal usage example.
- Link to full documentation on ReadTheDocs.

### 16.2 Sphinx documentation (RST)

Hosted on ReadTheDocs. Must build with zero warnings. The documentation is organized into
two separate guides:

#### User's Guide

Audience: end users who install from PyPI and run `link_check`.

- Installation (pipx, pip).
- Basic usage and minimal examples.
- All CLI options with descriptions and examples.
- Configuration file format with annotated examples.
- Report format: what each section means and how to interpret results.
- Exit codes.
- Troubleshooting common issues.

#### Developer's Guide

Audience: contributors who clone the repo and modify the source.

- Developer setup (clone, venv, `pip install -e ".[dev]"`).
- Architecture overview: module structure, class hierarchy, public API surface.
- API reference: auto-generated from docstrings (autodoc).
- Running tests (`pytest -n auto --cov`), linting (`ruff`), type-checking (`mypy`).
- Running all checks (`scripts/run-all-checks.sh`).
- Contributing guide: branching, commits, PR workflow, coding standards.
- Release process.

### 16.3 Docstrings

Every module, class, function, and method must have a Google-style docstring per PEP 257
with `Parameters:`, `Returns:`, `Raises:` sections as applicable. Wrap to 90 characters.

## 17. Packaging and Distribution

### 17.1 Build system

- `pyproject.toml` as the single source of truth for metadata, dependencies, and tool
  configuration.
- Use `setuptools` with `setuptools-scm` for version management from git tags.

### 17.2 Source layout and entry point

The source code lives under `src/link_checker/` (src-layout). The importable package is
`link_checker` (underscore). The CLI command is `link_check` (underscore).

```
src/
  link_checker/
    __init__.py
    cli.py
    ...
    py.typed
```

```toml
[tool.setuptools.packages.find]
where = ["src"]

[project.scripts]
link_check = "link_checker.cli:main"
```

### 17.3 Dependencies

Runtime dependencies declared in `[project].dependencies`. Dev and docs dependencies in
`[project.optional-dependencies]`. Minimum compatible versions only (no exact pins).

### 17.4 CI/CD

CI/CD is already implemented via the following GitHub Actions workflows in
`.github/workflows/`. Modify only as necessary for correctness; preserve existing
structure and details.

- **`run-tests.yml`**: Runs on push to `main`, PRs to `main`, weekly schedule, and
  manual dispatch. Lint job (ruff check, ruff format --check, mypy, Sphinx build,
  PyMarkdown scan). Test job (pytest with coverage, matrix across Python 3.10–3.13 on
  Ubuntu, codecov upload).
- **`publish_to_pypi.yml`**: Triggered by GitHub Release. Builds and publishes to PyPI.
- **`publish_to_test_pypi.yml`**: Manual dispatch. Builds and publishes to Test PyPI.

### 17.5 Quality gates

All of the following must pass before merge:

- `ruff check .` — zero errors.
- `ruff format --check .` — zero formatting differences.
- `mypy .` — zero errors (strict mode).
- `pytest -n auto --cov` — all tests pass, ≥80% coverage.
- `sphinx-build docs/ docs/_build/ -W` — zero warnings.

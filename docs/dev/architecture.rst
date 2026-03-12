Architecture
============

Module Structure
----------------

All source code lives under ``src/link_checker/``.

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Module
     - Responsibility
   * - ``__init__.py``
     - Package init, ``__version__``
   * - ``cli.py``
     - Entry point, argparse, logging setup
   * - ``config.py``
     - ``CrawlConfig`` dataclass, YAML loading, merge
   * - ``url_utils.py``
     - URL normalization, prefix matching, depth calculation
   * - ``classifier.py``
     - URL decision tree, ``AssetType`` enum
   * - ``http_client.py``
     - HTTP requests with retry, redirect, SSL handling
   * - ``html_parser.py``
     - Link extraction, anchor collection, base href handling
   * - ``results.py``
     - Thread-safe results aggregation
   * - ``crawler.py``
     - Main crawl engine with ``ThreadPoolExecutor``
   * - ``report.py``
     - Plain-text report generator (12 sections)
   * - ``progress.py``
     - Periodic stderr progress updates

Data Flow
---------

.. mermaid::

   flowchart TD
       CLI["cli.py<br/>main(), argparse"] --> Config["config.py<br/>CrawlConfig"]
       CLI --> Crawler["crawler.py<br/>Crawler class"]
       Crawler --> HttpClient["http_client.py<br/>HEAD/GET, retry, SSL"]
       Crawler --> HtmlParser["html_parser.py<br/>extract_links()"]
       Crawler --> Classifier["classifier.py<br/>URL decision tree"]
       Crawler --> UrlUtils["url_utils.py<br/>normalize, prefix match"]
       Crawler --> Results["results.py<br/>CrawlResults"]
       Crawler --> Progress["progress.py<br/>stderr updates"]
       Results --> Report["report.py<br/>generate_report()"]
       Report --> CLI

Threading Model
---------------

The crawler uses a ``ThreadPoolExecutor`` with at most ``--max-threads``
workers. Shared state (visited URL set, anchor registry, results) is protected
by ``threading.Lock`` instances. The visit-once guarantee is enforced
atomically: if two threads discover the same URL simultaneously, exactly one
thread issues the HTTP request.

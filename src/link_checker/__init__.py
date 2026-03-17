"""rms-link-checker package.

Website crawler, link checker, and content analyzer.
"""

from __future__ import annotations

try:
    from link_checker._version import version as __version__
except ImportError:
    __version__ = '0.0.0.dev0'

__all__ = ['__version__']

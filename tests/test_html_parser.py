"""Tests for html_parser module."""

from __future__ import annotations

from link_checker.html_parser import ExtractedLink, extract_anchors, extract_links, find_base_href

# ---------------------------------------------------------------------------
# extract_links
# ---------------------------------------------------------------------------


def test_extract_links_a_href() -> None:
    html = '<a href="/about">About</a>'
    links = extract_links(html, 'https://example.com/page.html')
    urls = [lk.url for lk in links]
    assert 'https://example.com/about' in urls


def test_extract_links_img_src() -> None:
    html = '<img src="/img/pic.png" alt="pic">'
    links = extract_links(html, 'https://example.com/page.html')
    assert len(links) == 1
    assert links[0].url == 'https://example.com/img/pic.png'
    assert links[0].is_asset is True
    assert links[0].source_element == 'img'
    assert links[0].source_attribute == 'src'


def test_extract_links_img_srcset() -> None:
    html = '<img srcset="/img/small.jpg 480w, /img/large.jpg 1080w" src="/img/small.jpg">'
    links = extract_links(html, 'https://example.com/page.html')
    urls = [lk.url for lk in links]
    assert 'https://example.com/img/small.jpg' in urls
    assert 'https://example.com/img/large.jpg' in urls


def test_extract_links_link_href() -> None:
    html = '<link rel="stylesheet" href="/style.css">'
    links = extract_links(html, 'https://example.com/page.html')
    assert any(lk.url == 'https://example.com/style.css' for lk in links)
    assert all(lk.is_asset for lk in links)


def test_extract_links_script_src() -> None:
    html = '<script src="/js/app.js"></script>'
    links = extract_links(html, 'https://example.com/page.html')
    assert any(lk.url == 'https://example.com/js/app.js' for lk in links)
    assert all(lk.is_asset for lk in links)


def test_extract_links_iframe_src() -> None:
    html = '<iframe src="/embed/player.html"></iframe>'
    links = extract_links(html, 'https://example.com/page.html')
    assert any(lk.url == 'https://example.com/embed/player.html' for lk in links)


def test_extract_links_source_src() -> None:
    html = '<video><source src="/video/clip.mp4"></video>'
    links = extract_links(html, 'https://example.com/page.html')
    assert any(lk.url == 'https://example.com/video/clip.mp4' for lk in links)


def test_extract_links_video_src_and_poster() -> None:
    html = '<video src="/video/clip.mp4" poster="/img/poster.jpg"></video>'
    links = extract_links(html, 'https://example.com/page.html')
    urls = [lk.url for lk in links]
    assert 'https://example.com/video/clip.mp4' in urls
    assert 'https://example.com/img/poster.jpg' in urls


def test_extract_links_audio_src() -> None:
    html = '<audio src="/audio/clip.mp3"></audio>'
    links = extract_links(html, 'https://example.com/page.html')
    assert any(lk.url == 'https://example.com/audio/clip.mp3' for lk in links)


def test_extract_links_object_data() -> None:
    html = '<object data="/flash/animation.swf"></object>'
    links = extract_links(html, 'https://example.com/page.html')
    assert any(lk.url == 'https://example.com/flash/animation.swf' for lk in links)


def test_extract_links_embed_src() -> None:
    html = '<embed src="/plugin/viewer.pdf">'
    links = extract_links(html, 'https://example.com/page.html')
    assert any(lk.url == 'https://example.com/plugin/viewer.pdf' for lk in links)


def test_extract_links_form_action() -> None:
    html = '<form action="/submit" method="post"><input type="submit"></form>'
    links = extract_links(html, 'https://example.com/page.html')
    assert any(lk.url == 'https://example.com/submit' for lk in links)


def test_extract_links_relative_resolved() -> None:
    html = '<a href="page.html">link</a>'
    links = extract_links(html, 'https://example.com/docs/')
    assert any(lk.url == 'https://example.com/docs/page.html' for lk in links)


def test_extract_links_absolute_unchanged() -> None:
    html = '<a href="https://external.com/page">ext</a>'
    links = extract_links(html, 'https://example.com/page.html')
    assert any(lk.url == 'https://external.com/page' for lk in links)


def test_extract_links_base_href() -> None:
    html = (
        '<html><head><base href="https://cdn.example.com/"></head>'
        '<body><img src="logo.png"></body></html>'
    )
    links = extract_links(html, 'https://example.com/page.html')
    assert any(lk.url == 'https://cdn.example.com/logo.png' for lk in links)


def test_extract_links_base_href_param_overrides() -> None:
    html = '<img src="logo.png">'
    links = extract_links(
        html, 'https://example.com/page.html', base_url='https://cdn.example.com/'
    )
    assert any(lk.url == 'https://cdn.example.com/logo.png' for lk in links)


def test_extract_links_skips_empty_href() -> None:
    html = '<a href="">empty</a><a href="#">frag</a>'
    links = extract_links(html, 'https://example.com/page.html')
    assert not any(lk.url == '' for lk in links)


def test_extract_links_malformed_html_tolerant() -> None:
    html = '<a href="/ok"><b>text<img src="/img.png"></a><p unclosed'
    links = extract_links(html, 'https://example.com/page.html')
    urls = [lk.url for lk in links]
    assert 'https://example.com/ok' in urls
    assert 'https://example.com/img.png' in urls


def test_extract_links_a_is_not_asset() -> None:
    html = '<a href="/page">link</a>'
    links = extract_links(html, 'https://example.com/page.html')
    assert all(lk.is_asset is False for lk in links if lk.source_element == 'a')


def test_extract_links_source_srcset() -> None:
    html = '<picture><source srcset="/img/sm.webp 480w, /img/lg.webp 1080w"></picture>'
    links = extract_links(html, 'https://example.com/page.html')
    urls = [lk.url for lk in links]
    assert 'https://example.com/img/sm.webp' in urls
    assert 'https://example.com/img/lg.webp' in urls


def test_extract_links_extracted_link_fields() -> None:
    html = '<a href="/page">link</a>'
    links = extract_links(html, 'https://example.com/')
    assert len(links) == 1
    lk = links[0]
    assert isinstance(lk, ExtractedLink)
    assert lk.source_element == 'a'
    assert lk.source_attribute == 'href'
    assert lk.is_asset is False


# ---------------------------------------------------------------------------
# extract_anchors
# ---------------------------------------------------------------------------


def test_extract_anchors_id() -> None:
    html = '<div id="section1"><p>text</p></div>'
    anchors = extract_anchors(html)
    assert 'section1' in anchors


def test_extract_anchors_a_name() -> None:
    html = '<a name="section2">anchor</a>'
    anchors = extract_anchors(html)
    assert 'section2' in anchors


def test_extract_anchors_multiple() -> None:
    html = '<h1 id="top">Top</h1><h2 id="intro">Intro</h2><a name="legacy">L</a>'
    anchors = extract_anchors(html)
    assert 'top' in anchors
    assert 'intro' in anchors
    assert 'legacy' in anchors


def test_extract_anchors_empty_page() -> None:
    anchors = extract_anchors('')
    assert len(anchors) == 0


def test_extract_anchors_returns_frozenset() -> None:
    anchors = extract_anchors('<div id="x">x</div>')
    assert isinstance(anchors, frozenset)


# ---------------------------------------------------------------------------
# find_base_href
# ---------------------------------------------------------------------------


def test_find_base_href_present() -> None:
    html = '<html><head><base href="https://cdn.example.com/static/"></head><body></body></html>'
    assert find_base_href(html) == 'https://cdn.example.com/static/'


def test_find_base_href_absent() -> None:
    html = '<html><head><title>page</title></head><body></body></html>'
    assert find_base_href(html) is None


def test_find_base_href_uses_first_only() -> None:
    html = '<html><head><base href="https://first.com/"><base href="https://second.com/"></head></html>'
    assert find_base_href(html) == 'https://first.com/'


# ---------------------------------------------------------------------------
# srcset parsing
# ---------------------------------------------------------------------------


def test_extract_links_srcset_single() -> None:
    html = '<img srcset="/img/pic.jpg">'
    links = extract_links(html, 'https://example.com/')
    assert any(lk.url == 'https://example.com/img/pic.jpg' for lk in links)


def test_extract_links_srcset_with_descriptors() -> None:
    html = '<img srcset="/img/sm.jpg 480w, /img/lg.jpg 1080w, /img/xl.jpg 2x">'
    links = extract_links(html, 'https://example.com/')
    urls = [lk.url for lk in links]
    assert 'https://example.com/img/sm.jpg' in urls
    assert 'https://example.com/img/lg.jpg' in urls
    assert 'https://example.com/img/xl.jpg' in urls


def test_parse_srcset_trailing_comma_ignored() -> None:
    """A srcset entry that is only whitespace/comma must not produce a URL."""
    from link_checker.html_parser import _parse_srcset

    result = _parse_srcset('  ,  ')
    assert result == []


def test_extract_anchors_skips_non_tag_nodes() -> None:
    """extract_anchors must return an empty set when no real anchor tags exist."""
    from link_checker.html_parser import extract_anchors

    # Plain text with no tags at all.
    result = extract_anchors('just plain text')
    assert result == frozenset()


def test_extract_anchors_id_and_name() -> None:
    """Both id= attributes and <a name=> attributes must be captured."""
    from link_checker.html_parser import extract_anchors

    html = '<h2 id="section1">Title</h2><a name="legacy">anchor</a>'
    result = extract_anchors(html)
    assert 'section1' in result
    assert 'legacy' in result

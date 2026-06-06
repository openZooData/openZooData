"""
test_feed.py — Tests für den öffentlichen RSS-Feed-Endpoint

Diese Tests prüfen:
- Feed-Struktur und RSS-Konformität
- Zoo-Namespace-Elemente
- Enclosure-Element (SQLite-Download-URL)
- Öffentlicher Zugang (kein API-Key nötig)
- Feed-Liste (/feed)
- Fehlerbehandlung
"""

import pytest

pytestmark = [pytest.mark.feed, pytest.mark.requires_data]
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

RSS_NS = "http://www.w3.org/2005/Atom"
ZOO_NS = "https://zooguide.app/rss/1.0"


###############################################################################
# 🔓 Öffentlicher Zugang
###############################################################################

@pytest.mark.requires_data
def test_feed_no_auth_required(base_url, test_feed_zoo):
    """GET /feed/<zoo> ohne API-Key → 200 (öffentlich)"""
    resp = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    assert resp.status_code == 200, f"Feed sollte ohne Auth erreichbar sein: {resp.text}"


@pytest.mark.requires_data
def test_feed_list_no_auth_required(base_url):
    """GET /feed ohne API-Key → 200 (öffentlich)"""
    resp = requests.get(f"{base_url}/feed")
    assert resp.status_code == 200


@pytest.mark.requires_data
def test_feed_invalid_slug(base_url):
    """GET /feed/<ungültiger Slug> → 400 oder 404"""
    resp = requests.get(f"{base_url}/feed/zoo_UNGUELTIG!")
    assert resp.status_code in (400, 404)


@pytest.mark.requires_data
def test_feed_unknown_zoo(base_url):
    """GET /feed/zoo_gibts_nicht → 404"""
    resp = requests.get(f"{base_url}/feed/zoo_gibts_nicht")
    assert resp.status_code == 404


###############################################################################
# 📄 RSS-Struktur
###############################################################################

@pytest.mark.requires_data
def test_feed_content_type(base_url, test_feed_zoo):
    """GET /feed/<zoo> → Content-Type: application/rss+xml"""
    resp = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    assert resp.status_code == 200
    assert "application/rss+xml" in resp.headers.get("Content-Type", "")


@pytest.mark.requires_data
def test_feed_is_valid_xml(base_url, test_feed_zoo):
    """GET /feed/<zoo> → valides XML"""
    resp = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    assert resp.status_code == 200
    try:
        ET.fromstring(resp.content)
    except ET.ParseError as e:
        pytest.fail(f"Feed ist kein valides XML: {e}")


@pytest.mark.requires_data
def test_feed_rss_version(base_url, test_feed_zoo):
    """Feed-Root hat version='2.0'"""
    resp = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root = ET.fromstring(resp.content)
    assert root.tag == "rss"
    assert root.attrib.get("version") == "2.0"


@pytest.mark.requires_data
def test_feed_has_channel(base_url, test_feed_zoo):
    """Feed enthält <channel>"""
    resp    = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root    = ET.fromstring(resp.content)
    channel = root.find("channel")
    assert channel is not None


@pytest.mark.requires_data
def test_feed_channel_required_elements(base_url, test_feed_zoo):
    """<channel> enthält title, link, description"""
    resp    = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root    = ET.fromstring(resp.content)
    channel = root.find("channel")
    assert channel.find("title")       is not None
    assert channel.find("link")        is not None
    assert channel.find("description") is not None


@pytest.mark.requires_data
def test_feed_has_at_least_one_item(base_url, test_feed_zoo):
    """Feed enthält mindestens ein <item>"""
    resp    = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root    = ET.fromstring(resp.content)
    channel = root.find("channel")
    items   = channel.findall("item")
    assert len(items) >= 1, "Feed muss mindestens ein Item enthalten"


@pytest.mark.requires_data
def test_feed_item_has_guid(base_url, test_feed_zoo):
    """Erstes <item> enthält <guid>"""
    resp = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root = ET.fromstring(resp.content)
    item = root.find("channel/item")
    assert item is not None
    guid = item.find("guid")
    assert guid is not None
    assert guid.text, "guid darf nicht leer sein"


@pytest.mark.requires_data
def test_feed_item_has_pubdate(base_url, test_feed_zoo):
    """Erstes <item> enthält <pubDate> mit Inhalt"""
    resp = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root = ET.fromstring(resp.content)
    item = root.find("channel/item")
    assert item is not None
    pub  = item.find("pubDate")
    assert pub is not None
    assert pub.text, "pubDate darf nicht leer sein"


###############################################################################
# 🦓 Zoo-Namespace-Elemente
###############################################################################

@pytest.mark.requires_data
def test_feed_zoo_slug(base_url, test_feed_zoo):
    """<zoo:slug> stimmt mit angefragtem Zoo überein"""
    resp    = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root    = ET.fromstring(resp.content)
    channel = root.find("channel")
    slug    = channel.find(f"{{{ZOO_NS}}}slug")
    assert slug is not None, "<zoo:slug> fehlt im Feed"
    assert slug.text == test_feed_zoo


@pytest.mark.requires_data
def test_feed_zoo_version(base_url, test_feed_zoo):
    """<zoo:version> ist eine positive Ganzzahl"""
    resp    = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root    = ET.fromstring(resp.content)
    channel = root.find("channel")
    version = channel.find(f"{{{ZOO_NS}}}version")
    assert version is not None, "<zoo:version> fehlt im Feed"
    assert int(version.text) > 0


@pytest.mark.requires_data
def test_feed_zoo_display_name(base_url, test_feed_zoo):
    """<zoo:displayName> ist nicht leer"""
    resp    = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root    = ET.fromstring(resp.content)
    channel = root.find("channel")
    name    = channel.find(f"{{{ZOO_NS}}}displayName")
    assert name is not None, "<zoo:displayName> fehlt"
    assert name.text, "<zoo:displayName> ist leer"


@pytest.mark.requires_data
def test_feed_zoo_feed_version(base_url, test_feed_zoo):
    """<zoo:feedVersion> ist vorhanden"""
    resp    = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root    = ET.fromstring(resp.content)
    channel = root.find("channel")
    fv      = channel.find(f"{{{ZOO_NS}}}feedVersion")
    assert fv is not None, "<zoo:feedVersion> fehlt"


@pytest.mark.requires_data
def test_feed_item_zoo_version(base_url, test_feed_zoo):
    """Erstes <item> enthält <zoo:version>"""
    resp    = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root    = ET.fromstring(resp.content)
    item    = root.find("channel/item")
    version = item.find(f"{{{ZOO_NS}}}version")
    assert version is not None, "<zoo:version> im Item fehlt"
    assert int(version.text) > 0


###############################################################################
# 📦 Enclosure — SQLite-Download
###############################################################################

@pytest.mark.requires_data
def test_feed_item_has_enclosure(base_url, test_feed_zoo):
    """Erstes <item> enthält <enclosure>"""
    resp      = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root      = ET.fromstring(resp.content)
    item      = root.find("channel/item")
    enclosure = item.find("enclosure")
    assert enclosure is not None, "<enclosure> fehlt im Feed-Item"


@pytest.mark.requires_data
def test_feed_enclosure_attributes(base_url, test_feed_zoo):
    """<enclosure> hat url, length und type"""
    resp      = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root      = ET.fromstring(resp.content)
    item      = root.find("channel/item")
    enclosure = item.find("enclosure")
    assert "url"    in enclosure.attrib, "enclosure.url fehlt"
    assert "length" in enclosure.attrib, "enclosure.length fehlt"
    assert "type"   in enclosure.attrib, "enclosure.type fehlt"


@pytest.mark.requires_data
def test_feed_enclosure_type(base_url, test_feed_zoo):
    """<enclosure type> ist application/x-sqlite3+gzip"""
    resp      = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root      = ET.fromstring(resp.content)
    enclosure = root.find("channel/item/enclosure")
    assert enclosure.attrib["type"] == "application/x-sqlite3+gzip"


@pytest.mark.requires_data
def test_feed_enclosure_url_reachable(base_url, test_feed_zoo, app_token_headers):
    """enclosure.url existiert und antwortet (Auth-Fehler = 403 ist OK)"""
    resp      = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root      = ET.fromstring(resp.content)
    enclosure = root.find("channel/item/enclosure")
    url       = enclosure.attrib["url"]
    assert url, "enclosure.url ist leer"
    # 403 = Auth nötig aber URL ist korrekt erreichbar
    resp_db = requests.head(url, headers=app_token_headers)
    assert resp_db.status_code in (200, 301, 304, 403), \
        f"enclosure.url nicht erreichbar: {resp_db.status_code}"


@pytest.mark.requires_data
def test_feed_version_matches_db(base_url, test_feed_zoo, app_token_headers):
    """
    <zoo:version> im Feed stimmt mit ETag aus /db/<zoo> überein.
    Stellt sicher dass Feed und SQLite-Endpoint synchron sind.
    """
    resp_feed = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    root      = ET.fromstring(resp_feed.content)
    channel   = root.find("channel")
    feed_ver  = int(channel.find(f"{{{ZOO_NS}}}version").text)

    resp_db  = requests.head(
        f"{base_url}/db/{test_feed_zoo}",
        headers=app_token_headers
    )
    db_etag  = int(resp_db.headers.get("ETag", "0").strip('"'))

    assert feed_ver == db_etag, (
        f"Feed-Version ({feed_ver}) stimmt nicht mit SQLite-ETag ({db_etag}) überein"
    )


###############################################################################
# 📋 Feed-Liste
###############################################################################

@pytest.mark.requires_data
def test_feed_list_returns_array(base_url):
    """GET /feed → JSON-Array"""
    resp = requests.get(f"{base_url}/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.requires_data
def test_feed_list_entry_structure(base_url):
    """Jeder Eintrag in /feed hat slug, name, feed_url, version"""
    resp = requests.get(f"{base_url}/feed")
    data = resp.json()
    for entry in data:
        assert "slug"     in entry, f"slug fehlt: {entry}"
        assert "name"     in entry, f"name fehlt: {entry}"
        assert "feed_url" in entry, f"feed_url fehlt: {entry}"
        assert "version"  in entry, f"version fehlt: {entry}"


@pytest.mark.requires_data
def test_feed_list_contains_test_zoo(base_url, test_feed_zoo):
    """Feed-Liste enthält den Test-Zoo"""
    resp  = requests.get(f"{base_url}/feed")
    slugs = [e["slug"] for e in resp.json()]
    assert test_feed_zoo in slugs, f"{test_feed_zoo} fehlt in Feed-Liste"


@pytest.mark.requires_data
def test_feed_list_feed_urls_valid(base_url):
    """Alle feed_url-Einträge zeigen auf denselben Host wie base_url"""
    resp          = requests.get(f"{base_url}/feed")
    expected_host = urlparse(base_url).netloc
    for entry in resp.json():
        feed_host = urlparse(entry["feed_url"]).netloc
        assert feed_host == expected_host, \
            f"feed_url hat falschen Host: {entry['feed_url']}"


###############################################################################
# 🚦 Caching & Headers
###############################################################################

@pytest.mark.requires_data
def test_feed_cache_control(base_url, test_feed_zoo):
    """Feed-Response hat Cache-Control Header"""
    resp = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    assert "Cache-Control" in resp.headers


@pytest.mark.requires_data
def test_feed_x_zoo_version_header(base_url, test_feed_zoo):
    """Feed-Response hat X-Zoo-Version Header"""
    resp = requests.get(f"{base_url}/feed/{test_feed_zoo}")
    assert "X-Zoo-Version" in resp.headers
    assert int(resp.headers["X-Zoo-Version"]) > 0

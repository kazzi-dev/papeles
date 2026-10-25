import httpx
import pytest

from app.ingest import load_text, page_text


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_file_entry_reads_local_file_without_network(tmp_path):
    (tmp_path / "manual").mkdir()
    (tmp_path / "manual" / "nbi.md").write_text("Bring two valid IDs.", encoding="utf-8")

    def no_network(request):
        raise AssertionError("file entries must not hit the network")

    entry = {"file": "manual/nbi.md", "url": "https://clearance.nbi.gov.ph/"}
    assert load_text(entry, client(no_network), tmp_path) == "Bring two valid IDs."


def test_url_entry_extracts_main_text_from_html():
    html = "<html><nav>Menu</nav><main><h1>SSS</h1><p>Register online.</p></main></html>"
    http = client(lambda r: httpx.Response(200, html=html))
    assert load_text({"url": "https://sss.gov.ph/x"}, http) == "SSS Register online."


def test_url_entry_raises_on_blocked_site():
    http = client(lambda r: httpx.Response(403))
    with pytest.raises(httpx.HTTPStatusError):
        load_text({"url": "https://dfa.gov.ph/x"}, http)


def test_page_text_drops_scripts_and_footer():
    html = "<body><script>x()</script><p>Fee: PHP 130</p><footer>(c) PSA</footer></body>"
    assert page_text(html) == "Fee: PHP 130"


def test_sources_yaml_entries_are_complete():
    import yaml

    from app.ingest import DATA_DIR, SOURCES_FILE

    entries = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    slugs = [e["slug"] for e in entries]
    assert len(slugs) == len(set(slugs)), "slugs must be unique"
    for e in entries:
        assert {"slug", "agency", "title", "url"} <= e.keys(), e
        if "file" in e:
            assert (DATA_DIR / e["file"]).is_file(), f"missing {e['file']}"


def test_page_text_drops_wordpress_menus():
    html = (
        '<body><div class="menu-main-container"><ul class="menu"><li>Loans</li></ul></div>'
        "<p>Apply for an SS number online.</p></body>"
    )
    assert page_text(html) == "Apply for an SS number online."

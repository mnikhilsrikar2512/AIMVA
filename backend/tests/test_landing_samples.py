"""The public site's sample pages come from the real page builder, and their forms never send anything."""
from scripts import landing_samples


def test_samples_build_with_the_page_builder_and_cannot_send(tmp_path, monkeypatch):
    monkeypatch.setattr(landing_samples, "OUT", tmp_path)
    landing_samples.main()
    for key in landing_samples.briefs:
        html = (tmp_path / f"{key}.html").read_text()
        assert "data-aimva-lead" in html or "<form" in html
        assert "stopImmediatePropagation" in html.split("</head>")[0]  # guard runs before the page's own scripts
        assert 'name="robots" content="noindex"' in html
        assert "Sample page made with AIMVA" in html

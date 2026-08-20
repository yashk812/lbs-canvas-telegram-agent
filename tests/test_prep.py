"""Tests for pre-session prep extraction (front-page panels + helpers)."""
from __future__ import annotations

import os

os.environ.setdefault("TIMEZONE", "Europe/London")

from canvas_agent import prep  # noqa: E402

# Minimal DesignPlus front page: two session panels, a reading link + questions.
FRONT_PAGE = """
<div class="dp-panel-group">
  <h3 class="dp-panel-heading">Session 1</h3>
  <div class="dp-panel-content">
    <h4>The Challenge</h4>
    <h4>Readings Before Class</h4>
    <ul><li>Case: <a href="/courses/12479/external_tools/retrieve?x=1">Honda (A)</a></li></ul>
    <h4>Class Preparation</h4>
    <ol>
      <li>Why was Honda so successful?</li>
      <li>How did Soichiro Honda add value?</li>
    </ol>
    <p>Nav <a href="/courses/12479/pages/summary">Course Summary</a></p>
  </div>
</div>
<div class="dp-panel-group">
  <h3 class="dp-panel-heading">Session 2 &amp; 3</h3>
  <div class="dp-panel-content"><h4>Framing Decisions</h4>
    <p><a href="/courses/12479/files/999?wrap=1">Reading 2</a></p></div>
</div>
"""


class _StubClient:
    def front_page(self, course_id):
        return {"body": FRONT_PAGE}

    def modules_with_items(self, course_id):
        return []


def test_front_page_prep_extracted():
    p = prep.extract_prep(_StubClient(), 12479, "Understanding General Management", 1)
    assert p is not None
    assert p.theme == "The Challenge"
    assert p.readings == [("Honda (A)", "/courses/12479/external_tools/retrieve?x=1")]
    assert p.prep_notes == ["Why was Honda so successful?", "How did Soichiro Honda add value?"]


def test_nav_links_excluded():
    p = prep.extract_prep(_StubClient(), 12479, "UGM", 1)
    urls = [u for _, u in p.readings]
    assert not any("pages/summary" in u for u in urls)  # navigation is not a reading


def test_combined_session_panel_matches_either_number():
    # "Session 2 & 3" panel should be found for both session 2 and session 3
    for n in (2, 3):
        p = prep.extract_prep(_StubClient(), 12479, "UGM", n)
        assert p is not None and p.theme == "Framing Decisions"


def test_no_panel_returns_none():
    assert prep.extract_prep(_StubClient(), 12479, "UGM", 9) is None


TEXT_PREP_PAGE = """
<h2>Multiple Regression</h2>
<h3>Preparation</h3>
<ul><li>Read OpenIntro sections 9.1-9.3</li><li>Review the material, work on the case</li></ul>
"""


class _ModuleClient:
    def front_page(self, course_id):
        return None

    def modules_with_items(self, course_id):
        return [{"name": "Sessions 4 & 5", "items": [{"type": "Page", "page_url": "4-5"}]}]

    def page_body(self, course_id, page_url):
        return TEXT_PREP_PAGE


def test_module_text_prep_without_links():
    # prep with instructions but no link (e.g. "Read OpenIntro 9.1-9.3") is still surfaced
    p = prep.extract_prep(_ModuleClient(), 12542, "Data Analytics", 4)
    assert p is not None and p.readings == []
    assert p.prep_notes == ["Read OpenIntro sections 9.1-9.3", "Review the material, work on the case"]


def test_clean_course_and_match():
    assert prep.clean_course("C122   AUT26 Understanding General Management") == "Understanding General Management"
    assert prep.matches_schedule("Understanding General Management", {"Understanding General Management"})
    assert not prep.matches_schedule("Ethics", {"Understanding General Management"})

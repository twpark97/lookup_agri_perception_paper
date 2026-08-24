from paper_bot.main import (
  Paper,
  deduplicate,
  inverted_abstract,
  normalize_title,
  paper_category,
  paper_key,
  select_quota,
)


def make_paper(title: str, doi: str | None = None) -> Paper:
  return Paper("id", title, "abstract", [], "2026-01-01", "https://example.com", None, doi, "test")


def make_venue_paper(title: str, venue: str, source: str = "OpenAlex") -> Paper:
  return Paper(
    title,
    title,
    "abstract",
    [],
    "2026-01-01",
    "https://example.com",
    None,
    None,
    source,
    venue,
    None,
  )


def test_normalize_title() -> None:
  assert normalize_title("LiDAR-Camera: Calibration!") == "lidar camera calibration"


def test_deduplicate_by_normalized_title() -> None:
  papers = [make_paper("Farm Robot"), make_paper("Farm-Robot")]
  assert len(deduplicate(papers)) == 1


def test_deduplicate_by_doi() -> None:
  papers = [make_paper("Title A", "https://doi.org/10.1/x"), make_paper("Title B", "10.1/x")]
  assert len(deduplicate(papers)) == 1
  assert paper_key(papers[0]) == "doi:10.1/x"


def test_inverted_abstract() -> None:
  assert inverted_abstract({"robot": [1], "A": [0], "works": [2]}) == "A robot works"


def test_paper_category() -> None:
  policy = {
    "robot_journals": ["IEEE Robotics and Automation Letters"],
    "phenotyping_journals": ["Plant Phenomics"],
    "other_q1_q2_journals": ["Pattern Recognition"],
    "blocked_publishers": ["MDPI AG", "Frontiers Media SA"],
  }
  assert paper_category(make_venue_paper("A", "IEEE Robotics and Automation Letters"), policy) == "robot"
  assert paper_category(make_venue_paper("B", "Plant Phenomics"), policy) == "phenotyping"
  assert paper_category(make_venue_paper("C", "Pattern Recognition"), policy) == "other"
  assert paper_category(make_venue_paper("D", "Unknown Journal"), policy) is None
  assert paper_category(make_venue_paper("E", "", "arXiv"), policy) == "other"


def test_select_quota() -> None:
  policy = {
    "robot_journals": ["Robot Journal"],
    "phenotyping_journals": ["Phenotyping Journal"],
    "other_q1_q2_journals": ["Other Journal"],
    "blocked_publishers": [],
  }
  papers = [
    make_venue_paper("Robot 1", "Robot Journal"),
    make_venue_paper("Robot 2", "Robot Journal"),
    make_venue_paper("Phenotyping 1", "Phenotyping Journal"),
    make_venue_paper("Other 1", "", "arXiv"),
  ]
  ranking = [
    {"key": paper_key(paper), "score": 100 - index, "reason": "test"}
    for index, paper in enumerate(papers)
  ]
  selected = select_quota(ranking, papers, policy)
  assert [item["category"] for item in selected] == [
    "robot",
    "robot",
    "phenotyping",
    "other",
  ]

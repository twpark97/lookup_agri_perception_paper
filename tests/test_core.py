from paper_bot.main import (
  Paper,
  deduplicate,
  inverted_abstract,
  normalize_title,
  paper_key,
)


def make_paper(title: str, doi: str | None = None) -> Paper:
  return Paper("id", title, "abstract", [], "2026-01-01", "https://example.com", None, doi, "test")


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


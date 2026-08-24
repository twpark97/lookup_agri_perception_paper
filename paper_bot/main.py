from __future__ import annotations

import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
ARXIV_API = "https://export.arxiv.org/api/query"
OPENALEX_API = "https://api.openalex.org/works"
SLACK_API = "https://slack.com/api/chat.postMessage"


@dataclass(frozen=True)
class Paper:
  paper_id: str
  title: str
  abstract: str
  authors: list[str]
  published: str
  url: str
  pdf_url: str | None
  doi: str | None
  source: str
  venue: str | None = None
  publisher: str | None = None


def required_env(name: str) -> str:
  value = os.environ.get(name)
  if not value:
    raise RuntimeError(f"Required environment variable is missing: {name}")
  return value


def normalize_title(title: str) -> str:
  return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def normalize_name(name: str | None) -> str:
  if not name:
    return ""
  return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def paper_key(paper: Paper) -> str:
  if paper.doi:
    return f"doi:{paper.doi.lower().removeprefix('https://doi.org/')}"
  digest = hashlib.sha256(normalize_title(paper.title).encode()).hexdigest()[:20]
  return f"title:{digest}"


def inverted_abstract(index: dict[str, list[int]] | None) -> str:
  if not index:
    return ""
  positions = [(position, word) for word, values in index.items() for position in values]
  return " ".join(word for _, word in sorted(positions))


def fetch_arxiv(queries: list[str], max_per_query: int = 30) -> list[Paper]:
  papers: list[Paper] = []
  ns = {"atom": "http://www.w3.org/2005/Atom"}
  for query in queries:
    response = requests.get(
      ARXIV_API,
      params={
        "search_query": query,
        "start": 0,
        "max_results": max_per_query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
      },
      timeout=45,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    for entry in root.findall("atom:entry", ns):
      entry_id = entry.findtext("atom:id", namespaces=ns)
      title = entry.findtext("atom:title", namespaces=ns)
      abstract = entry.findtext("atom:summary", namespaces=ns)
      published = entry.findtext("atom:published", namespaces=ns)
      if not all((entry_id, title, abstract, published)):
        raise ValueError("arXiv returned an entry with required fields missing")
      authors = [
        name.text or ""
        for name in entry.findall("atom:author/atom:name", ns)
      ]
      pdf_url = next(
        (
          link.attrib["href"]
          for link in entry.findall("atom:link", ns)
          if link.attrib.get("title") == "pdf"
        ),
        None,
      )
      papers.append(
        Paper(
          paper_id=entry_id.rsplit("/", 1)[-1],
          title=" ".join(title.split()),
          abstract=" ".join(abstract.split()),
          authors=authors,
          published=published,
          url=entry_id,
          pdf_url=pdf_url,
          doi=None,
          source="arXiv",
        )
      )
  return papers


def fetch_openalex(searches: list[str], max_per_query: int = 40) -> list[Paper]:
  papers: list[Paper] = []
  since = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
  for index, search in enumerate(searches):
    if index:
      time.sleep(1)
    response = requests.get(
      OPENALEX_API,
      params={
        "search": search,
        "filter": f"from_publication_date:{since}",
        "per-page": max_per_query,
        "sort": "publication_date:desc",
      },
      headers={"User-Agent": "lookup-agri-perception-paper/1.0"},
      timeout=45,
    )
    response.raise_for_status()
    for work in response.json()["results"]:
      title = work.get("title")
      if not title:
        raise ValueError("OpenAlex returned a work without a title")
      primary = work.get("primary_location") or {}
      best = work.get("best_oa_location") or {}
      venue_source = primary.get("source") or {}
      url = primary.get("landing_page_url") or work["id"]
      papers.append(
        Paper(
          paper_id=work["id"].rsplit("/", 1)[-1],
          title=" ".join(title.split()),
          abstract=inverted_abstract(work.get("abstract_inverted_index")),
          authors=[
            item["author"]["display_name"] for item in work["authorships"]
          ],
          published=work.get("publication_date") or "",
          url=url,
          pdf_url=best.get("pdf_url"),
          doi=work.get("doi"),
          source="OpenAlex",
          venue=venue_source.get("display_name"),
          publisher=venue_source.get("host_organization_name"),
        )
      )
  return papers


def deduplicate(papers: list[Paper]) -> list[Paper]:
  unique: dict[str, Paper] = {}
  titles: set[str] = set()
  for paper in papers:
    normalized = normalize_title(paper.title)
    key = paper_key(paper)
    if key in unique or normalized in titles:
      continue
    unique[key] = paper
    titles.add(normalized)
  return list(unique.values())


def paper_category(paper: Paper, policy: dict[str, Any]) -> str | None:
  if paper.source == "arXiv":
    return "other"

  publisher = normalize_name(paper.publisher)
  blocked_publishers = {
    normalize_name(name) for name in policy["blocked_publishers"]
  }
  if publisher in blocked_publishers:
    return None

  venue = normalize_name(paper.venue)
  robot_journals = {
    normalize_name(name) for name in policy["robot_journals"]
  }
  phenotyping_journals = {
    normalize_name(name) for name in policy["phenotyping_journals"]
  }
  other_journals = {
    normalize_name(name) for name in policy["other_q1_q2_journals"]
  }
  if venue in robot_journals:
    return "robot"
  if venue in phenotyping_journals:
    return "phenotyping"
  if venue in other_journals:
    return "other"
  return None


def select_quota(
  ranking: list[dict[str, Any]],
  papers: list[Paper],
  policy: dict[str, Any],
) -> list[dict[str, Any]]:
  by_key = {paper_key(paper): paper for paper in papers}
  quotas = {"robot": 2, "phenotyping": 1, "other": 1}
  selected: list[dict[str, Any]] = []
  for category, quota in quotas.items():
    matches = [
      item
      for item in ranking
      if paper_category(by_key[item["key"]], policy) == category
    ]
    if len(matches) < quota:
      raise RuntimeError(
        f"Only {len(matches)} eligible {category} papers were collected; "
        f"required {quota}"
      )
    selected.extend({**item, "category": category} for item in matches[:quota])
  return selected


def json_response(client: OpenAI, model: str, prompt: str, schema: dict[str, Any]) -> Any:
  response = client.responses.create(
    model=model,
    input=prompt,
    text={
      "format": {
        "type": "json_schema",
        "name": "paper_recommendation",
        "strict": True,
        "schema": schema,
      }
    },
  )
  return json.loads(response.output_text)


def rank_papers(client: OpenAI, profile: dict[str, Any], papers: list[Paper]) -> list[dict[str, Any]]:
  candidates = [
    {
      "key": paper_key(paper),
      "title": paper.title,
      "abstract": paper.abstract[:2500],
      "published": paper.published,
      "source": paper.source,
      "venue": paper.venue,
    }
    for paper in papers
  ]
  schema = {
    "type": "object",
    "properties": {
      "ranked": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "key": {"type": "string"},
            "score": {"type": "number"},
            "reason": {"type": "string"},
          },
          "required": ["key", "score", "reason"],
          "additionalProperties": False,
        },
      }
    },
    "required": ["ranked"],
    "additionalProperties": False,
  }
  prompt = (
    "Score every paper from 0 to 100 for this researcher's actual research utility. "
    "Prefer concrete methods, datasets, systems, and code over generic surveys. "
    "Return every input key exactly once.\n\n"
    f"RESEARCH PROFILE:\n{json.dumps(profile, ensure_ascii=False)}\n\n"
    f"PAPERS:\n{json.dumps(candidates, ensure_ascii=False)}"
  )
  result = json_response(
    client,
    os.getenv("RANK_MODEL", "gpt-4o-mini"),
    prompt,
    schema,
  )
  return sorted(result["ranked"], key=lambda item: item["score"], reverse=True)


def summarize_papers(
  client: OpenAI,
  profile: dict[str, Any],
  papers: list[Paper],
  ranking: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  by_key = {paper_key(paper): paper for paper in papers}
  shortlist = []
  for rank in ranking:
    paper = by_key[rank["key"]]
    shortlist.append(
      {
        **asdict(paper),
        "key": rank["key"],
        "category": rank["category"],
        "rank_reason": rank["reason"],
      }
    )
  schema = {
    "type": "object",
    "properties": {
      "recommendations": {
        "type": "array",
        "minItems": 4,
        "maxItems": 4,
        "items": {
          "type": "object",
          "properties": {
            "key": {"type": "string"},
            "reason_ko": {"type": "string"},
            "summary_ko": {"type": "string"},
            "application_ko": {"type": "string"},
            "confidence": {"type": "number"},
          },
          "required": ["key", "reason_ko", "summary_ko", "application_ko", "confidence"],
          "additionalProperties": False,
        },
      }
    },
    "required": ["recommendations"],
    "additionalProperties": False,
  }
  prompt = (
    "Summarize all four supplied papers and return every input key exactly once. "
    "Write compact Korean summaries. "
    "Do not exaggerate findings beyond the supplied abstract. application_ko must "
    "connect the paper to a specific part of the research profile.\n\n"
    f"PROFILE:\n{json.dumps(profile, ensure_ascii=False)}\n\n"
    f"SHORTLIST:\n{json.dumps(shortlist, ensure_ascii=False)}"
  )
  result = json_response(
    client,
    os.getenv("SUMMARY_MODEL", "gpt-4o-mini"),
    prompt,
    schema,
  )
  return result["recommendations"]


def format_slack(recommendations: list[dict[str, Any]], papers: list[Paper]) -> str:
  by_key = {paper_key(paper): paper for paper in papers}
  date = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
  sections = [f"*오늘의 농업 로봇·인식 논문 — {date}*"]
  for index, item in enumerate(recommendations, start=1):
    paper = by_key[item["key"]]
    links = f"<{paper.url}|Paper>"
    if paper.pdf_url:
      links += f" · <{paper.pdf_url}|PDF>"
    sections.append(
      f"*{index}. {paper.title}*\n"
      f"• 추천 이유: {item['reason_ko']}\n"
      f"• 핵심: {item['summary_ko']}\n"
      f"• 적용 아이디어: {item['application_ko']}\n"
      f"• 신뢰도: {item['confidence']:.2f} · {links}"
    )
  return "\n\n".join(sections)


def send_slack(token: str, channel: str, text: str) -> None:
  response = requests.post(
    SLACK_API,
    headers={"Authorization": f"Bearer {token}"},
    json={"channel": channel, "text": text, "unfurl_links": False},
    timeout=30,
  )
  response.raise_for_status()
  payload = response.json()
  if not payload.get("ok"):
    raise RuntimeError(f"Slack API rejected message: {payload.get('error')}")


def main() -> None:
  profile = json.loads((ROOT / "interests.json").read_text())
  policy = json.loads((ROOT / "journal_policy.json").read_text())
  state_path = ROOT / "state" / "seen.json"
  state = json.loads(state_path.read_text())

  papers = deduplicate(
    fetch_arxiv(profile["arxiv_queries"])
    + fetch_openalex(profile["openalex_searches"])
  )
  unseen = [paper for paper in papers if paper_key(paper) not in state["papers"]]
  eligible = [paper for paper in unseen if paper_category(paper, policy)]
  if len(eligible) < 4:
    raise RuntimeError(f"Only {len(eligible)} eligible unseen papers were collected")

  client = OpenAI(api_key=required_env("OPENAI_API_KEY"))
  ranking = rank_papers(client, profile, eligible)
  selected = select_quota(ranking, eligible, policy)
  recommendations = summarize_papers(client, profile, eligible, selected)
  message = format_slack(recommendations, eligible)

  send_slack(
    required_env("SLACK_TOKEN1"),
    required_env("SLACK_SUMMARY_CHANNEL_ID1"),
    message,
  )
  send_slack(
    required_env("SLACK_TOKEN2"),
    required_env("SLACK_SUMMARY_CHANNEL_ID2"),
    message,
  )

  now = datetime.now(timezone.utc).isoformat()
  by_key = {paper_key(paper): paper for paper in eligible}
  for item in recommendations:
    paper = by_key[item["key"]]
    state["papers"][item["key"]] = {
      "title": paper.title,
      "recommended_at": now,
      "url": paper.url,
    }
  state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
  main()

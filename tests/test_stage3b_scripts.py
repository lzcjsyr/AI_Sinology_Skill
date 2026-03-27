from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import sys
import unittest
from pathlib import Path


def _load_script_module(filename: str, module_name: str):
    script_path = (
        Path(__file__).resolve().parent.parent
        / ".agent"
        / "skills"
        / "ai-sinology"
        / "scripts"
        / filename
    )
    spec = spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    sys.path.insert(0, str(script_path.parent))
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if sys.path and sys.path[0] == str(script_path.parent):
            sys.path.pop(0)
    return module


_STAGE3_SOURCES = _load_script_module("stage3b_sources.py", "test_ai_sinology_stage3b_sources")


class Stage3BScriptsTests(unittest.TestCase):
    def test_normalize_openalex_work_extracts_abstract_and_authors(self) -> None:
        work = {
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.1234/demo",
            "display_name": "Ritual and Rain",
            "publication_year": 2024,
            "type": "article",
            "authorships": [{"author": {"display_name": "Li Ming"}}],
            "primary_location": {
                "source": {"display_name": "Journal of Ritual Studies"},
                "landing_page_url": "https://example.com",
            },
            "abstract_inverted_index": {"Rain": [0], "ritual": [1]},
            "cited_by_count": 8,
        }

        payload = _STAGE3_SOURCES.normalize_openalex_work(work)

        self.assertEqual(payload["doi"], "10.1234/demo")
        self.assertEqual(payload["authors"], ["Li Ming"])
        self.assertEqual(payload["abstract"], "Rain ritual")
        self.assertEqual(payload["openalex_id"], "W123")

    def test_normalize_baidu_scholar_work_extracts_core_fields(self) -> None:
        work = {
            "abstract": "讨论汉代灾异说。",
            "aiAbstract": "",
            "doi": "CNKI:SUN:ZSHK.0.1991-03-008",
            "keyword": "灾异说;儒家经典;董仲舒",
            "paperId": "paper-123",
            "publishInfo": {"journalName": "中国社会科学"},
            "publishYear": 1991,
            "title": "汉代灾异学说与儒家君道论",
            "url": "https://xueshu.baidu.com/demo",
        }

        payload = _STAGE3_SOURCES.normalize_baidu_scholar_work(work)

        self.assertEqual(payload["source"], "baidu-scholar")
        self.assertEqual(payload["baidu_scholar_id"], "paper-123")
        self.assertEqual(payload["journal"], "中国社会科学")
        self.assertEqual(payload["keywords"], ["灾异说", "儒家经典", "董仲舒"])
        self.assertEqual(payload["landing_page_url"], "https://xueshu.baidu.com/demo")

    def test_expand_openalex_citations_fetches_one_hop_and_dedupes(self) -> None:
        def fake_fetcher(
            *,
            query: str,
            per_page: int,
            page: int,
            filter_expr: str = "",
            mailto: str = "",
            api_key: str = "",
            sort: str = "",
        ):
            parent_id = filter_expr.split(":", 1)[1].split(",", 1)[0]
            records_by_parent = {
                "W123": [
                    {
                        "source": "openalex",
                        "id": "https://openalex.org/W900",
                        "openalex_id": "W900",
                        "doi": "10.1/demo",
                        "title": "Han Ritual Commentary",
                        "year": 2020,
                        "type": "article",
                        "authors": ["Li Ming"],
                        "journal": "Journal A",
                        "abstract": "Demo",
                        "cited_by_count": 12,
                    }
                ],
                "W456": [
                    {
                        "source": "openalex",
                        "id": "https://openalex.org/W900",
                        "openalex_id": "W900",
                        "doi": "10.1/demo",
                        "title": "Han Ritual Commentary",
                        "year": 2020,
                        "type": "article",
                        "authors": ["Li Ming"],
                        "journal": "Journal A",
                        "abstract": "Demo",
                        "cited_by_count": 12,
                    },
                    {
                        "source": "openalex",
                        "id": "https://openalex.org/W901",
                        "openalex_id": "W901",
                        "doi": "10.1/demo-2",
                        "title": "Rain and Portents",
                        "year": 2019,
                        "type": "article",
                        "authors": ["Wang Hua"],
                        "journal": "Journal B",
                        "abstract": "Demo",
                        "cited_by_count": 8,
                    },
                ],
            }
            return {"filter": filter_expr, "per-page": per_page, "page": page}, records_by_parent[parent_id]

        payload = _STAGE3_SOURCES.expand_openalex_citations(
            query="汉代 灾异 诠释",
            seed_ids=["W123", "https://openalex.org/W456"],
            per_page=10,
            page=1,
            round_index=2,
            fetcher=fake_fetcher,
        )

        self.assertEqual(payload["provider"], "openalex-expand")
        self.assertEqual(payload["record_count"], 2)
        self.assertEqual(payload["params"]["seed_ids"], ["W123", "W456"])
        self.assertEqual(len(payload["fetches"]), 2)
        by_id = {item["openalex_id"]: item for item in payload["records"]}
        self.assertEqual(by_id["W900"]["parent_ids"], ["W123", "W456"])
        self.assertEqual(by_id["W900"]["discovered_round"], 2)
        self.assertEqual(by_id["W901"]["discovered_via"], "cited_by")
        self.assertEqual(payload["expand_mode"], "cited-by")

    def test_expand_openalex_references_fetches_seed_reference_lists(self) -> None:
        def fake_work_detail_fetcher(*, work_id: str, mailto: str = "", api_key: str = ""):
            referenced_by_seed = {
                "W123": {
                    "referenced_works": [
                        "https://openalex.org/W900",
                        "https://openalex.org/W901",
                    ]
                },
                "W456": {
                    "referenced_works": [
                        "https://openalex.org/W901",
                        "https://openalex.org/W902",
                    ]
                },
            }
            return referenced_by_seed[work_id]

        def fake_fetcher(
            *,
            query: str,
            per_page: int,
            page: int,
            filter_expr: str = "",
            mailto: str = "",
            api_key: str = "",
            sort: str = "",
        ):
            ids_expr = filter_expr.split("ids.openalex:", 1)[1].split(",", 1)[0]
            ids = ids_expr.split("|")
            records = {
                "W900": {
                    "source": "openalex",
                    "id": "https://openalex.org/W900",
                    "openalex_id": "W900",
                    "doi": "10.1/demo",
                    "title": "Han Ritual Commentary",
                    "year": 2020,
                    "type": "article",
                    "authors": ["Li Ming"],
                    "journal": "Journal A",
                    "abstract": "Demo",
                    "cited_by_count": 12,
                },
                "W901": {
                    "source": "openalex",
                    "id": "https://openalex.org/W901",
                    "openalex_id": "W901",
                    "doi": "10.1/demo-2",
                    "title": "Rain and Portents",
                    "year": 2019,
                    "type": "article",
                    "authors": ["Wang Hua"],
                    "journal": "Journal B",
                    "abstract": "Demo",
                    "cited_by_count": 8,
                },
                "W902": {
                    "source": "openalex",
                    "id": "https://openalex.org/W902",
                    "openalex_id": "W902",
                    "doi": "10.1/demo-3",
                    "title": "Portents in Han Thought",
                    "year": 2018,
                    "type": "article",
                    "authors": ["Zhang Wei"],
                    "journal": "Journal C",
                    "abstract": "Demo",
                    "cited_by_count": 6,
                },
            }
            return {"filter": filter_expr, "per-page": per_page, "page": page}, [records[item] for item in ids]

        payload = _STAGE3_SOURCES.expand_openalex_references(
            query="汉代 灾异 诠释",
            seed_ids=["W123", "https://openalex.org/W456"],
            per_page=10,
            page=1,
            round_index=2,
            fetcher=fake_fetcher,
            work_detail_fetcher=fake_work_detail_fetcher,
        )

        self.assertEqual(payload["provider"], "openalex-expand")
        self.assertEqual(payload["expand_mode"], "references")
        self.assertEqual(payload["record_count"], 3)
        self.assertEqual(payload["params"]["seed_ids"], ["W123", "W456"])
        by_id = {item["openalex_id"]: item for item in payload["records"]}
        self.assertEqual(by_id["W901"]["parent_ids"], ["W123", "W456"])
        self.assertEqual(by_id["W901"]["discovered_via"], "referenced_works")
        self.assertEqual(len(payload["fetches"]), 2)

if __name__ == "__main__":
    unittest.main()

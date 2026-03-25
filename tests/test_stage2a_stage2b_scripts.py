from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import sys
import tempfile
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


_STAGE2_SOURCES = _load_script_module("stage2a_sources.py", "test_ai_sinology_stage2a_sources")
_STAGE2_MAP = _load_script_module("stage2b_scholarship_map.py", "test_ai_sinology_stage2b_scholarship_map")


class Stage2ScriptsTests(unittest.TestCase):
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

        payload = _STAGE2_SOURCES.normalize_openalex_work(work)

        self.assertEqual(payload["doi"], "10.1234/demo")
        self.assertEqual(payload["authors"], ["Li Ming"])
        self.assertEqual(payload["abstract"], "Rain ritual")
        self.assertEqual(payload["openalex_id"], "W123")

    def test_render_yaml_includes_core_works_and_source_files(self) -> None:
        records = [
            {
                "source": "openalex",
                "doi": "10.1234/demo",
                "title": "Ritual and Rain",
                "year": 2024,
                "type": "article",
                "authors": ["Li Ming"],
                "journal": "Journal of Ritual Studies",
                "abstract": "Discusses how rain rituals were interpreted in Han texts.",
                "cited_by_count": 8,
            }
        ]

        payload = _STAGE2_MAP.render_yaml(
            research_question="汉代灾异与祈雨如何进入经学解释框架？",
            target_journals=["中国语文"],
            keywords=["ritual", "rain"],
            source_files=["openalex-demo.json"],
            records=records,
            period_hint="近十年为主，可回溯经典文献",
        )

        self.assertIn('research_question: "汉代灾异与祈雨如何进入经学解释框架？"', payload)
        self.assertIn('work: "Ritual and Rain"', payload)
        self.assertIn('source: "openalex"', payload)
        self.assertIn('    - "openalex-demo.json"', payload)

    def test_normalize_doaj_work_extracts_subjects_and_links(self) -> None:
        item = {
            "id": "abc",
            "bibjson": {
                "title": "A systematic synthesis and analysis of English-language Shuowen scholarship",
                "year": "2024",
                "author": [{"name": "Jane Doe"}],
                "journal": {"title": "Humanities & Social Sciences Communications"},
                "identifier": [{"type": "doi", "id": "10.1038/example"}],
                "link": [{"type": "fulltext", "url": "https://example.org/paper.pdf"}],
                "subject": [{"term": "Philology"}],
            },
        }

        payload = _STAGE2_SOURCES.normalize_doaj_work(item)

        self.assertEqual(payload["doi"], "10.1038/example")
        self.assertEqual(payload["authors"], ["Jane Doe"])
        self.assertEqual(payload["keywords"], ["Philology"])
        self.assertTrue(payload["pdf_url"].endswith(".pdf"))

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

        payload = _STAGE2_SOURCES.expand_openalex_citations(
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

    def test_build_map_cli_writes_project_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outputs = root / "outputs"
            project = outputs / "demo"
            project.mkdir(parents=True)
            (project / "1_research_proposal.md").write_text("汉代灾异与祈雨如何进入经学解释框架？\n", encoding="utf-8")
            (project / "1_journal_targeting.md").write_text("目标期刊：《中国语文》\n", encoding="utf-8")
            source_json = project / "_stage2a" / "openalex-demo.json"
            source_json.parent.mkdir(parents=True)
            source_json.write_text(
                '{"records":[{"source":"openalex","title":"Ritual and Rain","year":2024,"type":"article","authors":["Li Ming"],"abstract":"Discusses Han texts.","cited_by_count":8}]}',
                encoding="utf-8",
            )

            argv = [
                "stage2b_scholarship_map.py",
                "--project",
                "demo",
                "--outputs",
                str(outputs),
                "--source-json",
                str(source_json),
            ]
            previous = sys.argv
            try:
                sys.argv = argv
                exit_code = _STAGE2_MAP.main()
            finally:
                sys.argv = previous

            payload = (project / "2b_scholarship_map.yaml").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn('target_journals:', payload)
        self.assertIn('"中国语文"', payload)


if __name__ == "__main__":
    unittest.main()

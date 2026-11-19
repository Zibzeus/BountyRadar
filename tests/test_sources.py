import unittest
from unittest.mock import patch
from radar.sources import SourceError, parse_dataset, fetch_source


class DatasetTests(unittest.TestCase):
    def test_public_gate_precedes_extraction(self):
        source = "dataset:yeswehack"
        rows = [
            {"private_user": "personal"},
            {
                "id": "example",
                "name": "Example",
                "public": True,
                "targets": {
                    "in_scope": [{"target": "API v2 only", "type": "api"}],
                    "out_of_scope": [
                        {"target": "www.example.org", "type": "web-application"}
                    ],
                },
            },
        ]
        programs = parse_dataset(source, rows)
        self.assertEqual(len(programs), 1)
        self.assertEqual(programs[0]["scope"][0]["raw"], "API v2 only")
        self.assertEqual(programs[0]["scope"][1]["effect"], "exclude")
        self.assertEqual(programs[0]["status"], "unknown")
        self.assertIsNone(programs[0]["reward"])

    def test_directory_link_status_is_not_program_status(self):
        row = {
            "program_name": "Example",
            "policy_url": "https://example.org/policy",
            "policy_url_status": "alive",
            "offers_bounty": "no",
        }
        item = parse_dataset("dataset:diodb", [row])[0]
        self.assertEqual(item["status"], "unknown")
        self.assertEqual(item["kind"], "vdp")
        self.assertIsNone(item["scope"])

    def test_reparse_failure_does_not_advance_cache(self):
        validators = {"etag": "old"}
        with patch(
            "radar.sources._get", return_value=([], {"ETag": "new"}, "newhash")
        ) as transport:
            with self.assertRaises(SourceError):
                fetch_source("dataset:bugcrowd", cache=validators)
        self.assertEqual(transport.call_args.args[1]["If-None-Match"], "old")
        self.assertEqual(validators, {"etag": "old"})

    def test_identical_dummy_ids_are_distinct_programs(self):
        rows = [
            {
                "id": 0,
                "handle": handle,
                "name": handle,
                "url": "https://hackerone.com/" + handle,
                "targets": {"in_scope": [], "out_of_scope": []},
            }
            for handle in ["alpha", "bravo"]
        ]
        self.assertEqual(
            [i["external_id"] for i in parse_dataset("dataset:hackerone", rows)],
            ["alpha", "bravo"],
        )
        with self.assertRaises(SourceError):
            parse_dataset(
                "dataset:hackerone", rows + [{**rows[0], "name": "Conflicting policy"}]
            )
        self.assertEqual(len(parse_dataset("dataset:hackerone", rows + rows)), 2)

    def test_private_feeds_do_not_persist(self):
        with self.assertRaises(SourceError):
            parse_dataset(
                "dataset:intigriti", [{"confidentiality_level": "Registered"}]
            )

    def test_missing_scope_fails_extraction(self):
        with self.assertRaises(SourceError):
            parse_dataset(
                "dataset:yeswehack", [{"id": "known", "public": True, "name": "Known"}]
            )

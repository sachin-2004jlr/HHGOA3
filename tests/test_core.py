"""Fast unit tests (no network, no chain node):  python -m unittest -v"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from facechain import evidence as ev
from facechain.chain.simchain import SimChain
from facechain.search import Candidate, Verified, choose_match, classify_platform, guess_entity_name


class TestHashing(unittest.TestCase):
    def test_canonical_json_is_order_independent(self):
        a = {"b": 1, "a": {"y": [1, 2], "x": "z"}}
        b = {"a": {"x": "z", "y": [1, 2]}, "b": 1}
        self.assertEqual(ev.canonical_json(a), ev.canonical_json(b))
        self.assertEqual(ev.record_hash(a), ev.record_hash(b))

    def test_any_change_changes_hash(self):
        rec = {"match": {"post_url": "https://x.com/a/status/1"}, "v": 1}
        h1 = ev.record_hash(rec)
        rec["match"]["post_url"] += "?edited=1"
        self.assertNotEqual(h1, ev.record_hash(rec))

    def test_embedding_hash_stable(self):
        v = np.array([0.1234567, -0.5, 0.25], dtype=np.float32)
        self.assertEqual(ev.embedding_hash(v), ev.embedding_hash(v.astype(np.float64)))


class TestPlatform(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_platform("https://www.instagram.com/p/abc/"), "instagram")
        self.assertEqual(classify_platform("https://twitter.com/x/status/1"), "x")
        self.assertEqual(classify_platform("https://x.com/x/status/1"), "x")
        self.assertEqual(classify_platform("https://m.facebook.com/FoxNews/posts/1"), "facebook")
        self.assertEqual(classify_platform("https://youtu.be/abc"), "youtube")
        self.assertEqual(classify_platform("https://example.org/article"), "web")

    def test_choose_match_prefers_social_above_threshold(self):
        web = Verified(Candidate("https://news.example/a"), 0.95, 1, "u")
        ig = Verified(Candidate("https://www.instagram.com/p/1/"), 0.70, 1, "u")
        low = Verified(Candidate("https://x.com/a/status/1"), 0.20, 1, "u")
        self.assertIs(choose_match([web, ig, low], 0.363), ig)
        self.assertIs(choose_match([web, low], 0.363), web)
        self.assertIsNone(choose_match([low], 0.363))

    def test_guess_entity_name(self):
        titles = ["Elon Musk on Instagram: post", "Why Elon Musk left", "Elon Musk trolls Facebook",
                  "Random Article Title"]
        self.assertEqual(guess_entity_name(titles), "Elon Musk")
        self.assertIsNone(guess_entity_name(["One Two", "Three Four"]))


class TestSimChain(unittest.TestCase):
    def test_anchor_lookup_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "chain.json"
            c = SimChain(p)
            rh = "ab" * 32
            c.anchor(record_hash=rh, image_hash="cd" * 32, face_hash="ef" * 32,
                     post_url="https://x.com/a/status/1", platform="x", similarity=0.9)
            self.assertIsNotNone(SimChain(p).get_record(rh))
            self.assertIsNone(SimChain(p).get_record("00" * 32))
            self.assertTrue(SimChain(p).validate()[0])
            blocks = json.loads(p.read_text())
            blocks[1]["records"][0]["post_url"] = "https://evil"
            p.write_text(json.dumps(blocks))
            ok, msg = SimChain(p).validate()
            self.assertFalse(ok)
            self.assertIn("hash mismatch", msg)


if __name__ == "__main__":
    unittest.main()

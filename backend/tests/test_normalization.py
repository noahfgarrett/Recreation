import unittest

from recreation_extractor.normalization import normalize_tag, score_text_similarity


class NormalizationTests(unittest.TestCase):
    def test_normalizes_common_tag_spacing(self):
        self.assertEqual(normalize_tag("pt 101a"), "PT-101A")

    def test_scores_similar_tags(self):
        self.assertGreater(score_text_similarity("P-101A", "P101-A"), 0.7)


if __name__ == "__main__":
    unittest.main()

import unittest
from lab_evaluators import citation_validity


class CitationValidityTests(unittest.TestCase):
    def test_citation_cases(self):
        inputs = {
            "evidence": [
                {"latest_readings": [
                    {"sample_id": "TEL-PAY-ACTIVE-011"}
                ]},
                {
                    "component_id": "AS-PAYMENT-GATEWAY",
                    "availability": "UNKNOWN",
                    "latest_readings": [],
                },
            ]
        }

        cases = [
            ("valid",
             "98 connections [TEL-PAY-ACTIVE-011].", True),
            ("invented",
             "[TEL-PAY-FAKE-999].", False),
            ("mixed",
             "[TEL-PAY-ACTIVE-011] and [LAB-PAY-FAKE-999].", False),
            ("missing",
             "High active connections.", False),
            ("unsupported_conclusion_valid_citation",
             "Restart immediately [TEL-PAY-ACTIVE-011].", True),
            ("component_mislabeled_as_sample",
             "[TEL-PAY-ACTIVE-011]. Gateway unknown "
             "(sample_id: AS-PAYMENT-GATEWAY).", False),
            ("component_correctly_labeled",
             "[TEL-PAY-ACTIVE-011]. No readings for "
             "component AS-PAYMENT-GATEWAY.", True),
            ("formatted_invalid_label",
             "**Sample ID**: `AS-PAYMENT-GATEWAY`", False),
        ]

        for name, brief, expected in cases:
            with self.subTest(case=name):
                result = citation_validity(inputs, {"brief": brief})
                self.assertEqual(result["score"], expected, result)


if __name__ == "__main__":
    unittest.main(verbosity=2)

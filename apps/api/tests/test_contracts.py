import unittest

from app.deepseek import parse_usage
from app.runtime import parse_route


class ContractTests(unittest.TestCase):
    def test_usage_complete(self):
        usage = parse_usage(
            {
                "prompt_cache_miss_tokens": 10,
                "prompt_cache_hit_tokens": 2,
                "prompt_tokens": 12,
                "completion_tokens": 4,
            },
            "deepseek-v4-flash",
        )
        self.assertEqual(usage["usage_status"], "COMPLETE")
        self.assertIsNotNone(usage["estimated_cost"])
        self.assertEqual(usage["price_snapshot"]["currency"], "CNY")
        self.assertEqual(
            usage["price_snapshot"]["exchange_rate_snapshot"]["quote"], "CNY"
        )

    def test_usage_missing_is_not_fabricated(self):
        usage = parse_usage({"prompt_tokens": 12}, "deepseek-v4-flash")
        self.assertEqual(usage["usage_status"], "INCOMPLETE")
        self.assertIsNone(usage["prompt_cache_miss_tokens"])
        self.assertIsNone(usage["prompt_cache_hit_tokens"])
        self.assertIsNone(usage["completion_tokens"])
        self.assertIsNone(usage["estimated_cost"])

    def test_router_rejects_multiple_agents(self):
        with self.assertRaises(ValueError):
            parse_route(
                '{"target_agent":["general-service","complaint-service"],'
                '"confidence":0.8,"reason":"bad"}'
            )


if __name__ == "__main__":
    unittest.main()

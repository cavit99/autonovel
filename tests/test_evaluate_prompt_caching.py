import unittest

import evaluate


class EvaluatePromptCachingTests(unittest.TestCase):
    def test_build_judge_payload_uses_automatic_cache_for_plain_prompts(self):
        payload = evaluate.build_judge_payload(prompt="judge this", max_tokens=123)

        self.assertEqual(payload["cache_control"], {"type": "ephemeral", "ttl": "5m"})
        self.assertEqual(payload["messages"], [{"role": "user", "content": "judge this"}])

    def test_build_chapter_judge_message_content_caches_planning_prefix(self):
        content = evaluate.build_chapter_judge_message_content(
            perspective="Perspective",
            voice="Voice",
            characters="Characters",
            character_engine="Engine",
            world="World",
            canon="Canon",
            thread_registry="Threads",
            chapter_reference="Chapter card",
            prev_chapter_tail="Previous tail",
            chapter_text="Chapter text",
            include_risk=True,
        )

        self.assertEqual(len(content), 2)
        self.assertEqual(content[0]["cache_control"], {"type": "ephemeral", "ttl": "5m"})
        self.assertNotIn("cache_control", content[1])
        self.assertIn("THREAD REGISTRY WINDOW:", content[0]["text"])
        self.assertIn("CHAPTER TO EVALUATE:", content[1]["text"])


if __name__ == "__main__":
    unittest.main()

import unittest

from foundation_mind import (
    PERSPECTIVE_SECTIONS,
    VOICE_PART2_HEADING,
    extract_json_object,
    normalize_character_engine,
    render_perspective_markdown,
    replace_voice_part2,
)


class FoundationMindTests(unittest.TestCase):
    def test_render_perspective_markdown_contains_all_sections(self):
        markdown = render_perspective_markdown(
            {
                "obsessions": ["sound before sight"],
                "blind_spots": ["underestimates affection"],
                "sense_of_humor": ["pomposity that collapses under detail"],
                "the_unbearable": ["institutional cruelty"],
                "self_awareness": "The narration revises itself when it gets too sure.",
                "formal_signatures": ["bureaucracy -> flatter diction"],
            }
        )

        for section in PERSPECTIVE_SECTIONS:
            self.assertIn(f"## {section}", markdown)

    def test_normalize_character_engine_fills_required_fields(self):
        engine = normalize_character_engine(
            {
                "Cass": {
                    "wound": "His brother was taken.",
                    "cognitive_ceiling": {"abstraction_level": "HIGH"},
                }
            }
        )

        cass = engine["Cass"]
        self.assertEqual(cass["wound"], "His brother was taken.")
        self.assertEqual(cass["cognitive_ceiling"]["abstraction_level"], "high")
        self.assertIn("reasoning_style", cass["cognitive_ceiling"])
        self.assertIn("failure_mode", cass["cognitive_ceiling"])
        self.assertIn("speech_sample", cass)

    def test_replace_voice_part2_preserves_part1(self):
        original = (
            "# Voice Profile\n\n"
            "## Part 1: Guardrails (permanent, all novels)\n"
            "Guardrails stay.\n\n"
            f"{VOICE_PART2_HEADING}\n"
            "Old body.\n"
        )
        updated = replace_voice_part2(original, "### Tone\nNew body.")

        self.assertIn("Guardrails stay.", updated)
        self.assertIn("### Tone\nNew body.", updated)
        self.assertNotIn("Old body.", updated)

    def test_extract_json_object_handles_fenced_payload(self):
        payload = """```json
        {"tone": "warm"}
        ```"""
        self.assertEqual(extract_json_object(payload), {"tone": "warm"})


if __name__ == "__main__":
    unittest.main()

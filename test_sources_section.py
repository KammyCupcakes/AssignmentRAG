import unittest
from unittest.mock import Mock


class SourcesSectionTests(unittest.TestCase):
    def test_web_url_source_is_shown(self):
        from prompt import format_sources_section

        section = format_sources_section(
            [
                {
                    "document_name": "UMass Boston Transportation",
                    "source": "https://www.umb.edu/transportation",
                    "chunk_index": 2,
                }
            ]
        )

        self.assertIn("Sources:", section)
        self.assertIn(
            "1. UMass Boston Transportation \u2014 https://www.umb.edu/transportation",
            section,
        )

    def test_local_pdf_source_is_skipped(self):
        from prompt import format_sources_section

        section = format_sources_section(
            [
                {
                    "document_name": "Parking Rates.pdf",
                    "source": "data/Parking Rates.pdf",
                    "chunk_index": 3,
                }
            ]
        )

        self.assertEqual(section, "")

    def test_mixed_sources_include_only_web_urls(self):
        from prompt import format_sources_section

        section = format_sources_section(
            [
                {
                    "document_name": "UMass Boston Transportation",
                    "source": "https://www.umb.edu/transportation",
                    "chunk_index": 2,
                },
                {
                    "document_name": "Parking Rates.pdf",
                    "source": "data/Parking Rates.pdf",
                    "chunk_index": 3,
                },
            ]
        )

        self.assertIn("https://www.umb.edu/transportation", section)
        self.assertNotIn("Parking Rates.pdf", section)
        self.assertNotIn("data/Parking Rates.pdf", section)

    def test_empty_sources_produce_no_section(self):
        from prompt import format_sources_section

        self.assertEqual(format_sources_section([]), "")

    def test_route_response_does_not_get_sources(self):
        from prompt import append_sources_section

        response = "Route found: University Hall \u2192 Quinn Administration Building"
        updated = append_sources_section(
            response,
            [
                {
                    "document_name": "UMass Boston Transportation",
                    "source": "https://www.umb.edu/transportation",
                }
            ],
        )

        self.assertEqual(updated, response)
        self.assertNotIn("Sources:", updated)

    def test_inline_source_marker_is_stripped(self):
        from prompt import strip_unsupported_citation_markers

        marker = "\u30104\u2020source\u3011"
        response = strip_unsupported_citation_markers(
            f"Visitors can park in the campus garage.{marker}"
        )

        self.assertEqual(response, "Visitors can park in the campus garage.")
        self.assertNotIn(marker, response)

    def test_rag_answer_appends_only_web_sources_from_search_tool(self):
        import prompt

        original_client = prompt.client
        original_execute_tool_call = prompt.execute_tool_call
        original_messages_history = prompt.messages_history
        try:
            tool_call = Mock()
            tool_call.function.name = "search_documents"
            tool_call.function.arguments = '{"query": "parking"}'

            first_message = Mock(content=None, tool_calls=[tool_call])
            marker = "\u30104\u2020source\u3011"
            second_message = Mock(content=f"Visitors can park in the campus garage.{marker}")

            prompt.client = Mock()
            prompt.client.chat.completions.create.side_effect = [
                Mock(choices=[Mock(message=first_message)]),
                Mock(choices=[Mock(message=second_message)]),
            ]
            prompt.execute_tool_call = Mock(
                return_value={
                    "query": "parking",
                    "low_confidence": False,
                    "results": [
                        {
                            "rank": 1,
                            "document_name": "UMass Boston Transportation",
                            "source": "https://www.umb.edu/transportation",
                            "chunk_index": 2,
                            "text": "Visitors can park on campus.",
                        },
                        {
                            "rank": 2,
                            "document_name": "Parking Rates.pdf",
                            "source": "data/Parking Rates.pdf",
                            "chunk_index": 3,
                            "text": "Local parking rates PDF text.",
                        },
                    ],
                }
            )
            prompt.messages_history = [{"role": "system", "content": prompt.SYSTEM_PROMPT}]

            response = prompt.handle_query("What parking options are available?")

            self.assertIn("Visitors can park in the campus garage.", response)
            self.assertNotIn(marker, response)
            self.assertIn("Sources:", response)
            self.assertIn(
                "1. UMass Boston Transportation \u2014 https://www.umb.edu/transportation",
                response,
            )
            self.assertNotIn("Parking Rates.pdf", response)
            self.assertNotIn("data/Parking Rates.pdf", response)
        finally:
            prompt.client = original_client
            prompt.execute_tool_call = original_execute_tool_call
            prompt.messages_history = original_messages_history


if __name__ == "__main__":
    unittest.main()

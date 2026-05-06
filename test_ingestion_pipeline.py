import unittest


class IngestionPipelineCleanupTests(unittest.TestCase):
    def test_clean_extracted_text_removes_repeated_footer_and_page_chrome(self):
        from ingestion_pipeline import clean_extracted_text

        raw_text = """
--- Page 1 ---
Home — Registrar
Menu menu
The Registrar's Office is on the 4th Floor of Campus Center.
100 Morrissey Blvd.
Contact UMass Boston

--- Page 2 ---
Home — Registrar
Menu menu
Registrar email: registrar@umb.edu
100 Morrissey Blvd.
Back To Top
"""

        cleaned = clean_extracted_text(raw_text)

        self.assertIn("The Registrar's Office is on the 4th Floor of Campus Center.", cleaned)
        self.assertIn("Registrar email: registrar@umb.edu", cleaned)
        self.assertNotIn("Home — Registrar", cleaned)
        self.assertNotIn("Menu menu", cleaned)
        self.assertNotIn("Contact UMass Boston", cleaned)
        self.assertNotIn("Back To Top", cleaned)
        self.assertNotIn("--- Page 1 ---", cleaned)
        self.assertNotIn("100 Morrissey Blvd.", cleaned)

    def test_clean_extracted_text_keeps_single_useful_address_line(self):
        from ingestion_pipeline import clean_extracted_text

        raw_text = """
Registrar's Office
Campus Center, 4th Floor
100 Morrissey Boulevard
registrar@umb.edu
"""

        cleaned = clean_extracted_text(raw_text)

        self.assertIn("Campus Center, 4th Floor", cleaned)
        self.assertIn("100 Morrissey Boulevard", cleaned)
        self.assertIn("registrar@umb.edu", cleaned)


if __name__ == "__main__":
    unittest.main()
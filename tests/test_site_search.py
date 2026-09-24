"""Tests for the no-site verification decision logic.

Network and model calls are not exercised here - only the pure function that
turns two model verdicts and a set of search results into a decision. See
modules/site_search.py for what each piece means.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import site_search as ss


LEAD = {"id": 1, "name": "Studio Dentistico Rossi", "city": "Bergamo",
        "category": "dentisti", "phone": "035 1234567", "whatsapp": "393331112222"}


def result(url, title="", snippet=""):
    return {"title": title, "url": url, "snippet": snippet}


class DomainTest(unittest.TestCase):
    def test_strips_scheme_and_www(self):
        self.assertEqual(ss.domain_of("https://www.example.it/foo"), "example.it")
        self.assertEqual(ss.domain_of("http://example.it"), "example.it")

    def test_directory_domains_are_flagged(self):
        self.assertTrue(ss.is_directory("https://www.facebook.com/studiorossi"))
        self.assertTrue(ss.is_directory("https://www.miodottore.it/rossi"))
        self.assertTrue(ss.is_directory("https://maps.google.com/?q=rossi"))

    def test_real_site_is_not_flagged(self):
        self.assertFalse(ss.is_directory("https://studiorossi.it"))


class ValidOwnSiteTest(unittest.TestCase):
    def test_none_when_no_url(self):
        self.assertIsNone(ss.valid_own_site(None, []))

    def test_none_when_url_not_among_results(self):
        results = [result("https://other.it")]
        self.assertIsNone(ss.valid_own_site("https://studiorossi.it", results))

    def test_none_when_url_is_a_directory(self):
        results = [result("https://www.facebook.com/studiorossi")]
        self.assertIsNone(ss.valid_own_site("https://www.facebook.com/studiorossi", results))

    def test_accepted_when_real_and_present_in_results(self):
        results = [result("https://studiorossi.it")]
        self.assertEqual(ss.valid_own_site("https://studiorossi.it", results), "https://studiorossi.it")


class RelevantResultsTest(unittest.TestCase):
    def test_matches_on_name_token(self):
        results = [result("https://x.it", title="Studio Rossi dentista a Bergamo"),
                  result("https://y.it", title="Ristoranti a Bergamo")]
        self.assertEqual(len(ss.relevant_results(LEAD, results)), 1)

    def test_matches_on_phone_digits_regardless_of_formatting(self):
        results = [result("https://x.it", snippet="Chiamaci al 035-123-4567 per un appuntamento")]
        self.assertEqual(len(ss.relevant_results(LEAD, results)), 1)

    def test_generic_result_does_not_count(self):
        results = [result("https://x.it", title="Guida ai dentisti in Lombardia")]
        self.assertEqual(len(ss.relevant_results(LEAD, results)), 0)


class DecideTest(unittest.TestCase):
    def test_found_site_from_model_a(self):
        results = [result("https://studiorossi.it")]
        verdict_a = {"has_own_site": True, "url": "https://studiorossi.it"}
        verdict_b = {"has_own_site": False, "url": None}
        action, detail = ss.decide(LEAD, results, verdict_a, verdict_b)
        self.assertEqual((action, detail), ("found_site", "https://studiorossi.it"))

    def test_found_site_from_model_b(self):
        results = [result("https://studiorossi.it")]
        verdict_a = {"has_own_site": False, "url": None}
        verdict_b = {"has_own_site": True, "url": "https://studiorossi.it"}
        action, detail = ss.decide(LEAD, results, verdict_a, verdict_b)
        self.assertEqual(action, "found_site")

    def test_hallucinated_url_is_not_a_found_site(self):
        # The model claims a site, but the URL never appeared in the search
        # results - it must not be trusted.
        results = [result("https://someone-else.it")]
        verdict_a = {"has_own_site": True, "url": "https://studiorossi.it"}
        verdict_b = {"has_own_site": False, "url": None}
        action, detail = ss.decide(LEAD, results, verdict_a, verdict_b)
        self.assertNotEqual(action, "found_site")

    def test_directory_citation_is_not_a_found_site(self):
        results = [result("https://www.facebook.com/studiorossi")]
        verdict_a = {"has_own_site": True, "url": "https://www.facebook.com/studiorossi"}
        verdict_b = {"has_own_site": False, "url": None}
        action, detail = ss.decide(LEAD, results, verdict_a, verdict_b)
        self.assertNotEqual(action, "found_site")

    def test_no_site_confirmed_needs_both_models_and_enough_evidence(self):
        results = [result(f"https://x{i}.it", title="Studio Rossi dentista Bergamo")
                  for i in range(4)]
        verdict_a = {"has_own_site": False, "url": None}
        verdict_b = {"has_own_site": False, "url": None}
        action, detail = ss.decide(LEAD, results, verdict_a, verdict_b)
        self.assertEqual(action, "no_site_confirmed")

    def test_too_few_relevant_results_is_inconclusive_even_if_both_agree(self):
        results = [result("https://x1.it", title="Studio Rossi dentista Bergamo"),
                  result("https://x2.it", title="pagine gialle generiche")]
        verdict_a = {"has_own_site": False, "url": None}
        verdict_b = {"has_own_site": False, "url": None}
        action, detail = ss.decide(LEAD, results, verdict_a, verdict_b)
        self.assertEqual(action, "inconclusive")

    def test_disagreement_is_inconclusive(self):
        results = [result(f"https://x{i}.it", title="Studio Rossi dentista Bergamo")
                  for i in range(5)]
        verdict_a = {"has_own_site": False, "url": None}
        verdict_b = {"has_own_site": True, "url": None}  # claims a site but cites nothing
        action, detail = ss.decide(LEAD, results, verdict_a, verdict_b)
        self.assertEqual(action, "inconclusive")

    def test_unparseable_verdict_defaults_to_none_and_is_inconclusive(self):
        results = []
        verdict_a = {"has_own_site": None, "url": None}
        verdict_b = {"has_own_site": None, "url": None}
        action, detail = ss.decide(LEAD, results, verdict_a, verdict_b)
        self.assertEqual(action, "inconclusive")


class ParseVerdictTest(unittest.TestCase):
    def test_parses_json_even_with_surrounding_prose(self):
        text = 'Sure, here you go:\n{"has_own_site": false, "url": null, "reason": "no site"}\nDone.'
        verdict = ss._parse_verdict(text)
        self.assertEqual(verdict, {"has_own_site": False, "url": None})

    def test_raises_when_no_json_object(self):
        with self.assertRaises(ValueError):
            ss._parse_verdict("no json here")


class CandidatesTest(unittest.TestCase):
    """candidates() needs a real (temp) database, unlike the rest of this
    file - it is the one part of this module that talks to modules.leads."""

    def setUp(self):
        import tempfile
        self.db = tempfile.mktemp(suffix=".db")
        os.environ["LEADS_DB"] = self.db
        for module in [m for m in list(sys.modules) if m.startswith("modules.")]:
            del sys.modules[module]
        global ss
        from modules import site_search as ss
        from modules import leads
        self.leads = leads
        leads.DB_PATH = self.db
        leads._schema_ready = False

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_only_new_mobile_leads_with_a_bare_no_website_finding_qualify(self):
        a = self.leads.add_lead("Con Mobile Solo Guess", city="Como", whatsapp="393331112222")
        self.leads.save_scan(a, [{"code": "no_website", "severity": 1, "detail": ""}], None)

        b = self.leads.add_lead("Senza Mobile", city="Como", phone="031 123456")
        self.leads.save_scan(b, [{"code": "no_website", "severity": 1, "detail": ""}], None)

        c = self.leads.add_lead("Con Mobile Altro Problema", city="Como", whatsapp="393339998888")
        self.leads.save_scan(c, [{"code": "site_down", "severity": 5, "detail": ""}], None)

        ids = [l["id"] for l in ss.candidates()]
        self.assertEqual(ids, [a])

    def test_already_checked_leads_are_skipped(self):
        a = self.leads.add_lead("Gia Controllato", city="Como", whatsapp="393331112222")
        self.leads.save_scan(a, [{"code": "no_website", "severity": 1, "detail": ""}], None)
        self.leads.log_event(a, "site_search", "inconclusive: test")
        self.assertEqual(ss.candidates(), [])


if __name__ == "__main__":
    unittest.main()

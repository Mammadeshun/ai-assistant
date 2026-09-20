"""Tests for the lead pipeline.

Standard library only, so they run in the service's own venv with nothing
extra installed:

    python -m unittest discover -s tests -v
"""

import os
import sys
import datetime
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class LeadStoreTest(unittest.TestCase):
    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")
        os.environ["LEADS_DB"] = self.db
        for module in [m for m in list(sys.modules) if m.startswith("modules.")]:
            del sys.modules[module]
        from modules import leads
        self.leads = leads
        leads.DB_PATH = self.db
        leads._schema_ready = False

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def _age(self, lead_id, days):
        """Pretend a lead has been sitting in its state for a while."""
        old = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
        with self.leads.connect() as conn:
            conn.execute("UPDATE leads SET state_changed_at = ? WHERE id = ?", (old, lead_id))

    def test_duplicates_are_rejected_including_when_city_is_missing(self):
        self.assertIsNotNone(self.leads.add_lead("Studio Rossi", city="Milano"))
        self.assertIsNone(self.leads.add_lead("Studio Rossi", city="Milano"))
        self.assertIsNotNone(self.leads.add_lead("Senza Citta"))
        self.assertIsNone(self.leads.add_lead("Senza Citta"),
                          "NULL city must not create a second copy")

    def test_new_lead_goes_to_whatsapp_only_with_a_mobile(self):
        mobile = self.leads.add_lead("Con Mobile", city="Milano", whatsapp="393331112222")
        landline = self.leads.add_lead("Solo Fisso", city="Milano", phone="02 1234567")
        due = self.leads.due_leads()
        self.assertEqual([l["id"] for l in due["to_whatsapp"]], [mobile])
        self.assertEqual([l["id"] for l in due["to_email"]], [landline])

    def test_cascade_escalates_only_after_the_wait(self):
        lead = self.leads.add_lead("Studio Alfa", city="Milano", whatsapp="393331112222")
        self.leads.set_state(lead, "WHATSAPP_SENT")
        self.assertEqual(self.leads.due_leads()["to_email"], [],
                         "must not escalate on the same day")
        self._age(lead, self.leads.WHATSAPP_WAIT_DAYS)
        self.assertEqual([l["id"] for l in self.leads.due_leads()["to_email"]], [lead])

    def test_advance_overdue_sets_call_due(self):
        lead = self.leads.add_lead("Studio Beta", city="Milano", email="b@example.invalid")
        self.leads.set_state(lead, "EMAIL_SENT")
        self.assertEqual(self.leads.advance_overdue(), [])
        self._age(lead, self.leads.EMAIL_WAIT_DAYS)
        self.assertEqual(self.leads.advance_overdue(), [lead])
        self.assertEqual(self.leads.get(lead)["state"], "CALL_DUE")

    def test_scanned_lead_with_no_findings_is_not_queued_for_sending(self):
        lead = self.leads.add_lead("Sito Perfetto", city="Milano", whatsapp="393331112222")
        self.leads.save_scan(lead, [], draft=None)
        due = self.leads.due_leads()
        self.assertEqual(due["to_whatsapp"], [])
        self.assertEqual([l["id"] for l in due["no_angle"]], [lead])

    def test_one_follow_up_then_the_lead_goes_quiet(self):
        lead = self.leads.add_lead("Studio Gamma", city="Milano")
        self.leads.set_state(lead, "CONTACTED")
        self._age(lead, self.leads.FOLLOW_UP_DAYS)
        self.assertEqual([l["id"] for l in self.leads.due_leads()["to_follow_up"]], [lead])
        self.leads.mark_followed_up(lead)
        self._age(lead, self.leads.FOLLOW_UP_DAYS)
        self.assertEqual(self.leads.due_leads()["to_follow_up"], [],
                         "a lead must not be chased twice")

    def test_notes_and_events_accumulate(self):
        lead = self.leads.add_lead("Studio Delta", city="Milano")
        self.leads.add_note(lead, "richiamare giovedì")
        self.leads.add_note(lead, "parlato con la segretaria")
        self.assertIn("richiamare giovedì", self.leads.get(lead)["notes"])
        with self.leads.connect() as conn:
            events = conn.execute("SELECT kind FROM events WHERE lead_id = ?", (lead,)).fetchall()
        self.assertIn("note", [e["kind"] for e in events])

    def test_connections_do_not_leak(self):
        self.leads.add_lead("Studio Epsilon", city="Milano")
        for _ in range(100):
            self.leads.counts()
        open_handles = 0
        for fd in os.listdir("/proc/self/fd"):
            try:
                if self.db in os.readlink(f"/proc/self/fd/{fd}"):
                    open_handles += 1
            except OSError:
                pass
        self.assertEqual(open_handles, 0, "connect() must close what it opens")

    def test_settings_round_trip(self):
        self.assertEqual(self.leads.get_setting("signature", "none"), "none")
        self.leads.set_setting("signature", "Mohammad - Pavia")
        self.assertEqual(self.leads.get_setting("signature"), "Mohammad - Pavia")
        self.leads.set_setting("signature", "aggiornata")
        self.assertEqual(self.leads.get_setting("signature"), "aggiornata")


class PhoneNumberTest(unittest.TestCase):
    def setUp(self):
        os.environ["LEADS_DB"] = tempfile.mktemp(suffix=".db")
        from modules.commands import mobile_number
        self.mobile_number = mobile_number

    def test_only_italian_mobiles_get_a_whatsapp_link(self):
        self.assertEqual(self.mobile_number("+39 333 111 2222"), "393331112222")
        self.assertEqual(self.mobile_number("0039 347 1234567"), "393471234567")
        self.assertEqual(self.mobile_number("3391112222"), "393391112222")
        # Landlines have no WhatsApp; a wa.me link to one fails after the tap.
        self.assertIsNone(self.mobile_number("+39 02 7654321"))
        self.assertIsNone(self.mobile_number("0382 123456"))
        self.assertIsNone(self.mobile_number("+44 20 1234 5678"))
        self.assertIsNone(self.mobile_number(""))
        self.assertIsNone(self.mobile_number(None))


class ScannerTest(unittest.TestCase):
    def setUp(self):
        from modules import scanner
        self.scanner = scanner

    def test_missing_website_is_itself_a_finding(self):
        self.assertEqual([f["code"] for f in self.scanner.check_site(None)], ["no_website"])

    def test_findings_are_deduplicated_and_ranked(self):
        raw = [self.scanner._finding("slow", "5s"),
               self.scanner._finding("ssl_expired", "a"),
               self.scanner._finding("ssl_expired", "b")]
        deduped = self.scanner._dedupe(raw)
        self.assertEqual([f["code"] for f in deduped], ["slow", "ssl_expired"])
        self.assertGreater(self.scanner.score([self.scanner._finding("ssl_expired", "")]),
                           self.scanner.score([self.scanner._finding("slow", "")]))


class OutreachTest(unittest.TestCase):
    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")
        os.environ["LEADS_DB"] = self.db
        os.environ.pop("OUTREACH_SIGNATURE", None)
        for module in [m for m in list(sys.modules) if m.startswith("modules.")]:
            del sys.modules[module]
        from modules import outreach, leads
        self.outreach, self.leads = outreach, leads
        leads.DB_PATH = self.db
        leads._schema_ready = False

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_weak_findings_stay_out_of_the_opener(self):
        findings = [self.outreach.PROBLEM_IT and {"code": "not_mobile", "severity": 4, "detail": ""},
                    {"code": "no_english", "severity": 1, "detail": ""}]
        described = self.outreach.describe(findings)
        self.assertIn("cellulare", described)
        self.assertNotIn("italiano", described,
                         "severity-1 noise must not pad a real problem")

    def test_whatsapp_link_encodes_the_message(self):
        link = self.outreach.whatsapp_link({"whatsapp": "393331112222"}, "ciao, come va?")
        self.assertTrue(link.startswith("https://wa.me/393331112222?text="))
        self.assertIn("%20", link)
        self.assertIsNone(self.outreach.whatsapp_link({"whatsapp": None}, "x"))

    def test_unsigned_email_is_refused(self):
        with self.assertRaises(RuntimeError) as caught:
            self.outreach.send_email({"id": 1, "name": "x", "email": "a@b.invalid"}, "s", "b")
        self.assertIn("firma", str(caught.exception))

    def test_footer_carries_identification_and_opt_out(self):
        self.leads.set_setting("signature", "Mohammad - Pavia")
        footer = self.outreach.email_footer()
        self.assertIn("Mohammad", footer)
        self.assertIn("non la contatterò più", footer)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class RouterSafetyTest(unittest.TestCase):
    """The split that keeps a misread sentence from sending an email."""

    def setUp(self):
        os.environ["LEADS_DB"] = tempfile.mktemp(suffix=".db")
        from modules import commands
        self.commands = commands

    def test_read_only_commands_are_auto_runnable(self):
        for name in ("status", "leads", "lead", "digest", "draft", "wa", "logs"):
            self.assertIn(name, self.commands.SAFE, f"/{name} only reads")

    def test_consequential_commands_need_a_human(self):
        for name in ("email", "restart", "dead", "contacted", "interested",
                     "sent", "scan", "import", "add", "signature", "note"):
            self.assertNotIn(name, self.commands.SAFE,
                             f"/{name} changes something and must be confirmed")

    def test_every_catalogue_entry_is_a_real_command_or_job(self):
        jobs = {"morning_routine", "kiro_check"}
        for entry, _ in self.commands.CATALOGUE:
            name = entry.split()[0].lstrip("/")
            self.assertTrue(name in jobs or f"/{name}" in self.commands.__doc__,
                            f"{entry} is advertised but not documented as a command")

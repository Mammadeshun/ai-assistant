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
        # A landline with no email address is a phone call: it used to be
        # queued for an email that could never be sent.
        self.assertEqual([l["id"] for l in due["to_call"]], [landline])
        self.assertEqual(due["to_email"], [])

    def test_cascade_escalates_only_after_the_wait(self):
        lead = self.leads.add_lead("Studio Alfa", city="Milano", whatsapp="393331112222",
                                   email="studio@alfa.it")
        self.leads.set_state(lead, "WHATSAPP_SENT")
        self.assertEqual(self.leads.due_leads()["to_email"], [],
                         "must not escalate on the same day")
        self._age(lead, self.leads.WHATSAPP_WAIT_DAYS)
        self.assertEqual([l["id"] for l in self.leads.due_leads()["to_email"]], [lead])

    def test_no_email_address_skips_straight_to_a_call(self):
        lead = self.leads.add_lead("Studio Beta", city="Milano", whatsapp="393331112222",
                                   phone="02 1234 5678")
        self.leads.set_state(lead, "WHATSAPP_SENT")
        self._age(lead, self.leads.WHATSAPP_WAIT_DAYS)
        due = self.leads.due_leads()
        self.assertEqual(due["to_email"], [], "no address to write to")
        self.assertEqual([l["id"] for l in due["to_call"]], [lead])

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



class WhatsAppFirstTest(unittest.TestCase):
    """Messages before calls, one clean message each, and a daily cap."""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")
        os.environ["LEADS_DB"] = self.db
        # The package too, not just its submodules: `from modules import x`
        # returns the attribute cached on the package, so without this the
        # skipped set and the cap another test changed would carry over.
        for module in [m for m in list(sys.modules) if m == "modules" or m.startswith("modules.")]:
            del sys.modules[module]
        from modules import leads, outreach, callmode, webapp
        self.leads, self.outreach, self.callmode, self.webapp = leads, outreach, callmode, webapp
        leads.DB_PATH = self.db
        leads._schema_ready = False

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)
        # Drop what these tests patched (send_email, the caps) so the next
        # class imports clean modules.
        for module in [m for m in list(sys.modules) if m == "modules" or m.startswith("modules.")]:
            del sys.modules[module]

    def _lead(self, name, code="not_mobile", severity=4, category="dentisti", whatsapp="393331112222",
              website="https://www.studiouno.it"):
        lead = self.leads.add_lead(name, category=category, city="Milano", website=website,
                                   phone="02 1234 5678", whatsapp=whatsapp, source=f"osm:node/{name}")
        self.assertIsNotNone(lead, "the store took it for a duplicate")
        self.leads.save_scan(lead, [{"code": code, "severity": severity, "detail": ""}], "bozza email")
        return lead

    def test_message_says_who_where_and_one_problem_with_one_soft_extra(self):
        lead = self.leads.get(self._lead("Studio Uno"))
        findings = [{"code": "not_mobile", "severity": 4, "detail": ""},
                    {"code": "slow", "severity": 2, "detail": ""}]
        msg = self.outreach.whatsapp_message(lead, findings, hour=10)
        self.assertTrue(msg.startswith("Buongiorno"))
        self.assertIn("Momo", msg)
        self.assertIn("studiouno.it", msg, "the site is named so the claim can be checked")
        self.assertIn("OpenStreetMap", msg, "says where the number came from")
        self.assertIn("non ricevere altri messaggi", msg, "says how to make it stop")
        self.assertNotIn("secondi", msg, "one problem only, not an audit")
        self.assertEqual(msg.count("?"), 1, "one question")
        self.assertEqual(msg.count("promemoria"), 1, "one extra offer")
        self.assertNotIn("www.", msg)

    def test_extra_offer_fits_the_trade_or_is_left_out(self):
        self.assertIn("pazienti", self.outreach.extra_offer({"category": "dentisti"}))
        self.assertIn("clienti", self.outreach.extra_offer({"category": "veterinari"}))
        self.assertIn("documenti", self.outreach.extra_offer({"category": "avvocati"}))
        self.assertIsNone(self.outreach.extra_offer({"category": "ristoranti"}))
        lead = self.leads.get(self._lead("Trattoria", category="ristoranti"))
        msg = self.outreach.whatsapp_message(lead, self.leads.findings_of(lead), hour=10)
        self.assertEqual(len(msg.split("\n\n")), 3, "intro, problem + question, source")

    def test_no_message_without_a_real_problem_and_evening_greeting(self):
        lead = self.leads.get(self._lead("Studio Due"))
        self.assertIsNone(self.outreach.whatsapp_message(lead, []))
        self.assertIsNone(self.outreach.whatsapp_message(
            lead, [{"code": "no_english", "severity": 1, "detail": ""}]))
        msg = self.outreach.whatsapp_message(lead, self.leads.findings_of(lead), hour=18)
        self.assertTrue(msg.startswith("Buonasera"))

    def test_today_serves_messages_before_calls_up_to_the_cap(self):
        wa = self._lead("Da scrivere")
        call = self._lead("Da chiamare", code="site_down", severity=5, whatsapp=None)
        nxt = self.webapp.today()["next"]
        self.assertEqual((nxt["id"], nxt["channel"]), (wa, "whatsapp"),
                         "a message comes first even when a call has the worse problem")
        self.assertTrue(nxt["wa_app"].startswith("whatsapp://send?phone=393331112222&text="))
        self.assertIn("Momo", nxt["message"])

        self.callmode.apply(wa, "wa_sent", "whatsapp")
        self.assertEqual(self.leads.get(wa)["state"], "WHATSAPP_SENT")
        t = self.webapp.today()
        self.assertEqual((t["messages"], t["calls"], t["done"]), (1, 0, 1))
        self.assertEqual((t["next"]["id"], t["next"]["channel"]), (call, "call"))

        self.outreach.MAX_WHATSAPP_PER_DAY = 1
        self._lead("Oltre il limite", whatsapp="393339998888")
        self.assertEqual(self.webapp.today()["next"]["channel"], "call",
                         "past the daily cap no new WhatsApp contact is offered")

    def test_a_whatsapp_reply_is_not_counted_as_a_call(self):
        wa = self._lead("Risponde")
        call = self._lead("Telefono", whatsapp=None)
        self.callmode.apply(wa, "hot", "whatsapp")
        self.assertEqual(self.webapp.calls_today(), 0)
        self.callmode.apply(call, "ok", "call")
        self.assertEqual(self.webapp.calls_today(), 1)

    def test_todo_list_is_messages_then_calls(self):
        self._lead("Chiamata forte", code="site_down", severity=5, whatsapp=None)
        self._lead("Messaggio", code="slow", severity=2)
        channels = [r["channel"] for r in self.webapp.leads_list("todo")]
        self.assertEqual(channels, ["whatsapp", "call"])


class EmailAndFollowUpTest(WhatsAppFirstTest):
    """Email as the second channel, sent only from what was on screen, once."""

    def setUp(self):
        super().setUp()
        self.sent = []
        self.outreach.send_email = lambda lead, subject, body: self.sent.append((lead["id"], subject, body)) or True
        self.leads.set_setting("signature", "Momo - siti e automazioni")

    def _email_lead(self, name="Studio Mail"):
        return self._lead(name, whatsapp=None)

    def _set_email(self, lead, address="studio@example.it"):
        with self.leads.connect() as conn:
            conn.execute("UPDATE leads SET email = ? WHERE id = ?", (address, lead))

    def test_email_body_is_the_same_opener_without_the_footer_lines(self):
        lead = self._email_lead(); self._set_email(lead)
        body = self.outreach.email_message(self.leads.get(lead), self.leads.findings_of(self.leads.get(lead)), hour=9)
        self.assertTrue(body.startswith("Buongiorno,\n\n"))
        self.assertIn("Momo", body)
        self.assertTrue(body.endswith("Un saluto,\nMomo"))
        self.assertNotIn("OpenStreetMap", body, "where-found and opt-out come from the footer")

    def test_channels_come_in_order_and_email_stops_at_its_cap(self):
        self._lead("Scrivere")
        mail = self._email_lead(); self._set_email(mail)
        self._lead("Chiamare", whatsapp=None)
        self.assertEqual([r["channel"] for r in self.webapp.leads_list("todo")],
                         ["whatsapp", "email", "call"])
        self.outreach.MAX_EMAIL_PER_DAY = 0
        self.assertEqual([r["channel"] for r in self.webapp.leads_list("todo")], ["whatsapp", "call"])
        self.assertTrue(self.webapp.lead_view(self.leads.get(mail), full=True)["email_capped"])

    def test_an_email_is_sent_once_with_the_text_shown(self):
        lead = self._email_lead(); self._set_email(lead)
        text = "Buongiorno, testo modificato a mano da Momo prima di inviarlo."
        status, payload = self.webapp.send_lead_email(lead, "Oggetto", text)
        self.assertEqual(status, 200)
        self.assertEqual(self.sent, [(lead, "Oggetto", text)], "sends exactly what was on screen")
        self.assertEqual(self.leads.get(lead)["state"], "EMAIL_SENT")
        self.assertEqual(payload["today"]["emails"], 1)
        status, _ = self.webapp.send_lead_email(lead, "Oggetto", text)
        self.assertEqual(status, 409, "a second tap must not send twice")
        self.assertEqual(len(self.sent), 1)

    def test_email_refused_without_address_text_or_under_the_cap(self):
        lead = self._email_lead()
        self.assertEqual(self.webapp.send_lead_email(lead, "Oggetto", "x" * 60)[0], 404)
        self._set_email(lead)
        self.assertEqual(self.webapp.send_lead_email(lead, "", "x" * 60)[0], 400)
        self.outreach.MAX_EMAIL_PER_DAY = 0
        self.assertEqual(self.webapp.send_lead_email(lead, "Oggetto", "x" * 60)[0], 429)
        self.assertEqual(self.sent, [])

    def test_whatsapp_cap_also_holds_in_the_lead_sheet(self):
        lead = self._lead("Nuovo")
        self.assertTrue(self.webapp.lead_view(self.leads.get(lead), full=True)["wa_app"])
        self.outreach.MAX_WHATSAPP_PER_DAY = 0
        view = self.webapp.lead_view(self.leads.get(lead), full=True)
        self.assertIsNone(view["wa_app"])
        self.assertTrue(view["wa_capped"])

    def test_owed_follow_up_is_listed_until_done(self):
        lead = self._lead("Sentito", whatsapp=None)
        self.leads.set_state(lead, "CONTACTED")
        self._age(lead, self.leads.FOLLOW_UP_DAYS)
        self.assertEqual([(r["id"], r["channel"]) for r in self.webapp.leads_list("todo")], [(lead, "follow")])
        self.callmode.apply(lead, "followed")
        self.assertEqual(self.webapp.leads_list("todo"), [])

    def _age(self, lead_id, days):
        old = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
        with self.leads.connect() as conn:
            conn.execute("UPDATE leads SET state_changed_at = ? WHERE id = ?", (old, lead_id))

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


class ChannelRoutingTest(unittest.TestCase):
    """Real data drove this: dentists publish landlines, not mobiles."""

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

    def test_each_lead_goes_to_a_channel_it_actually_has(self):
        mobile = self.leads.add_lead("Con Mobile", city="MI", whatsapp="393331112222",
                                     phone="+39 333 111 2222")
        emailed = self.leads.add_lead("Con Email", city="MI", phone="02 111111",
                                      email="a@b.invalid")
        landline = self.leads.add_lead("Solo Fisso", city="MI", phone="02 222222")
        nothing = self.leads.add_lead("Nessun Contatto", city="MI")
        due = self.leads.due_leads()
        self.assertEqual([l["id"] for l in due["to_whatsapp"]], [mobile])
        self.assertEqual([l["id"] for l in due["to_email"]], [emailed])
        self.assertEqual([l["id"] for l in due["to_call"]], [landline],
                         "a landline with no email is a phone call, not an email")
        self.assertEqual([l["id"] for l in due["no_angle"]], [nothing])


class PriorityTest(unittest.TestCase):
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

    def test_strongest_problem_is_called_first(self):
        weak = self.leads.add_lead("Senza Sito", city="MI", phone="02 1")
        strong = self.leads.add_lead("Certificato Scaduto", city="MI", phone="02 2")
        self.leads.save_scan(weak, [{"code": "no_website", "severity": 5, "detail": ""}])
        self.leads.save_scan(strong, [{"code": "ssl_expired", "severity": 5, "detail": ""},
                                      {"code": "slow", "severity": 2, "detail": ""}])
        order = [l["id"] for l in self.leads.due_leads()["to_call"]]
        self.assertEqual(order, [strong, weak], "more wrong beats less wrong at equal severity")


class CallAttemptTest(unittest.TestCase):
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

    def test_no_answer_moves_on_today_and_returns_tomorrow(self):
        lead = self.leads.add_lead("Studio", city="MI", phone="02 1")
        self.leads.record_attempt(lead, "non risponde")
        self.assertEqual(self.leads.due_leads()["to_call"], [], "not offered twice in a day")
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(timespec="seconds")
        with self.leads.connect() as conn:
            conn.execute("UPDATE leads SET last_attempt_at = ? WHERE id = ?", (yesterday, lead))
        self.assertEqual([l["id"] for l in self.leads.due_leads()["to_call"]], [lead])

    def test_three_unanswered_calls_give_up(self):
        lead = self.leads.add_lead("Mai Risponde", city="MI", phone="02 2")
        for _ in range(self.leads.MAX_ATTEMPTS):
            self.leads.record_attempt(lead, "non risponde")
        self.assertEqual(self.leads.get(lead)["state"], "DEAD")

    def test_migration_adds_columns_to_an_old_database(self):
        import sqlite3
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,"
                     " category TEXT, city TEXT, website TEXT, email TEXT, phone TEXT, whatsapp TEXT,"
                     " source TEXT, state TEXT NOT NULL DEFAULT 'NEW', created_at TEXT NOT NULL,"
                     " state_changed_at TEXT NOT NULL, next_action_at TEXT, scanned_at TEXT,"
                     " findings TEXT, draft TEXT, follow_ups INTEGER NOT NULL DEFAULT 0, notes TEXT,"
                     " UNIQUE (name, city))")
        conn.commit(); conn.close()
        lead = self.leads.add_lead("Vecchio DB", city="MI", phone="02 3")
        self.assertEqual(self.leads.record_attempt(lead, "x")["attempts"], 1)


class CallModeTest(unittest.TestCase):
    """The tap path, with Telegram replaced by a recorder."""

    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")
        os.environ["LEADS_DB"] = self.db
        for module in [m for m in list(sys.modules) if m.startswith("modules.")]:
            del sys.modules[module]
        from modules import leads, callmode, telegram_bot
        self.leads, self.callmode = leads, callmode
        leads.DB_PATH = self.db
        leads._schema_ready = False
        self.sent = []
        telegram_bot.send_with_buttons = lambda text, rows: self.sent.append(("card", text)) or 1
        telegram_bot.send_telegram_message = lambda text: self.sent.append(("msg", text))
        telegram_bot.edit_message = lambda mid, text: self.sent.append(("edit", text))
        telegram_bot.answer_callback = lambda cid, text="": self.sent.append(("ack", text))

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def _lead(self, name, severity_code="site_down"):
        lead = self.leads.add_lead(name, city="MI", phone="02 123")
        self.leads.save_scan(lead, [{"code": severity_code, "severity": 5, "detail": ""}], "Buongiorno.")
        return lead

    def test_a_tap_records_the_outcome_and_loads_the_next_card(self):
        first, second = self._lead("Primo"), self._lead("Secondo", "slow")
        self.callmode.start(lambda text: self.sent.append(("msg", text)))
        self.assertIn("Primo", [t for k, t in self.sent if k == "card"][0])
        self.callmode.on_button(f"c:{first}:hot", 1, "cb1")
        self.assertEqual(self.leads.get(first)["state"], "INTERESTED")
        self.assertIn("Secondo", [t for k, t in self.sent if k == "card"][-1])

    def test_no_answer_and_skip_both_move_on(self):
        a, b = self._lead("A"), self._lead("B", "slow")
        self.callmode.start(lambda text: None)
        self.callmode.on_button(f"c:{a}:noanswer", 1, "cb")
        self.assertEqual(self.leads.get(a)["attempts"], 1)
        self.assertIn("B", [t for k, t in self.sent if k == "card"][-1])
        self.callmode.on_button(f"c:{b}:skip", 2, "cb")
        self.assertIn("finita", [t for k, t in self.sent if k == "msg"][-1])

    def test_malformed_callback_data_is_ignored(self):
        self.callmode.on_button("garbage", 1, "cb")
        self.assertEqual(self.sent[-1], ("ack", "?"))

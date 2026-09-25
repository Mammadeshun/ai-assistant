"""Tests for dashboard v2 (docs/dashboard-v2/SPEC.md): caps, PEC, "Non
contattare", snooze, replies, follow-ups, results, the job whitelist and the
HTTP guards.

    python -m unittest discover -s tests -v

Every time-dependent rule takes a `now`, and the tests pass fixed ones, so
the suite gives the same answer on a Friday evening as on a Monday morning.
"""

import os
import sys
import json
import datetime
import tempfile
import threading
import unittest
import http.client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class V2Base(unittest.TestCase):
    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")
        os.environ["LEADS_DB"] = self.db
        # The package too: `from modules import x` returns the attribute
        # cached on the package, so a cap patched here would leak.
        for module in [m for m in list(sys.modules) if m == "modules" or m.startswith("modules.")]:
            del sys.modules[module]
        from modules import leads, outreach, webapp, dashboard, jobs
        self.leads, self.outreach, self.webapp, self.dash, self.jobs = leads, outreach, webapp, dashboard, jobs
        leads.DB_PATH = self.db
        leads._schema_ready = False
        self.now = datetime.datetime.now().replace(microsecond=0)

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)
        for module in [m for m in list(sys.modules) if m == "modules" or m.startswith("modules.")]:
            del sys.modules[module]

    def _lead(self, name, code="not_mobile", whatsapp="393331112222", email=None, phone="02 1234 5678",
              category="dentisti", city="Milano"):
        website = "https://www." + "".join(c for c in name.lower() if c.isalnum()) + ".it"
        lead = self.leads.add_lead(name, category=category, city=city, website=website, email=email,
                                   phone=phone, whatsapp=whatsapp, source=f"osm:node/{name}")
        self.assertIsNotNone(lead)
        self.leads.save_scan(lead, [{"code": code, "severity": 4, "detail": ""}], None)
        return lead

    def _age(self, lead_id, days):
        old = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
        with self.leads.connect() as conn:
            conn.execute("UPDATE leads SET state_changed_at = ? WHERE id = ?", (old, lead_id))

    def _send_whatsapp(self, lead_id, kind="first"):
        status, h = self.dash.start_handoff(lead_id, {"channel": "whatsapp", "kind": kind}, self.now)
        self.assertEqual(status, 200, h)
        status, r = self.dash.resolve_handoff(h["key"], {"result": "sent"}, self.now)
        self.assertEqual(status, 200, r)
        return h


class CapValidationTest(V2Base):
    def test_whatsapp_cap_31_is_rejected_and_30_accepted(self):
        status, payload = self.dash.update_settings({"cap_whatsapp": 31})
        self.assertEqual(status, 400)
        self.assertIn("30", payload["error"])
        self.assertEqual(self.dash.caps()["whatsapp"], 25, "a rejected value changes nothing")
        self.assertEqual(self.dash.update_settings({"cap_whatsapp": 30})[0], 200)
        self.assertEqual(self.dash.caps()["whatsapp"], 30)
        self.assertEqual(self.dash.update_settings({"cap_whatsapp": 0})[0], 200)

    def test_email_cap_is_0_to_20_and_junk_is_refused(self):
        for bad in (21, -1, "venti", True, 2.5, None):
            self.assertEqual(self.dash.update_settings({"cap_email": bad})[0], 400, bad)
        self.assertEqual(self.dash.update_settings({"cap_email": 20})[0], 200)
        self.assertEqual(self.dash.update_settings({"goal": 61})[0], 400)

    def test_a_stored_value_over_the_limit_is_clamped_not_used(self):
        self.leads.set_setting(self.dash.SETTINGS_KEY, json.dumps({"cap_whatsapp": 99, "cap_email": 50}))
        self.assertEqual(self.dash.caps(), {"whatsapp": 30, "email": 20})

    def test_the_env_default_can_never_exceed_30(self):
        self.outreach.MAX_WHATSAPP_PER_DAY = 45
        self.assertEqual(self.dash.caps()["whatsapp"], 30)

    def test_the_server_enforces_the_cap_on_the_handoff_and_the_queue(self):
        self.dash.update_settings({"cap_whatsapp": 1})
        first, second = self._lead("Primo"), self._lead("Secondo", whatsapp="393339998888")
        self.assertEqual(self.webapp.today()["message_cap"], 1, "the old app reads the same cap")
        self._send_whatsapp(first)
        status, payload = self.dash.start_handoff(second, {"channel": "whatsapp", "kind": "first"}, self.now)
        self.assertEqual(status, 429)
        self.assertIn("1/1", payload["error"])
        t = self.dash.today_view(self.now)
        self.assertEqual(t["sections"]["new"], 0, "no new WhatsApp past the cap")
        self.assertEqual(t["counts"]["whatsapp"], 1)

    def test_an_open_handoff_holds_its_place_under_the_cap(self):
        self.dash.update_settings({"cap_whatsapp": 1})
        a, b = self._lead("Alfa"), self._lead("Beta", whatsapp="393339998888")
        status, _ = self.dash.start_handoff(a, {"channel": "whatsapp", "kind": "first"}, self.now)
        self.assertEqual(status, 200)
        status, payload = self.dash.start_handoff(b, {"channel": "whatsapp", "kind": "first"}, self.now)
        self.assertEqual(status, 409, "one unconfirmed handoff at a time")
        self.assertEqual(payload["pending"]["lead_id"], a)


class HandoffTest(V2Base):
    def test_opening_whatsapp_records_nothing_and_inviato_records_once(self):
        lead = self._lead("Studio Uno")
        status, h = self.dash.start_handoff(lead, {"channel": "whatsapp", "kind": "first"}, self.now)
        self.assertEqual(status, 200)
        self.assertTrue(h["link"].startswith("whatsapp://send?phone=393331112222&text="))
        self.assertEqual(self.dash.count_whatsapp(self.now.date()), 0, "opening is not sending")
        self.assertEqual(self.leads.get(lead)["state"], "NEW")
        self.assertEqual(self.dash.today_view(self.now)["pending"]["key"], h["key"], "survives a reload")
        self.dash.resolve_handoff(h["key"], {"result": "sent"}, self.now)
        again = self.dash.resolve_handoff(h["key"], {"result": "sent"}, self.now)
        self.assertEqual(again[1].get("already"), "sent")
        with self.leads.connect() as conn:
            n = conn.execute("SELECT COUNT(*) n FROM events WHERE lead_id = ? AND kind = 'state:WHATSAPP_SENT'",
                             (lead,)).fetchone()["n"]
        self.assertEqual(n, 1, "a second Inviato must not record a second send")
        self.assertEqual(self.webapp.today()["messages"], 1)
        self.assertIsNone(self.dash.today_view(self.now)["pending"])

    def test_non_inviato_keeps_the_lead_in_the_queue(self):
        lead = self._lead("Studio Due")
        status, h = self.dash.start_handoff(lead, {"channel": "whatsapp", "kind": "first"}, self.now)
        self.dash.resolve_handoff(h["key"], {"result": "not_sent"}, self.now)
        self.assertEqual(self.leads.get(lead)["state"], "NEW")
        self.assertEqual(self.dash.today_view(self.now)["first"]["id"], lead)

    def test_the_edited_middle_goes_out_between_the_required_clauses(self):
        lead = self._lead("Studio Tre")
        status, h = self.dash.start_handoff(lead, {"channel": "whatsapp", "kind": "first",
                                                   "body": "Testo scritto a mano da Momo, niente altro."}, self.now)
        self.assertEqual(status, 200)
        with self.leads.connect() as conn:
            text = conn.execute("SELECT message FROM handoffs WHERE key = ?", (h["key"],)).fetchone()["message"]
        self.assertIn("Testo scritto a mano da Momo", text)
        self.assertEqual(self.outreach.missing_clauses(text), [])
        self.assertIn("Momo", text.split("\n\n")[0])
        self.assertIn("non ricevere altri messaggi", text.split("\n\n")[-1])
        self.assertEqual(self.dash.start_handoff(lead, {"channel": "whatsapp", "kind": "first", "body": " "},
                                                 self.now)[0], 400)

    def test_parts_rebuild_the_exact_message(self):
        lead = self.leads.get(self._lead("Studio Quattro"))
        findings = self.leads.findings_of(lead)
        for hour in (9, 18):
            p = self.outreach.whatsapp_parts(lead, findings, hour=hour)
            self.assertEqual("\n\n".join((p["intro"], p["body"], p["closing"])),
                             self.outreach.whatsapp_message(lead, findings, hour=hour))
        self.assertEqual(self.outreach.missing_clauses("Buongiorno"), ["identity", "source", "opt_out"])


class PecTest(V2Base):
    def test_pec_addresses_are_recognised(self):
        pec = self.leads.is_pec_address
        self.assertTrue(pec("studio@pec.it"))
        self.assertTrue(pec("studio.rossi@pec.ordineavvocati.it"))
        self.assertTrue(pec("info@studiorossi.pec.it"))
        self.assertFalse(pec("info@studiorossi.it"))
        self.assertFalse(pec("specialista@gmail.com"), "'pec' inside the local part is not PEC")
        self.assertFalse(pec(None))

    def test_a_pec_lead_gets_no_email_action_anywhere(self):
        lead = self._lead("Solo Pec", whatsapp=None, email="studio@pec.ordine.it")
        self.assertEqual(self.leads.due_leads()["to_email"], [])
        self.assertEqual([l["id"] for l in self.leads.due_leads()["to_call"]], [lead])
        self.leads.set_setting("signature", "Momo")
        sent = []
        self.outreach.send_email = lambda *a: sent.append(a)
        status, payload = self.webapp.send_lead_email(lead, "Oggetto", "x" * 60)
        self.assertEqual(status, 409)
        self.assertIn("PEC", payload["error"])
        self.assertEqual(sent, [])
        detail = self.dash.lead_detail(lead, self.now)
        self.assertFalse(detail["channels"]["email"]["ok"])
        self.assertIn("PEC", detail["channels"]["email"]["why"])
        self.assertNotIn("email_draft", detail)
        self.assertIsNone(self.webapp.lead_view(self.leads.get(lead), full=True)["email_body"])

    def test_a_lead_flagged_pec_by_hand_is_excluded_too(self):
        lead = self._lead("Flag Pec", whatsapp=None, email="info@legalmail.it")
        self.assertEqual([l["id"] for l in self.leads.due_leads()["to_email"]], [lead])
        status, _ = self.dash.edit_contact(lead, {"email_pec": True}, self.now)
        self.assertEqual(status, 200)
        self.assertEqual(self.leads.due_leads()["to_email"], [])


class DoNotContactTest(V2Base):
    def test_it_is_permanent_on_every_path(self):
        lead = self._lead("Mai Piu")
        self.assertEqual(self.dash.do_not_contact(lead, now=self.now)[0], 200)
        after = self.leads.get(lead)
        self.assertEqual(after["state"], "DEAD")
        buckets = self.leads.due_leads()
        self.assertFalse(any(l["id"] == lead for b in buckets.values() for l in b))
        t = self.dash.today_view(self.now)
        self.assertIsNone(t["first"])
        with self.assertRaises(ValueError):
            self.leads.set_state(lead, "CONTACTED")
        self.assertEqual(self.dash.set_follow_up(lead, {"preset": "tomorrow"}, self.now)[0], 409)
        self.assertEqual(self.dash.start_handoff(lead, {"channel": "whatsapp"}, self.now)[0], 409)
        self.assertEqual(self.dash.start_handoff(lead, {"channel": "call"}, self.now)[0], 409)
        self.assertEqual(self.dash.log_reply(lead, {"type": "positive"}, self.now)[0], 409)
        self.assertIsNone(self.webapp.lead_view(self.leads.get(lead), full=True)["wa_chat"])
        later = self.now + datetime.timedelta(seconds=self.dash.UNDO_SECONDS + 1)
        self.assertEqual(self.dash.undo_do_not_contact(lead, later)[0], 409)
        self.assertTrue(self.leads.get(lead)["do_not_contact_at"])

    def test_it_cancels_follow_ups_and_replies(self):
        lead = self._lead("Con Follow")
        self._send_whatsapp(lead)
        self.dash.log_reply(lead, {"type": "question"}, self.now)
        self.dash.do_not_contact(lead, now=self.now)
        after = self.leads.get(lead)
        self.assertIsNone(after["follow_up_at"])
        self.assertIsNone(after["reply_todo_at"])

    def test_undo_inside_the_window_restores_the_lead(self):
        lead = self._lead("Tocco Sbagliato")
        self.dash.do_not_contact(lead, now=self.now)
        status, _ = self.dash.undo_do_not_contact(lead, self.now + datetime.timedelta(seconds=3))
        self.assertEqual(status, 200)
        after = self.leads.get(lead)
        self.assertIsNone(after["do_not_contact_at"])
        self.assertEqual(after["state"], "NEW")
        self.assertEqual(self.dash.today_view(self.now)["first"]["id"], lead)

    def test_not_interested_with_opt_out_sets_it(self):
        lead = self._lead("Basta Messaggi")
        self._send_whatsapp(lead)
        self.dash.log_reply(lead, {"type": "not_interested", "opt_out": True}, self.now)
        self.assertTrue(self.leads.get(lead)["do_not_contact_at"])


class SnoozeAndSkipTest(V2Base):
    def at(self, h, m=0):
        return datetime.datetime(2026, 9, 23, h, m, 0)     # a Wednesday

    def test_later_today_is_two_hours_never_past_seven(self):
        self.assertEqual(self.dash.later_today(self.at(10)), self.at(12))
        self.assertEqual(self.dash.later_today(self.at(17, 30)), self.at(19))
        self.assertEqual(self.dash.later_today(self.at(18, 50)), datetime.datetime(2026, 9, 24, 9, 0))
        self.assertEqual(self.dash.later_today(self.at(22)), datetime.datetime(2026, 9, 24, 9, 0))

    def test_a_snoozed_lead_leaves_oggi_and_comes_back(self):
        lead = self._lead("Dopo")
        other = self._lead("Adesso", whatsapp="393339998888", code="site_down")
        now = datetime.datetime.now().replace(microsecond=0)
        status, payload = self.dash.snooze(lead, {"preset": "later"}, now)
        self.assertEqual(status, 200)
        ids = lambda t: [t["first"]["id"]] + [q["id"] for q in t["queue"]] if t["first"] else []
        self.assertEqual(ids(self.dash.today_view(now)), [other])
        self.assertEqual(self.dash.today_view(now)["sections"]["snoozed"], 1)
        until = datetime.datetime.fromisoformat(payload["until"])
        self.assertIn(lead, ids(self.dash.today_view(until + datetime.timedelta(minutes=1))))

    def test_salta_moves_to_the_end_without_changing_anything(self):
        a = self._lead("Aaa", code="site_down")
        b = self._lead("Bbb", whatsapp="393339998888")
        t = self.dash.today_view(self.now)
        self.assertEqual(t["first"]["id"], a)
        self.dash.skip(a, self.now)
        t = self.dash.today_view(self.now)
        self.assertEqual([t["first"]["id"]] + [q["id"] for q in t["queue"]], [b, a])
        self.assertEqual(self.leads.get(a)["state"], "NEW")
        self.assertEqual(t["counts"]["total"], 0)


class ReplyTest(V2Base):
    def _contacted(self, name, **kw):
        lead = self._lead(name, **kw)
        self._send_whatsapp(lead)
        return lead

    def test_positive_marks_hot_and_asks_for_an_answer_today(self):
        lead = self._contacted("Positivo")
        self.dash.log_reply(lead, {"type": "positive"}, self.now)
        after = self.leads.get(lead)
        self.assertEqual(after["state"], "INTERESTED")
        self.assertTrue(after["reply_todo_at"])
        t = self.dash.today_view(self.now)
        self.assertEqual((t["first"]["id"], t["first"]["kind"]), (lead, "reply"))

    def test_question_keeps_it_active_and_asks_for_an_answer(self):
        lead = self._contacted("Domanda")
        self.dash.log_reply(lead, {"type": "question"}, self.now)
        after = self.leads.get(lead)
        self.assertEqual(after["state"], "CONTACTED")
        self.assertEqual(self.dash.next_action(after, self.dash._context(self.now))["kind"], "reply")

    def test_not_interested_closes_and_cancels_follow_ups(self):
        lead = self._contacted("No Grazie")
        self.assertTrue(self.leads.get(lead)["follow_up_at"])
        self.dash.log_reply(lead, {"type": "not_interested"}, self.now)
        after = self.leads.get(lead)
        self.assertEqual(after["state"], "DEAD")
        self.assertIsNone(after["follow_up_at"])
        self.assertIsNone(after["do_not_contact_at"], "only an explicit opt-out is permanent")
        self.assertEqual(self.dash.next_action(after, self.dash._context(self.now))["kind"], "closed")

    def test_wrong_number_drops_the_phone_but_keeps_a_normal_email(self):
        lead = self._contacted("Numero Sbagliato", email="info@studio.it")
        self.dash.log_reply(lead, {"type": "wrong_number"}, self.now)
        after = self.leads.get(lead)
        self.assertTrue(after["phone_invalid_at"])
        self.assertEqual(after["follow_up_at"], self.now.date().isoformat(), "email is the next step, today")
        detail = self.dash.lead_detail(lead, self.now)
        self.assertFalse(detail["channels"]["whatsapp"]["ok"])
        self.assertFalse(detail["channels"]["call"]["ok"])
        self.assertTrue(detail["channels"]["email"]["ok"], detail["channels"]["email"])

    def test_wrong_number_without_email_leaves_nothing_to_do(self):
        lead = self._contacted("Solo Cellulare")
        self.dash.log_reply(lead, {"type": "wrong_number"}, self.now)
        after = self.leads.get(lead)
        self.assertIsNone(after["follow_up_at"])
        self.assertEqual(self.dash.next_action(after, self.dash._context(self.now))["kind"], "none")

    def test_answering_clears_the_reply_and_sets_the_next_follow_up(self):
        lead = self._contacted("Da Rispondere")
        self.dash.log_reply(lead, {"type": "question"}, self.now)
        self._send_whatsapp(lead, kind="reply")
        after = self.leads.get(lead)
        self.assertIsNone(after["reply_todo_at"])
        expected = self.dash.business_day(self.now.date() + datetime.timedelta(days=self.leads.FOLLOW_UP_DAYS))
        self.assertEqual(after["follow_up_at"], expected.isoformat())
        self.assertEqual(self.dash.count_whatsapp(self.now.date()), 1, "a reply is not counted against the cap")

    def test_unknown_type_is_refused(self):
        lead = self._contacted("Boh")
        self.assertEqual(self.dash.log_reply(lead, {"type": "maybe"}, self.now)[0], 400)


class FollowUpTest(V2Base):
    def test_business_day_moves_weekends_to_monday(self):
        self.assertEqual(self.dash.business_day(datetime.date(2026, 9, 26)), datetime.date(2026, 9, 28))
        self.assertEqual(self.dash.business_day(datetime.date(2026, 9, 27)), datetime.date(2026, 9, 28))
        self.assertEqual(self.dash.business_day(datetime.date(2026, 9, 25)), datetime.date(2026, 9, 25))

    def test_defaults_follow_the_existing_waits(self):
        self.assertEqual(self.dash.default_follow_up_days("first_whatsapp"), self.leads.WHATSAPP_WAIT_DAYS)
        self.assertEqual(self.dash.default_follow_up_days("first_email"), self.leads.EMAIL_WAIT_DAYS)
        self.assertEqual(self.dash.default_follow_up_days("contacted"), self.leads.FOLLOW_UP_DAYS)
        self.assertEqual(self.dash.default_follow_up_days("follow_up", 1), self.leads.FOLLOW_UP_DAYS)
        self.assertIsNone(self.dash.default_follow_up_days("follow_up", self.dash.MAX_FOLLOW_UPS))

    def test_a_send_leaves_the_default_follow_up(self):
        lead = self._lead("Inviato")
        self._send_whatsapp(lead)
        expected = self.dash.business_day(self.now.date() + datetime.timedelta(days=self.leads.WHATSAPP_WAIT_DAYS))
        self.assertEqual(self.leads.get(lead)["follow_up_at"], expected.isoformat())

    def test_an_email_leaves_the_email_wait(self):
        lead = self._lead("Email", whatsapp=None, email="info@studio.it")
        self.leads.set_setting("signature", "Momo")
        self.outreach.send_email = lambda *a: True
        status, _ = self.webapp.send_lead_email(lead, "Oggetto", "Buongiorno, " + "x" * 60)
        self.assertEqual(status, 200)
        expected = self.dash.business_day(datetime.date.today() + datetime.timedelta(days=self.leads.EMAIL_WAIT_DAYS))
        self.assertEqual(self.leads.get(lead)["follow_up_at"], expected.isoformat())

    def test_set_change_and_remove(self):
        lead = self._lead("Cambia")
        self._send_whatsapp(lead)
        self.assertEqual(self.dash.set_follow_up(lead, {"preset": "today"}, self.now)[1]["follow_up_at"],
                         self.now.date().isoformat())
        t = self.dash.today_view(self.now)
        self.assertEqual((t["first"]["id"], t["first"]["kind"]), (lead, "follow_today"))
        day = (self.now.date() + datetime.timedelta(days=10)).isoformat()
        self.assertEqual(self.dash.set_follow_up(lead, {"date": day}, self.now)[1]["follow_up_at"], day)
        self.assertEqual(self.dash.set_follow_up(lead, {"date": "2020-01-01"}, self.now)[0], 400)
        self.dash.set_follow_up(lead, {"remove": True}, self.now)
        self._age(lead, 30)          # the old cascade would have made it due long ago
        self.assertEqual(self.dash.next_action(self.leads.get(lead), self.dash._context(self.now))["kind"], "none")

    def test_an_overdue_follow_up_is_ahead_of_today_and_of_new_leads(self):
        new = self._lead("Nuovo", code="site_down", whatsapp="393330000009")
        old = self._lead("Scaduto")
        today = self._lead("Oggi Tocca", whatsapp="393330000008")
        self._send_whatsapp(old)
        self._send_whatsapp(today)
        self.dash.set_follow_up(today, {"preset": "today"}, self.now)
        with self.leads.connect() as conn:
            conn.execute("UPDATE leads SET follow_up_at = ? WHERE id = ?",
                         ((self.now.date() - datetime.timedelta(days=2)).isoformat(), old))
        t = self.dash.today_view(self.now)
        order = [(t["first"]["id"], t["first"]["kind"])] + [(q["id"], q["kind"]) for q in t["queue"]]
        self.assertEqual(order[:3], [(old, "follow_overdue"), (today, "follow_today"), (new, "new")])

    def test_a_follow_up_whatsapp_counts_and_closes_the_due_date(self):
        lead = self._lead("Secondo Giro")
        self._send_whatsapp(lead)
        self.dash.set_follow_up(lead, {"preset": "today"}, self.now)
        self._send_whatsapp(lead, kind="follow_up")
        with self.leads.connect() as conn:
            kinds = [r["kind"] for r in conn.execute("SELECT kind FROM events WHERE lead_id = ?", (lead,))]
        self.assertIn("follow_up_done", kinds)
        self.assertEqual(self.leads.get(lead)["follow_ups"], 1)


class ResultsTest(V2Base):
    def _event(self, lead_id, kind, days_ago, detail=None):
        at = (self.now - datetime.timedelta(days=days_ago)).isoformat(timespec="seconds")
        with self.leads.connect() as conn:
            conn.execute("INSERT INTO events (lead_id, at, kind, detail) VALUES (?,?,?,?)", (lead_id, at, kind, detail))

    def test_segments_carry_n_and_small_samples_are_flagged(self):
        # 12 WhatsApps ten days ago, 3 of them answered; 4 emails, 1 answered.
        for i in range(12):
            lead = self._lead(f"Wa {i}", whatsapp=f"39333000{i:04d}", code="site_down" if i < 6 else "not_mobile")
            self._event(lead, "state:WHATSAPP_SENT", 10, "whatsapp: inviato")
            if i < 3:
                self._event(lead, "reply:positive" if i == 0 else "reply:question", 9, "whatsapp")
        for i in range(4):
            lead = self._lead(f"Em {i}", whatsapp=None, email=f"a{i}@studio.it", code="ssl_expired")
            self._event(lead, "state:EMAIL_SENT", 12, "email: inviata dall'app")
            if i == 0:
                self._event(lead, "reply:not_interested", 11, "email")
        # A send from yesterday is too recent to judge.
        young = self._lead("Giovane", whatsapp="393339990000")
        self._event(young, "state:WHATSAPP_SENT", 1, "whatsapp: inviato")
        r = self.dash.results(30, self.now)
        ch = {s["key"]: s for s in r["by_channel"]}
        self.assertEqual((ch["whatsapp"]["n"], ch["whatsapp"]["replies"], ch["whatsapp"]["small"]), (12, 3, False))
        self.assertEqual((ch["email"]["n"], ch["email"]["replies"], ch["email"]["small"]), (4, 1, True))
        self.assertEqual(ch["call"]["n"], 0)
        self.assertIsNone(ch["call"]["rate"])
        problems = {s["key"]: s for s in r["by_problem"]}
        self.assertEqual(problems["site_down"]["n"], 6)
        self.assertEqual({k: v["n"] for k, v in problems.items()}, {"site_down": 6, "not_mobile": 6, "ssl_expired": 4})
        self.assertTrue(all(s["small"] for s in r["by_problem"]), "every problem segment is under 10")
        q = {i["key"]: i["count"] for i in r["quality"]["items"]}
        self.assertEqual((q["positive"], q["question"], q["not_interested"]), (1, 2, 1))
        self.assertTrue(r["quality"]["small"])
        self.assertEqual(sum(d["whatsapp"] for d in r["series"]), 13)
        self.assertEqual(len(r["series"]), 30)

    def test_old_app_outcomes_count_as_replies(self):
        lead = self._lead("Vecchia App")
        self._event(lead, "state:WHATSAPP_SENT", 8, "whatsapp: inviato")
        self._event(lead, "state:INTERESTED", 7, "whatsapp: interessato")
        r = self.dash.results(30, self.now)
        wa = [s for s in r["by_channel"] if s["key"] == "whatsapp"][0]
        self.assertEqual((wa["n"], wa["replies"]), (1, 1))


class JobsTest(V2Base):
    def test_only_whitelisted_jobs_can_be_requested(self):
        self.assertEqual(set(self.jobs.JOBS), {"scan_pending", "verify_no_site"})
        for bad in ("rm -rf", "sourcing", "../scan_pending", ""):
            self.assertEqual(self.jobs.request(bad)[0], 404, bad)
        with self.assertRaises(ValueError):
            self.jobs.run_job("restart")

    def test_single_flight_per_key(self):
        status, row = self.jobs.request("scan_pending")
        self.assertEqual((status, row["status"]), (200, "queued"))
        self.assertEqual(self.jobs.request("scan_pending")[0], 409)
        self.assertEqual(self.jobs.request("verify_no_site")[0], 200, "another key is independent")
        job = self.jobs.claim_next()
        self.assertEqual((job["key"], job["status"]), ("scan_pending", "running"))
        self.assertEqual(self.jobs.request("scan_pending")[0], 409, "running also blocks")
        self.jobs.finish(job["id"], "done", "ok")
        self.assertEqual(self.jobs.request("scan_pending")[0], 200)

    def test_a_restart_frees_an_interrupted_job(self):
        self.jobs.request("scan_pending")
        self.jobs.claim_next()
        self.assertEqual(self.jobs.recover_interrupted(), 1)
        self.assertEqual(self.jobs.overview()["jobs"][0]["last"]["status"], "error")
        self.assertEqual(self.jobs.request("scan_pending")[0], 200)

    def test_poll_runs_one_job_at_a_time_and_records_errors(self):
        started, release = [], threading.Event()

        def fake(key):
            started.append(key)
            release.wait(5)
            if key == "verify_no_site":
                raise RuntimeError("boom")
            return "fatto"
        self.jobs.run_job = fake
        self.jobs.request("scan_pending")
        self.jobs.request("verify_no_site")
        self.assertIsNotNone(self.jobs.poll())
        self.assertIsNone(self.jobs.poll(), "one at a time")
        release.set()
        self.jobs._worker["thread"].join(5)
        self.assertIsNotNone(self.jobs.poll())
        self.jobs._worker["thread"].join(5)
        rows = {j["key"]: j["last"] for j in self.jobs.overview()["jobs"]}
        self.assertEqual((rows["scan_pending"]["status"], rows["scan_pending"]["summary"]), ("done", "fatto"))
        self.assertEqual(rows["verify_no_site"]["status"], "error")
        self.assertIn("boom", rows["verify_no_site"]["summary"])
        self.assertEqual(started, ["scan_pending", "verify_no_site"])

    def test_poll_never_raises(self):
        self.jobs.claim_next = lambda: 1 / 0
        self.assertIsNone(self.jobs.poll())


class HttpGuardTest(V2Base):
    def setUp(self):
        super().setUp()
        import http.server
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self.webapp.Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.token = self.webapp.redeem_code(self.webapp.new_pairing_code())

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def request(self, method, path, body=None, headers=None, cookie=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        if cookie:
            h["Cookie"] = f"s={self.token}"
        data = json.dumps(body).encode() if body is not None else None
        if data is not None:
            h["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        payload = r.read()
        conn.close()
        return r.status, payload

    def test_a_post_without_the_header_is_rejected(self):
        for path in ("/api/v2/settings", "/api/v2/lead/1/dnc", "/api/v2/jobs/scan_pending", "/api/outcome"):
            self.assertEqual(self.request("POST", path, {"cap_whatsapp": 5})[0], 403, path)
        self.assertEqual(self.jobs.overview()["recent"], [], "nothing was queued")

    def test_v2_needs_a_session(self):
        for path in ("/api/v2/today", "/api/v2/leads", "/api/v2/lead/1", "/api/v2/results", "/api/v2/jobs"):
            self.assertEqual(self.request("GET", path, cookie=False)[0], 401, path)
        self.assertEqual(self.request("POST", "/api/v2/settings", {"cap_email": 3},
                                      {"X-Requested-With": "app"}, cookie=False)[0], 401)

    def test_signed_in_writes_are_validated_by_the_server(self):
        status, body = self.request("POST", "/api/v2/settings", {"cap_whatsapp": 31}, {"X-Requested-With": "app"})
        self.assertEqual(status, 400)
        status, body = self.request("POST", "/api/v2/jobs/shutdown", {}, {"X-Requested-With": "app"})
        self.assertEqual(status, 404)
        status, body = self.request("GET", "/api/v2/today")
        self.assertEqual(status, 200)
        self.assertIn("queue", json.loads(body))

    def test_both_pages_are_served(self):
        status, body = self.request("GET", "/", cookie=False)
        self.assertEqual(status, 200)
        self.assertIn(b'data-tab="sistema"', body, "the old app still at /")
        status, body = self.request("GET", "/v2", cookie=False)
        self.assertEqual(status, 200)
        self.assertIn(b"<!doctype html>", body.lower())


if __name__ == "__main__":
    unittest.main()

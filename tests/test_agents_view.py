"""Tests for the Agenti dashboard's data-building function.

    python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _line(**kw):
    return json.dumps(kw)


class AgentsViewTest(unittest.TestCase):
    def setUp(self):
        self.db = tempfile.mktemp(suffix=".db")
        os.environ["LEADS_DB"] = self.db
        for module in [m for m in list(sys.modules) if m.startswith("modules.")]:
            del sys.modules[module]
        from modules import webapp
        self.webapp = webapp

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_a_completed_run_merges_its_start_and_end_lines_by_id(self):
        lines = [
            _line(id="a1", status="running", ts=1000, pipeline="linkedin", step="draft",
                  model="cx/gpt-5.6-sol", prompt_preview="hello", prompt_file="p.txt", out_file="o.md"),
            _line(id="a1", status="ok", ts_end=1010, seconds=10, tokens=123, error=None,
                  output_preview="the result"),
        ]
        view = self.webapp.agents_view(lines, now=1020)
        self.assertEqual(view["running"], [])
        self.assertEqual(len(view["recent"]), 1)
        row = view["recent"][0]
        self.assertEqual(row["id"], "a1")
        self.assertEqual(row["pipeline"], "linkedin")
        self.assertEqual(row["step"], "draft")
        self.assertEqual(row["model"], "cx/gpt-5.6-sol")
        self.assertEqual(row["prompt_preview"], "hello")
        self.assertEqual(row["output_preview"], "the result")
        self.assertEqual(row["duration"], 10)
        self.assertEqual(row["status"], "ok")

    def test_a_run_with_only_a_start_line_is_running_with_an_elapsed_time(self):
        lines = [_line(id="b1", status="running", ts=1000, pipeline="eval", step="q1", model="kr/claude-haiku-4.5")]
        view = self.webapp.agents_view(lines, now=1090)
        self.assertEqual(len(view["running"]), 1)
        self.assertEqual(view["running"][0]["elapsed"], 90)
        self.assertFalse(view["running"][0]["stale"])

    def test_a_running_entry_older_than_thirty_minutes_with_no_end_is_stale(self):
        lines = [_line(id="c1", status="running", ts=1000, pipeline="eval", step="q1", model="kr/claude-haiku-4.5")]
        view = self.webapp.agents_view(lines, now=1000 + 31 * 60)
        self.assertTrue(view["running"][0]["stale"])

    def test_an_error_run_is_recorded_with_its_message(self):
        lines = [
            _line(id="d1", status="running", ts=1000, pipeline="eval", step="q1", model="cx/gpt-5.5"),
            _line(id="d1", status="error", ts_end=1005, seconds=5, error="boom"),
        ]
        view = self.webapp.agents_view(lines, now=1010)
        self.assertEqual(view["recent"][0]["status"], "error")
        self.assertEqual(view["recent"][0]["error"], "boom")

    def test_recent_is_newest_first_and_capped_at_sixty(self):
        lines = []
        for i in range(70):
            lines.append(_line(id=f"e{i}", status="running", ts=i, pipeline="p", step="s", model="m"))
            lines.append(_line(id=f"e{i}", status="ok", ts_end=i + 1))
        view = self.webapp.agents_view(lines, now=1000)
        self.assertEqual(len(view["recent"]), 60)
        self.assertEqual(view["recent"][0]["id"], "e69")   # the most recently finished
        self.assertEqual(view["recent"][-1]["id"], "e10")

    def test_pipelines_aggregate_ok_errors_and_running_counts(self):
        lines = [
            _line(id="f1", status="running", ts=1000, pipeline="linkedin", step="a", model="m"),
            _line(id="f1", status="ok", ts_end=1005),
            _line(id="f2", status="running", ts=1006, pipeline="linkedin", step="b", model="m"),
            _line(id="f2", status="error", ts_end=1008, error="x"),
            _line(id="f3", status="running", ts=1100, pipeline="linkedin", step="c", model="m"),
        ]
        view = self.webapp.agents_view(lines, now=1110)
        p = next(p for p in view["pipelines"] if p["name"] == "linkedin")
        self.assertEqual(p["ok"], 1)
        self.assertEqual(p["errors"], 1)
        self.assertEqual(p["running"], 1)
        self.assertEqual(p["last_activity"], 1100)   # the running job's own start, the latest activity

    def test_junk_and_truncated_lines_are_skipped_without_raising(self):
        lines = ["not json at all", "", '{"no": "id here"}', '{"id": "g1", "status": "running"',
                 _line(id="g2", status="running", ts=1000, pipeline="p", step="s", model="m")]
        view = self.webapp.agents_view(lines, now=1000)
        self.assertEqual(len(view["running"]), 1)
        self.assertEqual(view["running"][0]["id"], "g2")

    def test_an_end_line_whose_start_never_arrived_still_shows_up(self):
        lines = [_line(id="h1", status="ok", ts_end=1000, output_preview="orphan end")]
        view = self.webapp.agents_view(lines, now=1000)
        self.assertEqual(len(view["recent"]), 1)
        self.assertEqual(view["recent"][0]["pipeline"], "unknown")
        self.assertIsNone(view["recent"][0]["duration"])   # no start ts to measure from

    def test_empty_log_is_the_empty_state(self):
        view = self.webapp.agents_view([], now=1000)
        self.assertEqual(view, {"running": [], "recent": [], "pipelines": []})

    def test_router_active_reads_the_actual_port(self):
        # Real server or not, this must not depend on whether the real
        # router happens to be up on its real port right now.
        import socket
        old_port = self.webapp.AGENTS_ROUTER_PORT
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        self.webapp.AGENTS_ROUTER_PORT = port
        try:
            self.assertTrue(self.webapp.router_active())
        finally:
            srv.close()
        # A closed listening socket refuses new connections immediately.
        self.webapp.AGENTS_ROUTER_PORT = port
        try:
            self.assertFalse(self.webapp.router_active())
        finally:
            self.webapp.AGENTS_ROUTER_PORT = old_port

    def test_agents_data_never_raises_when_the_events_file_is_missing(self):
        self.webapp.AGENTS_EVENTS_FILE = "/nonexistent/path/events.jsonl"
        data = self.webapp.agents_data()
        self.assertEqual(data["running"], [])
        self.assertEqual(data["recent"], [])
        self.assertIn("active", data["router"])
        self.assertEqual(data["jobs"], [])


if __name__ == "__main__":
    unittest.main()

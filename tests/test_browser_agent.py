"""Browser agent end to end: real headless Chrome (Playwright) against a
local fixture site, driven by a scripted model. Skipped when Playwright or
a browser isn't available."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs

import pytest

pytest.importorskip("playwright")

from agent_core import AgentCore, ApprovalStatus, UserProfile  # noqa: E402
from shadow_node import browser_agent as ba  # noqa: E402
from shadow_node.provider_auth import CredentialStore  # noqa: E402

PAGES = {
    "/": "<html><title>Shop</title><body><h1>Tea shop</h1><p>Green tea costs $4.</p>"
         "<a href='/cart'>Cart</a></body></html>",
    "/cart": "<html><title>Cart</title><body><form action='/ordered' method='post'>"
             "<button type='submit'>Place order</button></form></body></html>",
    "/ordered": "<html><title>Thanks</title><body>Order placed</body></html>",
    "/login": "<html><title>Login</title><body><form action='/welcome' method='post'>"
              "<input name='user' placeholder='Email'><input name='pass' type='password' placeholder='Password'>"
              "<button type='submit'>Sign in</button></form></body></html>",
    "/welcome": "<html><title>Welcome</title><body>Signed in</body></html>",
}


class Site:
    def __init__(self):
        self.posts = []
        site = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _page(self, path):
                body = PAGES.get(path.split("?")[0], "<html><body>404</body></html>").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._page(self.path)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                site.posts.append((self.path, parse_qs(self.rfile.read(n).decode())))
                self._page(self.path)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


class ScriptedModel:
    """Returns queued actions; records what it was shown."""

    name = "scripted"

    def __init__(self, actions):
        self.actions = list(actions)
        self.seen = []

    def complete(self, prompt, context=""):
        self.seen.append(prompt + "\n" + context)
        if not self.actions:
            return json.dumps({"action": "done", "text": "out of script"})
        nxt = self.actions.pop(0)
        return nxt(context) if callable(nxt) else json.dumps(nxt)


def idx_of(context, label):
    for line in context.splitlines():
        if line.startswith("[") and label in line:
            return int(line[1:line.index("]")])
    raise AssertionError(f"{label!r} not in page: {context[:400]}")


@pytest.fixture(scope="module")
def site():
    s = Site()
    yield s
    s.server.shutdown()


@pytest.fixture
def env(tmp_path):
    from cryptography.fernet import Fernet
    core = AgentCore()
    prof = UserProfile()
    creds = CredentialStore(path=str(tmp_path / "c.enc"), key=Fernet.generate_key())
    events = []
    holder = SimpleNamespace(model=None)
    agent = ba.BrowserAgent(
        model_factory=lambda: holder.model, approvals=core.approvals, policy_profile=lambda: prof,
        vault=ba.Vault(creds), audit=lambda *a: events.append(a), allow_private_hosts=True,
    )
    try:
        with ba._launch_chrome():
            pass
    except Exception as e:  # no Chrome/Chromium available
        pytest.skip(f"no browser: {e}")
    return SimpleNamespace(agent=agent, core=core, profile=prof, holder=holder, events=events)


def wait_status(task, statuses, timeout=45):
    end = time.time() + timeout
    while time.time() < end:
        if task.status in statuses:
            return task.status
        time.sleep(0.2)
    raise AssertionError(f"task stuck in {task.status}: {task.error} {[ (s.action, s.result) for s in task.steps]}")


def test_read_task_finishes_with_answer_and_frames(site, env):
    env.holder.model = ScriptedModel([
        {"action": "note", "text": "green tea is $4"},
        {"action": "done", "text": "Green tea costs $4."},
    ])
    task = env.agent.start("How much is green tea?", site.url + "/", "scripted")
    assert wait_status(task, {"done", "failed"}) == "done", task.error
    assert task.answer == "Green tea costs $4." and task.notes == ["green tea is $4"]
    assert task.frame and task.frame[:3] == b"\xff\xd8\xff"  # JPEG live view
    assert "Tea shop" in env.holder.model.seen[0]
    assert "untrusted" in env.holder.model.seen[0].lower()


def test_place_order_waits_for_approval_then_runs(site, env):
    env.holder.model = ScriptedModel([
        {"action": "go", "url": site.url + "/cart"},
        lambda ctx: json.dumps({"action": "click", "index": idx_of(ctx, "Place order")}),
        {"action": "done", "text": "ordered"},
    ])
    task = env.agent.start("Order the tea", site.url + "/", "scripted")
    wait_status(task, {"waiting_approval"})
    req = env.core.approvals.requests[task.approval_id]
    assert req.action.tool_name == "browser.action" and "Place order" in req.action.description
    assert not any(p == "/ordered" for p, _ in site.posts)  # nothing happened yet
    env.core.approvals.decide(req.id, True)
    assert wait_status(task, {"done", "failed"}) == "done", task.error
    assert any(p == "/ordered" for p, _ in site.posts)
    assert env.core.approvals.requests[req.id].status == ApprovalStatus.CONSUMED  # one-shot


def test_denied_step_is_not_performed(site, env):
    env.holder.model = ScriptedModel([
        {"action": "go", "url": site.url + "/cart"},
        lambda ctx: json.dumps({"action": "click", "index": idx_of(ctx, "Place order")}),
        {"action": "done", "text": "gave up"},
    ])
    before = len(site.posts)
    task = env.agent.start("Order the tea", site.url + "/", "scripted")
    wait_status(task, {"waiting_approval"})
    env.core.approvals.decide(task.approval_id, False, "no")
    wait_status(task, {"done"})
    assert len(site.posts) == before
    assert "did not approve" in task.steps[1].result


def test_vault_login_never_shows_password_to_model(site, env):
    env.agent.vault.put(site.url, "me@example.com", "s3cret-Pa55word!")
    env.holder.model = ScriptedModel([
        lambda ctx: json.dumps({"action": "type", "index": idx_of(ctx, "Email"), "text": "{{vault:username}}"}),
        lambda ctx: json.dumps({"action": "type", "index": idx_of(ctx, "Password"), "text": "{{vault:password}}"}),
        lambda ctx: json.dumps({"action": "click", "index": idx_of(ctx, "Sign in")}),
        {"action": "done", "text": "signed in"},
    ])
    task = env.agent.start("Sign in", site.url + "/login", "scripted")
    wait_status(task, {"waiting_approval"})
    env.core.approvals.decide(task.approval_id, True)
    assert wait_status(task, {"done", "failed"}) == "done", task.error
    path, form = site.posts[-1]
    assert path == "/welcome" and form["pass"] == ["s3cret-Pa55word!"] and form["user"] == ["me@example.com"]
    shown = "\n".join(env.holder.model.seen)
    assert "s3cret-Pa55word!" not in shown and "Saved login for this site" in shown
    assert "s3cret" not in json.dumps(task.summary())


def test_password_field_only_takes_vault_and_secrets_are_refused(site, env):
    env.holder.model = ScriptedModel([
        lambda ctx: json.dumps({"action": "type", "index": idx_of(ctx, "Password"), "text": "hunter2"}),
        lambda ctx: json.dumps({"action": "type", "index": idx_of(ctx, "Email"),
                                "text": "sk-proj-" + "A" * 30}),
        {"action": "done", "text": "x"},
    ])
    task = env.agent.start("Sign in", site.url + "/login", "scripted")
    wait_status(task, {"done", "failed"})
    assert "only be filled from the vault" in task.steps[0].result
    assert "Refused" in task.steps[1].result and "API key" in task.steps[1].result


def test_stop_and_emergency_pause(site, env):
    env.holder.model = ScriptedModel([{"action": "scroll", "direction": "down"}] * 200)
    task = env.agent.start("Browse forever", site.url + "/", "scripted")
    wait_status(task, {"running"})
    env.agent.stop(task.id)
    assert wait_status(task, {"stopped", "failed"}) == "stopped"
    task2 = env.agent.start("Browse forever", site.url + "/", "scripted")
    wait_status(task2, {"running"})
    env.profile.emergency_paused = True
    assert wait_status(task2, {"stopped"}) == "stopped"
    env.profile.emergency_paused = False


# --- no-browser unit checks ------------------------------------------------------------------

def test_private_addresses_blocked_without_test_override(tmp_path):
    from cryptography.fernet import Fernet
    agent = ba.BrowserAgent(lambda: object(), AgentCore().approvals, lambda: UserProfile(),
                            ba.Vault(CredentialStore(path=str(tmp_path / "c.enc"), key=Fernet.generate_key())),
                            lambda *a: None)
    for url in ("http://127.0.0.1:8787/", "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd"):
        with pytest.raises(ba.BrowserTaskError):
            agent._check_url(url)
    aborted = []
    route = SimpleNamespace(request=SimpleNamespace(url="http://10.0.0.5/admin"),
                            abort=lambda reason: aborted.append(reason), continue_=lambda: aborted.append("continued"))
    agent._route(route)
    assert aborted == ["blockedbyclient"]


def test_needs_cloud_model(tmp_path):
    from cryptography.fernet import Fernet
    agent = ba.BrowserAgent(lambda: None, AgentCore().approvals, lambda: UserProfile(),
                            ba.Vault(CredentialStore(path=str(tmp_path / "c.enc"), key=Fernet.generate_key())),
                            lambda *a: None, allow_private_hosts=True)
    with pytest.raises(ba.BrowserTaskError, match="cloud model"):
        agent.start("x", "http://127.0.0.1/", "local_mock")


@pytest.mark.parametrize("element,action,expected", [
    ({"name": "Place order", "type": "submit", "tag": "button"}, {"action": "click"}, True),
    ({"name": "Pay now", "type": "", "tag": "a"}, {"action": "click"}, True),
    ({"name": "Next page", "type": "", "tag": "a"}, {"action": "click"}, False),
    ({"name": "Search", "type": "text", "tag": "input"}, {"action": "type", "submit": True}, True),
    ({"name": "Search", "type": "text", "tag": "input"}, {"action": "type"}, False),
])
def test_consequential_classification(element, action, expected):
    agent = ba.BrowserAgent(lambda: None, None, lambda: UserProfile(), None, lambda *a: None)
    assert (agent._consequential(action, element) is not None) is expected


def test_vault_origin_matching():
    assert ba.normalize_origin("Example.com") == "https://example.com"
    assert ba.normalize_origin("http://example.com:8080/login") == "http://example.com:8080"
    assert ba.origin_of("https://evil.example.com/") != ba.normalize_origin("example.com")

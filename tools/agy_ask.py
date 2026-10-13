#!/usr/bin/env python3
"""One-shot Antigravity (Gemini) ask-and-wait: create a conversation, poll the
local trajectory db until the planner produces a final answer, print it.

Usage: tools/agy_ask.py "prompt" [timeout_s]
Env: same as agentapi (ANTIGRAVITY_*), set by tools/agy or auto-discovered here.
"""
import os, re, sqlite3, subprocess, sys, time, glob

LS = '/Applications/Antigravity.app/Contents/Resources/bin/language_server'
SHIM = os.path.expanduser('~/.gemini/antigravity/bin/agentapi')
CONV_DIR = os.path.expanduser('~/.gemini/antigravity/conversations')


def discover_env():
    out = subprocess.run(['pgrep', '-f', 'language_server --standalone'],
                         capture_output=True, text=True).stdout.split()
    if out:
        pid = out[0]
        cmd = subprocess.run(['ps', '-p', pid, '-o', 'command='],
                             capture_output=True, text=True).stdout
        csrf = re.search(r'--csrf_token ([0-9a-f-]+)', cmd)
        ports = subprocess.run(['lsof', '-nP', '-p', pid], capture_output=True,
                               text=True).stdout
        pl = sorted({m for m in re.findall(r'127\.0\.0\.1:(\d+) \(LISTEN\)', ports)})
        os.environ['ANTIGRAVITY_LS_ADDRESS'] = '127.0.0.1:' + pl[-1]
        if csrf:
            os.environ['ANTIGRAVITY_CSRF_TOKEN'] = csrf.group(1)
    os.environ.setdefault('ANTIGRAVITY_PROJECT_ID', 'outside-of-project')


def newest_db(conv_id, since):
    p = os.path.join(CONV_DIR, conv_id + '.db')
    if os.path.exists(p) and os.path.getmtime(p) >= since:
        return p
    return None


def pull_answer(db_path):
    try:
        db = sqlite3.connect(db_path)
        rows = db.execute('SELECT step_payload FROM steps ORDER BY idx').fetchall()
    except sqlite3.Error:
        return None, False
    texts = []
    for (p,) in rows:
        for m in re.findall(r'[ -~]{80,}', p.decode('utf8', 'ignore')):
            if re.search(r'view_file|call_\d+|Read|Listed|Grep', m[:40]):
                continue
            texts.append(m)
    if not texts:
        return None, False
    # last message can span several chunks; join trailing readable chunks
    return '\n'.join(texts[-3:]), True


def main():
    prompt = sys.argv[1]
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 240
    discover_env()
    r = subprocess.run([SHIM, 'new-conversation', '--model=' + os.environ.get('AGY_MODEL', 'flash'), prompt],
                       capture_output=True, text=True, timeout=60)
    m = re.search(r'"conversationId": *"([^"]+)"', r.stdout)
    if not m:
        print('SPAWN FAILED:', r.stdout[-300:], r.stderr[-300:]); sys.exit(2)
    conv = m.group(1)
    t0 = time.time(); last = None; stable = 0
    while time.time() - t0 < timeout:
        time.sleep(10)
        p = newest_db(conv, t0)
        if p:
            ans, _ = pull_answer(p)
            if ans and ans != last:
                last = ans; stable = 0
            elif ans:
                stable += 1
                if stable >= 3:  # 30s no change -> done
                    break
    print('=== conversation', conv)
    print(last if last else '(no answer within timeout)')


if __name__ == '__main__':
    main()

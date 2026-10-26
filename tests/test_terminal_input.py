import errno
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "linux", "Linux terminal regression")
class TerminalInputTests(unittest.TestCase):
    def run_terminal(
        self, script: str, messages: list[bytes], environment: dict | None = None
    ) -> str:
        import pty
        import termios

        master, slave = pty.openpty()
        original = termios.tcgetattr(slave)
        original[0] &= ~getattr(termios, "IUTF8", 0x4000)
        termios.tcsetattr(slave, termios.TCSANOW, original)
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", script],
            cwd=ROOT,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env={
                **os.environ,
                "PYTHONIOENCODING": "utf-8:strict",
                **(environment or {}),
            },
        )
        output = bytearray()
        try:
            deadline = time.monotonic() + 20
            sent = 0
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError as exc:
                        if exc.errno == errno.EIO:
                            break
                        raise
                    if not chunk:
                        break
                    output.extend(chunk)
                    while sent < len(messages) and output.count("Вы: ".encode()) > sent:
                        os.write(master, messages[sent])
                        sent += 1
                if process.poll() is not None:
                    break
            process.wait(timeout=2)
            self.assertEqual(
                process.returncode, 0, output.decode(errors="backslashreplace")
            )
            self.assertEqual(termios.tcgetattr(slave)[0] & 0x4000, 0)
            return output.decode("utf-8", errors="backslashreplace")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    def test_cyrillic_edit_paste_and_invalid_input_in_real_pty(self):
        script = """
import asyncio, json
import httpx
from travel_agent.__main__ import dialogue, terminal_input
received = []
def handle(request):
    if request.method == 'POST':
        received.append(json.loads(request.content)['message'])
        return httpx.Response(200, json={'answer': 'Привет! Я помогу с поездкой.'})
    return httpx.Response(200, json={'revision': 0})
async def main():
    async with httpx.AsyncClient(base_url='http://local', transport=httpx.MockTransport(handle)) as client:
        with terminal_input():
            await dialogue(client, 'test-trip')
    print('RECEIVED=' + json.dumps(received, ensure_ascii=False))
asyncio.run(main())
"""
        output = self.run_terminal(
            script,
            [
                "Приветт".encode() + b"\x7f" + ", кто ты?\n".encode(),
                "Хочу в Сочи 🌊\n".encode(),
                b"broken \xd0\n",
                "Москва, двое взрослых\n".encode(),
                b"/quit\n",
            ],
        )
        received = json.loads(output.split("RECEIVED=")[1].splitlines()[0])
        self.assertEqual(
            received, ["Привет, кто ты?", "Хочу в Сочи 🌊", "Москва, двое взрослых"]
        )
        self.assertIn("Введите сообщение ещё раз", output)
        self.assertNotIn("Traceback", output)
        self.assertEqual(output.count("Агент: Привет!"), 3)

    def test_surrogate_input_is_not_sent(self):
        script = """
import asyncio
from unittest.mock import patch
import httpx
from travel_agent.__main__ import dialogue
async def main():
    async with httpx.AsyncClient(base_url='http://local', transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError('Unexpected network')))) as client:
        with patch('builtins.input', side_effect=['broken \\udcd0', '/quit']):
            await dialogue(client, 'test-trip')
asyncio.run(main())
"""
        output = self.run_terminal(script, [])
        self.assertIn("Введите сообщение ещё раз", output)
        self.assertNotIn("Traceback", output)

    def test_chat_entrypoint_with_real_api_graph_sqlite_and_terminal(self):
        script = """
import json, runpy, sys, tempfile
from pathlib import Path
from unittest.mock import patch
from travel_agent.schemas import SupervisorDecision
received = []
async def decide(state):
    received.append(state['messages'][-1].content)
    return SupervisorDecision(action='chat', reply='Привет! Я помощник по поездкам в Сочи.')
env = {'MODEL': 'offline-model', 'TOKEN': 'offline-token', 'BASE_URL': 'https://example.invalid/v1', 'TRAVEL_API_TOKEN': 'pty-test'}
with tempfile.TemporaryDirectory() as directory:
    with patch('travel_agent.api.llm_decider', return_value=decide), patch('travel_agent.api.environment', return_value=env), patch('travel_agent.config.environment', return_value=env), patch('travel_agent.__main__.Path', side_effect=lambda value: Path(directory) / value):
        sys.argv = ['chat.py', '--new']
        runpy.run_path('chat.py', run_name='__main__')
print('RECEIVED=' + json.dumps(received, ensure_ascii=False))
"""
        output = self.run_terminal(
            script,
            [
                "Приветт".encode() + b"\x7f" + ", кто ты?\n".encode(),
                b"/quit\n",
            ],
        )
        self.assertIn("Агент: Привет! Я помощник по поездкам в Сочи.", output)
        self.assertEqual(
            json.loads(output.split("RECEIVED=")[1].splitlines()[0]),
            ["Привет, кто ты?"],
        )
        self.assertNotIn("Traceback", output)

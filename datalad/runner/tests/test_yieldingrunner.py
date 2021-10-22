from queue import Queue

from datalad.runner.yielding_runner import yielding_run_command


def test_yielding_runner_basic():
    for i in yielding_run_command("python3 -i -", "print('aaa'); exit(0)\n", True, True):
        print(repr(i))

    stdin_queue = Queue()
    j = 0
    for i in yielding_run_command("python3 -i -", stdin_queue, True, True):
        print(i[1].decode())
        command = f"print({j} * {j})\n"
        stdin_queue.put(command)
        j += 1
        if j == 10:
            stdin_queue.put("exit(0)\n")

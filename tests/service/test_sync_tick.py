from scripts.service.sync_tick import should_sync, build_run_sync_cmd, decide_sync_action


def test_should_sync_true_when_shas_differ():
    assert should_sync("aaa", "bbb") is True


def test_should_sync_false_when_shas_equal():
    assert should_sync("aaa", "aaa") is False
    assert should_sync(" aaa\n", "aaa") is False  # 容错空白


def test_should_sync_false_when_either_empty():
    assert should_sync("", "bbb") is False
    assert should_sync("aaa", "") is False


def test_build_run_sync_cmd_shape():
    cmd = build_run_sync_cmd(compose_file="dc.yml", vault="/vault", state="/state", version=1)
    assert cmd[:6] == ["docker", "compose", "-f", "dc.yml", "run", "--rm"]
    assert "policy-pipeline" in cmd
    assert "scripts.sync.run_sync" in cmd
    assert cmd[cmd.index("--vault") + 1] == "/vault"
    assert cmd[cmd.index("--state-dir") + 1] == "/state"
    assert cmd[cmd.index("--pipeline-version") + 1] == "1"


def test_decide_reset_when_clean_and_not_ahead():
    assert decide_sync_action(local_ahead=0, dirty=False) == "reset"


def test_decide_abort_when_local_commits():
    assert decide_sync_action(local_ahead=2, dirty=False) == "abort"


def test_decide_abort_when_dirty():
    assert decide_sync_action(local_ahead=0, dirty=True) == "abort"

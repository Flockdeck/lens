from lens.parent_watch import same_program


def test_the_launcher_and_the_program_have_the_same_name():
    assert same_program(r"C:\Users\a\Downloads\lens.exe", r"D:\x\LENS.EXE")
    assert same_program("/usr/local/bin/lens", "/home/a/.cache/lens")
    assert same_program(r"C:\proj\.venv\Scripts\python.exe", r"C:\py\python.exe")  # venv


def test_a_shell_or_another_program_is_not_the_launcher():
    assert not same_program(r"C:\Windows\System32\cmd.exe", r"C:\x\lens.exe")
    assert not same_program("/bin/zsh", "/usr/local/bin/lens")
    assert not same_program("flockdeck.exe", "lens.exe")


def test_unknown_parents_are_left_alone():
    assert not same_program(None, "lens")
    assert not same_program("", "lens")
    assert not same_program("lens", "")

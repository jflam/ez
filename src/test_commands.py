import commands

def test_increment():
    assert commands.increment(3) == 4

def test_decrement():
    assert commands.decrement(3) == 2
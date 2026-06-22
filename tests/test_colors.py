from envguard.utils.colors import Colors

def test_colors_constants():
    """Test that Colors class provides expected ANSI codes."""
    assert Colors.RED == "\033[91m"
    assert Colors.GREEN == "\033[92m"
    assert Colors.YELLOW == "\033[93m"
    assert Colors.PURPLE == "\033[95m"
    assert Colors.RESET == "\033[0m"
    assert Colors.BOLD == "\033[1m"

def test_colors_formatting():
    """Test formatting helper methods if any."""
    assert Colors.red("text") == "\033[91mtext\033[0m"
    assert Colors.green("text") == "\033[92mtext\033[0m"
    assert Colors.yellow("text") == "\033[93mtext\033[0m"
    assert Colors.purple("text") == "\033[95mtext\033[0m"

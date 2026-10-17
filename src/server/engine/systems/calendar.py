"""The calendar: how many years each turn lasts."""
from __future__ import annotations

from ..rules.schema import Rules


def next_year(rules: Rules, year: int) -> int:
    """The year that follows `year`, one turn later."""
    years = next(step.years for step in rules.game.calendar.steps
                 if step.until is None or year < step.until)
    # There is no year 0: 20 BC is followed by 1 AD, then 20 AD.
    following = (0 if year == 1 else year) + years
    return 1 if following == 0 else following


def year_after(rules: Rules, year: int, turns: int) -> int:
    """The year `turns` turns after `year`."""
    for _ in range(turns):
        year = next_year(rules, year)
    return year


def year_of_turn(rules: Rules, turn: int) -> int:
    """The year of a turn of the game (turn 0 is the start year)."""
    return year_after(rules, rules.game.calendar.start_year, turn)


def turns_until(rules: Rules, year: int, target_year: int) -> int:
    """Number of turns before the calendar reaches `target_year`."""
    turns = 0
    while year < target_year:
        year = next_year(rules, year)
        turns += 1
    return turns

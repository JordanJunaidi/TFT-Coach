from tftcoach.agent.grounding import check_grounding, extract_numbers


def test_extracts_numbers_and_ignores_citations() -> None:
    text = "Durability 20/33/45% ⇒ 20/30/42% [18.4-20], damage 8,000"
    assert extract_numbers(text) == ["20", "33", "45", "20", "30", "42", "8,000"]


def test_numbers_from_tools_are_grounded_at_answer_precision() -> None:
    tool = '{"avg_placement": 4.82, "top4_rate_pct": 36.4, "games": 11}'
    report = check_grounding("Draven: 11 games, average 4.8, top 4 in 36% of them.", [tool])
    assert report.ok
    assert report.numbers_checked == 4


def test_fraction_matches_percentage() -> None:
    assert check_grounding("You top 4 in 36% of games.", ['{"rate": 0.364}']).ok


def test_invented_numbers_are_flagged() -> None:
    # A computed difference (45 - 42 = "3 points" is allowed as a star level, so use 13).
    report = check_grounding("Durability dropped 13 points, to 42%.", ['"20/33/45% ⇒ 20/30/42%"'])
    assert report.unsupported == ["13"]
    report = check_grounding("You win 27% of games.", ['{"wins": 2}'])
    assert report.unsupported == ["27"]


def test_game_rule_numbers_need_no_source() -> None:
    assert check_grounding("Aim for top 4 and a 2-star carry.", []).ok

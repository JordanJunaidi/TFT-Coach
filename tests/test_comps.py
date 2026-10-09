import pytest

from tftcoach.analysis.comps import (
    BoardTrait,
    BoardUnit,
    CompKey,
    PlayerBoard,
    comp_key,
    comp_label,
    find_carry,
    find_main_trait,
    offense_score,
    summarize_comps,
)

RECIPES = {
    "InfinityEdge": ["Component_BFSword", "Component_SparringGloves"],
    "Guinsoo": ["Component_RecurveBow", "Component_NeedlesslyLargeRod"],
    "Warmog": ["Component_GiantsBelt", "Component_GiantsBelt"],
    "Stoneplate": ["Component_ChainVest", "Component_NegatronCloak"],
}


def unit(character_id: str, items: int = 0, star: int = 2, rarity: int = 1) -> BoardUnit:
    return BoardUnit(character_id, star, rarity, tuple(f"Item{i}" for i in range(items)))


def trait(trait_id: str, num_units: int, style: int = 1, current: int = 1, total: int = 3):
    return BoardTrait(trait_id, num_units, style, current, total)


def board(placement: int, carry: str, main_trait: str, match_id: str = "M") -> PlayerBoard:
    return PlayerBoard(
        match_id,
        "18.4",
        placement,
        units=[unit(carry, items=3), unit("Filler", items=1)],
        traits=[trait(main_trait, 6), trait("Minor", 2)],
    )


def test_offense_score_counts_offensive_components() -> None:
    assert offense_score(["InfinityEdge", "Guinsoo"], RECIPES) == 3
    assert offense_score(["Warmog", "Stoneplate"], RECIPES) == 0
    assert offense_score(["DA_Component_BFSword"], RECIPES) == 1  # bare component


def test_carry_is_damage_unit_not_itemized_tank() -> None:
    tank = BoardUnit("Tank", 2, 4, ("Warmog", "Stoneplate", "Warmog"))
    carry = BoardUnit("Carry", 2, 1, ("InfinityEdge", "Guinsoo"))
    assert find_carry([tank, carry], RECIPES).character_id == "Carry"


def test_carry_falls_back_to_item_count() -> None:
    units = [unit("A", items=1), unit("B", items=3), unit("C")]
    assert find_carry(units, {}).character_id == "B"


def test_carry_ties_break_on_star_then_cost() -> None:
    units = [unit("A", items=3, star=2, rarity=4), unit("B", items=3, star=3, rarity=1)]
    assert find_carry(units, {}).character_id == "B"
    units = [unit("A", items=3, rarity=2), unit("B", items=3, rarity=4)]
    assert find_carry(units, {}).character_id == "B"


def test_main_trait_ignores_inactive_and_unique_traits() -> None:
    traits = [
        trait("Inactive", 7, current=0),
        trait("Unique", 9, style=3, total=1),
        trait("Real", 4),
    ]
    assert find_main_trait(traits).trait_id == "Real"


def test_main_trait_ties_break_on_style() -> None:
    assert find_main_trait([trait("A", 4, style=1), trait("B", 4, style=2)]).trait_id == "B"


def test_empty_board_has_no_carry_or_trait() -> None:
    assert comp_key(PlayerBoard("M", None, 8), {}) == CompKey(carry=None)


def test_label_uses_display_names_with_fallback() -> None:
    names = {"DA_18_Adaptor": "Adaptor"}
    assert comp_label(CompKey("DA_18_Diana"), names) == "Diana"
    assert comp_label(CompKey("DA_18_Diana", "DA_18_Adaptor"), names) == "Adaptor Diana"
    assert comp_label(CompKey(None), names) == "No carry"


def test_summarize_comps_computes_stats_per_comp() -> None:
    boards = [
        board(1, "Diana", "Adaptor"),
        board(4, "Diana", "Adaptor"),
        board(6, "Diana", "Adaptor"),
        board(5, "Jinx", "Sniper"),
    ]
    stats = summarize_comps(boards, {})

    assert [s.comp for s in stats] == [CompKey("Diana"), CompKey("Jinx")]
    top = stats[0]
    assert top.games == 3
    assert top.avg_placement == pytest.approx(11 / 3)
    assert top.top4_rate == pytest.approx(2 / 3)
    assert stats[1].top4_rate == 0


def test_summarize_breaks_game_count_ties_by_placement() -> None:
    stats = summarize_comps([board(7, "Jinx", "Sniper"), board(2, "Diana", "Adaptor")], {})
    assert stats[0].comp.carry == "Diana"


def test_default_groups_same_carry_across_traits() -> None:
    boards = [
        board(2, "Zyra", "Juggernaut"),
        board(3, "Zyra", "Executioner"),
        board(6, "Zyra", "Executioner"),
    ]
    [stats] = summarize_comps(boards, {})

    assert stats.comp == CompKey("Zyra")
    assert stats.games == 3
    assert stats.usual_trait == "Executioner"


def test_by_trait_splits_same_carry() -> None:
    boards = [board(2, "Zyra", "Juggernaut"), board(3, "Zyra", "Executioner")]
    stats = summarize_comps(boards, {}, by_trait=True)

    assert {s.comp for s in stats} == {
        CompKey("Zyra", main_trait="Juggernaut"),
        CompKey("Zyra", main_trait="Executioner"),
    }
    assert all(s.usual_trait == s.comp.main_trait for s in stats)

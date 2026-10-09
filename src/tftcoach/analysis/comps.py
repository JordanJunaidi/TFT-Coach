"""Comp labeling and per-comp stats.

The Riot API has no notion of a "comp", so one is derived from the final board as
"<main trait> <carry>", e.g. "Adaptor Diana". The label is computed at query time, never
stored, so the definition can change without re-ingesting.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# Components that add damage stats (AD, attack speed, AP, mana). Tanks also hold three
# items, so the carry is the unit whose items are built from the most of these. Component
# names have been stable across sets; matching on a substring tolerates set prefixes
# like "DA_Component_".
OFFENSIVE_COMPONENTS = ("BFSword", "RecurveBow", "NeedlesslyLargeRod", "TearOfTheGoddess")


@dataclass(frozen=True)
class BoardUnit:
    character_id: str
    star_level: int
    rarity: int
    items: tuple[str, ...] = ()


@dataclass(frozen=True)
class BoardTrait:
    trait_id: str
    num_units: int
    style: int
    tier_current: int
    tier_total: int


@dataclass
class PlayerBoard:
    match_id: str
    patch: str | None
    placement: int
    units: list[BoardUnit] = field(default_factory=list)
    traits: list[BoardTrait] = field(default_factory=list)


@dataclass(frozen=True)
class CompKey:
    main_trait: str | None
    carry: str | None


@dataclass(frozen=True)
class CompStats:
    comp: CompKey
    games: int
    avg_placement: float
    top4_rate: float


ItemComponents = Mapping[str, Sequence[str]]


def offense_score(items: Sequence[str], components: ItemComponents) -> int:
    """Count offensive components across a unit's items.

    An item missing from `components` (a bare component, or names not loaded yet) is
    scored as itself.
    """
    return sum(
        1
        for item in items
        for part in (components.get(item) or [item])
        if any(name in part for name in OFFENSIVE_COMPONENTS)
    )


def find_carry(units: list[BoardUnit], components: ItemComponents) -> BoardUnit | None:
    """The unit with the most offensive item components.

    Ties go to more items, then higher star level, then higher cost.
    """
    if not units:
        return None
    return max(
        units,
        key=lambda u: (offense_score(u.items, components), len(u.items), u.star_level, u.rarity),
    )


def find_main_trait(traits: list[BoardTrait]) -> BoardTrait | None:
    """The active, non-unique trait with the most units; ties go to the higher style.

    Unique traits (tier_total == 1) come from a single 5-cost or special unit and would
    otherwise win ties despite saying little about what the board is built around.
    """
    candidates = [t for t in traits if t.tier_current > 0 and t.tier_total > 1]
    if not candidates:
        return None
    return max(candidates, key=lambda t: (t.num_units, t.style))


def comp_key(board: PlayerBoard, components: ItemComponents) -> CompKey:
    carry = find_carry(board.units, components)
    trait = find_main_trait(board.traits)
    return CompKey(
        main_trait=trait.trait_id if trait else None,
        carry=carry.character_id if carry else None,
    )


def display_name(api_name: str | None, names: dict[str, str]) -> str:
    """Map an internal ID to its display name, falling back to the ID's last segment."""
    if api_name is None:
        return "None"
    return names.get(api_name, api_name.rsplit("_", 1)[-1])


def comp_label(comp: CompKey, names: dict[str, str]) -> str:
    trait = display_name(comp.main_trait, names) if comp.main_trait else "No trait"
    carry = display_name(comp.carry, names) if comp.carry else "No carry"
    return f"{trait} {carry}"


def summarize_comps(boards: list[PlayerBoard], components: ItemComponents) -> list[CompStats]:
    """Games, average placement, and top-4 rate per comp, most-played first."""
    placements: dict[CompKey, list[int]] = {}
    for board in boards:
        placements.setdefault(comp_key(board, components), []).append(board.placement)

    stats = [
        CompStats(
            comp=comp,
            games=len(places),
            avg_placement=sum(places) / len(places),
            top4_rate=sum(1 for p in places if p <= 4) / len(places),
        )
        for comp, places in placements.items()
    ]
    return sorted(stats, key=lambda s: (-s.games, s.avg_placement))

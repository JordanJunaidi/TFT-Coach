"""Comp labeling and per-comp stats.

The Riot API has no notion of a "comp", so one is derived from the final board. By
default a comp is its carry ("Diana"), reported with its usual tank and main trait; with
`by_trait=True` it is "<main trait> <carry>" ("Adaptor Diana"). Grouping by carry alone
keeps samples usable: the main trait and the tank often vary between games on the same
board, which split one player's 33 games on a patch into 26 trait+carry comps (25 for
carry+tank) versus 17 carries. Labels are computed at query time, never stored, so the
definition can change without re-ingesting.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# Components that add damage stats (AD, attack speed, AP, mana). Tanks also hold three
# items, so the carry is the unit whose items are built from the most of these. Component
# names have been stable across sets; matching on a substring tolerates set prefixes
# like "DA_Component_".
OFFENSIVE_COMPONENTS = ("BFSword", "RecurveBow", "NeedlesslyLargeRod", "TearOfTheGoddess")
# Components that add armor, magic resist, or health; used to find the main tank.
DEFENSIVE_COMPONENTS = ("ChainVest", "NegatronCloak", "GiantsBelt")


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
    carry: str | None
    main_trait: str | None = None  # only set when grouping by trait


@dataclass(frozen=True)
class CompStats:
    comp: CompKey
    games: int
    avg_placement: float
    top4_rate: float
    usual_tank: str | None  # most common main tank across the comp's games
    usual_trait: str | None  # most common main trait across the comp's games


ItemComponents = Mapping[str, Sequence[str]]


def component_score(items: Sequence[str], components: ItemComponents, kinds: Sequence[str]) -> int:
    """Count the components of the given kinds across a unit's items.

    An item missing from `components` (a bare component, or names not loaded yet) is
    scored as itself.
    """
    return sum(
        1
        for item in items
        for part in (components.get(item) or [item])
        if any(name in part for name in kinds)
    )


def offense_score(items: Sequence[str], components: ItemComponents) -> int:
    return component_score(items, components, OFFENSIVE_COMPONENTS)


def defense_score(items: Sequence[str], components: ItemComponents) -> int:
    return component_score(items, components, DEFENSIVE_COMPONENTS)


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


def find_tank(
    units: list[BoardUnit], components: ItemComponents, carry: BoardUnit | None
) -> BoardUnit | None:
    """The non-carry unit with the most defensive item components, if any has one.

    Ties go to more items, then higher star level, then higher cost. A board whose
    frontline holds no defensive items has no tank.
    """
    candidates = [u for u in units if u is not carry and defense_score(u.items, components) > 0]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda u: (defense_score(u.items, components), len(u.items), u.star_level, u.rarity),
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


def main_trait_id(board: PlayerBoard) -> str | None:
    trait = find_main_trait(board.traits)
    return trait.trait_id if trait else None


def tank_id(board: PlayerBoard, components: ItemComponents) -> str | None:
    tank = find_tank(board.units, components, find_carry(board.units, components))
    return tank.character_id if tank else None


def comp_key(board: PlayerBoard, components: ItemComponents, by_trait: bool = False) -> CompKey:
    carry = find_carry(board.units, components)
    return CompKey(
        carry=carry.character_id if carry else None,
        main_trait=main_trait_id(board) if by_trait else None,
    )


def display_name(api_name: str | None, names: dict[str, str]) -> str:
    """Map an internal ID to its display name, falling back to the ID's last segment."""
    if api_name is None:
        return "None"
    return names.get(api_name, api_name.rsplit("_", 1)[-1])


def comp_label(comp: CompKey, names: dict[str, str]) -> str:
    carry = display_name(comp.carry, names) if comp.carry else "No carry"
    if comp.main_trait is None:
        return carry
    return f"{display_name(comp.main_trait, names)} {carry}"


def summarize_comps(
    boards: list[PlayerBoard], components: ItemComponents, by_trait: bool = False
) -> list[CompStats]:
    """Games, average placement, and top-4 rate per comp, most-played first."""
    groups: dict[CompKey, list[PlayerBoard]] = {}
    for board in boards:
        groups.setdefault(comp_key(board, components, by_trait), []).append(board)

    stats = []
    for comp, games in groups.items():
        places = [b.placement for b in games]
        tanks = Counter(t for b in games if (t := tank_id(b, components)) is not None)
        traits = Counter(t for b in games if (t := main_trait_id(b)) is not None)
        stats.append(
            CompStats(
                comp=comp,
                games=len(places),
                avg_placement=sum(places) / len(places),
                top4_rate=sum(1 for p in places if p <= 4) / len(places),
                usual_tank=tanks.most_common(1)[0][0] if tanks else None,
                usual_trait=traits.most_common(1)[0][0] if traits else None,
            )
        )
    return sorted(stats, key=lambda s: (-s.games, s.avg_placement))

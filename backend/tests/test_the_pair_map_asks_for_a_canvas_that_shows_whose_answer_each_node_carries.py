"""The pair map asks for a canvas that shows whose answer each node carries.

Stage 73 put the Compatibility Universe on the wire: ``GET /api/v1/matches/{match_id}/universe``
answers seven layers, and every node of every layer carries its two values, its ``has_data`` flag,
its connection and the evidence sentence built from those same two numbers. What no client could do
with that answer was draw it. The compatibility screen still ended at one percent per band, so the
map existed as a route and a document, not as a feature a pair can open — and the brief named that
exact failure: «не выдавай концепцию за реализованную функцию».

A canvas over this answer has three rules, and each is a product-integrity rule rather than a taste:

* it must not become a second engine. The percent of a band, its weight and its ``has_data`` flag
  travel from ``CompatibilityResult``; a client that recomputes them can show the pair two numbers
  for one pair, which is the asymmetry class stage 70 named for the matrix and stage 72-1 fixed for
  the empty category.
* ``unknown`` must be drawn as an absence. A trait one person never answered has no comparison to
  paint, and a stroke between two marks asserts a meeting the data never took part in — the same
  sentence «не показывай неизвестное как совпадение» the server-side guard holds.
* the two worlds are the pair's, not the requester's. ``a`` and ``b`` come back in the pair's own
  ``user_a``/``user_b`` order, so labelling the left world "me" would print my own name over my
  partner's answers for half of all pairs.

Red state on the tree before the client existed: the Kotlin files this file reads were not in the
working tree at all, so every check below failed on a missing path rather than on a wrong value.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
CLIENT = ROOT / "android/app/src/main/java/app/befos"
API_SERVICE = CLIENT / "data/remote/ApiService.kt"
REPOSITORIES = CLIENT / "domain/repository/Repositories.kt"
MATCH_REPO_IMPL = CLIENT / "data/repository/MatchRepositoryImpl.kt"
MAPPERS = CLIENT / "data/mapper/Mappers.kt"
MODELS = CLIENT / "domain/model/Models.kt"
LAYOUT = CLIENT / "presentation/universe/UniverseLayout.kt"
SCREEN = CLIENT / "presentation/universe/UniverseScreen.kt"
VIEW_MODEL = CLIENT / "presentation/universe/UniverseViewModel.kt"
ROUTES = CLIENT / "presentation/navigation/Routes.kt"
NAV_HOST = CLIENT / "presentation/navigation/BeFosNavHost.kt"
COMPATIBILITY_SCREEN = CLIENT / "presentation/compatibility/CompatibilityScreen.kt"
LAYOUT_TEST = ROOT / "android/app/src/test/java/app/befos/presentation/universe/UniverseLayoutTest.kt"
VIEW_MODEL_TEST = (
    ROOT / "android/app/src/test/java/app/befos/presentation/universe/UniverseViewModelTest.kt"
)

SECTION_TITLES = (
    "Что нас объединяет",
    "В чём мы дополняем друг друга",
    "Где ответы расходятся",
    "Что нам ещё предстоит узнать",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"{path.relative_to(ROOT)} is not in the working tree"
    return path.read_text(encoding="utf-8")


def test_the_client_asks_the_pair_route_for_the_map() -> None:
    """The canvas reads the universe endpoint, not a number invented next to it."""
    service = _read(API_SERVICE)
    assert re.search(r"suspend fun getUniverse\(", service) is not None, (
        "ApiService.kt declares no read of the pair map"
    )
    call = service[service.index("getUniverse") :]
    assert re.search(r'matches/\$matchId/universe', call[:400]) is not None, (
        "the map is requested from somewhere other than the pair's own universe route"
    )
    repos = _read(REPOSITORIES)
    assert re.search(r"suspend fun universe\(matchId: String\): ApiResult<Universe>", repos) is not None, (
        "MatchRepository publishes no universe call, so a screen cannot ask for the map through"
        " the layer every other pair read goes through"
    )
    impl = _read(MATCH_REPO_IMPL)
    assert re.search(r"api\.getUniverse\(matchId\)\.map \{ it\.toDomain\(\) \}", impl) is not None, (
        "the repository hands the screen a transport object instead of a domain one"
    )


def test_the_connection_arrives_as_four_kinds_and_a_miss_falls_to_unknown() -> None:
    """An unrecognised word must not be promoted to a meeting by a default that guesses."""
    models = _read(MODELS)
    enum = re.search(r"enum class Connection \{(?P<body>.*?)\n\}", models, re.S)
    assert enum is not None, "domain model has no Connection enum to key the map on"
    for kind in ("HARMONY", "COMPLEMENTARITY", "DISCUSSION", "UNKNOWN"):
        assert re.search(rf"^\s+{kind},", enum["body"], re.M) is not None, (
            f"Connection lost {kind}, and one of the four bands of the answer has no shape"
        )
    assert re.search(r"\?: UNKNOWN", models) is not None, (
        "an unknown word in the answer becomes something the server never said"
    )


def test_the_map_carries_the_layers_numbers_instead_of_rebuilding_them() -> None:
    """No arithmetic over a percent on the whole geometry file: positions read values, nothing else."""
    mappers = _read(MAPPERS)
    layer_mapper = re.search(
        r"fun UniverseLayerDto\.toDomain\(\)[^\n]*\n(?P<body>.*?\n\))", mappers, re.S
    )
    assert layer_mapper is not None, "Mappers.kt no longer maps a universe layer in one readable block"
    body = layer_mapper["body"]
    assert re.search(r"score = score", body) is not None, (
        "the band percent is not copied out of the answer"
    )
    assert re.search(r"hasData = hasData", body) is not None, (
        "the «there was nothing to measure» flag is dropped somewhere between the wire and the map"
    )
    assert re.search(r"coverage = coverage", body) is not None, (
        "coverage is not copied, so the screen has no way to keep it apart from the percent"
    )
    layout = _read(LAYOUT)
    assert re.search(r"\.score|\.weight|overall", layout) is None, (
        "UniverseLayout.kt reads a band number to build geometry: that is the second engine the"
        " brief forbade, and it can drift from the compatibility screen it is supposed to explain"
    )


def test_an_unknown_node_owns_a_shape_and_never_a_line() -> None:
    """The absence of a comparison is drawn, not described."""
    layout = _read(LAYOUT)
    link = re.search(r"fun linkOf\((?P<body>.*?)\n    \}", layout, re.S)
    assert link is not None, "UniverseLayout.kt no longer decides the stroke in one readable function"
    assert re.search(r"connection == Connection\.UNKNOWN -> LinkStyle\.NONE", link["body"]) is not None, (
        "an unknown node is drawn with a line between two marks"
    )
    assert re.search(r"!bothSides.*-> LinkStyle\.NONE", link["body"], re.S) is not None, (
        "a node with one answer gets a stroke anyway, which reads as a meeting nobody took part in"
    )
    shapes = re.search(r"fun shapeOf\((?P<body>.*?)\n    \}", layout, re.S)
    assert shapes is not None, "UniverseLayout.kt no longer maps a connection onto a shape"
    assert len(set(re.findall(r"MarkShape\.\w+", shapes["body"]))) == 4, (
        "the four connection types do not own four shapes, so the map reads by colour alone"
    )
    tested = _read(LAYOUT_TEST)
    assert "an uncomparable node gets one mark and no stroke" in tested, (
        "the JVM suite has no test that holds a one-sided node to one mark and no stroke"
    )


def test_a_mark_labels_the_answer_it_stands_for() -> None:
    """A number printed on a mark has to be the answered value, not the place it was drawn at.

    The mark's x is squeezed into the world's inset, so a percent read back from the coordinate is a
    number nobody answered: the build measured a 0.9 answer labelled 40. This is the rule «Нельзя
    возвращать произвольные объяснения, которые не связаны с данными» applied to the canvas itself.
    """
    layout = _read(LAYOUT)
    marks = re.search(r"val marks = buildList \{(?P<body>.*?)\n                    \}", layout, re.S)
    assert marks is not None, "UniverseLayout.kt no longer builds a node's marks in one readable block"
    assert "percentOf(node.aValue?.toFloat())" in marks["body"], (
        "the left mark is labelled with something other than the left answer"
    )
    assert "percentOf(node.bValue?.toFloat())" in marks["body"], (
        "the right mark is labelled with something other than the right answer"
    )
    assert re.search(r"percentOf\((?:it|ax|bx)\)", marks["body"]) is None, (
        "a mark is labelled with its own coordinate, which is a number the pair never answered"
    )
    screen = _read(SCREEN)
    assert re.search(r"drawMarkPercent\(", screen) is not None, (
        "the expanded row draws shapes without the answers they stand for"
    )
    layout_test = _read(LAYOUT_TEST)
    assert "a mark carries the answer it was drawn for, not its own coordinate" in layout_test, (
        "the JVM suite has no run that holds a mark to the answer it stands for, so the number on"
        " the canvas is only guarded by a regex over the source that produced it"
    )


def test_the_map_is_measured_at_the_widths_the_brief_names() -> None:
    """320dp, 360dp and 540dp are checked by a run, not promised by a fraction-based layout."""
    layout_test = _read(LAYOUT_TEST)
    assert re.search(r"320f, 360f, 411f, 540f", layout_test) is not None, (
        "no JVM pass walks the narrowest phone through a 540dp split, so «responsive» would be"
        " an assumption about unit-space geometry"
    )
    assert re.search(r"minOf\(420f, screenDp - 72f\)", layout_test) is not None, (
        "the measured canvas width ignores the gutters and the 420dp cap the screen draws with"
    )
    screen = _read(SCREEN)
    assert "widthIn(max = 420.dp)" in screen, (
        "the canvas stops being a 420dp-wide map and starts stretching across a tablet split"
    )


def test_the_screen_draws_the_map_on_a_canvas_from_the_layout() -> None:
    """The map is a canvas that reads the layout, not a list of numbers that replaced it."""
    screen = _read(SCREEN)
    assert re.search(r"Canvas\(", screen) is not None, "UniverseScreen.kt draws no canvas"
    assert "UniverseLayout.place(" in screen, "the screen builds its own geometry instead of the layout"
    assert "drawMark" in screen and "drawLink" in screen, (
        "marks or strokes are drawn without the shape and link rules the layout owns"
    )
    assert "detectTapGestures" in screen, (
        "no tap reaches a mark, so the evidence the node carries stays unreadable"
    )
    assert "nodeAt(" in screen, "the canvas hit-tests taps without the layout's own rule"


def test_the_four_sections_the_brief_names_are_on_the_screen() -> None:
    """Words the pair reads, keyed on the connection the server named."""
    screen = _read(SCREEN)
    for title in SECTION_TITLES:
        assert title in screen, f"UniverseScreen.kt lost the section «{title}»"
    assert re.search(r"Карта — это считанные ответы, а не диагноз", screen) is not None, (
        "the screen lets the map read as a verdict instead of a set of answers"
    )
    assert re.search(r"обязательно полезно для отношений", screen) is not None, (
        "nothing on the screen refuses the promise that a combination must be useful"
    )


def test_percent_and_coverage_stay_two_numbers_on_the_caption() -> None:
    """«нет данных» is not 0%, and a layer that compared one node of nine is not 100%."""
    screen = _read(SCREEN)
    caption = re.search(r"internal fun bandCaption\((?P<fn>.*?\n\})", screen, re.S)
    assert caption is not None, "the caption is no longer built in one readable function"
    assert re.search(r'if \(layer\.hasData\) "\$\{layer\.score\}%" else "нет данных"', caption["fn"]) is not None, (
        "a band the engine never measured is drawn with the percent the engine never measured"
    )
    assert re.search(r"сверено \$compared из \$total", caption["fn"]) is not None, (
        "coverage is missing beside the percent, so a band that compared one node of nine looks"
        " like a band that compared nine"
    )


def test_the_map_is_readable_without_sight_and_without_motion() -> None:
    """A canvas is not an accessible surface on its own, and motion is not a preference to ignore."""
    screen = _read(SCREEN)
    assert re.search(r"contentDescription = universeDescription\(state\)", screen) is not None, (
        "the canvas carries no spoken summary of what it drew"
    )
    description = re.search(r"internal fun universeDescription\((?P<fn>.*?\n\})", screen, re.S)
    assert description is not None, "the spoken summary is no longer built in one readable function"
    assert re.search(r"Connection\.entries\.forEach \{ kind ->", description["fn"]) is not None, (
        "the spoken text walks some list other than the four connection types, so a screen reader"
        " can be handed three of four bands"
    )
    assert "nodes.count { it.connection == kind }" in description["fn"], (
        "the spoken counts are not taken from the nodes the map actually drew"
    )
    assert "ANIMATOR_DURATION_SCALE" in screen, (
        "the map animates without asking whether the device is told not to"
    )


def test_a_pair_that_is_gone_is_not_offered_a_retry_that_cannot_work() -> None:
    """The same rule defect 72-11 wrote for the chat screen, applied to the map."""
    view_model = _read(VIEW_MODEL)
    assert re.search(r"val gone\b", view_model) is not None, (
        "UniverseUiState has no state of its own for a pair the server refuses"
    )
    assert re.search(r"gone = result\.code == 404", view_model) is not None, (
        "the refusal is reduced to its sentence, so a gone pair and a dropped network stay one state"
    )
    screen = _read(SCREEN)
    gone = re.search(r"state\.data == null && state\.gone ->(?P<body>.*?)(?=\n            state\.data == null ->)", screen, re.S)
    assert gone is not None, "UniverseScreen.kt draws the refused map as one undifferentiated error"
    assert "onRetry" not in gone["body"], "the gone branch hands out a retry button"
    assert "EmptyState(" in gone["body"], "a refused pair is drawn as an error rather than as an end"
    tested = _read(VIEW_MODEL_TEST)
    assert "a pair that no longer exists answers without a retry it cannot serve" in tested, (
        "the JVM suite never asks what a 404 does to the map"
    )


def test_the_worlds_are_named_by_the_ids_the_answer_carries() -> None:
    """``a`` is not the person holding the phone."""
    view_model = _read(VIEW_MODEL)
    assert re.search(r"aName = byId\[universe\.aUserId\]", view_model) is not None, (
        "the left world is labelled without asking whose id the server put there"
    )
    assert re.search(r"bName = byId\[universe\.bUserId\]", view_model) is not None, (
        "the right world is labelled without asking whose id the server put there"
    )
    tested = _read(VIEW_MODEL_TEST)
    assert re.search(
        r"the worlds are labelled by the ids the map carries, not by who is asking", tested
    ) is not None, (
        "no test puts the requester on the right hand side of the pair, which is where half of all"
        " pairs would notice"
    )


def test_the_pair_reaches_the_map_from_the_number_it_was_shown() -> None:
    """A feature nobody can walk to is still a concept."""
    routes = _read(ROUTES)
    assert re.search(r'const val UNIVERSE = "universe/\{\$CHAT_ARG\}"', routes) is not None, (
        "no route carries the map"
    )
    host = _read(NAV_HOST)
    assert re.search(r"route = Routes\.UNIVERSE", host) is not None, (
        "the route is declared but no graph composable answers it"
    )
    assert re.search(r"onOpenUniverse = \{ navController\.navigate\(Routes\.universe\(matchId\)\)", host) is not None, (
        "the compatibility screen is not given the way to open the map it explains"
    )
    screen = _read(COMPATIBILITY_SCREEN)
    assert re.search(r"onOpenUniverse: \(\) -> Unit", screen) is not None, (
        "CompatibilityScreen.kt takes no callback for the map"
    )
    assert re.search(r'"Открыть карту пары"', screen) is not None, (
        "the pair reads one percent per band with no control that reaches the answers behind it"
    )

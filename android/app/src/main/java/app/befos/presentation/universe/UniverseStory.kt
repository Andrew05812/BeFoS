package app.befos.presentation.universe

import app.befos.domain.model.UniverseLayer

/**
 * The one sentence that says what the map is not. It lives here instead of inside the composable
 * because all three readings need it — the map prints it under the canvas, the analysis under the
 * bands, the story carries it into whatever app the pair shares to — and a caveat that exists in two
 * copies is a caveat one of those copies eventually forgets.
 */
internal const val MAP_DISCLAIMER: String =
    "Карта — это считанные ответы, а не диагноз: она не утверждает, что такое сочетание " +
        "обязательно полезно для отношений."

/** First line of the artefact the pair sends out of the app. */
internal const val STORY_TITLE: String = "Наша карта совместимости"

/**
 * The shared reading, assembled from the sentences the engine wrote and nothing else. The story
 * arrives already stripped to aggregates; re-deriving it here would put a second source of the
 * pair's numbers on the client, and appending the names of the two worlds would hand back exactly
 * what stage 79.3 exists to keep out of a share.
 */
internal fun storyShareText(story: List<String>): String =
    (listOf(STORY_TITLE) + story + MAP_DISCLAIMER).joinToString("\n\n")

/**
 * Deep Analysis reads the bands heaviest first, the same order the engine tells the story in. The
 * percents themselves are never touched here: this only picks which band is shown next.
 */
internal fun analysisOrder(layers: List<UniverseLayer>): List<UniverseLayer> =
    layers.sortedByDescending { it.weight }

package app.befos.presentation.compatibility

import app.befos.core.designsystem.EmblemBand
import app.befos.core.designsystem.ScoreEmblemGeometry
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Compatibility
import app.befos.domain.model.Connection
import app.befos.domain.model.Explanation
import app.befos.presentation.common.bandUnmeasuredWord
import app.befos.presentation.common.categoryReadout
import app.befos.presentation.common.connectionKindWord
import kotlin.math.roundToInt

/**
 * The words the pair's compatibility screen puts on its own numbers, and the mapping from the engine's
 * document to the shapes the headline graphic draws.
 *
 * All of it is here rather than in the composable for two reasons: a person listening to this screen has
 * to be told the same thing the strip shows, and nothing on this surface may become a second opinion
 * about the pair's data. So these functions quote, format and select — they never add a number, a
 * threshold or a verdict of their own. The bands the engine left unmeasured stay unmeasured in every
 * sentence below, and a document that did not report its completeness gets no caption rather than an
 * invented one.
 */

/** The noun after «из N»: one band is «из 1 полосы», any count above it is «из N полос». */
internal fun bandsWord(total: Int): String = if (total == 1) "полосы" else "полос"

/**
 * How much of the result was actually compared, in the fewest words that carry it.
 *
 * Both counts come from the answer; this only puts them in Russian order. Null in, null out: a document
 * from before the fields carry no completeness, and «сверено 0 из 0 полос» would be a claim about a pair
 * the server never made. The zero case is spelled out because it is the one a reader must not miss — at
 * `0 из 7` the percent stands entirely on the engine's neutral half, which is the difference between a
 * result and a placeholder.
 */
internal fun completenessCaption(measured: Int?, total: Int?): String? = when {
    measured == null || total == null || total <= 0 -> null
    measured <= 0 -> "ни одна из $total ${bandsWord(total)} не сверена"
    else -> "сверено $measured из $total ${bandsWord(total)}"
}

/**
 * The share of the total's weight that compared bands carry, said as the engine wrote it.
 *
 * [measuredWeight] arrives as a fraction of 1, which is how the weights themselves are stored; only the
 * unit changes here. null means the answer never named one, and the screen then says nothing about weight
 * rather than printing the bands it happens to have.
 */
internal fun measuredWeightCaption(weight: Double?): String? = when {
    weight == null || !weight.isFinite() -> null
    else -> "сравнённые полосы покрывают ${(weight * 100).roundToInt()}% веса итога"
}

/**
 * The headline graphic's bands: the engine's weights, the engine's percents, and the engine's own flag for
 * whether a band was compared at all.
 *
 * The order is the answer's, and no band is dropped: a strip that quietly skipped the unmeasured bands
 * would show completeness by absence of evidence, which is the thing this graphic exists to make
 * visible.
 */
internal fun emblemBands(categories: List<CategoryScore>): List<EmblemBand> =
    categories.map { band ->
        EmblemBand(
            category = band.category,
            label = band.label,
            weight = band.weight,
            score = band.score,
            measured = band.hasData,
        )
    }

/** Which bands the strip is drawing as holes, by their own labels — for the sentence TalkBack reads. */
internal fun quietBandLabels(categories: List<CategoryScore>): List<String> =
    categories.filterNot { it.hasData }.map { it.label }

/** One spoken statement for the whole emblem, built from the same counts the strip is drawn from. */
internal fun emblemSpoken(data: Compatibility): String =
    ScoreEmblemGeometry.spokenDescription(
        percent = data.overall,
        caption = completenessCaption(data.bandsMeasured, data.bandsTotal),
        quietLabels = quietBandLabels(data.categories),
    )

/**
 * The kind of difference, or nothing when the answer did not name one.
 *
 * `connection` came to the phone with stage 125, and an explanation from an older answer carries none.
 * Those rows keep their sentence and lose the label: «расхождение» over a line the engine never classified
 * would be this build's opinion about two people's answers.
 */
internal fun explanationKindWord(connection: Connection): String? =
    if (connection == Connection.UNKNOWN) null else connectionKindWord(connection)

/**
 * What the kind is, said the way the engine means it.
 *
 * A difference between two answers is not an error in one of them, and the three words the backend uses
 * are easy to read as a grade — so each one gets the half-sentence that says what was compared. `unknown`
 * is absent by [explanationKindWord]'s rule and never reaches this branch on screen; it stays defined so
 * the mapping cannot fall through to a wrong hint if the screen ever learns to show it.
 */
internal fun explanationKindHint(connection: Connection): String = when (connection) {
    Connection.HARMONY -> "вы ответили в одной полосе"
    Connection.COMPLEMENTARITY -> "ответы разные, но не противоположные"
    Connection.DISCUSSION -> "ответы из противоположных полос — это разговор, а не ошибка"
    Connection.UNKNOWN -> "связь не названа"
}

/**
 * Whether this band was compared, in the words the rest of the app already uses for an unmeasured band.
 *
 * The screen quotes [categoryReadout] for the reading and [bandUnmeasuredWord] for the absence, because
 * «нет данных» and «полоса не сверена» are the two words a person sees in the row, in the caption under
 * the emblem, and here — and a third spelling of the same fact is how a pair starts doubting which
 * absence they are looking at.
 */
internal fun bandMeasuredWord(band: CategoryScore): String =
    if (band.hasData) {
        "полоса сверена — ${band.score}% близости ваших ответов"
    } else {
        "${categoryReadout(hasData = false, score = band.score)}: ${bandUnmeasuredWord()}"
    }

/**
 * What the number means for this pair, taken from the lines the engine wrote about this very band.
 *
 * Nothing is paraphrased and nothing is filled in: the sentences under [Compatibility.strengths] and
 * [Compatibility.differences] are the engine's own account of what it compared, and a band it said nothing
 * about is reported as a band it said nothing about. Empty is the honest answer, and the screen shows it
 * as one rather than leaving the row silent.
 */
internal fun bandMeaning(band: CategoryScore, lines: List<Explanation>): List<String> =
    lines.filter { it.category == band.category }.map { it.text }

/**
 * The line the detail panel shows when the engine named nothing about the band.
 *
 * Two different silences, and they must not read the same: a band nobody compared has no meaning to
 * report, while a measured band the engine left without sentences still holds a percent the pair cannot
 * yet connect to an answer.
 */
internal fun bandMeaningAbsenceWord(band: CategoryScore): String =
    if (band.hasData) {
        "движок не назвал ни одной причины в этой полосе — число есть, слов к нему нет"
    } else {
        "сверять было нечего, поэтому и причины здесь нет"
    }

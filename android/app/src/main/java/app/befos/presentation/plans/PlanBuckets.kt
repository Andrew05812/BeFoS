package app.befos.presentation.plans

import app.befos.domain.model.Plan
import app.befos.domain.model.PlanDecisions
import app.befos.domain.model.PlanStatuses
import app.befos.presentation.common.PLAN_PAST_WORD
import app.befos.presentation.common.planMomentPassed
import app.befos.presentation.recommendations.formatMeetingInstant
import java.time.ZonedDateTime

/**
 * The four questions the pair's plan screen answers with its sections.
 *
 * The buckets divide on what the pair holds rather than on a word the server printed: an arrangement
 * with a moment the pair stands on is a different thing to read than one still looking for it, and
 * «состоялось» belongs to nobody until both halves have said it. So the rule below looks at the hour
 * and at the pair's own answers, which is how the server arrived at the status it sent.
 */
enum class PlanBucket {
    AHEAD,
    AGREED,
    DONE,
    GONE,
}

data class PlanSection(
    val bucket: PlanBucket,
    val title: String,
    val caption: String,
    val plans: List<Plan>,
)

/**
 * Which section a plan belongs to.
 *
 * Ordered, and ordered against the server's own rule rather than beside it: a cancellation outranks
 * the hour that still sits in the pair's rows, and a meeting both of them confirmed outranks the
 * hour it happened at. An hour that has passed does not move a plan into «состоялось»: the clock is
 * not evidence about the physical world, and a screen that called a spent hour a kept one would
 * report a meeting the pair never confirmed.
 */
fun planBucketOf(plan: Plan): PlanBucket = when {
    plan.status == PlanStatuses.CANCELLED || plan.status == PlanStatuses.DECLINED -> PlanBucket.GONE
    plan.status == PlanStatuses.COMPLETED -> PlanBucket.DONE
    // A plan under a new hour does hold an hour, but not one the pair stands on: one of them has
    // asked to move it and the other has not answered. Reading its row as a договорённость would
    // present the hour being replaced as the current arrangement.
    plan.status == PlanStatuses.RESCHEDULED -> PlanBucket.AHEAD
    plan.startsAt != null -> PlanBucket.AGREED
    else -> PlanBucket.AHEAD
}

/** Section headings in the order the pair reads them, with empty ones left out. */
private data class SectionWords(val title: String, val caption: String)

private val SECTION_WORDS = mapOf(
    PlanBucket.AHEAD to SectionWords(
        "Предстоит",
        "Идея, о которой пара говорит, а час ещё не назван или ждёт ответа.",
    ),
    PlanBucket.AGREED to SectionWords(
        "Договорились",
        "Час, на котором пара стоит. Отметить встречу можно, только когда он прошёл.",
    ),
    PlanBucket.DONE to SectionWords(
        "Состоялось",
        "Обе половины сказали, что встреча была.",
    ),
    PlanBucket.GONE to SectionWords(
        "Отменено",
        "Отказ или отмена: час больше не держится, историю плана это не стирает.",
    ),
)

private val BUCKET_ORDER = listOf(PlanBucket.AHEAD, PlanBucket.AGREED, PlanBucket.DONE, PlanBucket.GONE)

/**
 * The plan list as sections. The order the server sent the plans in is kept inside each section —
 * the pair's own page is sorted by when the arrangement was made, and re-sorting it here would put
 * the screen's layout above the pair's history.
 */
fun planSections(plans: List<Plan>): List<PlanSection> =
    BUCKET_ORDER.mapNotNull { bucket ->
        val inBucket = plans.filter { planBucketOf(it) == bucket }
        if (inBucket.isEmpty()) {
            null
        } else {
            val words = SECTION_WORDS.getValue(bucket)
            PlanSection(bucket, words.title, words.caption, inBucket)
        }
    }

/**
 * What the card calls the state of the plan.
 *
 * One sentence per state, said from the fields the server already answers. The refusal names whose
 * it is, because the two halves are not answering the same question: the one who put the idea to the
 * pair is editing their own page, the other is answering the pair. A status this build does not know
 * says that on its face — a newer server cannot buy a confident sentence on a screen it cannot reach.
 */
fun planStatusWord(plan: Plan): String = when (plan.status) {
    PlanStatuses.CANCELLED -> "отменена"
    PlanStatuses.COMPLETED -> "встреча состоялась"
    PlanStatuses.DECLINED -> when {
        plan.myDecision == PlanDecisions.DECLINED && plan.partnerDecision == PlanDecisions.DECLINED ->
            "вы оба отклонили"
        plan.myDecision == PlanDecisions.DECLINED -> "вы отклонили"
        else -> "партнёр отклонил"
    }
    PlanStatuses.PLANNED -> when {
        // The hour the pair stood on is still the row's hour, but this person no longer stands behind
        // it — the answer they changed outranks the arrangement it came after, which is what the
        // server's own status rule says and what the card has to say with it.
        plan.myDecision == PlanDecisions.DECLINED -> "вы отказались от договорённости"
        plan.hourPassed -> "час прошёл"
        else -> "договорились"
    }
    PlanStatuses.RESCHEDULED ->
        if (plan.needsMyAnswer) "новый час ждёт вашего ответа" else "новый час ждёт ответа партнёра"
    PlanStatuses.PROPOSED -> when {
        plan.myDecision == PlanDecisions.DECLINED -> "вы отклонили, идея осталась у партнёра"
        // Whose word is in, and whose is missing, are one sentence rather than two fields the reader
        // has to line up: half a confirmation is the state the pair is actually in.
        plan.myDecision == PlanDecisions.JOINED -> "подтвердили вы, ждём ответа партнёра"
        plan.needsMyAnswer -> "ждёт вашего ответа"
        else -> "ждёт ответа партнёра"
    }
    PlanStatuses.ACCEPTED -> "подтверждена обоими, час не назван"
    else -> "состояние, которое эта версия приложения не читает"
}

/**
 * Whether this person's own answer is still being taken.
 *
 * One rule for both doors, because the pair's plan is closed to answers by the same event for both of
 * them: a plan the pair called off, or already lived through, is not something to stand behind again.
 * The server refuses these two taps with the same sentence it gives the plan's words, so the card hides
 * the doors rather than handing the person a tap that can only be refused — and stays silent about a
 * refusal this person has not made yet, which is theirs to make from the recommendation deck whatever
 * the plan's status.
 */
fun canAnswerPlan(plan: Plan): Boolean =
    plan.status != PlanStatuses.CANCELLED && plan.status != PlanStatuses.COMPLETED

/**
 * Why the answer doors are shut, or null while they are open.
 *
 * The card without buttons needs a sentence rather than an absence: «отменена» on the badge says what
 * the plan is, not that the person's own word was asked for and can no longer be given.
 */
fun planAnswerWord(plan: Plan): String? = when (plan.status) {
    PlanStatuses.CANCELLED -> "План отменён — подтверждать его больше нечего"
    PlanStatuses.COMPLETED -> "Встреча состоялась — подтверждать её больше нечего"
    else -> if (canAnswerPlan(plan)) null else "План закрыт — отвечать на него больше нечего"
}

/**
 * Whether this person's own word about the hour is still missing.
 *
 * The screen asks it of a plan whose hour is behind them, and the answer is what «Состоялось» means:
 * the pair reads one mark per half, and the plan becomes completed only under two of them.
 */
fun canMarkAttended(plan: Plan): Boolean =
    plan.status == PlanStatuses.PLANNED && plan.hourPassed && !plan.iAttended

/** Whether the tap that would move the hour is allowed on this card. */
fun canOfferHour(plan: Plan): Boolean =
    plan.status in setOf(PlanStatuses.PROPOSED, PlanStatuses.ACCEPTED, PlanStatuses.PLANNED, PlanStatuses.RESCHEDULED) &&
        plan.myDecision != PlanDecisions.DECLINED

/**
 * Whether this person may still write the pair's own words about the arrangement.
 *
 * Read off the buckets rather than off a status list: the two sections the pair still reads as
 * ahead of them have something left to arrange, and the meeting that happened or was called off does
 * not. The server keeps its own refusal of a closed plan for the case this screen could not see —
 * the other half cancelling while this card was open.
 */
fun canEditPlanWords(plan: Plan): Boolean =
    planBucketOf(plan) == PlanBucket.AHEAD || planBucketOf(plan) == PlanBucket.AGREED

/**
 * The two words of the pair, as the write that carries them.
 *
 * A field the person left as it was says nothing at all: the wire omits it, and the server reads an
 * omitted field as «не трогать». Erasing what is already written is a different act from writing
 * nothing, so it is said by its own flag rather than by an empty string — the server refuses a place
 * that is blank on purpose, and a card that sent one would turn «снять место» into a failed tap.
 */
data class PlanWordsEdit(
    val place: String? = null,
    val note: String? = null,
    val clearPlace: Boolean = false,
    val clearNote: Boolean = false,
) {
    /** True when neither field moved, so there is no request to send and no line to report. */
    val nothingChanged: Boolean get() = place == null && note == null && !clearPlace && !clearNote
}

/**
 * What the tap sends for the text this person just left in the two fields of the card.
 *
 * Compared against the row the page holds, not against empty: the card prefills both fields with what
 * the plan already says, so a person who edited only the note would otherwise send the place back
 * unchanged and turn a one-field save into a write over both. Whitespace is the same case from the
 * other side — a field rubbed clean leaves no text behind, and sending it as `""` would be the blank
 * place the server refuses; what happened is the erasure below.
 */
fun planWordsEdit(plan: Plan, placeText: String, noteText: String): PlanWordsEdit {
    val place = placeText.trim()
    val note = noteText.trim()
    return PlanWordsEdit(
        place = place.takeIf { it.isNotEmpty() && it != plan.place?.trim() },
        note = note.takeIf { it.isNotEmpty() && it != plan.note?.trim() },
        clearPlace = place.isEmpty() && !plan.place.isNullOrBlank(),
        clearNote = note.isEmpty() && !plan.note.isNullOrBlank(),
    )
}

/**
 * What the card calls the hour the row holds.
 *
 * The same instant means a different thing per state: on a plan the pair stands on it is the hour
 * they agreed to, on a rescheduled one it is the hour one of them has already asked to move, and on a
 * completed one it is the evening that happened. Saying «Договорились» over a plan whose hour the
 * pair is replacing would present the superseded arrangement as the current one, which is the mistake
 * this screen is built to avoid. Null when the plan holds no hour at all.
 */
fun planHourWord(plan: Plan, now: ZonedDateTime): String? {
    val hour = plan.startsAt ?: return null
    // The instant the wire carries is read on this person's calendar; a row this build cannot parse
    // is still shown as the server sent it rather than as an empty agreement.
    val moment = formatMeetingInstant(hour, now, now.zone).ifBlank { hour }
    val standing = planHourIsThePairWord(plan, now)
    val passed = planMomentPassed(hour, now)
    return when {
        plan.status == PlanStatuses.COMPLETED -> "Встреча была: $moment"
        // The badge on a called-off card already says «отменена», while an hour ahead of the clock
        // would still read as an agreement under the pair's feet. Cancellation is the one move that
        // retires an hour while the clock is behind it, so here the state names the sentence and the
        // passed hour adds nothing to it.
        plan.status == PlanStatuses.CANCELLED -> "Час был назван: $moment"
        // The hour stands in the pair's rows while the pair no longer stands on it: an answer changed
        // after the agreement leaves the moment behind, and a card that called it «договорились»
        // would promise an evening to a person who has just said they are not coming.
        plan.status == PlanStatuses.RESCHEDULED -> "Прежний час: $moment"
        !standing && passed -> "Договорились: $moment · $PLAN_PAST_WORD"
        !standing -> "Час был назван: $moment"
        else -> "Договорились: $moment"
    }
}

/**
 * Whether the hour the row holds is the hour the pair currently stands on.
 *
 * The card marks that hour with a check and leaves it selected; an evening that has been replaced,
 * outlived, called off or refused is the plan's history rather than its promise, and the same reading
 * has to hold whatever the chip is drawn with.
 */
fun planHourIsThePairWord(plan: Plan, now: ZonedDateTime): Boolean {
    val hour = plan.startsAt ?: return false
    if (plan.status == PlanStatuses.RESCHEDULED || plan.status == PlanStatuses.DECLINED ||
        plan.status == PlanStatuses.COMPLETED || plan.status == PlanStatuses.CANCELLED ||
        plan.myDecision == PlanDecisions.DECLINED
    ) {
        return false
    }
    return !planMomentPassed(hour, now)
}

/**
 * What the card says about the pair's own marks that the meeting happened, or null while neither of
 * them has said it.
 *
 * One mark per half: the plan turns «состоялось» only under both, so the sentence between those two
 * states names whose word is in and whose is still missing.
 */
fun planAttendanceWord(plan: Plan): String? = when {
    plan.iAttended && plan.partnerAttended -> "встречу подтвердили вы оба"
    plan.iAttended -> "вы отметили встречу, партнёр ещё нет"
    plan.partnerAttended -> "партнёр отметил встречу, ждёт вашего слова"
    else -> null
}

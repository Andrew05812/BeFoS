package app.befos.presentation.plans

import app.befos.domain.model.Plan
import app.befos.domain.model.PlanStatuses
import app.befos.presentation.common.planMomentPassed
import app.befos.presentation.recommendations.formatMeetingInstant
import java.time.Duration
import java.time.OffsetDateTime
import java.time.ZonedDateTime

/**
 * How long before the hour the pair is called back.
 *
 * One hour, not a day: a person who was told about an evening twenty-four hours ahead has the number
 * on the screen already, and by the time the day arrives the reminder has said nothing new. An hour is
 * the window in which the plan is still a thing somebody can leave the house for.
 */
val REMINDER_LEAD: Duration = Duration.ofMinutes(60)

/**
 * The local call-back one plan owes its pair.
 *
 * Carries its own words because the device layer posts what it is handed and cannot re-read the plan:
 * the alarm fires when the app may be nowhere near the pair's page, and a receiver that asked the
 * server for the sentence would be a reminder that depends on a network the person has already left.
 */
data class PlanReminder(
    val planId: String,
    val title: String,
    val text: String,
    val firesAt: ZonedDateTime,
)

/**
 * The reminder this plan owes, or null when it owes none.
 *
 * Only `planned` is an hour both halves stand on, and the server's own projection says so: a plan whose
 * `startsAt` is filled is named planned before anything else it could be. Every other state is a thing
 * nobody is on their way to — an idea not yet accepted, an offer waiting for an answer (`rescheduled`
 * is a plan whose agreed hour was taken back and a new one asked for, so it carries no `startsAt` at
 * all), a plan called off, a meeting both marked as kept.
 *
 * An instant this build cannot parse yields no reminder rather than a guessed one, for the same reason
 * the cards refuse to guess: a call at a wrong hour is worse than no call at all.
 */
fun reminderFor(plan: Plan, now: ZonedDateTime): PlanReminder? {
    if (plan.status != PlanStatuses.PLANNED) return null
    val iso = plan.startsAt ?: return null
    if (planMomentPassed(iso, now)) return null
    val agreed = runCatching { OffsetDateTime.parse(iso).atZoneSameInstant(now.zone) }.getOrNull()
        ?: return null
    val lead = agreed.minus(REMINDER_LEAD)
    // The hour itself, not the lead, is the last moment a call still reaches a person who can use it.
    val firesAt = if (lead.toInstant().isBefore(now.toInstant())) agreed else lead
    val whenWord = formatMeetingInstant(iso, now, now.zone)
    return PlanReminder(
        planId = plan.id,
        title = plan.title,
        text = if (firesAt == agreed) "Сейчас — $whenWord" else "Через час — $whenWord",
        firesAt = firesAt,
    )
}

/**
 * What the page says when an agreed hour is waiting and the app may not put a notice up.
 *
 * A reminder the pair never granted is not a promise the screen gets to keep quietly: the page names
 * what is missing and gives the one tap that fixes it.
 */
const val REMINDER_NEEDS_PERMISSION_WORD = "Напоминание о часе пары не придёт, пока приложению " +
    "не разрешат показывать уведомления."

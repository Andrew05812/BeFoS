package app.befos.presentation.plans

import app.befos.domain.model.Plan
import app.befos.domain.model.PlanStatuses
import app.befos.presentation.common.planMomentPassed
import app.befos.presentation.recommendations.formatMeetingInstant
import java.time.Duration
import java.time.Instant
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
 * Carries its own words because the alarm fires when the app may be nowhere near the pair's page and a
 * device with no signal is still a device the person is holding. It carries the hour it was written
 * about for the same reason the cards keep the instant they read: the moment the alarm wakes the device,
 * what the pair stands on has to be compared with what this sentence promises, because an hour the other
 * half moved while nobody opened the plans page left this sentence behind.
 */
data class PlanReminder(
    val planId: String,
    val title: String,
    val text: String,
    val firesAt: ZonedDateTime,
    val agreedHourIso: String,
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
        agreedHourIso = iso,
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

/**
 * What the device learned about the plan its alarm carries, at the moment the alarm woke it.
 *
 * An hour is written onto the clock by the plans page and spoken a day or two later, when the app may be
 * nowhere near that page and nobody has opened it since. The other half can move the evening, call it
 * off or let it pass in the meantime, and this device would still hold a notice about the hour the pair
 * no longer stands on.
 */
sealed interface PlanReading {
    /** The server answered for this plan, and the answer is the plan as the pair stands on it now. */
    data class Read(val plan: Plan) : PlanReading

    /** This plan is no longer this person's to be told about: it went, or the pair went with it. */
    data object Refused : PlanReading

    /**
     * Nothing was answered: no signal, no session left to ask with, a server that did not reply inside
     * the window the alarm gives the device.
     */
    data object Unreachable : PlanReading
}

/** What the device is allowed to say once it knows what it knows. */
sealed interface ReminderDelivery {
    data class Speak(val title: String, val text: String) : ReminderDelivery

    /**
     * This plan's own hour goes back onto the device's clock, and nothing is said about the old one.
     *
     * The alarm that woke the device was armed for an hour the pair no longer stands on, and the plans
     * page is not open to put the new one on. Without this case the moved evening would arrive as
     * nothing at all: the person loses the old hour to a correct silence and the new hour to a clock
     * nobody re-armed.
     */
    data class Rearm(val plan: Plan) : ReminderDelivery

    /** No notice at all: the hour this alarm was armed for is not the hour the pair stands on. */
    data object Silent : ReminderDelivery
}

/**
 * The word a notice adds to its hour when the server that could have confirmed it did not answer.
 */
const val REMINDER_NOT_VERIFIED_SUFFIX = "; этот час не удалось сверить с сервером"

/**
 * The sentence an armed alarm is allowed to speak, read against what the plan says now.
 *
 * A plan the device can see and that still owes a call is answered in one of two ways, and which one it
 * is comes down to a single comparison: the hour this alarm carries against the hour the pair stands on.
 * The same moment spoken in the plan's own words ends the alarm's life; a different one says nothing
 * about the evening nobody is standing at and puts the live hour back on the clock instead, because a
 * silence here would be the person losing both hours at once — the old one to a correct quiet and the
 * new one to an armed alarm that was never moved with it.
 *
 * Silence is the answer when the plan is known and owes no hour at all — a meeting the pair called off,
 * kept or let pass. An unreadable plan is the one case that speaks on its own risk: the hour was real
 * when it was written down, and a person standing on a threshold because the network was gone deserves
 * the notice with its doubt named more than a silent phone. Nothing is armed across that gap, because an
 * hour nobody confirmed is not a moment to wake a device for. The two hours are compared as moments
 * rather than as the characters the server happened to write them in, because a sentence this device
 * cannot place on a timeline is no more allowed to speak over a live hour than a moved one is.
 */
fun deliveryFor(armed: PlanReminder, reading: PlanReading, now: ZonedDateTime): ReminderDelivery =
    when (reading) {
        is PlanReading.Read -> readDelivery(armed, reading.plan, now)
        PlanReading.Refused -> ReminderDelivery.Silent
        PlanReading.Unreachable -> unverifiedDelivery(armed)
    }

/** The armed sentence read against the hour the pair stands on now. */
private fun readDelivery(armed: PlanReminder, plan: Plan, now: ZonedDateTime): ReminderDelivery {
    val current = reminderFor(plan, now) ?: return ReminderDelivery.Silent
    val armedHour = armed.agreedHourIso.toInstantOrNull() ?: return unverifiedDelivery(armed)
    return if (armedHour == current.agreedHourIso.toInstantOrNull())
        ReminderDelivery.Speak(current.title, current.text)
    else ReminderDelivery.Rearm(plan)
}

/** The hour was real when it was written down; the device says it and names that nothing confirmed it. */
private fun unverifiedDelivery(armed: PlanReminder) =
    ReminderDelivery.Speak(armed.title, armed.text + REMINDER_NOT_VERIFIED_SUFFIX)

/** The moment an hour string names, or null when this build cannot read it as one. */
private fun String.toInstantOrNull(): Instant? =
    runCatching { OffsetDateTime.parse(this).toInstant() }.getOrNull()

package app.befos.core.notifications

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import app.befos.BeFoSApplication
import app.befos.core.network.ApiResult
import app.befos.domain.repository.PlanRepository
import app.befos.presentation.plans.PlanReading
import app.befos.presentation.plans.PlanReminder
import app.befos.presentation.plans.ReminderDelivery
import app.befos.presentation.plans.deliveryFor
import java.time.ZonedDateTime
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout

/**
 * The device's wake-up for one plan's hour.
 *
 * A reminder has to arrive whether or not anybody left the app open, so the alarm cannot call a
 * ViewModel: this receiver is what the system reaches, and it carries the sentence the plans page wrote
 * when it set the alarm.
 *
 * That sentence is then read against the plan itself before it is spoken. The page arms an hour and the
 * pair can move it while nobody is on that page — an evening the other half called off or rescheduled
 * would otherwise arrive on this phone as news the person can still act on. So the alarm asks the server
 * for its own plan: what the pair no longer stands on says nothing here, and what could not be answered
 * says its hour with the doubt named in the same line.
 *
 * A moved evening is the one answer this wake gives rather than speaks. The alarm that woke the device
 * held the old hour, the page that would have re-armed it is not open, so silence alone would leave the
 * pair's new hour with no call at all: this receiver puts it back on the clock under the same plan id,
 * which is what makes the wake a move rather than the last sound the evening ever made.
 */
class PlanReminderReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val planId = intent.getStringExtra(PlanReminders.EXTRA_PLAN_ID) ?: return
        val title = intent.getStringExtra(PlanReminders.EXTRA_TITLE) ?: return
        val text = intent.getStringExtra(PlanReminders.EXTRA_TEXT) ?: return
        val agreedHour = intent.getStringExtra(PlanReminders.EXTRA_AGREED_HOUR) ?: return
        val armed = PlanReminder(
            planId = planId,
            title = title,
            text = text,
            // The alarm has just woken the device, so this is the moment the sentence belongs to.
            firesAt = ZonedDateTime.now(),
            agreedHourIso = agreedHour,
        )
        val repository = (context.applicationContext as BeFoSApplication).container.planRepository
        val wakeLockToken = goAsync()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        scope.launch {
            try {
                val reading = read(repository, planId)
                // One moment for both halves of this decision: what the delivery was read against is the
                // moment the new hour is armed from, so an evening the pair moved cannot be armed for a
                // lead this same wake has already walked past.
                val now = ZonedDateTime.now()
                when (val delivery = deliveryFor(armed, reading, now)) {
                    is ReminderDelivery.Speak ->
                        PlanReminders.post(context, planId, delivery.title, delivery.text)
                    // The page that armed this hour is not open, so the moved evening would be left with
                    // no call at all. Arming under the same plan id is what makes this a move rather than
                    // a second alarm for the same evening.
                    is ReminderDelivery.Rearm -> PlanReminders.sync(context, listOf(delivery.plan), now)
                    ReminderDelivery.Silent -> Unit
                }
            } finally {
                scope.cancel()
                wakeLockToken.finish()
            }
        }
    }

    /**
     * The plan as the server says it now, or the reason this device does not know.
     *
     * A refused read is a different answer than an unreadable one: the pair dissolved or the plan went,
     * and a notice about it would be old news. A session that has expired, a server that is silent and a
     * window that closed all leave the hour unproven rather than disproved, so they speak with the doubt
     * in the line instead of holding the person's evening back.
     */
    private suspend fun read(repository: PlanRepository, planId: String) =
        try {
            when (val result = withTimeout(READ_WINDOW_MS) { repository.plan(planId) }) {
                is ApiResult.Success -> PlanReading.Read(result.data)
                is ApiResult.Error ->
                    if (result.code in REFUSED_CODES) PlanReading.Refused else PlanReading.Unreachable
            }
        } catch (_: Exception) {
            PlanReading.Unreachable
        }

    private companion object {
        // The window the waking device gives the server to answer about one plan. The notice is a
        // courtesy, so a slow answer is not allowed to hold the phone awake past this moment.
        const val READ_WINDOW_MS = 8_000L

        // 403 and 404 are the server saying this plan is not this person's to be told about any more.
        val REFUSED_CODES = setOf(403, 404)
    }
}

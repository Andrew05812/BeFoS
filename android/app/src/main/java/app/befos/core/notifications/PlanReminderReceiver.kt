package app.befos.core.notifications

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * The device's wake-up for one plan's hour.
 *
 * A reminder has to arrive whether or not anybody left the app open, so the alarm cannot call a
 * ViewModel: this receiver is what the system reaches, and it carries the sentence the plans page wrote
 * when it set the alarm. Nothing is read from the server here — an hour the pair moved would have
 * replaced this request rather than waited behind it.
 */
class PlanReminderReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val planId = intent.getStringExtra(PlanReminders.EXTRA_PLAN_ID) ?: return
        val title = intent.getStringExtra(PlanReminders.EXTRA_TITLE) ?: return
        val text = intent.getStringExtra(PlanReminders.EXTRA_TEXT) ?: return
        PlanReminders.post(context, planId, title, text)
    }
}

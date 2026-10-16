package app.befos.core.notifications

import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import app.befos.MainActivity
import app.befos.R
import app.befos.domain.model.Plan
import app.befos.presentation.plans.reminderFor
import java.time.ZonedDateTime

/**
 * The pair's own notice, put on this device by this app.
 *
 * There is no push here and none is pretended at: the server holds no key for a messaging service, and
 * a reminder for an hour the person arranged on this phone is a thing this phone already knows. What
 * the device can do by itself is what this file does.
 */
object PlanReminders {

    private const val CHANNEL_ID = "befos.plan.reminder"
    private const val ACTION_REMIND = "app.befos.action.PLAN_REMIND"

    const val EXTRA_PLAN_ID = "app.befos.extra.PLAN_ID"
    const val EXTRA_TITLE = "app.befos.extra.TITLE"
    const val EXTRA_TEXT = "app.befos.extra.TEXT"

    /** Whether a notice this app posts can reach the person at all. */
    fun canPost(context: Context): Boolean =
        NotificationManagerCompat.from(context).areNotificationsEnabled()

    /**
     * Puts every reminder the pair's plans owe onto the device's clock and takes away the ones they no
     * longer owe.
     *
     * The list is walked whole rather than appended to. An hour the pair moved has to replace the alarm
     * for the same plan — one request code per plan id is what makes that a move rather than a second
     * call for the same evening — and a plan the pair called off or marked as kept has to lose its alarm
     * while it is still on the page to be named.
     *
     * `setAndAllowWhileIdle` is the API this uses on purpose. The exact-alarm permission would put the
     * person through a system screen for a notice that is a courtesy, and what skipping it costs is that
     * a dozing device may wake a few minutes late. The hour the pair arranged does not move; only the
     * moment the phone gets round to saying it can.
     */
    fun sync(context: Context, plans: List<Plan>, now: ZonedDateTime) {
        ensureChannel(context)
        val manager = context.getSystemService(AlarmManager::class.java) ?: return
        for (plan in plans) {
            val reminder = reminderFor(plan, now)
            if (reminder == null) {
                cancel(context, manager, plan.id)
            } else {
                manager.setAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP,
                    reminder.firesAt.toInstant().toEpochMilli(),
                    alarmFor(context, reminder.planId, reminder.title, reminder.text),
                )
            }
        }
    }

    /**
     * The notice an alarm hands to the system; the receiver below is its only caller.
     *
     * The tap opens the app rather than this plan's card: the route to a pair's page runs through the
     * screen the person was last on, and a reminder that started a navigation it could not finish would
     * be a tap that does nothing.
     */
    fun post(context: Context, planId: String, title: String, text: String) {
        ensureChannel(context)
        val open = Intent(context, MainActivity::class.java)
            .setAction(Intent.ACTION_MAIN)
            .addCategory(Intent.CATEGORY_LAUNCHER)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(title)
            .setContentText(text)
            .setAutoCancel(true)
            .setContentIntent(
                PendingIntent.getActivity(context, planId.hashCode(), open, pendingFlags()),
            )
            .build()
        // A device whose notifications the person switched off between the alarm and this moment is not
        // a failure to work around: there is no channel left to speak on. The hour itself is still on the
        // pair's page, which is where it was written down in the first place.
        runCatching { NotificationManagerCompat.from(context).notify(planId.hashCode(), notification) }
    }

    private fun cancel(context: Context, manager: AlarmManager, planId: String) {
        val existing = PendingIntent.getBroadcast(context, planId.hashCode(), bare(context, planId), noCreate())
            ?: return
        manager.cancel(existing)
        existing.cancel()
    }

    private fun alarmFor(context: Context, planId: String, title: String, text: String) =
        PendingIntent.getBroadcast(
            context,
            planId.hashCode(),
            bare(context, planId)
                .putExtra(EXTRA_PLAN_ID, planId)
                .putExtra(EXTRA_TITLE, title)
                .putExtra(EXTRA_TEXT, text),
            pendingFlags(),
        )

    // The data uri is what makes one plan's request its own: a PendingIntent compares the action, the
    // data, the type and the target class and ignores the extras, so without it a second plan's alarm
    // would replace the first one's instead of joining it.
    private fun bare(context: Context, planId: String) = Intent(context, PlanReminderReceiver::class.java)
        .setAction(ACTION_REMIND)
        .setData(Uri.parse("befos://plan/$planId"))

    private fun pendingFlags(): Int = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE

    private fun noCreate(): Int = PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE

    private fun ensureChannel(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Планы пары", NotificationManager.IMPORTANCE_DEFAULT),
        )
    }
}

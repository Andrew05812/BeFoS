package app.befos.core.designsystem

import android.view.HapticFeedbackConstants
import android.view.View
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.platform.LocalView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Semantic haptics — three named intensities instead of ad-hoc constants scattered
 * across screens. Devices without a vibrator simply no-op, so nothing here needs a
 * capability check.
 *
 * - [light]: a tick confirming a choice registered (answer selected, threshold crossed).
 * - [medium]: a commit — the action left the screen (like, pass, send).
 * - [success]: a double pulse reserved for outcomes worth celebrating (mutual match).
 *
 * Talks to [HapticFeedbackConstants] directly because the Compose wrapper of this UI
 * version only exposes the long-press channel.
 */
class Haptics internal constructor(
    private val view: View,
    private val scope: CoroutineScope,
) {
    fun light() {
        view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
    }

    fun medium() {
        view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
    }

    fun success() {
        scope.launch {
            medium()
            delay(110)
            medium()
        }
    }
}

@Composable
fun rememberHaptics(): Haptics {
    val view = LocalView.current
    val scope = rememberCoroutineScope()
    return remember(view, scope) { Haptics(view, scope) }
}

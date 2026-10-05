package app.befos.core.designsystem

import androidx.compose.foundation.text.KeyboardActionScope
import androidx.compose.ui.text.input.ImeAction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Where the keyboard's action key actually lands.
 *
 * Compose gives every IME action its own callback, and the primitive wired only `onDone`. So a
 * field that declared ImeAction.Next behaved differently depending on whether the screen also
 * passed a submit handler: the email field, with no handler, was advanced by the platform itself
 * (measured on emulator-5554: focus went from field 0 to field 1 with the keyboard still open),
 * while the register-mode password field, which does pass one, closed the keyboard and left
 * focus on the node between two fields. Both cases now route through the action the field named.
 *
 * Next and Previous are focus moves and never run the submit handler: submitting from the middle
 * of a three-field form fails on a field the user has not reached yet, so the key would report a
 * reason the user did not cause.
 */
class ImeActionRoutingTest {

    /**
     * Compose hands every action callback a scope, so the test presses the key the way the
     * keyboard does instead of calling a bare lambda. No route uses the scope's fallback: a
     * handler that leaned on it would be a handler that never moved focus anywhere.
     */
    private val scope = object : KeyboardActionScope {
        override fun defaultKeyboardAction(imeAction: ImeAction) = Unit
    }

    private fun press(imeAction: ImeAction, key: String): Set<String> {
        val seen = mutableSetOf<String>()
        val actions = imeActionsFor(
            imeAction = imeAction,
            onAction = { seen += "action" },
            onForward = { seen += "forward" },
            onBackward = { seen += "backward" },
        )
        when (key) {
            "next" -> actions.onNext?.invoke(scope)
            "previous" -> actions.onPrevious?.invoke(scope)
            "done" -> actions.onDone?.invoke(scope)
            "go" -> actions.onGo?.invoke(scope)
            "search" -> actions.onSearch?.invoke(scope)
            "send" -> actions.onSend?.invoke(scope)
        }
        return seen
    }

    @Test
    fun `next key moves focus and never submits`() {
        assertEquals(setOf("forward"), press(ImeAction.Next, "next"))
    }

    @Test
    fun `previous key moves focus backwards and never submits`() {
        assertEquals(setOf("backward"), press(ImeAction.Previous, "previous"))
    }

    /**
     * The case the sign-up password field is in: it declares Next and the screen still passes
     * a submit handler for the Done case. The declared action wins, so the arrow cannot fire a
     * registration the user did not ask for.
     */
    @Test
    fun `a declared Next outranks the submit handler`() {
        assertEquals(emptySet<String>(), press(ImeAction.Next, "done"))
        assertEquals(setOf("forward"), press(ImeAction.Next, "next"))
    }

    @Test
    fun `every completing action reaches the handler`() {
        listOf(
            ImeAction.Done to "done",
            ImeAction.Go to "go",
            ImeAction.Search to "search",
            ImeAction.Send to "send",
        ).forEach { (action, key) ->
            assertEquals(setOf("action"), press(action, key))
        }
    }

    @Test
    fun `only the declared action is wired`() {
        assertEquals(emptySet<String>(), press(ImeAction.Done, "next"))
        assertEquals(emptySet<String>(), press(ImeAction.Search, "done"))
        assertEquals(emptySet<String>(), press(ImeAction.Next, "previous"))
    }

    /**
     * Multi-line fields — «О себе», the chat composer — declare no action, and Enter must stay
     * a newline instead of being swallowed by a handler the screen never asked for.
     */
    @Test
    fun `unspecified actions are left to the keyboard`() {
        listOf(ImeAction.Default, ImeAction.None, ImeAction.Unspecified).forEach { action ->
            listOf("next", "previous", "done", "go", "search", "send").forEach { key ->
                assertTrue("$action / $key", press(action, key).isEmpty())
            }
        }
    }

    /**
     * A password field composes its reveal toggle inside its own row, so the next node in focus
     * traversal is an icon, not the next field: measured on the sign-up form, one forward step
     * from the password field landed on the toggle spanning x 397..463, y 549..615 and the
     * keyboard closed with it. The primitive owns that toggle, so it also counts it.
     */
    @Test
    fun `forward from a password field steps over its own toggle`() {
        assertEquals(2, imeForwardSteps(isPassword = true))
        assertEquals(1, imeForwardSteps(isPassword = false))
    }
}

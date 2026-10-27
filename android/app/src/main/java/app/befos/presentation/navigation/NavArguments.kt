package app.befos.presentation.navigation

import androidx.navigation.NavType
import androidx.navigation.NamedNavArgument
import androidx.navigation.navArgument

/**
 * The navigation graph's argument declarations, in one place the unit suite can reach.
 *
 * `NavHost` builds every destination while the app's first frame is composed, and an argument that the
 * library will not accept therefore does not fail a screen — it fails the process. `NavArgument` says
 * so with «integer does not allow nullable values» the moment its builder is asked to `build()`, which
 * is inside `navArgument { … }`, which is inside `composable(route, arguments = …)`. Nothing in this
 * module's tests ever composed `BeFosNavHost`, so a graph that died on the device passed 724 checks on
 * the JVM. Declaring the arguments here costs the host nine short calls and buys one test that builds
 * exactly what the first frame builds.
 */
internal object NavArguments {

    /** Every argument-carrying route of the graph, keyed by the route it is registered under. */
    fun byRoute(): Map<String, List<NamedNavArgument>> = linkedMapOf(
        Routes.TEST to test(),
        Routes.PUBLIC_PROFILE to publicProfile(),
        Routes.CHAT to chat(),
        Routes.COMPATIBILITY to compatibility(),
        Routes.PAIR to pair(),
        Routes.UNIVERSE to universe(),
        Routes.PARTNER to partner(),
        Routes.RECOMMENDATIONS to recommendations(),
        Routes.PLANS to plans(),
        Routes.PLAN_HISTORY to planHistory(),
    )

    /**
     * The band a compatibility screen sent the person in for. Nullable with no default, so a route
     * built without one opens the test where they stopped, as it did before.
     */
    fun test(): List<NamedNavArgument> = listOf(
        navArgument(Routes.SECTION_ARG) {
            type = NavType.StringType
            nullable = true
            defaultValue = null
        },
    )

    fun publicProfile(): List<NamedNavArgument> = listOf(
        navArgument(Routes.USER_ARG) { type = NavType.StringType },
    )

    /**
     * The thread to open, and the line a tap on the map left for the composer. The draft is nullable
     * with no default so a route built without one opens an empty field, exactly as it did before.
     */
    fun chat(): List<NamedNavArgument> = listOf(
        navArgument(Routes.CHAT_ARG) { type = NavType.StringType },
        navArgument(Routes.DRAFT_ARG) {
            type = NavType.StringType
            nullable = true
            defaultValue = null
        },
    )

    fun compatibility(): List<NamedNavArgument> = listOf(
        navArgument(Routes.CHAT_ARG) { type = NavType.StringType },
    )

    /**
     * The pair whose reading this is. One placeholder, one string, no optional value: the session on the
     * server says whose pair it is, and a route copied to another device reaches a 404 rather than
     * somebody else's reading.
     */
    fun pair(): List<NamedNavArgument> = listOf(
        navArgument(Routes.CHAT_ARG) { type = NavType.StringType },
    )

    fun universe(): List<NamedNavArgument> = listOf(
        navArgument(Routes.CHAT_ARG) { type = NavType.StringType },
    )

    fun partner(): List<NamedNavArgument> = listOf(
        navArgument(Routes.CHAT_ARG) { type = NavType.StringType },
    )

    /**
     * The page of ideas for one pair, and the idea it is asked to bring into view.
     *
     * A pair that taps its agreement in the chat arrives at the list of ideas for the same pair, and the
     * card the plan is about has to be the one under their eyes rather than somewhere down the list.
     * The idea is optional, so the plain route from the top bar still matches the same screen.
     *
     * It is declared as text, not as `NavType.IntType`: `NavArgument` refuses an int that may be absent
     * («integer does not allow nullable values»), and it refuses while `NavHost` registers this route —
     * which is the app's first frame, so the pair does not reach a page with no idea highlighted, they
     * reach no page at all. The digits are read back by [focusActivityId].
     */
    fun recommendations(): List<NamedNavArgument> = listOf(
        navArgument(Routes.CHAT_ARG) { type = NavType.StringType },
        navArgument(Routes.ACTIVITY_ARG) {
            type = NavType.StringType
            nullable = true
            defaultValue = null
        },
    )

    /** The thread to open and the plan to bring into view; the plan is optional. */
    fun plans(): List<NamedNavArgument> = listOf(
        navArgument(Routes.CHAT_ARG) { type = NavType.StringType },
        navArgument(Routes.PLAN_ARG) {
            type = NavType.StringType
            nullable = true
            defaultValue = null
        },
    )

    fun planHistory(): List<NamedNavArgument> = listOf(
        navArgument(Routes.PLAN_ARG) { type = NavType.StringType },
    )

    /**
     * The idea the route was built with, or `null` when it was built without one.
     *
     * Read from text rather than from `getInt`: an absent optional int answers 0 to the latter, and 0 is
     * a row the page would go looking for.
     */
    fun focusActivityId(raw: String?): Int? = raw?.toIntOrNull()
}

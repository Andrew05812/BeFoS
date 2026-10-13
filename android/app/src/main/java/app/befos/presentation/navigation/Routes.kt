package app.befos.presentation.navigation

object Routes {
    const val SPLASH = "splash"
    const val AUTH = "auth"
    const val ONBOARDING = "onboarding"
    const val TEST = "test"
    const val MAIN = "main"
    const val EDIT_PROFILE = "editProfile"
    const val SETTINGS = "settings"

    const val CHAT_ARG = "matchId"
    const val CHAT = "chat/{$CHAT_ARG}"
    fun chat(matchId: String) = "chat/$matchId"

    const val COMPATIBILITY = "compatibility/{$CHAT_ARG}"
    fun compatibility(matchId: String) = "compatibility/$matchId"

    // The same pair's answers, opened as a map instead of a percent: the compatibility screen
    // sums the seven bands, this one shows the two answers each sum was built from.
    const val UNIVERSE = "universe/{$CHAT_ARG}"
    fun universe(matchId: String) = "universe/$matchId"

    const val RECOMMENDATIONS = "recommendations/{$CHAT_ARG}"
    fun recommendations(matchId: String) = "recommendations/$matchId"

    const val USER_ARG = "userId"
    const val PUBLIC_PROFILE = "user/{$USER_ARG}"
    fun publicProfile(userId: String) = "user/$userId"

    // The same card, asked by the pair instead of by the deck: `GET /users/{id}` filters on
    // «Скрыть из подбора» on purpose, so a link built on the user id answers «Профиль недоступен»
    // to the person sitting in the chat the card was opened from.
    const val PARTNER = "partner/{$CHAT_ARG}"
    fun partner(matchId: String) = "partner/$matchId"
}

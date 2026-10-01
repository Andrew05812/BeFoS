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

    const val RECOMMENDATIONS = "recommendations/{$CHAT_ARG}"
    fun recommendations(matchId: String) = "recommendations/$matchId"

    const val USER_ARG = "userId"
    const val PUBLIC_PROFILE = "user/{$USER_ARG}"
    fun publicProfile(userId: String) = "user/$userId"
}

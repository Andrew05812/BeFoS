package app.befos.presentation.navigation

object Routes {
    const val SPLASH = "splash"
    const val AUTH = "auth"
    const val ONBOARDING = "onboarding"
    const val MAIN = "main"
    const val EDIT_PROFILE = "editProfile"
    const val SETTINGS = "settings"

    const val SECTION_ARG = "section"
    // The band the person came from, when the test was opened from a compatibility screen rather
    // than from the profile. Optional, so the plain «test» route still matches the same screen.
    const val TEST = "test?${SECTION_ARG}={$SECTION_ARG}"

    /** `section` is a catalogue key like `values`; a route built without one opens the whole test. */
    fun test(section: String? = null): String =
        if (section == null) "test?" else "test?$SECTION_ARG=$section"

    // The person's own compatibility profile, read back at any time. One route, no identifier: whose
    // profile it is comes from the session, and the finished questionnaire and the profile tab both
    // lead here rather than to a second copy of the same reading.
    const val MY_PROFILE = "myProfile"

    const val CHAT_ARG = "matchId"
    // A question the map hands to the composer. Optional, so a route built without one still matches
    // the same screen, and every caller that opens a thread pays the same single read it always did.
    const val DRAFT_ARG = "draft"
    // The parameter name is written out and only its value is a placeholder — the form the navigator
    // reads as «this query argument may be absent».
    const val CHAT = "chat/{$CHAT_ARG}?${DRAFT_ARG}={$DRAFT_ARG}"

    /** `draft` has to arrive already percent-encoded: the text it carries is a whole sentence. */
    fun chat(matchId: String, draft: String? = null): String =
        if (draft == null) "chat/$matchId" else "chat/$matchId?$DRAFT_ARG=$draft"

    const val COMPATIBILITY = "compatibility/{$CHAT_ARG}"
    fun compatibility(matchId: String) = "compatibility/$matchId"

    // The same pair's answers, opened as a map instead of a percent: the compatibility screen
    // sums the seven bands, this one shows the two answers each sum was built from.
    const val UNIVERSE = "universe/{$CHAT_ARG}"
    fun universe(matchId: String) = "universe/$matchId"

    // The idea the page is asked to bring into view. A pair that taps its agreement in the chat
    // arrives at the list of ideas for the same pair, and the card the plan is about has to be the
    // one under their eyes rather than somewhere down the list. Optional, so a route built without
    // one opens the page at its top, exactly as it did before this link existed.
    const val ACTIVITY_ARG = "activity"
    const val RECOMMENDATIONS = "recommendations/{$CHAT_ARG}?${ACTIVITY_ARG}={$ACTIVITY_ARG}"

    fun recommendations(matchId: String, activityId: Int? = null): String =
        if (activityId == null) "recommendations/$matchId" else "recommendations/$matchId?$ACTIVITY_ARG=$activityId"

    const val USER_ARG = "userId"
    const val PUBLIC_PROFILE = "user/{$USER_ARG}"
    fun publicProfile(userId: String) = "user/$userId"

    // The same card, asked by the pair instead of by the deck: `GET /users/{id}` filters on
    // «Скрыть из подбора» on purpose, so a link built on the user id answers «Профиль недоступен»
    // to the person sitting in the chat the card was opened from.
    const val PARTNER = "partner/{$CHAT_ARG}"
    fun partner(matchId: String) = "partner/$matchId"
}

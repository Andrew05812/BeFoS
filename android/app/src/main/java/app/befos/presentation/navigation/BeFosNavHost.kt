package app.befos.presentation.navigation

import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import app.befos.core.di.appContainer
import app.befos.core.di.beFosViewModel
import app.befos.presentation.auth.AuthScreen
import app.befos.presentation.chat.ChatScreen
import app.befos.presentation.compatibility.CompatibilityScreen
import app.befos.presentation.universe.UniverseScreen
import app.befos.presentation.editprofile.EditProfileScreen
import app.befos.presentation.main.MainScreen
import app.befos.presentation.onboarding.OnboardingScreen
import app.befos.presentation.profile.MyProfileScreen
import app.befos.presentation.publicprofile.PublicProfileScreen
import app.befos.presentation.recommendations.RecommendationsScreen
import app.befos.presentation.root.RootDestination
import app.befos.presentation.root.RootViewModel
import app.befos.presentation.root.SplashScreen
import app.befos.presentation.settings.SettingsScreen
import app.befos.presentation.test.TestScreen

@Composable
fun BeFosNavHost(navController: NavHostController) {
    val container = appContainer()
    val rootVm: RootViewModel = beFosViewModel { RootViewModel(it.authRepository, it.profileRepository) }
    val destination by rootVm.destination.collectAsState()

    // When the access token expires and the refresh is rejected, the client clears the
    // session. That leaves every screen showing «Сессия истекла. Войдите снова.» above a
    // «Повторить» button that can never succeed — so the clear itself routes to login.
    LaunchedEffect(container) {
        container.tokenStore.signedOut.collect {
            if (navController.currentDestination?.route == Routes.AUTH) return@collect
            navController.navigate(Routes.AUTH) {
                popUpTo(navController.graph.id) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    // Logging in must re-resolve the destination: a returning user who already
    // completed onboarding goes straight to MAIN, a fresh account to ONBOARDING.
    LaunchedEffect(destination) {
        if (navController.currentDestination?.route != Routes.AUTH) return@LaunchedEffect
        val target = when (destination) {
            RootDestination.MAIN -> Routes.MAIN
            RootDestination.ONBOARDING -> Routes.ONBOARDING
            else -> null
        } ?: return@LaunchedEffect
        navController.navigate(target) { popUpTo(Routes.AUTH) { inclusive = true } }
    }

    NavHost(navController = navController, startDestination = Routes.SPLASH) {
        composable(Routes.SPLASH) {
            SplashScreen(
                vm = rootVm,
                onRoute = { destination ->
                    val target = when (destination) {
                        RootDestination.AUTH -> Routes.AUTH
                        RootDestination.ONBOARDING -> Routes.ONBOARDING
                        else -> Routes.MAIN
                    }
                    navController.navigate(target) {
                        popUpTo(Routes.SPLASH) { inclusive = true }
                    }
                },
            )
        }

        composable(Routes.AUTH) {
            AuthScreen(
                onAuthed = { rootVm.resolve() },
            )
        }

        composable(Routes.ONBOARDING) {
            OnboardingScreen(
                onDone = {
                    navController.navigate(Routes.test()) {
                        popUpTo(Routes.ONBOARDING) { inclusive = true }
                    }
                },
            )
        }

        composable(
            route = Routes.TEST,
            arguments = listOf(
                // The band a compatibility screen sent the person in for. Nullable with no default,
                // so a route built without one opens the test where they stopped, as it did before.
                navArgument(Routes.SECTION_ARG) {
                    type = NavType.StringType
                    nullable = true
                    defaultValue = null
                },
            ),
        ) { entry ->
            TestScreen(
                startSection = entry.arguments?.getString(Routes.SECTION_ARG),
                onOpenProfile = { navController.navigate(Routes.MY_PROFILE) { launchSingleTop = true } },
                onFinished = {
                    // Re-test from Profile: return to the existing MAIN instead of stacking a second one.
                    if (!navController.popBackStack(Routes.MAIN, false)) {
                        navController.navigate(Routes.MAIN) {
                            popUpTo(Routes.TEST) { inclusive = true }
                        }
                    }
                },
            )
        }

        composable(Routes.MY_PROFILE) {
            MyProfileScreen(
                // Back goes where the person came from — the profile tab, or the questionnaire they
                // just finished — and nothing else: the screen has no second copy of that content to
                // fall back on.
                onBack = { navController.popBackStack() },
                onOpenTest = { section ->
                    navController.navigate(Routes.test(section)) { launchSingleTop = true }
                },
            )
        }

        composable(Routes.MAIN) {
            MainScreen(
                onOpenChat = { matchId -> navController.navigate(Routes.chat(matchId)) { launchSingleTop = true } },
                onOpenProfile = { userId -> navController.navigate(Routes.publicProfile(userId)) { launchSingleTop = true } },
                onEditProfile = { navController.navigate(Routes.EDIT_PROFILE) { launchSingleTop = true } },
                onOpenSettings = { navController.navigate(Routes.SETTINGS) { launchSingleTop = true } },
                onOpenTest = { navController.navigate(Routes.test()) { launchSingleTop = true } },
                onOpenMyProfile = { navController.navigate(Routes.MY_PROFILE) { launchSingleTop = true } },
                onLoggedOut = {
                    navController.navigate(Routes.AUTH) {
                        popUpTo(Routes.MAIN) { inclusive = true }
                    }
                },
            )
        }

        composable(Routes.EDIT_PROFILE) {
            EditProfileScreen(onBack = { navController.popBackStack() })
        }

        composable(Routes.SETTINGS) {
            SettingsScreen(
                onBack = { navController.popBackStack() },
                onLoggedOut = {
                    navController.navigate(Routes.AUTH) {
                        // Drop SETTINGS *and* MAIN so back from AUTH cannot resurrect a logged-out stack.
                        popUpTo(Routes.MAIN) { inclusive = true }
                    }
                },
            )
        }

        composable(
            route = Routes.PUBLIC_PROFILE,
            arguments = listOf(navArgument(Routes.USER_ARG) { type = NavType.StringType }),
        ) { entry ->
            val userId = entry.arguments?.getString(Routes.USER_ARG).orEmpty()
            PublicProfileScreen(
                userId = userId,
                onBack = { navController.popBackStack() },
                // An empty band on someone else's card is explained by the reader's own counts, so the
                // card has to reach both places those counts live in: the section of the questionnaire
                // and the profile fields the interests and the goal come from.
                onOpenSection = { section ->
                    navController.navigate(Routes.test(section)) { launchSingleTop = true }
                },
                onEditProfile = { navController.navigate(Routes.EDIT_PROFILE) { launchSingleTop = true } },
                onOpenChat = { matchId ->
                    navController.navigate(Routes.chat(matchId)) { launchSingleTop = true }
                },
            )
        }

        composable(
            route = Routes.CHAT,
            arguments = listOf(
                navArgument(Routes.CHAT_ARG) { type = NavType.StringType },
                // The line a tap on the map left for the composer. Nullable with no default so a
                // route built without one opens an empty field, exactly as it did before.
                navArgument(Routes.DRAFT_ARG) {
                    type = NavType.StringType
                    nullable = true
                    defaultValue = null
                },
            ),
        ) { entry ->
            val matchId = entry.arguments?.getString(Routes.CHAT_ARG).orEmpty()
            ChatScreen(
                matchId = matchId,
                initialDraft = entry.arguments?.getString(Routes.DRAFT_ARG),
                onBack = { navController.popBackStack() },
                onOpenCompatibility = { navController.navigate(Routes.compatibility(matchId)) { launchSingleTop = true } },
                onOpenRecommendations = { navController.navigate(Routes.recommendations(matchId)) { launchSingleTop = true } },
                // A plan line names the idea it was about, and the pair tapping it wants that card,
                // not the top of the list; an unknown idea still opens the page rather than dying.
                onOpenPlan = { activityId ->
                    navController.navigate(Routes.recommendations(matchId, activityId)) { launchSingleTop = true }
                },
                // Keyed by the pair, not by the person: the card of a partner who pressed
                // «Скрыть из подбора» answers here and 404s on the deck route.
                onOpenPartnerCard = { navController.navigate(Routes.partner(matchId)) { launchSingleTop = true } },
            )
        }

        composable(
            route = Routes.PARTNER,
            arguments = listOf(navArgument(Routes.CHAT_ARG) { type = NavType.StringType }),
        ) { entry ->
            val matchId = entry.arguments?.getString(Routes.CHAT_ARG).orEmpty()
            PublicProfileScreen(
                userId = "",
                matchId = matchId,
                onBack = { navController.popBackStack() },
                // The partner's card opened from a chat is the same pair readout as the card opened
                // from Discovery, so it explains an empty band with the same words and offers the same
                // two ways out; a second copy of this screen with only one of them would drift.
                onOpenSection = { section ->
                    navController.navigate(Routes.test(section)) { launchSingleTop = true }
                },
                onEditProfile = { navController.navigate(Routes.EDIT_PROFILE) { launchSingleTop = true } },
                onOpenChat = { id -> navController.navigate(Routes.chat(id)) { launchSingleTop = true } },
            )
        }

        composable(
            route = Routes.COMPATIBILITY,
            arguments = listOf(navArgument(Routes.CHAT_ARG) { type = NavType.StringType }),
        ) { entry ->
            val matchId = entry.arguments?.getString(Routes.CHAT_ARG).orEmpty()
            CompatibilityScreen(
                matchId = matchId,
                onBack = { navController.popBackStack() },
                onOpenUniverse = { navController.navigate(Routes.universe(matchId)) { launchSingleTop = true } },
                // The band names the section of the questionnaire that would have filled it, and the
                // tap opens the test at that section instead of at its beginning.
                onOpenSection = { section ->
                    navController.navigate(Routes.test(section)) { launchSingleTop = true }
                },
                onEditProfile = { navController.navigate(Routes.EDIT_PROFILE) { launchSingleTop = true } },
                // The bands on this screen are the reader's own answers averaged against someone
                // else's; the reading that belongs to her alone is the one screen the caption points
                // at, and it is already on this graph under its own route.
                onOpenMyProfile = { navController.navigate(Routes.MY_PROFILE) { launchSingleTop = true } },
            )
        }

        composable(
            route = Routes.UNIVERSE,
            arguments = listOf(navArgument(Routes.CHAT_ARG) { type = NavType.StringType }),
        ) { entry ->
            val matchId = entry.arguments?.getString(Routes.CHAT_ARG).orEmpty()
            UniverseScreen(
                matchId = matchId,
                onBack = { navController.popBackStack() },
                // The draft travels as text, encoded: it is a whole sentence, and a route is a URI.
                onAskInChat = { draft ->
                    navController.navigate(Routes.chat(matchId, Uri.encode(draft))) {
                        launchSingleTop = true
                    }
                },
                onOpenRecommendations = {
                    navController.navigate(Routes.recommendations(matchId)) { launchSingleTop = true }
                },
            )
        }

        composable(
            route = Routes.RECOMMENDATIONS,
            arguments = listOf(
                navArgument(Routes.CHAT_ARG) { type = NavType.StringType },
                navArgument(Routes.ACTIVITY_ARG) {
                    type = NavType.IntType
                    nullable = true
                    defaultValue = null
                },
            ),
        ) { entry ->
            val matchId = entry.arguments?.getString(Routes.CHAT_ARG).orEmpty()
            RecommendationsScreen(
                matchId = matchId,
                // The idea a plan line in the chat was about, or null when the page was opened from
                // the top bar and has nothing to bring into view. Read with `get` rather than
                // `getInt`: an absent optional int answers 0 to the latter, and 0 is a row the page
                // would go looking for.
                focusActivityId = entry.arguments?.get(Routes.ACTIVITY_ARG) as? Int,
                onBack = { navController.popBackStack() },
            )
        }
    }
}

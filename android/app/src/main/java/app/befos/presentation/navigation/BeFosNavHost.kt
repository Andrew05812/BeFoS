package app.befos.presentation.navigation

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
import app.befos.presentation.editprofile.EditProfileScreen
import app.befos.presentation.main.MainScreen
import app.befos.presentation.onboarding.OnboardingScreen
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
                    navController.navigate(Routes.TEST) {
                        popUpTo(Routes.ONBOARDING) { inclusive = true }
                    }
                },
            )
        }

        composable(Routes.TEST) {
            TestScreen(
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

        composable(Routes.MAIN) {
            MainScreen(
                onOpenChat = { matchId -> navController.navigate(Routes.chat(matchId)) { launchSingleTop = true } },
                onOpenProfile = { userId -> navController.navigate(Routes.publicProfile(userId)) { launchSingleTop = true } },
                onEditProfile = { navController.navigate(Routes.EDIT_PROFILE) { launchSingleTop = true } },
                onOpenSettings = { navController.navigate(Routes.SETTINGS) { launchSingleTop = true } },
                onOpenTest = { navController.navigate(Routes.TEST) { launchSingleTop = true } },
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
                onOpenChat = { matchId ->
                    navController.navigate(Routes.chat(matchId)) { launchSingleTop = true }
                },
            )
        }

        composable(
            route = Routes.CHAT,
            arguments = listOf(navArgument(Routes.CHAT_ARG) { type = NavType.StringType }),
        ) { entry ->
            val matchId = entry.arguments?.getString(Routes.CHAT_ARG).orEmpty()
            ChatScreen(
                matchId = matchId,
                onBack = { navController.popBackStack() },
                onOpenCompatibility = { navController.navigate(Routes.compatibility(matchId)) { launchSingleTop = true } },
                onOpenRecommendations = { navController.navigate(Routes.recommendations(matchId)) { launchSingleTop = true } },
            )
        }

        composable(
            route = Routes.COMPATIBILITY,
            arguments = listOf(navArgument(Routes.CHAT_ARG) { type = NavType.StringType }),
        ) { entry ->
            val matchId = entry.arguments?.getString(Routes.CHAT_ARG).orEmpty()
            CompatibilityScreen(matchId = matchId, onBack = { navController.popBackStack() })
        }

        composable(
            route = Routes.RECOMMENDATIONS,
            arguments = listOf(navArgument(Routes.CHAT_ARG) { type = NavType.StringType }),
        ) { entry ->
            val matchId = entry.arguments?.getString(Routes.CHAT_ARG).orEmpty()
            RecommendationsScreen(matchId = matchId, onBack = { navController.popBackStack() })
        }
    }
}

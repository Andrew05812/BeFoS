package app.befos.presentation.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import app.befos.presentation.auth.AuthScreen
import app.befos.presentation.chat.ChatScreen
import app.befos.presentation.compatibility.CompatibilityScreen
import app.befos.presentation.editprofile.EditProfileScreen
import app.befos.presentation.main.MainScreen
import app.befos.presentation.onboarding.OnboardingScreen
import app.befos.presentation.publicprofile.PublicProfileScreen
import app.befos.presentation.recommendations.RecommendationsScreen
import app.befos.presentation.root.RootDestination
import app.befos.presentation.root.SplashScreen
import app.befos.presentation.settings.SettingsScreen
import app.befos.presentation.test.TestScreen

@Composable
fun BeFosNavHost(navController: NavHostController) {
    NavHost(navController = navController, startDestination = Routes.SPLASH) {
        composable(Routes.SPLASH) {
            SplashScreen(
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
                onAuthed = {
                    navController.navigate(Routes.ONBOARDING) {
                        popUpTo(Routes.AUTH) { inclusive = true }
                    }
                },
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
                    navController.navigate(Routes.MAIN) {
                        popUpTo(Routes.TEST) { inclusive = true }
                    }
                },
            )
        }

        composable(Routes.MAIN) {
            MainScreen(
                onOpenChat = { matchId -> navController.navigate(Routes.chat(matchId)) },
                onOpenProfile = { userId -> navController.navigate(Routes.publicProfile(userId)) },
                onEditProfile = { navController.navigate(Routes.EDIT_PROFILE) },
                onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                onOpenTest = { navController.navigate(Routes.TEST) },
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
                        popUpTo(Routes.SETTINGS) { inclusive = true }
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
                    navController.navigate(Routes.chat(matchId))
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
                onOpenCompatibility = { navController.navigate(Routes.compatibility(matchId)) },
                onOpenRecommendations = { navController.navigate(Routes.recommendations(matchId)) },
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

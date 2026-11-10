package app.befos

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.navigation.compose.rememberNavController
import app.befos.core.designsystem.BeFosTheme
import app.befos.core.di.AppContainer
import app.befos.presentation.navigation.BeFosNavHost

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        openInvitation(intent)
        setContent {
            BeFosTheme(darkTheme = isSystemInDarkTheme()) {
                BeFosNavHost(rememberNavController())
            }
        }
    }

    /**
     * A link arriving while the app is already open: the same door as a cold start, without a second
     * task and without a second splash. `singleTop` in the manifest is what lets this callback exist.
     */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        openInvitation(intent)
    }

    /**
     * `befos://invite/<code>` is the only link this app claims. The code is kept as-is; whether it is
     * live is the server's answer on the landing screen, not this parser's guess — a parser that
     * rejected an expired code would have to know the invitation table, and an app that knows it
     * is an app that can be asked about somebody else's row.
     */
    private fun openInvitation(intent: Intent?) {
        val code = app.befos.core.invite.InvitationLink.code(intent?.dataString) ?: return
        container.openInvite(code)
    }

    private val container: AppContainer
        get() = (application as BeFoSApplication).container
}

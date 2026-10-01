package app.befos

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.navigation.compose.rememberNavController
import app.befos.core.designsystem.BeFosTheme
import app.befos.presentation.navigation.BeFosNavHost

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent {
            BeFosTheme(darkTheme = isSystemInDarkTheme()) {
                BeFosNavHost(rememberNavController())
            }
        }
    }
}

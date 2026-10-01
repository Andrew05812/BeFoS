package app.befos.core.designsystem

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

private val LightColors = lightColorScheme(
    primary = Coral,
    onPrimary = CreamSurface,
    primaryContainer = Color(0xFFFFE1DE),
    onPrimaryContainer = CoralDark,
    secondary = Violet,
    onSecondary = CreamSurface,
    secondaryContainer = Color(0xFFE7E0FF),
    onSecondaryContainer = VioletDark,
    tertiary = Peach,
    onTertiary = Color(0xFF3A2312),
    background = CreamBackground,
    onBackground = InkPrimary,
    surface = CreamSurface,
    onSurface = InkPrimary,
    surfaceVariant = CreamSurfaceVariant,
    onSurfaceVariant = InkSecondary,
    outline = Color(0xFFE2D6D2),
    error = ErrorRed,
    onError = CreamSurface,
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFFF8A8F),
    onPrimary = Color(0xFF3A0A10),
    primaryContainer = Color(0xFF5C1F26),
    onPrimaryContainer = Color(0xFFFFDAD6),
    secondary = Color(0xFFB9A6FF),
    onSecondary = Color(0xFF1E1140),
    secondaryContainer = Color(0xFF3A2A6B),
    onSecondaryContainer = Color(0xFFE7E0FF),
    tertiary = Peach,
    onTertiary = Color(0xFF3A2312),
    background = NightBackground,
    onBackground = NightInk,
    surface = NightSurface,
    onSurface = NightInk,
    surfaceVariant = NightSurfaceVariant,
    onSurfaceVariant = NightInkSecondary,
    outline = Color(0xFF3A3142),
    error = Color(0xFFFF8A8F),
    onError = Color(0xFF3A0A10),
)

val BeFosShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(18.dp),
    large = RoundedCornerShape(26.dp),
    extraLarge = RoundedCornerShape(34.dp),
)

@Composable
fun BeFosTheme(
    darkTheme: Boolean = false,
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = BeFosTypography,
        shapes = BeFosShapes,
        content = content,
    )
}

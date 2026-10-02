package app.befos.core.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.dp

/**
 * Frosted-glass surface used over photos: translucent white fill + hairline
 * light border. Keeps text legible without opaque panels on imagery.
 */
@Composable
fun Modifier.glassSurface(shape: Shape = RoundedCornerShape(18.dp)): Modifier =
    this
        .clip(shape)
        .background(Color.White.copy(alpha = 0.16f))
        .border(1.dp, Color.White.copy(alpha = 0.28f), shape)

/** Minimal photo+name pair for decorative card layers (preview stack behind the active card). */
data class DiscoveryCardData(val photoUrl: String?, val name: String)

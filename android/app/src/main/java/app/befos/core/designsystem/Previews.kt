package app.befos.core.designsystem

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

/**
 * Design-system previews for the components every screen is built from.
 * View in Android Studio: app > ...designsystem > Previews.kt.
 */
@Preview(showBackground = true, widthDp = 360)
@Composable
private fun AppButtonVariantsPreview() {
    BeFosTheme {
        Column(
            modifier = Modifier.padding(Spacing.gutter),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            AppButton(text = "Нравится", onClick = {})
            AppButton(text = "Пропустить", onClick = {}, variant = AppButtonVariant.Tonal)
            AppButton(text = "Позже", onClick = {}, variant = AppButtonVariant.Ghost)
            AppButton(text = "Загрузка", onClick = {}, loading = true)
        }
    }
}

@Preview(showBackground = true, widthDp = 360)
@Composable
private fun ScoreAndChipsPreview() {
    BeFosTheme {
        Column(
            modifier = Modifier.padding(Spacing.gutter),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            CompatibilityScore(percent = 78, size = 92.dp, strokeWidth = 8.dp)
            CompatibilityBadge(percent = 64, compact = false)
            InterestChip(label = "Походы", selected = true, onClick = {})
            InterestChip(label = "Джаз")
            AppTextField(value = "Андрей", onValueChange = {}, label = "Имя")
        }
    }
}

@Preview(showBackground = true, widthDp = 360)
@Composable
private fun MessageBubblePreview() {
    BeFosTheme {
        Column(
            modifier = Modifier.padding(Spacing.gutter),
            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            MessageBubble(body = "Привет! Как насчёт кофе?", isOwn = false, footer = "12:04")
            MessageBubble(body = "Только за! Где красивое место?", isOwn = true, footer = "прочитано")
        }
    }
}

@Preview(showBackground = true, widthDp = 320, heightDp = 480)
@Composable
private fun EmptyStatePreview() {
    BeFosTheme {
        EmptyState(
            title = "Пар пока нет",
            message = "Когда вы и другой человек поставите друг другу «Нравится», здесь появится пара.",
            overline = "Пары",
        )
    }
}

@Preview(showBackground = true, widthDp = 360)
@Composable
private fun MatchCardPreview() {
    BeFosTheme {
        MatchCard(
            photoUrl = null,
            name = "Алина, 24",
            subtitle = "Привет! Как дела?",
            compatibility = 81,
            unread = 2,
            onClick = {},
        )
    }
}

@Preview(showBackground = true, widthDp = 360)
@Composable
private fun TypeScalePreview() {
    BeFosTheme {
        Column(modifier = Modifier.padding(Spacing.gutter), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Display", style = MaterialTheme.typography.displaySmall)
            Text("Headline", style = MaterialTheme.typography.headlineMedium)
            Text("Title", style = MaterialTheme.typography.titleLarge)
            Text("Body — основной текст анкеты", style = MaterialTheme.typography.bodyLarge)
            Text("Secondary text", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("OVERLINE", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

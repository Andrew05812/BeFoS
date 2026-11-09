package app.befos.presentation.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.Spacing
import app.befos.domain.model.ConsentDocument

/**
 * The text the account accepts, the version it is accepting, and the one check that makes the door
 * open.
 *
 * The words come from the server and are drawn inside a bounded, scrolled box: a document that pushes
 * the two password fields off the screen turns reading it into a hunt. `toggleable` on the whole row,
 * rather than a bare checkbox, is what gives the label a touch target and TalkBack its state — the
 * same reason the checkbox itself is drawn without its own callback.
 */
@Composable
fun ConsentPanel(
    document: ConsentDocument?,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    loading: Boolean,
    error: String?,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Text(
            text = "Что вы принимаете",
            style = MaterialTheme.typography.titleSmall,
            color = MaterialTheme.colorScheme.onBackground,
        )
        if (document == null) {
            Text(
                text = when {
                    loading -> "Загружаем текст согласия…"
                    error != null -> "Текст согласия не загрузился. Проверьте связь и попробуйте ещё раз."
                    else -> "Текст согласия не загрузился. Проверьте связь."
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            return@Column
        }
        Text(
            text = document.text,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 220.dp)
                .clip(MaterialTheme.shapes.medium)
                .background(MaterialTheme.colorScheme.surfaceVariant)
                .padding(Spacing.md)
                .verticalScroll(rememberScrollState()),
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .toggleable(
                    value = checked,
                    enabled = !loading,
                    role = Role.Checkbox,
                    onValueChange = onCheckedChange,
                ),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Checkbox(checked = checked, onCheckedChange = null)
            Text(
                text = "Мне есть 18 лет. Я прочитал(а) и принимаю этот текст.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.padding(start = Spacing.sm),
            )
        }
        Text(
            text = "Версия ${document.version} · ${document.effectiveDate}",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

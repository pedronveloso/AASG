package io.github.pedronveloso.aasg

import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiFile
import org.jetbrains.yaml.psi.YAMLDocument
import org.jetbrains.yaml.psi.YAMLKeyValue
import org.jetbrains.yaml.psi.YAMLMapping
import org.jetbrains.yaml.psi.YAMLScalar

internal object AasgYaml {
    fun isConfig(file: PsiFile): Boolean = isConfigName(file.name)

    fun isConfigName(name: String): Boolean = name == "aasg.yaml" || name == "aasg.yml"

    fun isRunner(scalar: YAMLScalar): Boolean =
        path(scalar) == listOf("android", "direct_instrumentation", "runner")

    fun isReference(scalar: YAMLScalar): Boolean {
        if (!isConfig(scalar.containingFile) || scalar.isMultiline) return false
        val path = path(scalar)
        return (path.size == 3 && path[0] == "captures" && path[2] == "test") || isRunner(scalar)
    }

    private fun path(scalar: YAMLScalar): List<String> {
        val keys = mutableListOf<String>()
        var value: com.intellij.psi.PsiElement = scalar
        while (true) {
            val key = value.parent as? YAMLKeyValue ?: return emptyList()
            if (key.value != value) return emptyList()
            keys.add(key.keyText)
            val mapping = key.parent as? YAMLMapping ?: return emptyList()
            if (mapping.parent is YAMLDocument) return keys.reversed()
            value = mapping
        }
    }
}

/** Decoded scalar text, with offsets mapped back through YAML's literal escaper. */
internal class ScalarText(val scalar: YAMLScalar) {
    private val escaper = scalar.createLiteralTextEscaper()
    private val contentRange = escaper.relevantTextRange
    val value: String? =
        StringBuilder().let {
            if (escaper.decode(contentRange, it)) it.toString() else null
        }

    fun range(start: Int, end: Int): TextRange? {
        val hostStart = escaper.getOffsetInHost(start, contentRange)
        val hostEnd = escaper.getOffsetInHost(end, contentRange)
        if (hostStart < 0 || hostEnd < hostStart) return null
        return TextRange(hostStart, hostEnd)
    }

    fun decodedOffset(hostOffset: Int): Int? {
        val text = value ?: return null
        return (0..text.length).firstOrNull {
            escaper.getOffsetInHost(it, contentRange) == hostOffset
        }
    }
}

internal data class SelectorPart(
    val className: String,
    val classStart: Int,
    val classEnd: Int,
    val methodName: String?,
    val methodStart: Int?,
    val methodEnd: Int?,
)

internal object Selectors {
    private val identifier = "[A-Za-z_$][A-Za-z0-9_$]*"
    private val selector = Regex("($identifier(?:\\.$identifier)+)(?:#($identifier))?")

    fun parse(value: String, runner: Boolean): List<SelectorPart> {
        val parts = mutableListOf<SelectorPart>()
        var start = 0
        for (segment in value.split(',')) {
            val trimmed = segment.trim()
            val match = selector.matchEntire(trimmed)
            if (match != null && (!runner || (value.indexOf(',') < 0 && match.groups[2] == null))) {
                val offset = start + segment.indexOf(trimmed)
                val clazz = match.groups[1]!!
                val method = match.groups[2]
                parts.add(
                    SelectorPart(
                        clazz.value,
                        offset + clazz.range.first,
                        offset + clazz.range.last + 1,
                        method?.value,
                        method?.let { offset + it.range.first },
                        method?.let { offset + it.range.last + 1 },
                    )
                )
            }
            start += segment.length + 1
        }
        return parts
    }
}

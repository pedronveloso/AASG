package io.github.pedronveloso.aasg

import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.openapi.project.DumbService
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiElementVisitor
import org.jetbrains.yaml.psi.YAMLScalar

class AasgUnresolvedReferenceInspection : LocalInspectionTool() {
    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PsiElementVisitor() {
            override fun visitElement(element: PsiElement) {
                if (element !is YAMLScalar || DumbService.isDumb(element.project)) return
                for (reference in AasgReferenceContributor.references(element)) {
                    val android = reference as AndroidReference
                    if (android.multiResolve(false).isNotEmpty()) continue
                    // Avoid a second warning on a method whose owning class cannot be found.
                    if (
                        android.methodName != null &&
                            AndroidSymbols.classes(element.project, android.className).isEmpty()
                    )
                        continue
                    val message =
                        if (android.methodName == null)
                            "Cannot resolve Android class '${android.className}'"
                        else
                            "Cannot resolve method '${android.methodName}' in '${android.className}'"
                    holder.registerProblem(
                        element,
                        message,
                        ProblemHighlightType.GENERIC_ERROR_OR_WARNING,
                        android.rangeInElement,
                    )
                }
            }
        }
}

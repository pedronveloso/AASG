package io.github.pedronveloso.aasg

import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.LightJavaCodeInsightFixtureTestCase
import java.nio.file.Files
import java.nio.file.Path
import org.jetbrains.kotlin.psi.KtClass
import org.jetbrains.yaml.psi.YAMLScalar

/** Optional real-source smoke tests; the projects are read and never modified. */
class AasgPilotSmokeTest : LightJavaCodeInsightFixtureTestCase() {
    fun testAltSeaCapture() {
        smoke("altSeaPath", "app.altsea.feature.screenshots", "PlayStoreScreenshotCaptureTest")
    }

    fun testLazuliteCapture() {
        smoke("lazulitePath", "com.pedronveloso.lazulite.e2e", "HomeScreenshotCaptureTest")
    }

    private fun smoke(property: String, packageName: String, className: String) {
        val root =
            Path.of(
                requireNotNull(System.getProperty(property)) { "Missing pilot path: $property" }
            )
        val source =
            root.resolve("app/src/androidTest/java/${packageName.replace('.', '/')}/$className.kt")
        myFixture.addFileToProject(
            "androidTest/${packageName.replace('.', '/')}/$className.kt",
            Files.readString(source),
        )
        val file =
            myFixture.configureByText("aasg.yaml", Files.readString(root.resolve("aasg.yaml")))
        val qualifiedName = "$packageName.$className"
        val references =
            PsiTreeUtil.findChildrenOfType(file, YAMLScalar::class.java)
                .flatMap { it.references.filterIsInstance<AndroidReference>() }
                .filter { it.className == qualifiedName }
        assertTrue("Pilot YAML must reference $qualifiedName", references.isNotEmpty())
        for (reference in references) {
            val target = reference.resolve()
            assertInstanceOf(target, KtClass::class.java)
            assertEquals(className, (target as KtClass).name)
            assertEquals("$className.kt", target.containingFile.name)
        }
    }
}

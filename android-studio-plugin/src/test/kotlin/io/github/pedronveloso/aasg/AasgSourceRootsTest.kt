package io.github.pedronveloso.aasg

import com.intellij.openapi.module.JavaModuleType
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.util.io.FileUtil
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiCompiledElement
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.PsiTestUtil
import com.intellij.testFramework.fixtures.JavaCodeInsightFixtureTestCase
import java.nio.file.Files
import java.util.jar.JarEntry
import java.util.jar.JarOutputStream
import org.jetbrains.yaml.psi.YAMLScalar

class AasgSourceRootsTest : JavaCodeInsightFixtureTestCase() {
    fun testInstrumentationRootResolves() {
        val file =
            myFixture.addFileToProject(
                "androidTest/example/Capture.java",
                "package example; public class Capture {}",
            )
        PsiTestUtil.addSourceRoot(module, file.virtualFile.parent.parent, true)
        val reference = configure("captures:\n  home:\n    test: example.Capture\n")
        assertEquals(file, reference.resolve()!!.containingFile)
    }

    fun testDuplicateClassesAcrossModulesReturnEveryTarget() {
        for (name in listOf("one", "two")) {
            val root = myFixture.tempDirFixture.findOrCreateDir(name)
            val otherModule =
                PsiTestUtil.addModule(project, JavaModuleType.getModuleType(), name, root)
            PsiTestUtil.addSourceRoot(otherModule, root, true)
            myFixture.addFileToProject(
                "$name/example/Capture.java",
                "package example; public class Capture {}",
            )
        }
        val reference = configure("captures:\n  home:\n    test: example.Capture\n")
        assertEquals(2, reference.multiResolve(false).size)
    }

    fun testRunnerDependencyAndProjectSourcePreference() {
        val root = Files.createTempDirectory("aasg-runner-library")
        Disposer.register(testRootDisposable) { FileUtil.delete(root.toFile()) }
        val source = root.resolve("Runner.java")
        Files.writeString(source, "package example; public class Runner {}")
        val classes = Files.createDirectory(root.resolve("classes"))
        val compiler =
            ProcessBuilder(
                    System.getProperty("aasg.javac"),
                    "--release",
                    "21",
                    "-d",
                    classes.toString(),
                    source.toString(),
                )
                .redirectErrorStream(true)
                .start()
        val output = compiler.inputStream.bufferedReader().use { it.readText() }
        assertEquals(output, 0, compiler.waitFor())
        val jar = root.resolve("runner.jar")
        JarOutputStream(Files.newOutputStream(jar)).use { output ->
            output.putNextEntry(JarEntry("example/Runner.class"))
            output.write(Files.readAllBytes(classes.resolve("example/Runner.class")))
            output.closeEntry()
        }
        PsiTestUtil.addLibrary(testRootDisposable, module, "runner", root.toString(), "runner.jar")
        val yaml = "android:\n  direct_instrumentation:\n    runner: example.Runner\n"
        val dependency = configure(yaml).resolve()
        assertInstanceOf(dependency, PsiCompiledElement::class.java)
        val sourceClass = myFixture.addClass("package example; public class Runner {}")
        assertEquals(sourceClass, configure(yaml).resolve())
        assertEquals("example.Runner", (dependency as PsiClass).qualifiedName)
    }

    private fun configure(yaml: String): AndroidReference {
        // The heavy fixture gives repeated configureByText files unique names.
        val file =
            if (myFixture.tempDirFixture.getFile("aasg.yaml") == null)
                myFixture.configureByText("aasg.yaml", yaml)
            else myFixture.configureFromTempProjectFile("aasg.yaml")
        IndexingTestUtil.waitUntilIndexesAreReady(project)
        val scalars = PsiTreeUtil.findChildrenOfType(file, YAMLScalar::class.java)
        val refs = scalars.flatMap { it.references.filterIsInstance<AndroidReference>() }
        assertEquals(
            "References in ${file.name}: ${scalars.map { it.text to it.references.map { ref -> ref.javaClass.name } }}",
            1,
            refs.size,
        )
        return refs.single()
    }
}
